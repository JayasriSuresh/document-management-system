"""
Module 12 – Search Upgrade Service.

Provides production-ready full-text search, trigram matching, structured filtering,
relevance-based ranking, secure snippets, and pagination with strict multi-tenant
and 30-day uploader isolation enforced via DocumentAccessPolicy.
"""

from datetime import date, datetime
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException, status as http_status
from sqlalchemy import (
    Date,
    Numeric,
    and_,
    case,
    cast,
    func,
    or_,
    text,
)
from sqlalchemy.orm import Session, Query

from app.auth.document_access_policy import DocumentAccessPolicy
from app.context import AuthContext, MasterAdminContext
from app.models import Document, UserRole


# ── 1. Normalization Helpers ─────────────────────────────────────────────────

def parse_indian_amount(val: Any) -> Optional[float]:
    """
    Parses Indian and international formatted currency and numeric strings into float.
    Handles:
      - '1,20,000' -> 120000.0
      - '12,50,000' -> 1250000.0
      - '1,20,000.50' -> 120000.5
      - '₹ 96,000.00' -> 96000.0
      - 'Rs. 1,50,000' -> 150000.0
      - 'Rs.1,50,000.75' -> 150000.75
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r'(?i)[₹\s]|rs\.?|inr|,', '', val).strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_indian_date(date_val: Any) -> Optional[date]:
    """
    Parses common Indian and ISO date formats into a standard date object.
    Supports formats like '19-Mar-26', '19-Mar-2026', '19/03/2026', '2026-03-19'.
    """
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    if isinstance(date_val, str):
        clean = date_val.strip()
        fmts = [
            "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
            "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
            "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
            "%d-%B-%Y", "%d-%B-%y", "%d %B %Y", "%d %B %y",
            "%b %d, %Y", "%B %d, %Y", "%d/%b/%Y", "%d/%b/%y"
        ]
        for f in fmts:
            try:
                return datetime.strptime(clean, f).date()
            except ValueError:
                pass
            try:
                return datetime.strptime(clean.title(), f).date()
            except ValueError:
                pass
    return None


def sync_document_search_metadata(doc: Document, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Populates extracted search columns (invoice_number, invoice_date, seller_name,
    seller_gstin, buyer_name, buyer_gstin, grand_total) on Document model.
    The database trigger will automatically compute and update doc.search_vector.
    """
    if data is None and doc.structured_data:
        try:
            data = json.loads(doc.structured_data)
        except Exception:
            data = {}

    if not data or not isinstance(data, dict):
        return

    inv = data.get("invoice") or {}
    seller = data.get("seller") or {}
    buyer = data.get("buyer") or {}
    totals = data.get("totals") or {}

    # Invoice Number
    inv_num = inv.get("number") or data.get("invoice_number") or data.get("bill_no")
    if inv_num:
        doc.invoice_number = str(inv_num).strip()

    # Invoice Date
    inv_date_str = inv.get("date") or data.get("invoice_date") or data.get("date")
    parsed_d = parse_indian_date(inv_date_str)
    if parsed_d:
        doc.invoice_date = parsed_d

    # Seller / Vendor
    s_name = seller.get("name") or data.get("seller_name") or data.get("merchant_name")
    if s_name:
        doc.seller_name = str(s_name).strip()
    s_gstin = seller.get("gstin") or data.get("seller_gstin") or data.get("gst_reg_no")
    if s_gstin:
        doc.seller_gstin = str(s_gstin).strip().upper()

    # Buyer
    b_name = buyer.get("name") or data.get("buyer_name") or data.get("customer_name")
    if b_name:
        doc.buyer_name = str(b_name).strip()
    b_gstin = buyer.get("gstin") or data.get("buyer_gstin")
    if b_gstin:
        doc.buyer_gstin = str(b_gstin).strip().upper()

    # Grand Total Amount
    tot = totals.get("grand_total") if totals.get("grand_total") is not None else data.get("total_amount")
    parsed_amt = parse_indian_amount(tot)
    if parsed_amt is not None:
        doc.grand_total = parsed_amt


# ── 2. Centralized Document Search Service ───────────────────────────────────

class DocumentSearchService:
    """
    Enterprise Document Search Engine enforcing multi-tenant isolation,
    relevance scoring, trigram matching, and highlighted snippet extraction.
    """

    def __init__(self, db: Session, auth_context: Union[AuthContext, MasterAdminContext]):
        self.db = db
        self.auth_context = auth_context

    def search_documents(
        self,
        q: Optional[str] = None,
        date_from: Optional[Union[str, date]] = None,
        date_to: Optional[Union[str, date]] = None,
        vendor_name: Optional[str] = None,
        invoice_number: Optional[str] = None,
        gstin: Optional[str] = None,
        amount_min: Optional[Union[str, float]] = None,
        amount_max: Optional[Union[str, float]] = None,
        branch_id: Optional[int] = None,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Executes a secure, indexed search with relevance ranking, snippet highlighting,
        and deterministic pagination.
        """
        # Master Admin has no access to company document content
        if isinstance(self.auth_context, MasterAdminContext):
            return {
                "items": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
                "query": q,
                "filters": {},
            }

        # 1. Enforce active company status (suspended companies cannot search)
        self.auth_context.assert_active_company()

        # 2. Base query strictly scoped through DocumentAccessPolicy
        query: Query = DocumentAccessPolicy.apply_query_scope(
            self.auth_context,
            self.db.query(Document),
            Document,
            include_deleted=include_deleted,
        )

        filters_applied: Dict[str, Any] = {}

        # 3. Branch Security Validation & Filter
        if branch_id is not None:
            if self.auth_context.is_global_admin:
                query = query.filter(Document.branch_id == branch_id)
                filters_applied["branch_id"] = branch_id
            elif self.auth_context.role == UserRole.ADMIN:
                assigned = self.auth_context.assigned_branch_ids
                if branch_id in assigned:
                    query = query.filter(Document.branch_id == branch_id)
                    filters_applied["branch_id"] = branch_id
                else:
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail="Permission denied: You do not have access to documents in this branch.",
                    )
            else:
                # Staff / Uploader: can only view own assigned branch
                if branch_id == self.auth_context.branch_id:
                    query = query.filter(Document.branch_id == branch_id)
                    filters_applied["branch_id"] = branch_id
                else:
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail="Permission denied: You do not have access to documents in this branch.",
                    )

        # 4. Status Filter
        if status:
            norm_status = status.strip().upper()
            query = query.filter(Document.ocr_status == norm_status)
            filters_applied["status"] = norm_status

        # 5. Document Type / Mime Type Filter
        if document_type:
            dt = document_type.strip().lower()
            filters_applied["document_type"] = dt
            if dt in ("pdf", "application/pdf"):
                query = query.filter(Document.mime_type == "application/pdf")
            elif dt in ("image", "img", "jpeg", "jpg", "png"):
                query = query.filter(Document.mime_type.ilike("image/%"))
            else:
                query = query.filter(
                    or_(
                        Document.mime_type.ilike(f"%{dt}%"),
                        Document.original_filename.ilike(f"%.{dt}"),
                    )
                )

        # 6. Date Range Filters (Evaluates invoice_date or fallback created_at::date)
        parsed_date_from = parse_indian_date(date_from)
        if parsed_date_from:
            query = query.filter(
                func.coalesce(Document.invoice_date, cast(Document.created_at, Date)) >= parsed_date_from
            )
            filters_applied["date_from"] = parsed_date_from.isoformat()

        parsed_date_to = parse_indian_date(date_to)
        if parsed_date_to:
            query = query.filter(
                func.coalesce(Document.invoice_date, cast(Document.created_at, Date)) <= parsed_date_to
            )
            filters_applied["date_to"] = parsed_date_to.isoformat()

        # 7. Structured Vendor Filter
        if vendor_name and vendor_name.strip():
            v = vendor_name.strip()
            filters_applied["vendor_name"] = v
            query = query.filter(
                or_(
                    Document.seller_name.ilike(f"%{v}%"),
                    func.word_similarity(v, Document.seller_name) >= 0.3,
                )
            )

        # 8. Structured Invoice Number Filter
        if invoice_number and invoice_number.strip():
            inv_no = invoice_number.strip()
            filters_applied["invoice_number"] = inv_no
            clean_inv = re.sub(r'[^a-zA-Z0-9]+', '', inv_no)
            query = query.filter(
                or_(
                    Document.invoice_number.ilike(f"%{inv_no}%"),
                    func.replace(func.coalesce(Document.invoice_number, ''), '-', '').ilike(f"%{clean_inv}%"),
                    func.word_similarity(inv_no, Document.invoice_number) >= 0.3,
                )
            )

        # 9. Structured GSTIN Filter
        if gstin and gstin.strip():
            g = gstin.strip().upper()
            filters_applied["gstin"] = g
            query = query.filter(
                or_(
                    Document.seller_gstin.ilike(f"%{g}%"),
                    Document.buyer_gstin.ilike(f"%{g}%"),
                )
            )

        # 10. Amount Range Filters with Indian Currency normalization
        min_val = parse_indian_amount(amount_min)
        if min_val is not None:
            query = query.filter(Document.grand_total >= min_val)
            filters_applied["amount_min"] = min_val

        max_val = parse_indian_amount(amount_max)
        if max_val is not None:
            query = query.filter(Document.grand_total <= max_val)
            filters_applied["amount_max"] = max_val

        # 11. Text Search & Relevance Ranking
        clean_q = q.strip() if q and q.strip() else None
        score_expr = None

        if clean_q:
            q_lower = clean_q.lower()
            # Clean alphanumeric query variant for matching punctuated numbers
            clean_alphanumeric_q = re.sub(r'[^a-zA-Z0-9]+', ' ', clean_q).strip()

            fts_match_eng = Document.search_vector.op("@@")(func.plainto_tsquery('english', clean_q))
            fts_match_smp = Document.search_vector.op("@@")(func.plainto_tsquery('simple', clean_q))

            # Trigram & Substring matching
            trg_inv = Document.invoice_number.ilike(f"%{clean_q}%")
            trg_gst_s = Document.seller_gstin.ilike(f"%{clean_q}%")
            trg_gst_b = Document.buyer_gstin.ilike(f"%{clean_q}%")
            trg_fn = Document.original_filename.ilike(f"%{clean_q}%")
            trg_ven = func.word_similarity(clean_q, func.coalesce(Document.seller_name, '')) >= 0.3
            trg_buyer = func.word_similarity(clean_q, func.coalesce(Document.buyer_name, '')) >= 0.3
            trg_ocr = Document.ocr_text.ilike(f"%{clean_q}%")

            # Combine match condition
            text_match_condition = or_(
                fts_match_eng,
                fts_match_smp,
                trg_inv,
                trg_gst_s,
                trg_gst_b,
                trg_fn,
                trg_ven,
                trg_buyer,
                trg_ocr,
            )
            query = query.filter(text_match_condition)

            # Relevance Score Calculation (Prioritizes exact identifier matches)
            score_expr = (
                case((func.lower(func.coalesce(Document.invoice_number, '')) == q_lower, 100.0), else_=0.0)
                + case((or_(func.lower(func.coalesce(Document.seller_gstin, '')) == q_lower, func.lower(func.coalesce(Document.buyer_gstin, '')) == q_lower), 80.0), else_=0.0)
                + case((func.lower(func.coalesce(Document.seller_name, '')) == q_lower, 60.0), else_=0.0)
                + case((func.lower(func.coalesce(Document.original_filename, '')) == q_lower, 40.0), else_=0.0)
                + case((Document.invoice_number.ilike(f"%{clean_q}%"), 30.0), else_=0.0)
                + case((or_(Document.seller_gstin.ilike(f"%{clean_q}%"), Document.buyer_gstin.ilike(f"%{clean_q}%")), 25.0), else_=0.0)
                + case((Document.original_filename.ilike(f"%{clean_q}%"), 20.0), else_=0.0)
                + (func.coalesce(func.word_similarity(clean_q, Document.seller_name), 0.0) * 25.0)
                + (func.coalesce(func.word_similarity(clean_q, Document.buyer_name), 0.0) * 20.0)
                + (func.coalesce(func.ts_rank_cd(Document.search_vector, func.plainto_tsquery('english', clean_q)), 0.0) * 15.0)
                + (func.coalesce(func.ts_rank_cd(Document.search_vector, func.plainto_tsquery('simple', clean_q)), 0.0) * 15.0)
            )

        # 12. Ordering
        if score_expr is not None:
            query = query.order_by(score_expr.desc(), Document.created_at.desc(), Document.id.desc())
        else:
            query = query.order_by(Document.created_at.desc(), Document.id.desc())

        # 13. Pagination & Count
        safe_page_size = max(1, min(page_size, 100))
        safe_page = max(1, page)
        total_count = query.count()
        total_pages = max(1, (total_count + safe_page_size - 1) // safe_page_size)

        docs: List[Document] = (
            query.offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )

        # 14. Snippet Generation & Formatting
        items = []
        for doc in docs:
            snippet = self._generate_snippet(doc, clean_q)
            items.append({
                "id": doc.id,
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "file_size": doc.file_size,
                "ocr_status": doc.ocr_status.value if hasattr(doc.ocr_status, 'value') else str(doc.ocr_status),
                "page_count": doc.page_count,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "uploaded_by": doc.uploaded_by,
                "uploader_name": doc.uploader.name if doc.uploader else "Unknown",
                "company_id": doc.company_id,
                "branch_id": doc.branch_id,
                "branch_name": doc.branch.name if doc.branch else "Unknown",
                "invoice_number": doc.invoice_number,
                "invoice_date": doc.invoice_date.isoformat() if doc.invoice_date else None,
                "vendor_name": doc.seller_name,
                "seller_name": doc.seller_name,
                "seller_gstin": doc.seller_gstin,
                "buyer_name": doc.buyer_name,
                "buyer_gstin": doc.buyer_gstin,
                "invoice_amount": float(doc.grand_total) if doc.grand_total is not None else None,
                "grand_total": float(doc.grand_total) if doc.grand_total is not None else None,
                "currency": doc.currency or "INR",
                "snippet": snippet,
                "thumbnail_url": f"/api/documents/{doc.id}/thumbnail",
                "file_url": f"/api/documents/{doc.id}/file",
            })

        return {
            "items": items,
            "total": total_count,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
            "query": clean_q,
            "filters": filters_applied,
        }

    def _generate_snippet(self, doc: Document, q: Optional[str]) -> Optional[str]:
        """
        Extracts a safe search headline snippet with [[HL]]...[[/HL]] markers.
        Guarantees that unauthorized documents are never processed here.
        """
        if not q or not q.strip():
            # If no search term, return a summary preview of extracted fields or first line of OCR
            if doc.invoice_number or doc.seller_name:
                parts = []
                if doc.invoice_number:
                    parts.append(f"Invoice: {doc.invoice_number}")
                if doc.seller_name:
                    parts.append(f"Vendor: {doc.seller_name}")
                if doc.grand_total is not None:
                    parts.append(f"Amount: ₹ {doc.grand_total:,.2f}")
                return " | ".join(parts)
            if doc.ocr_text:
                return doc.ocr_text[:140].strip() + ("…" if len(doc.ocr_text) > 140 else "")
            return None

        clean_q = q.strip()
        ocr_text = doc.ocr_text or ""

        # Try PostgreSQL ts_headline
        if ocr_text:
            try:
                hl = self.db.execute(
                    text("""
                        SELECT ts_headline(
                            'english',
                            :txt,
                            plainto_tsquery('english', :q),
                            'StartSel=[[HL]], StopSel=[[/HL]], MaxWords=25, MinWords=10, MaxFragments=2, FragmentDelimiter=" … "'
                        );
                    """),
                    {"txt": ocr_text, "q": clean_q},
                ).scalar()
                if hl and "[[HL]]" in hl:
                    return hl.strip()
            except Exception:
                pass

            # Try with simple dictionary if english headline did not match
            try:
                hl_s = self.db.execute(
                    text("""
                        SELECT ts_headline(
                            'simple',
                            :txt,
                            plainto_tsquery('simple', :q),
                            'StartSel=[[HL]], StopSel=[[/HL]], MaxWords=25, MinWords=10, MaxFragments=2, FragmentDelimiter=" … "'
                        );
                    """),
                    {"txt": ocr_text, "q": clean_q},
                ).scalar()
                if hl_s and "[[HL]]" in hl_s:
                    return hl_s.strip()
            except Exception:
                pass

        # If OCR text didn't contain highlighted match, check metadata fields:
        q_low = clean_q.lower()
        if doc.invoice_number and q_low in doc.invoice_number.lower():
            return f"Matched Invoice No: [[HL]]{doc.invoice_number}[[/HL]]"
        if doc.seller_name and q_low in doc.seller_name.lower():
            return f"Matched Vendor: [[HL]]{doc.seller_name}[[/HL]]"
        if doc.seller_gstin and q_low in doc.seller_gstin.lower():
            return f"Matched GSTIN: [[HL]]{doc.seller_gstin}[[/HL]]"
        if doc.original_filename and q_low in doc.original_filename.lower():
            return f"Matched Filename: [[HL]]{doc.original_filename}[[/HL]]"
        if doc.buyer_name and q_low in doc.buyer_name.lower():
            return f"Matched Buyer: [[HL]]{doc.buyer_name}[[/HL]]"

        # Fallback to OCR excerpt
        if ocr_text:
            idx = ocr_text.lower().find(q_low)
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(ocr_text), idx + len(clean_q) + 60)
                frag = ocr_text[start:end]
                # Insert markers around match
                pattern = re.compile(re.escape(clean_q), re.IGNORECASE)
                highlighted_frag = pattern.sub(lambda m: f"[[HL]]{m.group(0)}[[/HL]]", frag)
                return ("…" if start > 0 else "") + highlighted_frag.strip() + ("…" if end < len(ocr_text) else "")

            return ocr_text[:140].strip() + ("…" if len(ocr_text) > 140 else "")

        return None
