"""
Module 9 — Durable PostgreSQL Job Queue Service.

Implements transaction-safe job queueing, worker claiming using:
  SELECT ... FOR UPDATE SKIP LOCKED
lease timeouts, exponential retry backoff with jitter, and stale-job recovery.
"""

from datetime import datetime, timedelta, timezone
import random
import re
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException, status

from app.models import ProcessingJob, Document, OcrStatus
from app.config import settings
from app.logging_redactor import redact_sensitive_data


class ActiveJobConflictError(HTTPException):
    def __init__(self, detail: str = "An active processing job is already running for this document."):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


def sanitize_error_message(err: str) -> str:
    """Strip sensitive information like passwords, tokens, API keys, and server filesystem paths."""
    if not err:
        return "Unknown error"
    s = str(err)
    # Redact JWTs, query tokens, passwords, and bearer tokens
    s = redact_sensitive_data(s)
    # Mask API keys and bearer tokens
    s = re.sub(r'(?:AIza[0-9A-Za-z-_]{20,60}|Bearer\s+[A-Za-z0-9-_.]+)', '[REDACTED_SECRET]', s)
    # Strip database connection strings
    s = re.sub(r'postgresql://[^@]+@[^\s/]+', '[REDACTED_DB_URL]', s)
    # Mask server filesystem paths
    s = re.sub(r'/(?:home|var|tmp|etc|usr|app)/[A-Za-z0-9-_/.]+', '[INTERNAL_PATH]', s)
    # Strip verbose Python traceback frames if present, leaving the clean exception summary
    if "Traceback (most recent call last):" in s:
        lines = [line.strip() for line in s.splitlines() if line.strip()]
        err_msg = lines[-1] if lines else "Processing failure"
        return err_msg[:500]
    return s.strip()[:2000]


class JobQueueService:
    """High-concurrency durable PostgreSQL job queue."""

    @staticmethod
    def enqueue_job(
        db: Session,
        document_id: int,
        company_id: int,
        branch_id: int,
        job_type: str = "ocr_extraction",
        run_after: Optional[datetime] = None,
        max_attempts: Optional[int] = None,
        commit: bool = True,
    ) -> ProcessingJob:
        """
        Enqueue a new processing job for a document.
        Guarantees at most one active (pending/running) job per document.
        """
        # 1. Application-level check
        active_job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == job_type,
                ProcessingJob.status.in_(["pending", "running"]),
            )
            .first()
        )
        if active_job:
            raise ActiveJobConflictError(
                f"An active processing job #{active_job.id} ({active_job.status}) already exists for document {document_id}."
            )

        job = ProcessingJob(
            document_id=document_id,
            company_id=company_id,
            branch_id=branch_id,
            job_type=job_type,
            status="pending",
            attempts=0,
            max_attempts=max_attempts or settings.QUEUE_MAX_ATTEMPTS,
            run_after=run_after or datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        try:
            if commit:
                db.commit()
                db.refresh(job)
            else:
                db.flush()
            return job
        except Exception as e:
            db.rollback()
            # If unique index uq_processing_jobs_active_doc caught a race condition:
            if "uq_processing_jobs_active_doc" in str(e).lower() or "unique constraint" in str(e).lower():
                raise ActiveJobConflictError()
            raise e

    @staticmethod
    def claim_next_job(
        db: Session,
        worker_id: str,
        lock_timeout_seconds: Optional[int] = None,
    ) -> Optional[ProcessingJob]:
        """
        Claim the next available pending job using PostgreSQL SKIP LOCKED.
        Also reclaims any stale jobs that exceeded the lease timeout.
        """
        timeout = lock_timeout_seconds or settings.QUEUE_LOCK_TIMEOUT_SECONDS
        stale_threshold = datetime.utcnow() - timedelta(seconds=timeout)

        # 1. Recover stale running jobs whose lock expired
        stale_jobs = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == "running",
                ProcessingJob.locked_at < stale_threshold,
            )
            .with_for_update(skip_locked=True)
            .all()
        )
        for sj in stale_jobs:
            if sj.attempts >= sj.max_attempts:
                sj.status = "failed"
                sj.completed_at = datetime.utcnow()
                sj.last_error = "Job exceeded maximum execution attempts after worker lease expired."
                sj.error_code = "LEASE_TIMEOUT_EXHAUSTED"
            else:
                # Re-queue for retry
                sj.status = "pending"
                sj.run_after = datetime.utcnow()
                sj.last_error = f"Recovered from stale worker lease (was locked by {sj.locked_by})."
            sj.locked_by = None
            sj.locked_at = None
            sj.updated_at = datetime.utcnow()

        if stale_jobs:
            db.commit()

        # 2. Select next pending job ready for execution
        job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.status == "pending",
                ProcessingJob.run_after <= datetime.utcnow(),
            )
            .order_by(ProcessingJob.run_after.asc(), ProcessingJob.id.asc())
            .with_for_update(skip_locked=True)
            .first()
        )

        if not job:
            return None

        # 3. Claim job
        job.status = "running"
        job.locked_by = worker_id
        job.locked_at = datetime.utcnow()
        job.attempts += 1
        job.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def complete_job(db: Session, job_id: int, worker_id: str) -> bool:
        """
        Mark job completed. Enforces worker lease check to ensure stale workers
        cannot overwrite newer execution states.
        """
        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            return False

        # Lease verification
        if job.locked_by != worker_id or job.status != "running":
            # Stale worker attempted to complete a reclaimed job
            db.rollback()
            return False

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.locked_by = None
        job.locked_at = None
        job.updated_at = datetime.utcnow()
        db.commit()
        return True

    @staticmethod
    def fail_job(
        db: Session,
        job_id: int,
        worker_id: str,
        error_message: str,
        error_code: Optional[str] = None,
        is_retryable: bool = True,
    ) -> bool:
        """
        Mark job failed with optional exponential backoff retry.
        Sanitizes error output to avoid security leaks.
        """
        job = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.id == job_id)
            .with_for_update()
            .first()
        )
        if not job:
            return False

        if job.locked_by != worker_id or job.status != "running":
            db.rollback()
            return False

        safe_err = sanitize_error_message(error_message)
        job.last_error = safe_err
        job.error_code = error_code or "PROCESSING_FAILED"
        job.updated_at = datetime.utcnow()

        # Retry with exponential backoff and jitter if retryable
        if is_retryable and job.attempts < job.max_attempts:
            # Backoff: 5s, 10s, 20s... with random jitter
            delay = min(300, (2 ** job.attempts) * 5 + random.uniform(1.0, 5.0))
            job.status = "pending"
            job.run_after = datetime.utcnow() + timedelta(seconds=delay)
            job.locked_by = None
            job.locked_at = None
        else:
            job.status = "failed"
            job.completed_at = datetime.utcnow()
            job.locked_by = None
            job.locked_at = None

        db.commit()
        return True

    @staticmethod
    def get_active_job(db: Session, document_id: int, job_type: str = "ocr_extraction") -> Optional[ProcessingJob]:
        """Check if an active job is currently pending or running for a document."""
        timeout = settings.QUEUE_LOCK_TIMEOUT_SECONDS
        stale_threshold = datetime.utcnow() - timedelta(seconds=timeout)

        # Recover stale lock if present
        stale = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.document_id == document_id,
                ProcessingJob.status == "running",
                ProcessingJob.locked_at < stale_threshold,
            )
            .first()
        )
        if stale:
            stale.status = "failed"
            stale.last_error = "Worker lease expired."
            stale.locked_by = None
            stale.locked_at = None
            db.commit()

        return (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.document_id == document_id,
                ProcessingJob.job_type == job_type,
                ProcessingJob.status.in_(["pending", "running"]),
            )
            .first()
        )
