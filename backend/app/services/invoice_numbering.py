"""
Invoice sequence allocation and financial year service.
Compliant with GST Rule 46(b) (max 16 alphanumeric characters, unique per FY & registration).
Uses transactional row-level locks (SELECT ... FOR UPDATE) to guarantee gapless, concurrency-safe numbering.
"""

from datetime import datetime, date, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import NumberSequence

INDIA_TZ = ZoneInfo("Asia/Kolkata")
DEFAULT_SERIES_CODE = "INV"
MAX_INVOICE_NUMBER_LENGTH = 16


def get_current_financial_year(dt: Optional[date] = None) -> str:
    """
    Computes the Indian Financial Year (April 1 to March 31) in Asia/Kolkata timezone.
    Examples:
        2026-03-19 -> '2025-26'
        2026-04-01 -> '2026-27'
        2026-11-12 -> '2026-27'
    """
    if dt is None:
        target_dt = datetime.now(INDIA_TZ).date()
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            target_dt = dt.replace(tzinfo=timezone.utc).astimezone(INDIA_TZ).date()
        else:
            target_dt = dt.astimezone(INDIA_TZ).date()
    else:
        target_dt = dt

    year = target_dt.year
    month = target_dt.month

    if month >= 4:
        next_yy = str(year + 1)[-2:]
        return f"{year}-{next_yy}"
    else:
        curr_yy = str(year)[-2:]
        return f"{year - 1}-{curr_yy}"


def format_invoice_number(series_code: str, financial_year: str, seq_num: int) -> str:
    """
    Formats the invoice number: e.g. INV/2026-27/0001.
    Enforces GST Rule 46(b) requirement of max 16 characters.
    """
    prefix = (series_code or DEFAULT_SERIES_CODE).strip().upper()
    formatted = f"{prefix}/{financial_year}/{seq_num:04d}"
    if len(formatted) > MAX_INVOICE_NUMBER_LENGTH:
        raise ValueError(
            f"Invoice number '{formatted}' exceeds the statutory maximum length of "
            f"{MAX_INVOICE_NUMBER_LENGTH} characters prescribed under GST Rule 46(b)."
        )
    return formatted


def reserve_invoice_number(
    db: Session,
    company_id: int,
    gst_registration_id: int,
    series_code: str = DEFAULT_SERIES_CODE,
    invoice_date: Optional[date] = None,
    financial_year: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Reserves the next consecutive invoice number for the given company and GST registration.
    
    Locks the corresponding row in `number_sequences` with `FOR UPDATE`.
    If no sequence row exists yet for this FY and series, creates one safely.
    
    Returns:
        (invoice_number: str, financial_year: str)
    """
    fy = financial_year or get_current_financial_year(invoice_date)
    series = (series_code or DEFAULT_SERIES_CODE).strip().upper()

    # Attempt to fetch with row lock
    seq = (
        db.query(NumberSequence)
        .filter(
            NumberSequence.company_id == company_id,
            NumberSequence.gst_registration_id == gst_registration_id,
            NumberSequence.financial_year == fy,
            NumberSequence.series_code == series,
        )
        .with_for_update()
        .first()
    )

    if not seq:
        # Sequence doesn't exist yet: insert initial row
        # To handle potential race condition if two threads attempt creation simultaneously,
        # we can flush and catch/retry or use savepoint
        seq = NumberSequence(
            company_id=company_id,
            gst_registration_id=gst_registration_id,
            financial_year=fy,
            series_code=series,
            next_value=1,
            padding=4,
        )
        db.add(seq)
        try:
            db.flush()
        except Exception:
            db.rollback()
            # Retry fetching now that row was created by concurrent transaction
            seq = (
                db.query(NumberSequence)
                .filter(
                    NumberSequence.company_id == company_id,
                    NumberSequence.gst_registration_id == gst_registration_id,
                    NumberSequence.financial_year == fy,
                    NumberSequence.series_code == series,
                )
                .with_for_update()
                .one()
            )

    current_val = seq.next_value
    formatted_number = format_invoice_number(series, fy, current_val)

    # Advance sequence
    seq.next_value = current_val + 1
    db.flush()

    return formatted_number, fy
