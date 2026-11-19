"""
Module 9 — Durable Document Processing Worker.

Independent worker process that polls the PostgreSQL processing_jobs queue,
claims jobs using SKIP LOCKED, processes documents through the OCR and extraction pipeline,
handles transient retries with exponential backoff, and supports graceful shutdown.

Usage:
  python -m app.worker
  uvicorn / systemd service / standalone daemon
"""

import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.config import settings
from app.models import (
    ProcessingJob, Document, OcrStatus, Company, PlatformSetting, AIUsageLedger
)
from app.logging_redactor import apply_redaction_filters
from app.middleware import configure_logging
from app.services.job_queue import JobQueueService, sanitize_error_message
from app.storage import get_storage_adapter
from app.ai.service import AIExecutionService
from app.ai.base import AIProviderError

# Configure worker logging with request-id and sensitive data redaction
configure_logging(level="INFO")
apply_redaction_filters()
logger = logging.getLogger("dms.worker")


class DocumentWorker:
    """Production document processing worker with graceful shutdown."""

    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.running = True
        self._register_signals()

    def _register_signals(self):
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError):
            # In non-main threads or restricted environments
            pass

    def _handle_signal(self, signum, frame):
        logger.info(f"Received termination signal ({signum}). Initiating graceful worker shutdown...")
        self.running = False

    def stop(self):
        """Request worker shutdown after finishing current task."""
        self.running = False

    def process_one_job(self, db: Session, job: ProcessingJob) -> bool:
        """
        Execute document processing for a claimed job.
        Returns True on success, False on failure.
        """
        doc_id = job.document_id
        start_time = time.time()
        logger.info(f"[{self.worker_id}] Starting Job #{job.id} (Doc #{doc_id}, Attempt {job.attempts}/{job.max_attempts})")

        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.warning(f"Job #{job.id} targeted missing document #{doc_id}. Marking job completed.")
            JobQueueService.complete_job(db, job.id, self.worker_id)
            return True

        # Check if document was soft-deleted while waiting in queue
        if doc.deleted_at is not None:
            logger.info(f"Document #{doc_id} was deleted before processing. Cancelling Job #{job.id}.")
            JobQueueService.complete_job(db, job.id, self.worker_id)
            return True

        # Check company active status
        company = db.query(Company).filter(Company.id == doc.company_id).first()
        if company and (company.status or "").lower() == "suspended":
            logger.warning(f"Company #{doc.company_id} is suspended. Failing Job #{job.id}.")
            doc.ocr_status = OcrStatus.FAILED
            doc.error_code = "COMPANY_SUSPENDED"
            db.commit()
            JobQueueService.fail_job(
                db, job.id, self.worker_id,
                error_message="Cannot process documents for a suspended company.",
                error_code="COMPANY_SUSPENDED",
                is_retryable=False,
            )
            return False

        # Update document status to processing
        doc.ocr_status = OcrStatus.PROCESSING
        db.commit()

        storage = get_storage_adapter()
        if not storage.exists(doc.storage_key):
            err_msg = f"Original file '{doc.storage_key}' not found in storage."
            logger.error(f"Job #{job.id} error: {err_msg}")
            doc.ocr_status = OcrStatus.FAILED
            doc.error_code = "FILE_NOT_FOUND"
            db.commit()
            JobQueueService.fail_job(
                db, job.id, self.worker_id,
                error_message=err_msg,
                error_code="FILE_NOT_FOUND",
                is_retryable=False,
            )
            return False

        # Execute OCR & extraction pipeline
        try:
            self._execute_pipeline(db, doc, company, job=job)
            JobQueueService.complete_job(db, job.id, self.worker_id)
            duration = time.time() - start_time
            logger.info(f"[{self.worker_id}] Job #{job.id} completed successfully in {duration:.2f}s")
            return True
        except Exception as exc:
            err_str = str(exc)
            duration = time.time() - start_time
            logger.error(f"[{self.worker_id}] Job #{job.id} failed after {duration:.2f}s: {err_str}")

            is_retryable = self._is_retryable_error(exc)
            if not is_retryable or job.attempts >= job.max_attempts:
                doc.ocr_status = OcrStatus.FAILED
                doc.error_code = "PROCESSING_FAILED"
                doc.ocr_text = f"Processing failed: {sanitize_error_message(err_str)}"
                db.commit()

            JobQueueService.fail_job(
                db, job.id, self.worker_id,
                error_message=err_str,
                error_code="OCR_EXTRACTION_ERROR",
                is_retryable=is_retryable,
            )
            return False

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Classify whether an exception is transient (network/rate-limit) or permanent."""
        if isinstance(exc, AIProviderError):
            return exc.is_retryable
        s = str(exc).lower()
        if "429" in s or "resource_exhausted" in s or "rate limit" in s:
            return True
        if "503" in s or "service unavailable" in s or "timeout" in s or "connection" in s:
            return True
        # Permanent validation or configuration errors
        if "budget" in s or "consent" in s or "disabled" in s or "disallowed" in s or "credential" in s:
            return False
        return True

    def _execute_pipeline(self, db: Session, doc: Document, company: Optional[Company], job: Optional[ProcessingJob] = None):
        """Run multi-provider AI document extraction pipeline."""
        storage = get_storage_adapter()
        file_bytes = storage.read(doc.storage_key)

        target_bytes = file_bytes
        target_mime = doc.mime_type or "image/jpeg"

        # Convert PDF first page to JPEG for OCR if PDF
        if doc.mime_type == "application/pdf":
            import tempfile, pdf2image
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
                tmp_pdf.write(file_bytes)
                tmp_pdf_path = tmp_pdf.name
            try:
                images = pdf2image.convert_from_path(tmp_pdf_path, dpi=200, first_page=1, last_page=1)
                if images:
                    import io
                    buf = io.BytesIO()
                    images[0].save(buf, format="JPEG")
                    target_bytes = buf.getvalue()
                    target_mime = "image/jpeg"
            finally:
                if os.path.exists(tmp_pdf_path):
                    try:
                        os.unlink(tmp_pdf_path)
                    except OSError:
                        pass

        # Resolve or retrieve pinned template version
        from app.services.template_service import TemplateResolver
        from app.services.validation_engine import validate_extraction
        from app.models import TemplateVersion, DocumentExtraction

        tmpl_version = None
        if doc.template_version_id:
            tmpl_version = db.query(TemplateVersion).filter(TemplateVersion.id == doc.template_version_id).first()

        if not tmpl_version:
            try:
                tmpl_version = TemplateResolver.resolve_template(
                    db,
                    company_id=doc.company_id,
                    branch_id=doc.branch_id,
                    document_type="gst_invoice",
                )
                doc.template_version_id = tmpl_version.id
                db.flush()
            except Exception as te:
                logger.warning(f"Could not resolve template for document {doc.id}: {te}")

        schema_json = tmpl_version.schema_json if tmpl_version else None
        instructions = tmpl_version.extraction_instructions if tmpl_version else None

        # Execute extraction through Module 10 multi-provider architecture
        # (Handles platform checks, branch config, credentials, consent, row-level budget, fallback, and logs)
        try:
            result = AIExecutionService.extract_document(
                db=db,
                company_id=doc.company_id,
                branch_id=doc.branch_id,
                images=[target_bytes],
                mime_type=target_mime,
                schema=schema_json,
                prompt=instructions,
                document_id=doc.id,
                job_id=job.id if job else None,
            )

            import json
            doc.ocr_text = result.raw_text or "[No text detected]"
            doc.structured_data = json.dumps(result.structured_data) if result.structured_data else "{}"
            doc.ocr_status = OcrStatus.COMPLETED
            doc.error_code = None

            # Module 11: Deterministic validation & DocumentExtraction persistence
            if tmpl_version:
                validation_res = validate_extraction(result.structured_data, tmpl_version)
                extraction_status = "needs_review" if validation_res.has_errors else "extracted"

                extraction = db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()
                flags_dict_list = [f.to_dict() for f in validation_res.flags]
                if extraction:
                    extraction.template_version_id = tmpl_version.id
                    extraction.data = result.structured_data or {}
                    extraction.raw_text = result.raw_text or ""
                    extraction.validation_flags = flags_dict_list
                    extraction.status = extraction_status
                    extraction.updated_at = datetime.utcnow()
                else:
                    extraction = DocumentExtraction(
                        document_id=doc.id,
                        template_version_id=tmpl_version.id,
                        data=result.structured_data or {},
                        raw_text=result.raw_text or "",
                        validation_flags=flags_dict_list,
                        status=extraction_status,
                    )
                    db.add(extraction)

            # Module 12: Synchronize structured search columns & update search_vector
            from app.services.search_service import sync_document_search_metadata
            sync_document_search_metadata(doc, result.structured_data)

            db.commit()
        except AIProviderError as aie:
            doc.ocr_status = OcrStatus.FAILED
            doc.ocr_text = f"[{aie.message}]"
            doc.error_code = aie.error_code
            db.commit()
            raise aie

    def run_loop(self, poll_interval: Optional[float] = None):
        """Continuous polling worker loop."""
        interval = poll_interval or settings.QUEUE_POLL_INTERVAL_SECONDS
        logger.info(f"DMS Worker '{self.worker_id}' started. Polling every {interval}s...")

        last_cleanup = 0.0
        while self.running:
            db = SessionLocal()
            try:
                # Periodic cleanup of expired temporary signature uploads
                now = time.time()
                if now - last_cleanup > 3600:
                    try:
                        from app.services.invoice_issuance import cleanup_expired_signature_uploads
                        cleaned = cleanup_expired_signature_uploads(db)
                        if cleaned > 0:
                            logger.info(f"Cleaned up {cleaned} expired temporary signature uploads")
                        last_cleanup = now
                    except Exception as err:
                        logger.warning(f"Error during signature cleanup: {err}")

                job = JobQueueService.claim_next_job(db, self.worker_id)
                if job:
                    self.process_one_job(db, job)
                else:
                    # Idle sleep with interrupt check
                    time.sleep(interval)
            except Exception as e:
                logger.error(f"Unexpected error in worker loop: {e}", exc_info=True)
                time.sleep(interval)
            finally:
                db.close()

        logger.info(f"DMS Worker '{self.worker_id}' stopped gracefully.")


def main():
    worker = DocumentWorker()
    worker.run_loop()


if __name__ == "__main__":
    main()
