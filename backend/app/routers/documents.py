import io
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Union

import pytesseract
from PIL import Image
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_from_query
from app.auth.dependencies import require_permission, requires
from app.auth.document_access_policy import DocumentAccessPolicy
from app.auth.permissions import (
    DOCUMENT_DELETE,
    DOCUMENT_DOWNLOAD,
    DOCUMENT_REPROCESS,
    DOCUMENT_SEARCH,
    DOCUMENT_UPLOAD,
    DOCUMENT_VIEW_OWN,
    INVOICE_VIEW,
)
from app.audit import audit
from app.audit.events import (
    DOCUMENT_UPLOAD as AUDIT_DOCUMENT_UPLOAD,
    DOCUMENT_VIEW as AUDIT_DOCUMENT_VIEW,
    DOCUMENT_DOWNLOAD as AUDIT_DOCUMENT_DOWNLOAD,
    DOCUMENT_DELETE as AUDIT_DOCUMENT_DELETE,
    DOCUMENT_REPROCESS as AUDIT_DOCUMENT_REPROCESS,
    DOCUMENT_RESTORE as AUDIT_DOCUMENT_RESTORE,
    ObjectType,
)
from app.config import settings
from app.context import AuthContext, get_auth_context, get_auth_context_from_query
from app.database import get_db
from app.models import (
    AIUsageLedger,
    Company,
    CompanyStatus,
    Document,
    OcrStatus,
    PlatformSetting,
    User,
    UserRole,
    ProcessingJob,
)
from app.services.currency_service import get_usd_to_inr_rate, convert_usd_cents_to_inr
from app.repositories import DocumentRepository
from app.schemas import (
    DocumentOut,
    DocumentListItem,
    BatchUploadResponse,
    FileUploadResultItem,
    PaginatedDocumentResponse,
    SearchResponse,
    SearchResultItem,
)
from app.services.file_validator import FileValidator, FileValidationError
from app.services.job_queue import JobQueueService, ActiveJobConflictError
from app.services.search_service import DocumentSearchService, sync_document_search_metadata
from app.storage import get_storage_adapter
from app.storage.local import LocalStorageAdapter

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "application/pdf",
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


def run_ocr(document_id: int, file_path: str, mime_type: str):
    """Background task: runs Gemini Flash OCR via Google Cloud API and updates DB."""
    import os
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return

        # 1. Check platform AI provider availability
        s_providers = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_providers").first()
        providers_cfg = s_providers.value if s_providers and isinstance(s_providers.value, dict) else {}
        gemini_cfg = providers_cfg.get("gemini", {"enabled": True})
        if not gemini_cfg.get("enabled", True):
            doc.ocr_status = OcrStatus.FAILED
            doc.ocr_text = "[AI provider 'gemini' is disabled platform-wide]"
            db.commit()
            return

        # 2. Check company AI monthly budget
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent_cents = (
            db.query(func.coalesce(func.sum(AIUsageLedger.cost_cents), 0))
            .filter(
                AIUsageLedger.company_id == doc.company_id,
                AIUsageLedger.created_at >= start_of_month,
                AIUsageLedger.status == "success",
            )
            .scalar()
            or 0
        )
        company = db.query(Company).filter(Company.id == doc.company_id).first()
        if company and spent_cents >= company.monthly_ai_budget_cents:
            doc.ocr_status = OcrStatus.FAILED
            doc.ocr_text = "[Monthly AI budget exceeded for this company]"
            rate = get_usd_to_inr_rate(db)
            db.add(AIUsageLedger(
                company_id=doc.company_id,
                branch_id=doc.branch_id,
                provider="gemini",
                model=gemini_cfg.get("default_model", "gemini-2.0-flash"),
                operation="ocr",
                cost_cents=0,
                cost_inr=0.0,
                exchange_rate=rate,
                converted_at=datetime.utcnow(),
                currency="INR",
                status="budget_exceeded",
            ))
            db.commit()
            return

        doc.ocr_status = OcrStatus.PROCESSING
        db.commit()

        try:
            from app.config import settings
            gemini_key = settings.GEMINI_API_KEY
            if not gemini_key:
                raise ValueError("Missing GEMINI_API_KEY in .env file.")
            
            from google import genai
            
            client = genai.Client(api_key=gemini_key)

            # For PDF, we just grab the first page
            target_file_path = file_path
            if mime_type == "application/pdf":
                from pdf2image import convert_from_path
                import tempfile
                images = convert_from_path(file_path, dpi=200)
                if images:
                    temp_img_path = tempfile.mktemp(suffix=".jpg")
                    images[0].save(temp_img_path, format="JPEG")
                    target_file_path = temp_img_path
                    mime_type = "image/jpeg"

            from PIL import Image
            img = Image.open(target_file_path)

            prompt = "Extract all the text from this receipt. Do NOT output any markdown formatting, do NOT output '```', and completely ignore and exclude any noisy artifacts like dashed lines (e.g. '----'), repeated symbols (e.g. '===='), or squiggly lines. Just output the clean text exactly as it appears."

            import time
            max_retries = 3
            response = None
            
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[
                            img,
                            prompt
                        ]
                    )
                    break # Success!
                except Exception as api_e:
                    # If it's a 429 Resource Exhausted or 503 error, wait and retry
                    if ("429" in str(api_e) or "503" in str(api_e)) and attempt < max_retries - 1:
                        time.sleep(4)
                        continue
                    raise api_e

            ocr_text = response.text.strip() if response else "[No text detected]"
            doc.ocr_text = ocr_text if ocr_text else "[No text detected]"

            # --- Hybrid Extraction (Layer 1: Local, Layer 2: Gemini Fallback) ---
            import json
            import re
            from rapidfuzz import process, fuzz
            
            t = doc.ocr_text or ""
            
            FIELD_ALIASES = {
                "bill_no": ["invoice number", "invoice no", "invoice #", "inv no", "inv #", "bill number", "bill no", "bill #", "tax invoice no", "billno"],
                "gst_reg_no": ["gst number", "gst no", "gstin", "gstin no", "gst identification number", "tax registration number", "gst reg no"],
                "date": ["invoice date", "invoice dt", "bill date", "date of invoice", "tax invoice date", "date"],
                "total_amount": ["grand total", "invoice total", "total amount", "net amount", "amount payable", "total payable", "total value", "total"]
            }

            def fuzzy_extract(field_key):
                aliases = FIELD_ALIASES.get(field_key, [])
                best_score = 0
                extracted_val = ""
                for line in t.split('\n'):
                    parts = re.split(r':|\s{2,}', line, maxsplit=1)
                    if len(parts) >= 2:
                        label = parts[0].strip().lower()
                        val = parts[1].strip()
                        
                        match = process.extractOne(label, aliases, scorer=fuzz.ratio)
                        if match and match[1] > best_score:
                            best_score = match[1]
                            extracted_val = val
                return extracted_val if best_score >= 80 else ""

            # Layer 1: Fuzzy Matching & Aliases
            local_gst = fuzzy_extract("gst_reg_no")
            local_date = fuzzy_extract("date")
            local_bill = fuzzy_extract("bill_no")
            local_total = fuzzy_extract("total_amount")

            # Layer 1b: Exact Regex (if fuzzy missed it because of formatting)
            def exact_extract(pattern, text):
                m = re.search(pattern, text, re.IGNORECASE)
                return m.group(1).strip() if m else ""

            if not local_gst: local_gst = exact_extract(r'(?:Gst Reg No|GSTIN|GST No)[:\s]*([A-Z0-9]+)', t)
            if not local_date: local_date = exact_extract(r'(?:Date|Bill Date)[:\s]*([\d]{2}/[\d]{2}/[\d]{4})', t)
            if not local_bill: local_bill = exact_extract(r'(?:Billno|Bill No|Invoice No)[:\s]*([a-zA-Z0-9-]+)', t)
            if not local_total: local_total = exact_extract(r'(?:Total Value|Total Amount|Grand Total)[:\s]*([\d.,]+)', t)

            # Confidence check: if we got the basic fields, we trust the local extraction
            if local_gst and local_bill and local_total:
                branch = exact_extract(r'(?:Branch)[:\s]*(.*?)(?:\n|$)', t)
                customer = exact_extract(r'(?:Customer Name|Billed To)[:\s]*(.*?)(?:\n|$)', t)
                contact = exact_extract(r'(?:Contact Number|Phone)[:\s]*([\d]+)', t)
                
                b_match = re.search(r'(?:Billing Address)[:\s]*(.*?)(?:Delivery Address|$)', t, re.IGNORECASE | re.DOTALL)
                billing = b_match.group(1).strip().replace('\n', ' ') if b_match else ""
                
                d_match = re.search(r'(?:Delivery Address)[:\s]*(.*?)(?:SLNO|Description|$)', t, re.IGNORECASE | re.DOTALL)
                delivery = d_match.group(1).strip().replace('\n', ' ') if d_match else ""

                items = []
                for line in t.split('\n'):
                    if re.match(r'^\s*\d+\s+[A-Za-z]', line):
                        parts = re.split(r'\s{2,}|\t', line.strip())
                        if len(parts) >= 3:
                            items.append({
                                "sl_no": parts[0].split()[0],
                                "description": " ".join(parts[0].split()[1:] + [parts[1] if len(parts)>1 else ""]),
                                "hsn_code": parts[2] if len(parts) > 2 else "",
                                "qty": "1",
                                "unit_price": parts[-2] if len(parts) >= 5 else "",
                                "total": parts[-1] if len(parts) >= 4 else "",
                                "gst": "18",
                                "central_tax": "",
                                "state_tax": "",
                                "integrate": "",
                                "total_value": parts[-1] if len(parts) >= 4 else ""
                            })
                
                doc.structured_data = json.dumps({
                    "gst_reg_no": local_gst,
                    "date": local_date,
                    "bill_no": local_bill,
                    "branch": branch,
                    "customer_name": customer,
                    "contact_number": contact,
                    "billing_address": billing,
                    "delivery_address": delivery,
                    "items": items,
                    "total_amount_words": exact_extract(r'(?:Rupees)\s*(.*?)(?:\n|$)', t),
                    "total_amount": local_total
                })
            else:
                # Fallback to Gemini
                try:
                    p = f"""
                    You are an advanced invoice extraction AI. 
                    Extract the following standardized fields from the invoice text below. The invoice may come from any company and use variations in terminology.
                    Map whatever wording they use to these exact JSON keys. If a field is missing, leave it blank (empty string).
                    Fields: gst_reg_no, date, bill_no, branch, customer_name, contact_number, billing_address, delivery_address, items (list of objects with: sl_no, description, hsn_code, qty, unit_price, total, gst, central_tax, state_tax, integrate, total_value), total_amount_words, total_amount.
                    Return ONLY valid JSON.
                    Text:
                    {t}
                    """
                    extraction_resp = client.models.generate_content(model='gemini-3.6-flash', contents=p)
                    json_str = extraction_resp.text
                    match = re.search(r'```(?:json)?\n(.*?)\n```', json_str, re.DOTALL)
                    if match: json_str = match.group(1)
                    # test parse
                    json.loads(json_str) 
                    doc.structured_data = json_str
                except Exception as ex:
                    # if fallback fails, store empty JSON object
                    doc.structured_data = "{}"

            doc.ocr_status = OcrStatus.COMPLETED
            # Record AI usage in ledger
            cost_cents = 1
            rate = get_usd_to_inr_rate(db)
            cost_inr = convert_usd_cents_to_inr(cost_cents, rate)
            db.add(AIUsageLedger(
                company_id=doc.company_id,
                branch_id=doc.branch_id,
                provider="gemini",
                model="gemini-2.0-flash",
                operation="ocr_extraction",
                tokens_in=150,
                tokens_out=80,
                cost_cents=cost_cents,
                cost_inr=cost_inr,
                exchange_rate=rate,
                converted_at=datetime.utcnow(),
                currency="INR",
                status="success",
            ))
            if company:
                company.ai_budget_spent_cents = int(spent_cents + cost_cents)
                company.ai_budget_spent_inr = round(float(company.ai_budget_spent_inr or 0.0) + cost_inr, 4)
        except Exception as e:
            doc.ocr_status = OcrStatus.FAILED
            doc.ocr_text = f"Cloud OCR failed: {str(e)}"

        db.commit()
    finally:
        db.close()


def get_document_or_404(doc_id: int, db: Session, user_or_context) -> Document:
    """Fetch a document enforcing company and branch isolation via DocumentRepository."""
    if isinstance(user_or_context, AuthContext):
        repo = DocumentRepository(db, user_or_context)
        return repo.get_document(doc_id)

    # Legacy User fallback: construct AuthContext from user
    ctx = AuthContext(
        user_id=user_or_context.id,
        user_email=user_or_context.email,
        user_name=user_or_context.name,
        role=user_or_context.role,
        company_id=user_or_context.company_id,
        company_name=user_or_context.company.name if getattr(user_or_context, "company", None) else "",
        company_code=user_or_context.company.code if getattr(user_or_context, "company", None) else "",
        company_status=user_or_context.company.status if getattr(user_or_context, "company", None) else CompanyStatus.ACTIVE,
        branch_id=user_or_context.branch_id,
        branch_name=user_or_context.branch.name if getattr(user_or_context, "branch", None) else "",
        branch_code=user_or_context.branch.code if getattr(user_or_context, "branch", None) else "",
    )
    repo = DocumentRepository(db, ctx)
    return repo.get_document(doc_id)


def run_worker_job(job_id: int):
    """Executes a specific job via DocumentWorker in background tasks."""
    from app.database import SessionLocal
    from app.worker import DocumentWorker
    from app.models import ProcessingJob

    db = SessionLocal()
    try:
        worker = DocumentWorker(worker_id=f"api-bg-{uuid.uuid4().hex[:6]}")
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job and job.status in ("pending", "running"):
            worker.process_one_job(db, job)
    except Exception as e:
        import logging
        logging.getLogger("dms.api").error(f"Error executing worker job #{job_id}: {e}")
    finally:
        db.close()


async def _process_single_upload(
    file: UploadFile,
    db: Session,
    auth_context: AuthContext,
    request: Request,
    background_tasks: BackgroundTasks,
    raise_on_error: bool = False,
    document_type: Optional[str] = "gst_invoice",
):
    """
    Internal helper to validate, store, and enqueue an individual file upload.
    Returns (Document, error_code, error_message).
    """
    contents = await file.read()
    filename = file.filename or "uploaded_document"

    # 1. Content-based validation
    validation = FileValidator.validate(filename, contents)
    if not validation.is_valid:
        if raise_on_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.error_message or "Invalid file format.",
            )
        return None, validation.error_code, validation.error_message

    # 2. Duplicate Detection
    dup = (
        db.query(Document)
        .filter(
            Document.company_id == auth_context.company_id,
            Document.sha256 == validation.sha256,
            Document.deleted_at.is_(None),
        )
        .first()
    )
    if dup:
        # Anti-enumeration check
        is_accessible = (
            auth_context.is_global_admin or
            dup.branch_id in auth_context.assigned_branch_ids
        )
        if is_accessible:
            dup_msg = f"Duplicate document: exact identical file already exists (Document #{dup.id} '{dup.original_filename}')."
        else:
            dup_msg = "Duplicate document: an exact identical file already exists within your company."

        if raise_on_error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=dup_msg,
            )
        return None, "DUPLICATE_DOCUMENT", dup_msg

    # 3. Company Storage Quota check with row-level lock
    company = db.query(Company).filter(Company.id == auth_context.company_id).with_for_update().first()
    if company:
        current_storage_bytes = (
            db.query(func.coalesce(func.sum(Document.file_size), 0))
            .filter(
                Document.company_id == auth_context.company_id,
                Document.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )
        if (current_storage_bytes + validation.file_size) > company.storage_limit_bytes:
            limit_mb = company.storage_limit_bytes // (1024 * 1024)
            quota_msg = f"Company storage quota exceeded. Limit: {limit_mb} MB."
            if raise_on_error:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=quota_msg,
                )
            return None, "STORAGE_QUOTA_EXCEEDED", quota_msg

    # 4. Storage Adapter write
    storage = get_storage_adapter()
    doc_uuid = uuid.uuid4().hex
    storage_key = LocalStorageAdapter.build_original_key(
        auth_context.company_id,
        auth_context.branch_id,
        doc_uuid,
    )
    storage.save(storage_key, contents)

    # 5. Database record creation
    repo = DocumentRepository(db, auth_context)
    doc = repo.create_document(
        original_filename=filename,
        storage_key=storage_key,
        mime_type=validation.mime_type,
        file_size=validation.file_size,
        sha256=validation.sha256,
        page_count=validation.page_count,
        error_code=None,
        commit=False,
    )

    # 5b. Resolve and pin extraction template version (Module 11)
    from app.services.template_service import TemplateResolver
    try:
        resolved_v = TemplateResolver.resolve_template(
            db,
            company_id=auth_context.company_id,
            branch_id=auth_context.branch_id,
            document_type=document_type or "gst_invoice",
        )
        doc.template_version_id = resolved_v.id
    except Exception as te:
        logger.warning(f"Could not resolve template version on upload: {te}")

    # 6. Durable Job Queue registration
    job = JobQueueService.enqueue_job(
        db,
        document_id=doc.id,
        company_id=auth_context.company_id,
        branch_id=auth_context.branch_id,
        commit=False,
    )

    # 7. Audit log
    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_UPLOAD,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc.id,
        metadata={
            "filename": doc.original_filename,
            "file_size": doc.file_size,
            "mime_type": doc.mime_type,
            "sha256": doc.sha256,
            "job_id": job.id,
        },
    )

    db.commit()
    db.refresh(doc)
    db.refresh(job)

    # Trigger background worker execution
    background_tasks.add_task(run_worker_job, job.id)
    return doc, None, None


@router.post("", response_model=Union[DocumentOut, BatchUploadResponse])
@requires(DOCUMENT_UPLOAD)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    document_type: Optional[str] = Form("gst_invoice"),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_UPLOAD)),
):
    upload_list = []
    if files:
        upload_list.extend(files)
    if file:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No files provided for upload.")

    # Single-file upload mode (preserves 100% backward compatibility for single-file tests & clients)
    if len(upload_list) == 1 and file is not None and not files:
        doc, err_code, err_msg = await _process_single_upload(
            file=upload_list[0],
            db=db,
            auth_context=auth_context,
            request=request,
            background_tasks=background_tasks,
            raise_on_error=True,
            document_type=document_type,
        )
        return _doc_to_out(doc, auth_context.user_name)

    # Multi-file batch upload mode
    if len(upload_list) > settings.MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum limit of {settings.MAX_BATCH_FILES} files per request.",
        )

    results: List[FileUploadResultItem] = []
    successful_count = 0
    failed_count = 0

    for f in upload_list:
        doc, err_code, err_msg = await _process_single_upload(
            file=f,
            db=db,
            auth_context=auth_context,
            request=request,
            background_tasks=background_tasks,
            raise_on_error=False,
            document_type=document_type,
        )
        if doc:
            successful_count += 1
            results.append(FileUploadResultItem(
                filename=f.filename or "unknown",
                status="success",
                document=_doc_to_out(doc, auth_context.user_name),
            ))
        else:
            failed_count += 1
            results.append(FileUploadResultItem(
                filename=f.filename or "unknown",
                status="error",
                error_code=err_code,
                error=err_msg,
            ))

    return BatchUploadResponse(
        total=len(upload_list),
        successful=successful_count,
        failed=failed_count,
        results=results,
    )


@router.post("/batch", response_model=BatchUploadResponse)
@requires(DOCUMENT_UPLOAD)
async def upload_documents_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_UPLOAD)),
):
    """Explicit batch upload endpoint returning individual results per file."""
    if len(files) > settings.MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size exceeds maximum limit of {settings.MAX_BATCH_FILES} files per request.",
        )

    results: List[FileUploadResultItem] = []
    successful_count = 0
    failed_count = 0

    for f in files:
        doc, err_code, err_msg = await _process_single_upload(
            file=f,
            db=db,
            auth_context=auth_context,
            request=request,
            background_tasks=background_tasks,
            raise_on_error=False,
        )
        if doc:
            successful_count += 1
            results.append(FileUploadResultItem(
                filename=f.filename or "unknown",
                status="success",
                document=_doc_to_out(doc, auth_context.user_name),
            ))
        else:
            failed_count += 1
            results.append(FileUploadResultItem(
                filename=f.filename or "unknown",
                status="error",
                error_code=err_code,
                error=err_msg,
            ))

    return BatchUploadResponse(
        total=len(files),
        successful=successful_count,
        failed=failed_count,
        results=results,
    )


@router.get("/search", response_model=SearchResponse)
@requires(DOCUMENT_SEARCH)
def search_documents(
    request: Request,
    q: Optional[str] = Query(default=None, description="Search term for full-text and trigram matching"),
    date_from: Optional[str] = Query(default=None, description="Start date filter (YYYY-MM-DD or Indian format)"),
    date_to: Optional[str] = Query(default=None, description="End date filter (YYYY-MM-DD or Indian format)"),
    vendor_name: Optional[str] = Query(default=None, description="Filter by vendor / supplier name"),
    invoice_number: Optional[str] = Query(default=None, description="Filter by invoice number"),
    gstin: Optional[str] = Query(default=None, description="Filter by GSTIN"),
    amount_min: Optional[str] = Query(default=None, description="Minimum invoice amount"),
    amount_max: Optional[str] = Query(default=None, description="Maximum invoice amount"),
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    status: Optional[str] = Query(default=None, description="Filter by document OCR status"),
    document_type: Optional[str] = Query(default=None, description="Filter by document or MIME type"),
    include_deleted: bool = Query(default=False, description="Include soft-deleted documents"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_SEARCH)),
):
    """
    Centralized Module 12 search endpoint:
    Full-text search, trigram matching, structured filters, relevance ranking,
    and highlighted snippets strictly scoped via DocumentAccessPolicy.
    """
    search_service = DocumentSearchService(db, auth_context)
    return search_service.search_documents(
        q=q,
        date_from=date_from,
        date_to=date_to,
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        gstin=gstin,
        amount_min=amount_min,
        amount_max=amount_max,
        branch_id=branch_id,
        status=status,
        document_type=document_type,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=Union[PaginatedDocumentResponse, List[DocumentListItem]])
@requires(DOCUMENT_VIEW_OWN)
def list_documents(
    response: Response,
    page: Optional[int] = Query(default=None, ge=1, description="Page number for pagination"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
    search: Optional[str] = Query(default="", description="Search in OCR text, filename, or identifiers"),
    status: Optional[str] = Query(default=None, description="Filter by OCR processing status"),
    branch_id: Optional[int] = Query(default=None, description="Filter by branch ID"),
    date_from: Optional[str] = Query(default=None, description="Filter documents created after"),
    date_to: Optional[str] = Query(default=None, description="Filter documents created before"),
    vendor_name: Optional[str] = Query(default=None, description="Filter by vendor / supplier name"),
    invoice_number: Optional[str] = Query(default=None, description="Filter by invoice number"),
    gstin: Optional[str] = Query(default=None, description="Filter by GSTIN"),
    amount_min: Optional[str] = Query(default=None, description="Minimum invoice amount"),
    amount_max: Optional[str] = Query(default=None, description="Maximum invoice amount"),
    document_type: Optional[str] = Query(default=None, description="Filter by document type or MIME"),
    include_deleted: bool = Query(default=False, description="Include soft-deleted documents"),
    paginate: bool = Query(default=False, description="Force paginated response envelope"),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_VIEW_OWN)),
):
    curr_page = page or 1

    # If any search or advanced filter is present, use DocumentSearchService for relevance & FTS
    has_search = bool(
        (search and search.strip()) or
        (vendor_name and vendor_name.strip()) or
        (invoice_number and invoice_number.strip()) or
        (gstin and gstin.strip()) or
        (amount_min and amount_min.strip()) or
        (amount_max and amount_max.strip()) or
        (document_type and document_type.strip())
    )

    if has_search:
        search_service = DocumentSearchService(db, auth_context)
        res = search_service.search_documents(
            q=search if search and search.strip() else None,
            date_from=date_from,
            date_to=date_to,
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            gstin=gstin,
            amount_min=amount_min,
            amount_max=amount_max,
            branch_id=branch_id,
            status=status,
            document_type=document_type,
            include_deleted=include_deleted,
            page=curr_page,
            page_size=page_size,
        )

        response.headers["X-Total-Count"] = str(res["total"])
        response.headers["X-Page"] = str(res["page"])
        response.headers["X-Page-Size"] = str(res["page_size"])
        response.headers["X-Total-Pages"] = str(res["total_pages"])

        item_schemas = [
            DocumentListItem(
                id=item["id"],
                original_filename=item["original_filename"],
                mime_type=item["mime_type"],
                file_size=item["file_size"],
                ocr_status=item["ocr_status"],
                page_count=item["page_count"],
                created_at=datetime.fromisoformat(item["created_at"]) if item.get("created_at") else datetime.utcnow(),
                uploaded_by=item["uploaded_by"],
                uploader_name=item["uploader_name"],
                company_id=item["company_id"],
                branch_id=item["branch_id"],
                branch_name=item.get("branch_name", ""),
                invoice_number=item.get("invoice_number"),
                invoice_date=item.get("invoice_date"),
                vendor_name=item.get("vendor_name"),
                seller_name=item.get("seller_name"),
                seller_gstin=item.get("seller_gstin"),
                buyer_name=item.get("buyer_name"),
                buyer_gstin=item.get("buyer_gstin"),
                invoice_amount=item.get("invoice_amount"),
                grand_total=item.get("grand_total"),
                currency=item.get("currency", "INR"),
                snippet=item.get("snippet"),
                thumbnail_url=item.get("thumbnail_url"),
                file_url=item.get("file_url"),
                tenant_id=item["branch_id"],
            )
            for item in res["items"]
        ]

        if page is not None or paginate:
            return PaginatedDocumentResponse(
                items=item_schemas,
                total=res["total"],
                page=res["page"],
                page_size=res["page_size"],
                total_pages=res["total_pages"],
            )
        return item_schemas

    repo = DocumentRepository(db, auth_context)
    items, total, p, ps, total_pages = repo.list_documents_paginated(
        page=curr_page,
        page_size=page_size,
        search="",
        status_filter=status,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
        include_deleted=include_deleted,
    )

    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(p)
    response.headers["X-Page-Size"] = str(ps)
    response.headers["X-Total-Pages"] = str(total_pages)

    item_schemas = [
        DocumentListItem(
            id=doc.id,
            original_filename=doc.original_filename,
            mime_type=doc.mime_type,
            file_size=doc.file_size,
            ocr_status=doc.ocr_status,
            sha256=doc.sha256,
            page_count=doc.page_count,
            error_code=doc.error_code,
            created_at=doc.created_at,
            uploaded_by=doc.uploaded_by,
            uploader_name=doc.uploader.name if doc.uploader else "Unknown",
            company_id=doc.company_id,
            branch_id=doc.branch_id,
            branch_name=doc.branch.name if doc.branch else "",
            template_version_id=doc.template_version_id,
            deleted_at=doc.deleted_at,
            restored_at=doc.restored_at,
            restored_by=doc.restored_by,
            invoice_number=doc.invoice_number,
            invoice_date=doc.invoice_date.isoformat() if doc.invoice_date else None,
            vendor_name=doc.seller_name,
            seller_name=doc.seller_name,
            seller_gstin=doc.seller_gstin,
            buyer_name=doc.buyer_name,
            buyer_gstin=doc.buyer_gstin,
            invoice_amount=float(doc.grand_total) if doc.grand_total is not None else None,
            grand_total=float(doc.grand_total) if doc.grand_total is not None else None,
            currency=doc.currency or "INR",
            thumbnail_url=f"/api/documents/{doc.id}/thumbnail",
            file_url=f"/api/documents/{doc.id}/file",
            tenant_id=doc.branch_id,
        )
        for doc in items
    ]

    if page is not None or paginate:
        return PaginatedDocumentResponse(
            items=item_schemas,
            total=total,
            page=p,
            page_size=ps,
            total_pages=total_pages,
        )

    return item_schemas


@router.get("/{doc_id}", response_model=DocumentOut)
@requires(DOCUMENT_VIEW_OWN)
def get_document(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_VIEW_OWN)),
):
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)
    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_VIEW,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc.id,
        metadata={"filename": doc.original_filename},
    )
    db.commit()
    return _doc_to_out(doc, doc.uploader.name if doc.uploader else "Unknown")


@router.get("/{doc_id}/file")
@requires(DOCUMENT_DOWNLOAD)
def get_document_file(
    request: Request,
    doc_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_DOWNLOAD)),
):
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)
    if doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage_adapter()
    if not storage.exists(doc.storage_key):
        raise HTTPException(status_code=404, detail="File not found in storage")

    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_DOWNLOAD,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc.id,
        metadata={
            "filename": doc.original_filename,
            "download_format": "original",
        },
    )
    db.commit()

    safe_name = Path(doc.original_filename).name.replace('"', '')
    disp = "attachment" if download else "inline"
    headers = {
        "Content-Disposition": f'{disp}; filename="{safe_name}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
    }
    return StreamingResponse(
        storage.open_stream(doc.storage_key),
        media_type=doc.mime_type or "application/octet-stream",
        headers=headers,
    )


@router.get("/{doc_id}/thumbnail")
@requires(DOCUMENT_VIEW_OWN)
def get_document_thumbnail(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_VIEW_OWN)),
):
    """
    Module 12 Document Thumbnail:
    Generates and returns a 200x200 JPEG thumbnail of the document.
    Enforces tenant scoping, branch permission, and 30-day access policy.
    Caches the generated thumbnail in the storage adapter.
    """
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)
    if doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found")

    storage = get_storage_adapter()
    if not storage.exists(doc.storage_key):
        raise HTTPException(status_code=404, detail="File not found in storage")

    thumb_key = f"{doc.storage_key}_thumb_200.jpg"
    if storage.exists(thumb_key):
        return StreamingResponse(
            storage.open_stream(thumb_key),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )

    # Generate thumbnail dynamically
    raw_bytes = storage.read(doc.storage_key)
    mime = (doc.mime_type or "").lower()
    filename = (doc.original_filename or "").lower()

    try:
        if "pdf" in mime or filename.endswith(".pdf"):
            import pymupdf
            doc_pdf = pymupdf.open(stream=raw_bytes, filetype="pdf")
            if len(doc_pdf) == 0:
                raise HTTPException(status_code=400, detail="Empty PDF file")
            page = doc_pdf.load_page(0)
            pix = page.get_pixmap(dpi=150)
            img = Image.open(io.BytesIO(pix.tobytes("jpeg")))
            doc_pdf.close()
        else:
            img = Image.open(io.BytesIO(raw_bytes))

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((200, 200), Image.Resampling.LANCZOS)
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=85)
        thumb_bytes = out_buf.getvalue()

        try:
            storage.save(thumb_key, thumb_bytes)
        except Exception as e:
            logger.warning(f"Failed to cache thumbnail {thumb_key}: {e}")

        return Response(
            content=thumb_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=86400",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating thumbnail for doc {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate document thumbnail")


@router.delete("/{doc_id}")
@requires(DOCUMENT_DELETE)
def delete_document(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_DELETE)),
):
    """Soft delete a document. Staff role is forbidden (HTTP 403)."""
    repo = DocumentRepository(db, auth_context)
    doc = repo.delete_document(doc_id, commit=False)
    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_DELETE,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc_id,
        metadata={"filename": doc.original_filename},
    )
    db.commit()
    return {"status": "ok"}


@router.post("/{doc_id}/restore", response_model=DocumentOut)
@requires(DOCUMENT_DELETE)
def restore_document(
    request: Request,
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_DELETE)),
):
    """Restore a soft-deleted document."""
    repo = DocumentRepository(db, auth_context)
    doc = repo.restore_document(doc_id)
    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_RESTORE,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc.id,
        metadata={"filename": doc.original_filename},
    )
    db.commit()
    return _doc_to_out(doc, doc.uploader.name if doc.uploader else "Unknown")


@router.post("/{doc_id}/reprocess", response_model=DocumentOut)
@requires(DOCUMENT_REPROCESS)
def reprocess_document(
    request: Request,
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_REPROCESS)),
):
    """Re-run OCR and extraction on an already-uploaded document."""
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)
    if doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Cannot reprocess deleted document.")

    # 1. Active Job Protection: Prevent concurrent duplicate execution
    active_job = JobQueueService.get_active_job(db, doc.id)
    if active_job:
        # If the document is already in FAILED or COMPLETED state, the user is requesting a re-run
        # of an already-finished or failed document. Supersede any old job instead of deadlocking.
        if doc.ocr_status in (OcrStatus.FAILED, OcrStatus.COMPLETED):
            active_job.status = "failed"
            active_job.last_error = "Superseded by user reprocess request"
            active_job.locked_by = None
            active_job.locked_at = None
            db.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An active processing job #{active_job.id} ({active_job.status}) is already running for this document. Please wait a moment.",
            )

    # 2. Check Company AI monthly budget
    company = db.query(Company).filter(Company.id == auth_context.company_id).first()
    if company:
        start_of_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent_cents = (
            db.query(func.coalesce(func.sum(AIUsageLedger.cost_cents), 0))
            .filter(
                AIUsageLedger.company_id == auth_context.company_id,
                AIUsageLedger.created_at >= start_of_month,
                AIUsageLedger.status == "success",
            )
            .scalar()
            or 0
        )
        if spent_cents >= company.monthly_ai_budget_cents:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Monthly AI budget exceeded for this company (${company.monthly_ai_budget_cents / 100:.2f}).",
            )

    storage = get_storage_adapter()
    if not storage.exists(doc.storage_key):
        raise HTTPException(status_code=404, detail="File not found in storage")

    doc = repo.reprocess_document(doc_id, commit=False)
    doc.ocr_status = OcrStatus.PROCESSING
    job = JobQueueService.enqueue_job(
        db,
        document_id=doc.id,
        company_id=auth_context.company_id,
        branch_id=auth_context.branch_id,
        commit=False,
    )

    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_REPROCESS,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.DOCUMENT,
        object_id=doc.id,
        metadata={"filename": doc.original_filename, "job_id": job.id},
    )
    db.commit()
    db.refresh(doc)
    db.refresh(job)

    background_tasks.add_task(run_worker_job, job.id)
    return _doc_to_out(doc, doc.uploader.name if doc.uploader else "Unknown")


@router.get("/{doc_id}/invoice.pdf")
@requires(INVOICE_VIEW)
def generate_invoice(
    request: Request,
    doc_id: int,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)

    if not doc.ocr_text or doc.ocr_status != OcrStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="OCR not completed yet.")

    # ── 0. Check for current supplier invoice copy ───────────────────────────
    from app.services.supplier_copy_service import (
        get_current_supplier_copy,
        check_supplier_copy_stale,
    )

    current_copy = get_current_supplier_copy(db, doc.id)
    disp = "attachment" if download else "inline"

    if current_copy and current_copy.pdf_storage_key:
        pdf_path = Path(settings.STORAGE_PATH) / current_copy.pdf_storage_key
        if not pdf_path.exists():
            # Check repo storage fallback
            alt_path = Path("./storage/documents") / current_copy.pdf_storage_key
            if alt_path.exists():
                pdf_path = alt_path

        if pdf_path.exists():
            is_stale = check_supplier_copy_stale(db, doc)
            audit.record_event(
                db=db,
                action=AUDIT_DOCUMENT_DOWNLOAD if download else AUDIT_DOCUMENT_VIEW,
                request=request,
                auth_context=auth_context,
                object_type=ObjectType.INVOICE,
                object_id=doc.id,
                metadata={
                    "filename": current_copy.pdf_storage_key,
                    "copy_version": current_copy.copy_version,
                    "is_stale": is_stale,
                    "download_format": "pdf",
                },
            )
            db.commit()
            return FileResponse(
                str(pdf_path),
                media_type="application/pdf",
                filename=f"invoice_{doc_id}_v{current_copy.copy_version}.pdf",
                content_disposition_type=disp,
                headers={
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "private, no-store",
                    "X-Invoice-Copy-Version": str(current_copy.copy_version),
                    "X-Invoice-Stale": "true" if is_stale else "false",
                },
            )

    # Legacy fallback: check if we already have frozen PDF saved to disk
    frozen_pdf_path = Path(settings.STORAGE_PATH) / f"generated_invoice_{doc.id}.pdf"
    if frozen_pdf_path.exists():
        audit.record_event(
            db=db,
            action=AUDIT_DOCUMENT_DOWNLOAD if download else AUDIT_DOCUMENT_VIEW,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.INVOICE,
            object_id=doc.id,
            metadata={"filename": f"invoice_{doc_id}.pdf", "download_format": "pdf"},
        )
        db.commit()
        return FileResponse(
            str(frozen_pdf_path),
            media_type="application/pdf",
            filename=f"invoice_{doc_id}.pdf",
            content_disposition_type=disp,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
            },
        )

    import json, re

    # ── 1. Load cached invoice_data (nested schema only) ──────────────────────
    invoice_data = {}
    if doc.structured_data:
        try:
            candidate = json.loads(doc.structured_data)
            if "totals" in candidate:          # must be nested schema
                invoice_data = candidate
        except Exception:
            pass

    # ── 2. Extract via Gemini if not cached ───────────────────────────────────
    if not invoice_data:
        t = (doc.ocr_text or "").strip()
        if not t:
            raise HTTPException(status_code=422, detail="No OCR text available to extract invoice data.")

        try:
            from app.ai.service import AIExecutionService
            system_prompt = """You are an expert Indian GST invoice extraction and normalization AI.
Extract EVERY field from the invoice text and return ONLY valid JSON matching this schema:
{
  "seller":  {"name":"","address":"","gstin":"","state":"","state_code":"","phone":"","email":""},
  "buyer":   {"name":"","address":"","gstin":"","state":"","state_code":"","phone":""},
  "invoice": {"number":"","date":"","payment_terms":"","reference_no":"","buyers_order_no":"","terms_of_delivery":"","other_references":""},
  "delivery":{"name":"","address":""},
  "items":   [{"sl":1,"description":"","batch":"","hsn":"","gst_rate":null,"qty":"","rate":null,"discount":null,"amount":null}],
  "totals":  {"taxable_value":null,"cgst":null,"sgst":null,"igst":null,"round_off":null,"total_qty":"","grand_total":null,"amount_in_words":""},
  "bank":    {"holder":"","bank_name":"","account_no":"","branch":"","ifsc":""},
  "declaration":"",
  "warranty_note":"",
  "footer":[]
}
Keep seller and buyer data strictly separate — do NOT copy buyer contact/GSTIN into seller fields.
Do NOT invent placeholder values like 'Extracted Seller' or '123'."""

            gen_result = AIExecutionService.generate_document(
                db=db,
                company_id=doc.company_id,
                branch_id=doc.branch_id,
                input_data={"ocr_text": t},
                system_prompt=system_prompt,
            )
            invoice_data = gen_result.structured_data if gen_result.structured_data else json.loads(gen_result.content)
            # Persist only valid extractions
            doc.structured_data = json.dumps(invoice_data)
            db.commit()

        except Exception as exc:
            # Do NOT save fake data — let the user know extraction failed
            raise HTTPException(
                status_code=502,
                detail=f"AI extraction failed: {exc}. Please check your configured AI provider settings or try re-processing."
            )

    try:
        from app.services.supplier_copy_service import regenerate_supplier_copy
        copy_rec, pdf_path = regenerate_supplier_copy(
            db=db,
            ctx=auth_context,
            doc_id=doc.id,
        )
        return FileResponse(
            str(pdf_path),
            media_type="application/pdf",
            filename=f"invoice_{doc_id}_v{copy_rec.copy_version}.pdf",
            content_disposition_type=disp,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, no-store",
                "X-Invoice-Copy-Version": str(copy_rec.copy_version),
                "X-Invoice-Stale": "false",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {e}")


@router.get("/{doc_id}/copies")
@requires(INVOICE_VIEW)
def list_document_invoice_copies(
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    """Lists all versions of supplier invoice copies generated for this document."""
    from app.services.supplier_copy_service import (
        list_supplier_copies_for_document,
        check_supplier_copy_stale,
    )
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)
    copies = list_supplier_copies_for_document(db, auth_context, doc.id)
    is_stale = check_supplier_copy_stale(db, doc)

    return [
        {
            "id": c.id,
            "document_id": c.document_id,
            "invoice_id": c.invoice_id,
            "supplier_invoice_number": c.supplier_invoice_number,
            "supplier_name": c.supplier_name,
            "copy_version": c.copy_version,
            "is_current": c.is_current,
            "is_stale": (c.is_current and is_stale),
            "source_data_hash": c.source_data_hash,
            "pdf_storage_key": c.pdf_storage_key,
            "pdf_sha256": c.pdf_sha256,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in copies
    ]


@router.post("/{doc_id}/copies/regenerate")
@requires(DOCUMENT_REPROCESS)
def regenerate_document_invoice_copy(
    doc_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(DOCUMENT_REPROCESS)),
):
    """
    Regenerates a supplier invoice copy as a new version:
    Locks document, re-renders PDF with latest structured data, and increments version.
    """
    from app.services.supplier_copy_service import regenerate_supplier_copy
    new_copy, pdf_path = regenerate_supplier_copy(db, auth_context, doc_id)

    return {
        "status": "success",
        "copy_version": new_copy.copy_version,
        "is_current": new_copy.is_current,
        "pdf_filename": new_copy.pdf_storage_key,
        "pdf_sha256": new_copy.pdf_sha256,
        "source_data_hash": new_copy.source_data_hash,
    }


@router.get("/{doc_id}/copies/{copy_version}/pdf")
@requires(INVOICE_VIEW)
def get_historical_supplier_copy_pdf(
    request: Request,
    doc_id: int,
    copy_version: int,
    download: bool = Query(False),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(INVOICE_VIEW)),
):
    """Retrieves a specific historical version PDF of a supplier invoice copy."""
    from app.models import SupplierInvoiceCopy
    repo = DocumentRepository(db, auth_context)
    doc = repo.get_document(doc_id)

    copy_record = (
        db.query(SupplierInvoiceCopy)
        .filter(SupplierInvoiceCopy.document_id == doc.id, SupplierInvoiceCopy.copy_version == copy_version)
        .first()
    )
    if not copy_record or not copy_record.pdf_storage_key:
        raise HTTPException(status_code=404, detail=f"Invoice copy version {copy_version} not found")

    pdf_path = Path(settings.STORAGE_PATH) / copy_record.pdf_storage_key
    if not pdf_path.exists():
        alt_path = Path("./storage/documents") / copy_record.pdf_storage_key
        if alt_path.exists():
            pdf_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="Historical PDF file missing from storage")

    disp = "attachment" if download else "inline"
    audit.record_event(
        db=db,
        action=AUDIT_DOCUMENT_DOWNLOAD if download else AUDIT_DOCUMENT_VIEW,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.INVOICE,
        object_id=doc.id,
        metadata={"copy_version": copy_version, "download_format": "pdf"},
    )
    db.commit()

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"invoice_{doc_id}_v{copy_version}.pdf",
        content_disposition_type=disp,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "X-Invoice-Copy-Version": str(copy_version),
        },
    )


def _doc_to_out(doc: Document, uploader_name: str) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        file_size=doc.file_size,
        ocr_status=doc.ocr_status,
        ocr_text=doc.ocr_text,
        sha256=doc.sha256,
        page_count=doc.page_count,
        error_code=doc.error_code,
        created_at=doc.created_at,
        uploaded_by=doc.uploaded_by,
        uploader_name=uploader_name,
        company_id=doc.company_id,
        branch_id=doc.branch_id,
        branch_name=doc.branch.name if doc.branch else "",
        template_version_id=doc.template_version_id,
        deleted_at=doc.deleted_at,
        restored_at=doc.restored_at,
        restored_by=doc.restored_by,
        tenant_id=doc.branch_id,
    )
