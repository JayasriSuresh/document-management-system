"""
Module 14 – Secure CSV Export Service with Formula-Injection Defense.

Implements streaming CSV generation for:
  - documents
  - ai-usage
  - failed-jobs
  - invoices

Security:
  - Formula Injection Immunity (OWASP CSV Injection):
    Any string beginning with '=', '+', '-', '@', '\\t', or '\\r' is prepended with a single quote (').
  - Standard RFC 4180 CSV escaping via Python's built-in csv module.
  - Streaming generation via Python generators for O(1) memory overhead.
  - Multi-tenant and branch scoping enforced from AuthContext.
"""

import csv
import io
from datetime import datetime
from typing import Any, Generator, List, Optional

from sqlalchemy import Date, cast, desc
from sqlalchemy.orm import Session

from app.auth.authorization import can, scope_filter
from app.auth.permissions import DOCUMENT_REPROCESS, DOCUMENT_VIEW_COMPANY
from app.context import AuthContext
from app.models import (
    AIProcessingLog,
    Branch,
    Document,
    Invoice,
    ProcessingJob,
)
from app.services.job_queue import sanitize_error_message


def sanitize_csv_cell(val: Any) -> str:
    """
    Sanitizes a single CSV cell value against CSV / Spreadsheet Formula Injection.
    Prepends a single quote (') if the string begins with '=', '+', '-', '@', '\\t', or '\\r'.
    """
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d %H:%M:%S")

    s = str(val)
    if not s:
        return ""

    # Neutralize spreadsheet formula injection execution triggers
    if s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{s}"

    return s


def _format_csv_row(writer: csv.writer, string_buffer: io.StringIO, row: List[Any]) -> str:
    """Helper to format a row through csv.writer and extract string content."""
    string_buffer.seek(0)
    string_buffer.truncate(0)
    sanitized_row = [sanitize_csv_cell(c) for c in row]
    writer.writerow(sanitized_row)
    return string_buffer.getvalue()


# ── 1. Documents CSV Generator ────────────────────────────────────────────────

def generate_documents_csv(
    db: Session,
    auth_ctx: AuthContext,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    branch_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """Stream documents report as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    # 1. UTF-8 Byte Order Mark for Excel compatibility
    yield "\ufeff"

    # 2. Header
    headers = [
        "Document ID",
        "Original Filename",
        "Branch ID",
        "Branch Name",
        "Status",
        "File Size (Bytes)",
        "File Size (MB)",
        "MIME Type",
        "Uploaded By User ID",
        "Invoice Number",
        "Grand Total",
        "Currency",
        "Created At (UTC)",
    ]
    yield _format_csv_row(writer, buf, headers)

    # 3. Data Query
    query = scope_filter(auth_ctx, db.query(Document, Branch), Document, include_deleted=False)
    query = query.outerjoin(Branch, Document.branch_id == Branch.id)
    if branch_id is not None:
        query = query.filter(Document.branch_id == branch_id)
    if start_dt:
        query = query.filter(Document.created_at >= start_dt)
    if end_dt:
        query = query.filter(Document.created_at <= end_dt)

    query = query.order_by(Document.created_at.desc())

    # Stream rows
    for doc, br in query.yield_per(500):
        mb = round(float(doc.file_size or 0) / (1024 * 1024), 2)
        status_val = doc.ocr_status.value if hasattr(doc.ocr_status, "value") else str(doc.ocr_status)
        row = [
            doc.id,
            doc.original_filename,
            doc.branch_id,
            br.name if br else f"Branch #{doc.branch_id}",
            status_val,
            doc.file_size,
            mb,
            doc.mime_type,
            doc.uploaded_by,
            doc.invoice_number or "",
            float(doc.grand_total) if doc.grand_total is not None else "",
            doc.currency or "INR",
            doc.created_at,
        ]
        yield _format_csv_row(writer, buf, row)


# ── 2. AI Usage CSV Generator ────────────────────────────────────────────────

def generate_ai_usage_csv(
    db: Session,
    auth_ctx: AuthContext,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    branch_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """Stream AI usage log report as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    yield "\ufeff"

    headers = [
        "Log ID",
        "Document ID",
        "Branch ID",
        "Branch Name",
        "Operation",
        "Provider",
        "Model",
        "Is Fallback",
        "Attempt Number",
        "Tokens In",
        "Tokens Out",
        "Total Tokens",
        "Cost (USD Cents)",
        "Estimated Cost (USD)",
        "Cost (INR)",
        "Exchange Rate (USD to INR)",
        "Reporting Currency",
        "Latency (ms)",
        "Success",
        "Error Code",
        "Created At (UTC)",
    ]
    yield _format_csv_row(writer, buf, headers)

    query = db.query(AIProcessingLog, Branch).outerjoin(
        Branch, AIProcessingLog.branch_id == Branch.id
    ).filter(AIProcessingLog.company_id == auth_ctx.company_id)

    # Branch scoping for non-company-wide users
    if not auth_ctx.is_global_admin and DOCUMENT_VIEW_COMPANY not in auth_ctx.permissions:
        if branch_id is not None:
            query = query.filter(AIProcessingLog.branch_id == branch_id)
        else:
            query = query.filter(AIProcessingLog.branch_id.in_(auth_ctx.assigned_branch_ids))
    else:
        if branch_id is not None:
            query = query.filter(AIProcessingLog.branch_id == branch_id)

    if start_dt:
        query = query.filter(AIProcessingLog.created_at >= start_dt)
    if end_dt:
        query = query.filter(AIProcessingLog.created_at <= end_dt)

    query = query.order_by(AIProcessingLog.created_at.desc())

    for log, br in query.yield_per(500):
        t_in = log.tokens_in or 0
        t_out = log.tokens_out or 0
        cents = log.cost_cents or 0
        usd = round(cents / 100.0, 4)
        inr = round(float(log.cost_inr if log.cost_inr is not None else (usd * (log.exchange_rate or 85.0))), 4)
        rate = log.exchange_rate or 85.0
        currency = log.currency or "INR"
        row = [
            log.id,
            log.document_id or "",
            log.branch_id or "",
            br.name if br else (f"Branch #{log.branch_id}" if log.branch_id else "Company Scope"),
            log.operation,
            log.provider,
            log.model,
            "Yes" if log.is_fallback else "No",
            log.attempt_number,
            t_in,
            t_out,
            t_in + t_out,
            cents,
            usd,
            inr,
            rate,
            currency,
            log.latency_ms or 0,
            "Success" if log.success else "Failed",
            log.error_code or "",
            log.created_at,
        ]
        yield _format_csv_row(writer, buf, row)


# ── 3. Failed Background Jobs CSV Generator ───────────────────────────────────

def generate_failed_jobs_csv(
    db: Session,
    auth_ctx: AuthContext,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    branch_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """Stream background processing jobs as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    yield "\ufeff"

    headers = [
        "Job ID",
        "Document ID",
        "Document Filename",
        "Branch ID",
        "Branch Name",
        "Job Type",
        "Status",
        "Attempts",
        "Max Attempts",
        "Error Code",
        "Sanitized Error Summary",
        "Created At (UTC)",
        "Updated At (UTC)",
        "Completed At (UTC)",
    ]
    yield _format_csv_row(writer, buf, headers)

    query = (
        db.query(ProcessingJob, Document, Branch)
        .outerjoin(Document, ProcessingJob.document_id == Document.id)
        .outerjoin(Branch, ProcessingJob.branch_id == Branch.id)
        .filter(ProcessingJob.company_id == auth_ctx.company_id)
    )

    if not auth_ctx.is_global_admin and DOCUMENT_VIEW_COMPANY not in auth_ctx.permissions:
        if branch_id is not None:
            query = query.filter(ProcessingJob.branch_id == branch_id)
        else:
            query = query.filter(ProcessingJob.branch_id.in_(auth_ctx.assigned_branch_ids))
    else:
        if branch_id is not None:
            query = query.filter(ProcessingJob.branch_id == branch_id)

    if start_dt:
        query = query.filter(ProcessingJob.created_at >= start_dt)
    if end_dt:
        query = query.filter(ProcessingJob.created_at <= end_dt)

    query = query.order_by(ProcessingJob.created_at.desc())

    for job, doc, br in query.yield_per(500):
        clean_error = sanitize_error_message(job.last_error) if job.last_error else ""
        row = [
            job.id,
            job.document_id,
            doc.original_filename if doc else f"Document #{job.document_id}",
            job.branch_id,
            br.name if br else f"Branch #{job.branch_id}",
            job.job_type,
            job.status,
            job.attempts,
            job.max_attempts,
            job.error_code or "",
            clean_error,
            job.created_at,
            job.updated_at,
            job.completed_at or "",
        ]
        yield _format_csv_row(writer, buf, row)


# ── 4. Invoices CSV Generator ─────────────────────────────────────────────────

def generate_invoices_csv(
    db: Session,
    auth_ctx: AuthContext,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    branch_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """Stream invoices report as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    yield "\ufeff"

    headers = [
        "Invoice ID",
        "Document ID",
        "Branch ID",
        "Branch Name",
        "Kind",
        "Status",
        "Invoice Number",
        "Invoice Date",
        "Due Date",
        "Taxable Amount",
        "CGST Amount",
        "SGST Amount",
        "IGST Amount",
        "Round Off",
        "Grand Total",
        "Currency",
        "Seller Name",
        "Seller GSTIN",
        "Buyer Name",
        "Buyer GSTIN",
        "Created At (UTC)",
    ]
    yield _format_csv_row(writer, buf, headers)

    query = scope_filter(auth_ctx, db.query(Invoice, Branch), Invoice, include_deleted=False)
    query = query.outerjoin(Branch, Invoice.branch_id == Branch.id)

    if branch_id is not None:
        query = query.filter(Invoice.branch_id == branch_id)
    if start_dt:
        query = query.filter(Invoice.created_at >= start_dt)
    if end_dt:
        query = query.filter(Invoice.created_at <= end_dt)

    query = query.order_by(Invoice.created_at.desc())

    for inv, br in query.yield_per(500):
        row = [
            inv.id,
            inv.document_id or "",
            inv.branch_id,
            br.name if br else f"Branch #{inv.branch_id}",
            inv.kind,
            inv.status,
            inv.invoice_number or "",
            inv.invoice_date.isoformat() if inv.invoice_date else "",
            inv.due_date.isoformat() if inv.due_date else "",
            float(inv.taxable_amount) if inv.taxable_amount is not None else 0.0,
            float(inv.cgst_amount or 0.0),
            float(inv.sgst_amount or 0.0),
            float(inv.igst_amount or 0.0),
            float(inv.round_off or 0.0),
            float(inv.grand_total) if inv.grand_total is not None else 0.0,
            inv.currency or "INR",
            inv.seller_name or "",
            inv.seller_gstin or "",
            inv.buyer_name or "",
            inv.buyer_gstin or "",
            inv.created_at,
        ]
        yield _format_csv_row(writer, buf, row)
