"""
Module 14 – Operational Dashboards, Usage Reporting, and Job Monitoring Router.

Provides high-performance, tenant-isolated operational aggregates:
  1. GET /api/dashboard/company             — Company-level operational KPIs and summaries
  2. GET /api/dashboard/branch/{branch_id}  — Branch-level operational KPIs and summaries
  3. GET /api/dashboard/ai-usage            — AI usage, provider/model breakdown & daily trends
  4. GET /api/dashboard/jobs                — Background processing job monitoring with sanitized errors
  5. GET /api/dashboard/export/csv          — Formula-injection safe streaming CSV exports
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import (
    BigInteger,
    Date,
    Numeric,
    and_,
    asc,
    case,
    cast,
    desc,
    func,
    or_,
)
from sqlalchemy.orm import Session

from app.auth.authorization import can, scope_filter
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import (
    AI_USAGE_VIEW,
    BRANCH_VIEW,
    COMPANY_VIEW,
    DOCUMENT_REPROCESS,
    DOCUMENT_VIEW_BRANCH,
    DOCUMENT_VIEW_COMPANY,
    INVOICE_VIEW,
)
from app.context import AuthContext
from app.database import get_db
from app.models import (
    AIProcessingLog,
    Branch,
    Company,
    Document,
    Invoice,
    OcrStatus,
    ProcessingJob,
    User,
)
from app.services.csv_export import (
    generate_ai_usage_csv,
    generate_documents_csv,
    generate_failed_jobs_csv,
    generate_invoices_csv,
)
from app.services.currency_service import get_usd_to_inr_rate, convert_usd_cents_to_inr
from app.services.job_queue import sanitize_error_message
from app.services.search_service import parse_indian_date

logger = logging.getLogger("dms.routers.dashboard")

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ── Helper: Safe Date Boundary Parsing & Timezone Handling ───────────────────

def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    Serializes a datetime to ISO-8601 with an explicit UTC indicator ('Z').
    Ensures browser JavaScript parses it as UTC and converts to local browser time.
    """
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_date_boundary(
    date_val: Optional[Union[str, date, datetime]],
    is_end: bool = False,
) -> Optional[datetime]:
    """
    Parses ISO strings or Indian date formats into strict UTC datetime boundaries.
    If is_end is True, expands a date to 23:59:59.999999 to ensure inclusive range filtering.
    """
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, date):
        if is_end:
            return datetime.combine(date_val, time.max)
        return datetime.combine(date_val, time.min)
    if isinstance(date_val, str):
        clean = date_val.strip()
        if not clean:
            return None
        # If it contains explicit time (has 'T' or space with ':')
        if "T" in clean or (":" in clean and " " in clean):
            try:
                return datetime.fromisoformat(clean)
            except ValueError:
                pass
        # Try Indian and ISO date formats (e.g. 2026-11-12, 12/11/2026)
        d = parse_indian_date(clean)
        if d:
            if is_end:
                return datetime.combine(d, time.max)
            return datetime.combine(d, time.min)
        try:
            parsed_dt = datetime.fromisoformat(clean)
            if is_end and parsed_dt.time() == time.min:
                return datetime.combine(parsed_dt.date(), time.max)
            return parsed_dt
        except ValueError:
            pass
    return None


# ── 1. COMPANY OPERATIONAL DASHBOARD ─────────────────────────────────────────

@router.get("/company")
@requires(COMPANY_VIEW)
def get_company_dashboard(
    request: Request,
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD or ISO)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD or ISO)"),
    branch_id: Optional[int] = Query(default=None, description="Optional branch ID filter"),
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Company-level operational dashboard returning aggregated document totals,
    status distribution, storage usage, branch activity, invoice totals, AI usage,
    and background job counts. Strictly isolated to the caller's tenant.
    """
    auth_ctx.assert_active_company()

    start_dt = parse_date_boundary(date_from, is_end=False)
    end_dt = parse_date_boundary(date_to, is_end=True)

    # 1. Branch Validation: If filtering by branch_id, ensure branch belongs to company
    if branch_id is not None:
        target_branch = (
            db.query(Branch)
            .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
            .first()
        )
        if not target_branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Branch #{branch_id} not found in this company.",
            )

    # 2. Document Metrics & Status Breakdown (excluding soft-deleted)
    doc_query = scope_filter(auth_ctx, db.query(Document), Document, include_deleted=False)
    if branch_id is not None:
        doc_query = doc_query.filter(Document.branch_id == branch_id)
    if start_dt:
        doc_query = doc_query.filter(Document.created_at >= start_dt)
    if end_dt:
        doc_query = doc_query.filter(Document.created_at <= end_dt)

    status_counts_raw = (
        doc_query.with_entities(Document.ocr_status, func.count(Document.id))
        .group_by(Document.ocr_status)
        .all()
    )
    status_map = {
        "uploaded": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    total_docs = 0
    for st, count in status_counts_raw:
        st_key = st.value.lower() if hasattr(st, "value") else str(st).lower()
        status_map[st_key] = count
        total_docs += count

    storage_bytes = (
        doc_query.with_entities(func.coalesce(func.sum(Document.file_size), 0)).scalar()
        or 0
    )
    storage_mb = round(float(storage_bytes) / (1024 * 1024), 2)

    # Daily Upload Trend (for activity chart)
    daily_uploads_raw = (
        doc_query.with_entities(
            cast(Document.created_at, Date).label("day"),
            func.count(Document.id).label("count"),
            func.coalesce(func.sum(Document.file_size), 0).label("bytes"),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    upload_activity = [
        {
            "date": row.day.isoformat(),
            "count": row.count,
            "bytes": row.bytes,
            "mb": round(float(row.bytes) / (1024 * 1024), 2),
        }
        for row in daily_uploads_raw
    ]

    # 3. Branch Distribution
    branches_query = db.query(Branch).filter(Branch.company_id == auth_ctx.company_id)
    if branch_id is not None:
        branches_query = branches_query.filter(Branch.id == branch_id)
    branches = branches_query.order_by(Branch.name.asc()).all()

    branch_stats_raw = (
        doc_query.with_entities(
            Document.branch_id,
            func.count(Document.id).label("doc_count"),
            func.coalesce(func.sum(Document.file_size), 0).label("storage_bytes"),
            func.coalesce(
                func.sum(case((Document.ocr_status == OcrStatus.FAILED, 1), else_=0)),
                0,
            ).label("failed_docs"),
        )
        .group_by(Document.branch_id)
        .all()
    )
    branch_stats_lookup = {
        row.branch_id: {
            "doc_count": row.doc_count,
            "storage_bytes": row.storage_bytes,
            "failed_docs": row.failed_docs,
        }
        for row in branch_stats_raw
    }

    branch_distribution = []
    for b in branches:
        s = branch_stats_lookup.get(
            b.id, {"doc_count": 0, "storage_bytes": 0, "failed_docs": 0}
        )
        branch_distribution.append({
            "branch_id": b.id,
            "branch_name": b.name,
            "branch_code": b.code,
            "status": b.status or "active",
            "document_count": s["doc_count"],
            "storage_bytes": s["storage_bytes"],
            "storage_mb": round(float(s["storage_bytes"]) / (1024 * 1024), 2),
            "failed_count": s["failed_docs"],
        })

    # 4. Invoice Summaries (excluding soft-deleted)
    inv_query = scope_filter(auth_ctx, db.query(Invoice), Invoice, include_deleted=False)
    if branch_id is not None:
        inv_query = inv_query.filter(Invoice.branch_id == branch_id)
    if start_dt:
        inv_query = inv_query.filter(Invoice.created_at >= start_dt)
    if end_dt:
        inv_query = inv_query.filter(Invoice.created_at <= end_dt)

    inv_breakdown = (
        inv_query.with_entities(
            Invoice.kind,
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.taxable_amount), 0).label("taxable_total"),
            func.coalesce(
                func.sum(Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                0,
            ).label("tax_total"),
            func.coalesce(func.sum(Invoice.grand_total), 0).label("grand_total"),
        )
        .group_by(Invoice.kind)
        .all()
    )

    total_invoices = 0
    total_taxable = 0.0
    total_tax = 0.0
    total_grand = 0.0
    by_kind = {
        "copy": {"count": 0, "taxable": 0.0, "tax": 0.0, "grand_total": 0.0},
        "generated": {"count": 0, "taxable": 0.0, "tax": 0.0, "grand_total": 0.0},
    }

    for row in inv_breakdown:
        kind_key = (row.kind or "copy").lower()
        k_count = int(row.count or 0)
        k_taxable = float(row.taxable_total or 0.0)
        k_tax = float(row.tax_total or 0.0)
        k_grand = float(row.grand_total or 0.0)

        total_invoices += k_count
        total_taxable += k_taxable
        total_tax += k_tax
        total_grand += k_grand

        if kind_key in by_kind:
            by_kind[kind_key] = {
                "count": k_count,
                "taxable": round(k_taxable, 2),
                "tax": round(k_tax, 2),
                "grand_total": round(k_grand, 2),
            }

    invoice_summary = {
        "total_invoices": total_invoices,
        "total_taxable_amount": round(total_taxable, 2),
        "total_tax_amount": round(total_tax, 2),
        "total_grand_amount": round(total_grand, 2),
        "currency": "INR",
        "by_kind": by_kind,
    }

    # 5. AI Usage Summary (from ai_processing_logs)
    ai_query = db.query(AIProcessingLog).filter(
        AIProcessingLog.company_id == auth_ctx.company_id
    )
    if branch_id is not None:
        ai_query = ai_query.filter(AIProcessingLog.branch_id == branch_id)
    if start_dt:
        ai_query = ai_query.filter(AIProcessingLog.created_at >= start_dt)
    if end_dt:
        ai_query = ai_query.filter(AIProcessingLog.created_at <= end_dt)

    ai_agg = (
        ai_query.with_entities(
            func.count(AIProcessingLog.id).label("total_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.is_fallback == True, 1), else_=0)), 0
            ).label("fallback_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
            func.coalesce(func.avg(AIProcessingLog.latency_ms), 0).label("avg_latency_ms"),
        )
        .one()
    )

    t_in = int(ai_agg.tokens_in or 0)
    t_out = int(ai_agg.tokens_out or 0)
    c_cents = int(ai_agg.cost_cents or 0)
    rate = get_usd_to_inr_rate(db)
    cost_inr = round(float(ai_agg.cost_inr or 0.0), 2)
    if cost_inr == 0.0 and c_cents > 0:
        cost_inr = round(convert_usd_cents_to_inr(c_cents, rate), 2)

    ai_summary = {
        "total_calls": int(ai_agg.total_calls or 0),
        "successful_calls": int(ai_agg.success_calls or 0),
        "failed_calls": int(ai_agg.failed_calls or 0),
        "fallback_calls": int(ai_agg.fallback_calls or 0),
        "tokens_in": t_in,
        "tokens_out": t_out,
        "total_tokens": t_in + t_out,
        "cost_cents": c_cents,
        "estimated_cost_usd": round(c_cents / 100.0, 4),
        "cost_inr": cost_inr,
        "exchange_rate": rate,
        "reporting_currency": "INR",
        "avg_latency_ms": round(float(ai_agg.avg_latency_ms or 0), 1),
    }

    # 6. Background Jobs Counts
    job_query = db.query(ProcessingJob).filter(
        ProcessingJob.company_id == auth_ctx.company_id
    )
    if branch_id is not None:
        job_query = job_query.filter(ProcessingJob.branch_id == branch_id)
    if start_dt:
        job_query = job_query.filter(ProcessingJob.created_at >= start_dt)
    if end_dt:
        job_query = job_query.filter(ProcessingJob.created_at <= end_dt)

    job_status_counts = (
        job_query.with_entities(ProcessingJob.status, func.count(ProcessingJob.id))
        .group_by(ProcessingJob.status)
        .all()
    )
    jobs_map = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
    }
    total_jobs = 0
    for j_status, j_count in job_status_counts:
        j_key = (j_status or "pending").lower()
        jobs_map[j_key] = j_count
        total_jobs += j_count

    jobs_summary = {
        "total_jobs": total_jobs,
        "pending": jobs_map.get("pending", 0),
        "running": jobs_map.get("running", 0),
        "completed": jobs_map.get("completed", 0),
        "failed": jobs_map.get("failed", 0),
    }

    return {
        "company_id": auth_ctx.company_id,
        "company_name": auth_ctx.company_name,
        "time_window": {
            "date_from": start_dt.isoformat() if start_dt else None,
            "date_to": end_dt.isoformat() if end_dt else None,
            "applied_branch_id": branch_id,
        },
        "documents": {
            "total_count": total_docs,
            "by_status": status_map,
            "storage_used_bytes": storage_bytes,
            "storage_used_mb": storage_mb,
            "upload_activity": upload_activity,
        },
        "branch_distribution": branch_distribution,
        "invoices": invoice_summary,
        "ai_usage": ai_summary,
        "jobs": jobs_summary,
    }


# ── 2. BRANCH OPERATIONAL DASHBOARD ──────────────────────────────────────────

@router.get("/branch/{target_branch_id}")
@requires(BRANCH_VIEW)
def get_branch_dashboard(
    target_branch_id: int,
    request: Request,
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD or ISO)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD or ISO)"),
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Branch-level operational dashboard returning aggregated document totals,
    status distribution, storage usage, invoice totals, AI usage, and background jobs
    specifically scoped to target_branch_id. Enforces branch assignment boundaries.
    """
    auth_ctx.assert_active_company()

    # 1. Branch existence and tenant verification
    branch = (
        db.query(Branch)
        .filter(Branch.id == target_branch_id, Branch.company_id == auth_ctx.company_id)
        .first()
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch #{target_branch_id} not found in this company.",
        )

    # 2. Branch Authorization Check: Non-global admins must have branch in assigned_branch_ids
    if not auth_ctx.is_global_admin and DOCUMENT_VIEW_COMPANY not in auth_ctx.permissions:
        if target_branch_id not in auth_ctx.assigned_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: You are not authorized to view metrics for branch #{target_branch_id}.",
            )

    start_dt = parse_date_boundary(date_from, is_end=False)
    end_dt = parse_date_boundary(date_to, is_end=True)

    # 3. Document Metrics & Status Breakdown (excluding soft-deleted)
    doc_query = (
        scope_filter(auth_ctx, db.query(Document), Document, include_deleted=False)
        .filter(Document.branch_id == target_branch_id)
    )
    if start_dt:
        doc_query = doc_query.filter(Document.created_at >= start_dt)
    if end_dt:
        doc_query = doc_query.filter(Document.created_at <= end_dt)

    status_counts_raw = (
        doc_query.with_entities(Document.ocr_status, func.count(Document.id))
        .group_by(Document.ocr_status)
        .all()
    )
    status_map = {
        "uploaded": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    total_docs = 0
    for st, count in status_counts_raw:
        st_key = st.value.lower() if hasattr(st, "value") else str(st).lower()
        status_map[st_key] = count
        total_docs += count

    storage_bytes = (
        doc_query.with_entities(func.coalesce(func.sum(Document.file_size), 0)).scalar()
        or 0
    )
    storage_mb = round(float(storage_bytes) / (1024 * 1024), 2)

    # Daily Upload Trend
    daily_uploads_raw = (
        doc_query.with_entities(
            cast(Document.created_at, Date).label("day"),
            func.count(Document.id).label("count"),
            func.coalesce(func.sum(Document.file_size), 0).label("bytes"),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    upload_activity = [
        {
            "date": row.day.isoformat(),
            "count": row.count,
            "bytes": row.bytes,
            "mb": round(float(row.bytes) / (1024 * 1024), 2),
        }
        for row in daily_uploads_raw
    ]

    # 4. Invoice Summaries for Branch
    inv_query = (
        scope_filter(auth_ctx, db.query(Invoice), Invoice, include_deleted=False)
        .filter(Invoice.branch_id == target_branch_id)
    )
    if start_dt:
        inv_query = inv_query.filter(Invoice.created_at >= start_dt)
    if end_dt:
        inv_query = inv_query.filter(Invoice.created_at <= end_dt)

    inv_breakdown = (
        inv_query.with_entities(
            Invoice.kind,
            func.count(Invoice.id).label("count"),
            func.coalesce(func.sum(Invoice.taxable_amount), 0).label("taxable_total"),
            func.coalesce(
                func.sum(Invoice.cgst_amount + Invoice.sgst_amount + Invoice.igst_amount),
                0,
            ).label("tax_total"),
            func.coalesce(func.sum(Invoice.grand_total), 0).label("grand_total"),
        )
        .group_by(Invoice.kind)
        .all()
    )

    total_invoices = 0
    total_taxable = 0.0
    total_tax = 0.0
    total_grand = 0.0
    by_kind = {
        "copy": {"count": 0, "taxable": 0.0, "tax": 0.0, "grand_total": 0.0},
        "generated": {"count": 0, "taxable": 0.0, "tax": 0.0, "grand_total": 0.0},
    }

    for row in inv_breakdown:
        kind_key = (row.kind or "copy").lower()
        k_count = int(row.count or 0)
        k_taxable = float(row.taxable_total or 0.0)
        k_tax = float(row.tax_total or 0.0)
        k_grand = float(row.grand_total or 0.0)

        total_invoices += k_count
        total_taxable += k_taxable
        total_tax += k_tax
        total_grand += k_grand

        if kind_key in by_kind:
            by_kind[kind_key] = {
                "count": k_count,
                "taxable": round(k_taxable, 2),
                "tax": round(k_tax, 2),
                "grand_total": round(k_grand, 2),
            }

    invoice_summary = {
        "total_invoices": total_invoices,
        "total_taxable_amount": round(total_taxable, 2),
        "total_tax_amount": round(total_tax, 2),
        "total_grand_amount": round(total_grand, 2),
        "currency": "INR",
        "by_kind": by_kind,
    }

    # 5. AI Usage for Branch
    ai_query = db.query(AIProcessingLog).filter(
        AIProcessingLog.company_id == auth_ctx.company_id,
        AIProcessingLog.branch_id == target_branch_id,
    )
    if start_dt:
        ai_query = ai_query.filter(AIProcessingLog.created_at >= start_dt)
    if end_dt:
        ai_query = ai_query.filter(AIProcessingLog.created_at <= end_dt)

    ai_agg = (
        ai_query.with_entities(
            func.count(AIProcessingLog.id).label("total_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.is_fallback == True, 1), else_=0)), 0
            ).label("fallback_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
            func.coalesce(func.avg(AIProcessingLog.latency_ms), 0).label("avg_latency_ms"),
        )
        .one()
    )

    t_in = int(ai_agg.tokens_in or 0)
    t_out = int(ai_agg.tokens_out or 0)
    c_cents = int(ai_agg.cost_cents or 0)
    rate = get_usd_to_inr_rate(db)
    cost_inr = round(float(ai_agg.cost_inr or 0.0), 2)
    if cost_inr == 0.0 and c_cents > 0:
        cost_inr = round(convert_usd_cents_to_inr(c_cents, rate), 2)

    ai_summary = {
        "total_calls": int(ai_agg.total_calls or 0),
        "successful_calls": int(ai_agg.success_calls or 0),
        "failed_calls": int(ai_agg.failed_calls or 0),
        "fallback_calls": int(ai_agg.fallback_calls or 0),
        "tokens_in": t_in,
        "tokens_out": t_out,
        "total_tokens": t_in + t_out,
        "cost_cents": c_cents,
        "estimated_cost_usd": round(c_cents / 100.0, 4),
        "cost_inr": cost_inr,
        "exchange_rate": rate,
        "reporting_currency": "INR",
        "avg_latency_ms": round(float(ai_agg.avg_latency_ms or 0), 1),
    }

    # 6. Background Jobs for Branch
    job_query = db.query(ProcessingJob).filter(
        ProcessingJob.company_id == auth_ctx.company_id,
        ProcessingJob.branch_id == target_branch_id,
    )
    if start_dt:
        job_query = job_query.filter(ProcessingJob.created_at >= start_dt)
    if end_dt:
        job_query = job_query.filter(ProcessingJob.created_at <= end_dt)

    job_status_counts = (
        job_query.with_entities(ProcessingJob.status, func.count(ProcessingJob.id))
        .group_by(ProcessingJob.status)
        .all()
    )
    jobs_map = {
        "pending": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
    }
    total_jobs = 0
    for j_status, j_count in job_status_counts:
        j_key = (j_status or "pending").lower()
        jobs_map[j_key] = j_count
        total_jobs += j_count

    # Count unresolved failed jobs (where document is currently in FAILED status)
    unresolved_failed_count = (
        db.query(func.count(func.distinct(ProcessingJob.id)))
        .outerjoin(Document, ProcessingJob.document_id == Document.id)
        .filter(
            ProcessingJob.company_id == auth_ctx.company_id,
            ProcessingJob.branch_id == target_branch_id,
            ProcessingJob.status == "failed",
            or_(
                Document.id.is_(None),
                Document.ocr_status == OcrStatus.FAILED,
            ),
        )
        .scalar()
        or 0
    )

    jobs_summary = {
        "total_jobs": total_jobs,
        "pending": jobs_map.get("pending", 0),
        "running": jobs_map.get("running", 0),
        "completed": jobs_map.get("completed", 0),
        "failed": unresolved_failed_count,
        "historical_failed": jobs_map.get("failed", 0),
    }

    # 7. Recent Failed Jobs (Top 5 unresolved failures requiring attention)
    recent_failed_jobs = (
        db.query(ProcessingJob, Document)
        .outerjoin(Document, ProcessingJob.document_id == Document.id)
        .filter(
            ProcessingJob.company_id == auth_ctx.company_id,
            ProcessingJob.branch_id == target_branch_id,
            ProcessingJob.status == "failed",
            or_(
                Document.id.is_(None),
                Document.ocr_status == OcrStatus.FAILED,
            ),
        )
        .order_by(ProcessingJob.created_at.desc())
        .limit(5)
        .all()
    )
    can_reprocess = can(auth_ctx, DOCUMENT_REPROCESS)
    failed_jobs_list = []
    for job, doc in recent_failed_jobs:
        failed_jobs_list.append({
            "job_id": job.id,
            "document_id": job.document_id,
            "document_filename": doc.original_filename if doc else None,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "error_code": job.error_code or "PROCESSING_FAILED",
            "error_summary": sanitize_error_message(job.last_error),
            "created_at": to_utc_iso(job.created_at),
            "updated_at": to_utc_iso(job.updated_at),
            "can_reprocess": bool(can_reprocess and (not doc or doc.deleted_at is None)),
        })

    return {
        "branch_info": {
            "id": branch.id,
            "name": branch.name,
            "code": branch.code,
            "branch_type": branch.branch_type or "Branch",
            "city": branch.city,
            "state": branch.state,
            "status": branch.status or "active",
        },
        "time_window": {
            "date_from": start_dt.isoformat() if start_dt else None,
            "date_to": end_dt.isoformat() if end_dt else None,
        },
        "documents": {
            "total_count": total_docs,
            "by_status": status_map,
            "storage_used_bytes": storage_bytes,
            "storage_used_mb": storage_mb,
            "upload_activity": upload_activity,
        },
        "invoices": invoice_summary,
        "ai_usage": ai_summary,
        "jobs": jobs_summary,
        "recent_failed_jobs": failed_jobs_list,
    }


# ── 3. AI USAGE AND ESTIMATED COST REPORTING ─────────────────────────────────

@router.get("/ai-usage")
@requires(AI_USAGE_VIEW)
def get_ai_usage_report(
    request: Request,
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD or ISO)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD or ISO)"),
    branch_id: Optional[int] = Query(default=None, description="Optional branch ID filter"),
    auth_ctx: AuthContext = Depends(require_permission(AI_USAGE_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Detailed AI usage, token consumption, and estimated USD cost reporting.
    Aggregates attempt-level ai_processing_logs across providers, models, branches,
    and daily usage time series.
    """
    auth_ctx.assert_active_company()

    start_dt = parse_date_boundary(date_from, is_end=False)
    end_dt = parse_date_boundary(date_to, is_end=True)

    base_query = db.query(AIProcessingLog).filter(
        AIProcessingLog.company_id == auth_ctx.company_id
    )

    # Branch scoping
    if not auth_ctx.is_global_admin and DOCUMENT_VIEW_COMPANY not in auth_ctx.permissions:
        if branch_id is not None:
            if branch_id not in auth_ctx.assigned_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: You are not authorized to view AI metrics for branch #{branch_id}.",
                )
            base_query = base_query.filter(AIProcessingLog.branch_id == branch_id)
        else:
            base_query = base_query.filter(
                AIProcessingLog.branch_id.in_(auth_ctx.assigned_branch_ids)
            )
    else:
        if branch_id is not None:
            target_branch = (
                db.query(Branch)
                .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
                .first()
            )
            if not target_branch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Branch #{branch_id} not found in this company.",
                )
            base_query = base_query.filter(AIProcessingLog.branch_id == branch_id)

    if start_dt:
        base_query = base_query.filter(AIProcessingLog.created_at >= start_dt)
    if end_dt:
        base_query = base_query.filter(AIProcessingLog.created_at <= end_dt)

    # 1. Overall Summary
    agg = (
        base_query.with_entities(
            func.count(AIProcessingLog.id).label("total_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.is_fallback == True, 1), else_=0)), 0
            ).label("fallback_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
            func.coalesce(func.avg(AIProcessingLog.latency_ms), 0).label("avg_latency_ms"),
        )
        .one()
    )

    t_in = int(agg.tokens_in or 0)
    t_out = int(agg.tokens_out or 0)
    c_cents = int(agg.cost_cents or 0)
    rate = get_usd_to_inr_rate(db)
    c_inr = round(float(agg.cost_inr or 0.0), 2)
    if c_inr == 0.0 and c_cents > 0:
        c_inr = round(convert_usd_cents_to_inr(c_cents, rate), 2)

    # Logical documents count (distinguish provider attempts from distinct documents processed)
    logical_docs = (
        base_query.filter(AIProcessingLog.document_id.isnot(None))
        .with_entities(func.count(func.distinct(AIProcessingLog.document_id)))
        .scalar()
        or 0
    )

    summary = {
        "total_calls": int(agg.total_calls or 0),
        "successful_calls": int(agg.success_calls or 0),
        "failed_calls": int(agg.failed_calls or 0),
        "fallback_calls": int(agg.fallback_calls or 0),
        "tokens_in": t_in,
        "tokens_out": t_out,
        "total_tokens": t_in + t_out,
        "cost_cents": c_cents,
        "estimated_cost_usd": round(c_cents / 100.0, 4),
        "cost_inr": c_inr,
        "exchange_rate": rate,
        "reporting_currency": "INR",
        "avg_latency_ms": round(float(agg.avg_latency_ms or 0), 1),
        "logical_documents_processed": logical_docs,
    }

    # 2. Provider Breakdown
    provider_rows = (
        base_query.with_entities(
            AIProcessingLog.provider,
            func.count(AIProcessingLog.id).label("calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
        )
        .group_by(AIProcessingLog.provider)
        .order_by(desc("cost_cents"))
        .all()
    )

    by_provider = [
        {
            "provider": row.provider,
            "calls": row.calls,
            "successful_calls": row.success_calls,
            "failed_calls": row.failed_calls,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "total_tokens": row.tokens_in + row.tokens_out,
            "cost_cents": row.cost_cents,
            "estimated_cost_usd": round(row.cost_cents / 100.0, 4),
            "cost_inr": round(float(row.cost_inr or convert_usd_cents_to_inr(row.cost_cents, rate)), 2),
        }
        for row in provider_rows
    ]

    # 3. Model Breakdown
    model_rows = (
        base_query.with_entities(
            AIProcessingLog.provider,
            AIProcessingLog.model,
            func.count(AIProcessingLog.id).label("calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
        )
        .group_by(AIProcessingLog.provider, AIProcessingLog.model)
        .order_by(desc("cost_cents"))
        .all()
    )

    by_model = [
        {
            "provider": row.provider,
            "model": row.model,
            "calls": row.calls,
            "successful_calls": row.success_calls,
            "failed_calls": row.failed_calls,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "total_tokens": row.tokens_in + row.tokens_out,
            "cost_cents": row.cost_cents,
            "estimated_cost_usd": round(row.cost_cents / 100.0, 4),
            "cost_inr": round(float(row.cost_inr or convert_usd_cents_to_inr(row.cost_cents, rate)), 2),
        }
        for row in model_rows
    ]

    # 4. Branch Breakdown
    branch_rows = (
        base_query.with_entities(
            AIProcessingLog.branch_id,
            func.count(AIProcessingLog.id).label("calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
        )
        .group_by(AIProcessingLog.branch_id)
        .order_by(desc("cost_cents"))
        .all()
    )

    # Lookup branch names
    company_branches = {
        b.id: b
        for b in db.query(Branch).filter(Branch.company_id == auth_ctx.company_id).all()
    }

    by_branch = []
    for row in branch_rows:
        b_id = row.branch_id
        br = company_branches.get(b_id) if b_id else None
        by_branch.append({
            "branch_id": b_id,
            "branch_name": br.name if br else ("Company Wide" if not b_id else f"Branch #{b_id}"),
            "branch_code": br.code if br else ("—" if not b_id else f"BR-{b_id}"),
            "calls": row.calls,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "total_tokens": row.tokens_in + row.tokens_out,
            "cost_cents": row.cost_cents,
            "estimated_cost_usd": round(row.cost_cents / 100.0, 4),
            "cost_inr": round(float(row.cost_inr or convert_usd_cents_to_inr(row.cost_cents, rate)), 2),
        })

    # 5. Daily Trends
    daily_rows = (
        base_query.with_entities(
            cast(AIProcessingLog.created_at, Date).label("day"),
            func.count(AIProcessingLog.id).label("calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == True, 1), else_=0)), 0
            ).label("success_calls"),
            func.coalesce(
                func.sum(case((AIProcessingLog.success == False, 1), else_=0)), 0
            ).label("failed_calls"),
            func.coalesce(func.sum(AIProcessingLog.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AIProcessingLog.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AIProcessingLog.cost_cents), 0).label("cost_cents"),
            func.coalesce(func.sum(AIProcessingLog.cost_inr), 0.0).label("cost_inr"),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    daily_trends = [
        {
            "date": row.day.isoformat(),
            "calls": row.calls,
            "successful_calls": row.success_calls,
            "failed_calls": row.failed_calls,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "total_tokens": row.tokens_in + row.tokens_out,
            "cost_cents": row.cost_cents,
            "estimated_cost_usd": round(row.cost_cents / 100.0, 4),
            "cost_inr": round(float(row.cost_inr or convert_usd_cents_to_inr(row.cost_cents, rate)), 2),
        }
        for row in daily_rows
    ]

    return {
        "company_id": auth_ctx.company_id,
        "time_window": {
            "date_from": start_dt.isoformat() if start_dt else None,
            "date_to": end_dt.isoformat() if end_dt else None,
            "applied_branch_id": branch_id,
        },
        "summary": summary,
        "by_provider": by_provider,
        "by_model": by_model,
        "by_branch": by_branch,
        "daily_trends": daily_trends,
    }


# ── 4. FAILED BACKGROUND JOBS MONITORING ─────────────────────────────────────

@router.get("/jobs")
@requires(COMPANY_VIEW)
def get_dashboard_jobs(
    request: Request,
    status_filter: str = Query(
        default="failed",
        alias="status",
        description="Filter by job status: failed, pending, running, completed, all",
    ),
    branch_id: Optional[int] = Query(default=None, description="Optional branch ID filter"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=200, description="Items per page"),
    auth_ctx: AuthContext = Depends(require_permission(COMPANY_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Monitoring endpoint for background processing jobs.
    Sanitizes raw stack traces, file paths, and credentials from last_error
    and evaluates DOCUMENT_REPROCESS permission for safe retry initiation.
    """
    auth_ctx.assert_active_company()

    query = (
        db.query(ProcessingJob, Document, Branch)
        .outerjoin(Document, ProcessingJob.document_id == Document.id)
        .outerjoin(Branch, ProcessingJob.branch_id == Branch.id)
        .filter(ProcessingJob.company_id == auth_ctx.company_id)
    )

    # Branch scoping
    if not auth_ctx.is_global_admin and DOCUMENT_VIEW_COMPANY not in auth_ctx.permissions:
        if branch_id is not None:
            if branch_id not in auth_ctx.assigned_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: You are not authorized to view jobs for branch #{branch_id}.",
                )
            query = query.filter(ProcessingJob.branch_id == branch_id)
        else:
            query = query.filter(
                ProcessingJob.branch_id.in_(auth_ctx.assigned_branch_ids)
            )
    else:
        if branch_id is not None:
            target_branch = (
                db.query(Branch)
                .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
                .first()
            )
            if not target_branch:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Branch #{branch_id} not found in this company.",
                )
            query = query.filter(ProcessingJob.branch_id == branch_id)

    # Status filter
    clean_st = (status_filter or "all").lower().strip()
    if clean_st != "all":
        query = query.filter(ProcessingJob.status == clean_st)

    total_count = query.with_entities(func.count(ProcessingJob.id)).scalar() or 0

    jobs_data = (
        query.order_by(ProcessingJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    can_reprocess = can(auth_ctx, DOCUMENT_REPROCESS)
    results = []
    for job, doc, br in jobs_data:
        doc_filename = doc.original_filename if doc else f"Document #{job.document_id}"
        doc_status = (
            doc.ocr_status.value
            if doc and hasattr(doc.ocr_status, "value")
            else (str(doc.ocr_status) if doc else None)
        )
        is_doc_deleted = bool(doc and doc.deleted_at is not None)

        clean_error = sanitize_error_message(job.last_error) if job.last_error else ""

        results.append({
            "job_id": job.id,
            "document_id": job.document_id,
            "document_filename": doc_filename,
            "document_status": doc_status,
            "document_deleted": is_doc_deleted,
            "branch_id": job.branch_id,
            "branch_name": br.name if br else f"Branch #{job.branch_id}",
            "branch_code": br.code if br else f"BR-{job.branch_id}",
            "job_type": job.job_type,
            "status": job.status,
            "attempts": job.attempts,
            "max_attempts": job.max_attempts,
            "error_code": job.error_code or ("PROCESSING_FAILED" if job.status == "failed" else None),
            "error_summary": clean_error,
            "created_at": to_utc_iso(job.created_at),
            "updated_at": to_utc_iso(job.updated_at),
            "completed_at": to_utc_iso(job.completed_at),
            "can_reprocess": bool(can_reprocess and job.status == "failed" and not is_doc_deleted),
        })

    return {
        "jobs": results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_count,
            "total_pages": (total_count + page_size - 1) // page_size if page_size else 1,
        },
    }


# ── 5. SECURE CSV EXPORT ──────────────────────────────────────────────────────

@router.get("/export/csv")
@requires(BRANCH_VIEW)
def export_dashboard_csv(
    request: Request,
    export_type: str = Query(
        ...,
        description="Export dataset: documents, ai-usage, failed-jobs, invoices",
    ),
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD or ISO)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD or ISO)"),
    branch_id: Optional[int] = Query(default=None, description="Optional branch ID filter"),
    auth_ctx: AuthContext = Depends(require_permission(BRANCH_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Streaming CSV export with formula injection defense (OWASP CSV Injection).
    Enforces multi-tenant isolation, branch validation, and streaming I/O.
    """
    auth_ctx.assert_active_company()

    valid_types = ("documents", "ai-usage", "failed-jobs", "invoices")
    clean_type = export_type.lower().strip()
    if clean_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid export_type '{export_type}'. Must be one of: {', '.join(valid_types)}",
        )

    has_company_view = (
        auth_ctx.is_global_admin
        or COMPANY_VIEW in auth_ctx.permissions
        or DOCUMENT_VIEW_COMPANY in auth_ctx.permissions
    )

    # 1. Company vs Branch Scope Authorization
    if branch_id is None:
        if not has_company_view:
            if auth_ctx.assigned_branch_ids and len(auth_ctx.assigned_branch_ids) == 1:
                branch_id = auth_ctx.assigned_branch_ids[0]
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied: Missing required permission 'company.view' for company-wide exports. Please specify an authorized branch_id.",
                )

    # 2. Branch validation and authorization
    if branch_id is not None:
        target_branch = (
            db.query(Branch)
            .filter(Branch.id == branch_id, Branch.company_id == auth_ctx.company_id)
            .first()
        )
        if not target_branch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Branch #{branch_id} not found in this company.",
            )

        if not has_company_view:
            if branch_id not in auth_ctx.assigned_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: You are not authorized to export data for branch #{branch_id}.",
                )

    start_dt = parse_date_boundary(date_from, is_end=False)
    end_dt = parse_date_boundary(date_to, is_end=True)

    date_label = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{auth_ctx.company_code.lower()}_{clean_type}_{date_label}.csv"

    if clean_type == "documents":
        generator = generate_documents_csv(db, auth_ctx, start_dt, end_dt, branch_id)
    elif clean_type == "ai-usage":
        generator = generate_ai_usage_csv(db, auth_ctx, start_dt, end_dt, branch_id)
    elif clean_type == "failed-jobs":
        generator = generate_failed_jobs_csv(db, auth_ctx, start_dt, end_dt, branch_id)
    elif clean_type == "invoices":
        generator = generate_invoices_csv(db, auth_ctx, start_dt, end_dt, branch_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported export type.")

    return StreamingResponse(
        generator,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
