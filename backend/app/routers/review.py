"""
Module 11 – Human Review and Document Extraction Router.

Endpoints for document extraction viewing, side-by-side verification,
transactional field-level corrections with complete edit history,
deterministic re-validation, and approval gating:
- GET /api/documents/{document_id}/extraction
- POST /api/documents/{document_id}/review/save
- POST /api/documents/{document_id}/review/approve
- GET /api/documents/{document_id}/edits
"""

from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.context import AuthContext
from app.auth.dependencies import require_permission
from app.auth.permissions import (
    EXTRACTION_VIEW,
    EXTRACTION_REVIEW,
    EXTRACTION_EDIT,
    EXTRACTION_APPROVE,
    EXTRACTION_OVERRIDE,
    DOCUMENT_VIEW_OWN,
)
from app.auth.document_access_policy import DocumentAccessPolicy
from app.audit.service import audit
from app.audit.events import (
    EXTRACTION_EDIT as AUDIT_EXTRACTION_EDIT,
    EXTRACTION_REVIEW_SUBMIT as AUDIT_REVIEW_SUBMIT,
    EXTRACTION_APPROVE as AUDIT_EXTRACTION_APPROVE,
    EXTRACTION_OVERRIDE as AUDIT_EXTRACTION_OVERRIDE,
    ObjectType,
)
from app.models import (
    Document,
    DocumentExtraction,
    ExtractionEdit,
    TemplateVersion,
    User,
    OcrStatus,
)
from app.services.template_service import TemplateResolver
from app.services.validation_engine import validate_extraction, ValidationResult

logger = logging.getLogger("dms.routers.review")

router = APIRouter(prefix="/api/documents", tags=["Document Review & Verification"])


# ── Pydantic Request / Response Schemas ───────────────────────────────────────

class ValidationFlagOut(BaseModel):
    field_path: str
    rule_id: str
    severity: str
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None


class ExtractionEditOut(BaseModel):
    id: int
    field_path: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    edited_by: Optional[int] = None
    editor_name: Optional[str] = None
    edited_at: datetime

    model_config = {"from_attributes": True}


class DocumentExtractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    document_id: int
    template_version_id: int
    template_name: str
    template_version_number: int
    document_type: str
    data: Dict[str, Any]
    validation_flags: List[ValidationFlagOut]
    status: str  # 'pending', 'extracted', 'needs_review', 'approved', 'rejected'
    version: int  # Concurrency lock
    has_errors: bool
    has_warnings: bool
    reviewed_by: Optional[int] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    original_file_url: str
    original_filename: str
    mime_type: str
    schema_json: Dict[str, Any]
    edits_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class SaveReviewRequest(BaseModel):
    version: int = Field(..., description="Optimistic concurrency control version")
    data: Dict[str, Any] = Field(..., description="Updated structured document data")


class ApproveReviewRequest(BaseModel):
    override: bool = Field(False, description="Whether to override unresolved validation errors")
    override_reason: Optional[str] = Field(None, description="Reason required when overriding validation errors")


# ── Helper for deep diff between old and new dictionary ───────────────────────

def _compute_leaf_diffs(old_data: Any, new_data: Any, prefix: str = "") -> List[Dict[str, Any]]:
    """Compute recursive field-level diffs between old and new state."""
    diffs = []
    if isinstance(old_data, dict) and isinstance(new_data, dict):
        all_keys = set(old_data.keys()).union(set(new_data.keys()))
        for k in sorted(all_keys):
            p = f"{prefix}.{k}" if prefix else k
            if k not in old_data:
                diffs.append({"field_path": p, "old_value": None, "new_value": new_data[k]})
            elif k not in new_data:
                diffs.append({"field_path": p, "old_value": old_data[k], "new_value": None})
            else:
                diffs.extend(_compute_leaf_diffs(old_data[k], new_data[k], p))
    elif isinstance(old_data, list) and isinstance(new_data, list):
        if old_data != new_data:
            diffs.append({"field_path": prefix, "old_value": old_data, "new_value": new_data})
    else:
        if old_data != new_data:
            diffs.append({"field_path": prefix, "old_value": old_data, "new_value": new_data})
    return diffs


# ── Authorization Check Helper ───────────────────────────────────────────────

def _assert_document_access(doc: Document, auth_context: AuthContext, required_action: str = "view") -> None:
    DocumentAccessPolicy.verify_document_access(auth_context, DOCUMENT_VIEW_OWN, doc)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/{document_id}/extraction", response_model=DocumentExtractionOut)
def get_document_extraction(
    document_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(EXTRACTION_VIEW)),
):
    """
    Retrieve document extraction, original document view link,
    pinned template schema, and deterministic validation flags.
    """
    doc = db.query(Document).filter(Document.id == document_id, Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")

    _assert_document_access(doc, auth_context, required_action="view")

    extraction = db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()

    # If extraction record does not exist yet (e.g. uploaded before module 11), construct or initialize it
    if not extraction:
        # Resolve template version
        tmpl_v = None
        if doc.template_version_id:
            tmpl_v = db.query(TemplateVersion).filter(TemplateVersion.id == doc.template_version_id).first()
        if not tmpl_v:
            tmpl_v = TemplateResolver.resolve_template(db, doc.company_id, doc.branch_id, "gst_invoice")
            doc.template_version_id = tmpl_v.id
            db.flush()

        parsed_data = {}
        if doc.structured_data:
            try:
                parsed_data = json.loads(doc.structured_data)
            except Exception:
                parsed_data = {"raw_content": doc.structured_data}

        val_res = validate_extraction(parsed_data, tmpl_v)
        flags_dict = [f.to_dict() for f in val_res.flags]
        init_status = "needs_review" if val_res.has_errors else "extracted"

        extraction = DocumentExtraction(
            document_id=doc.id,
            template_version_id=tmpl_v.id,
            data=parsed_data,
            raw_text=doc.ocr_text or "",
            validation_flags=flags_dict,
            status=init_status,
            version=1,
        )
        db.add(extraction)
        db.commit()
        db.refresh(extraction)

    tmpl_v = extraction.template_version
    reviewer_name = None
    if extraction.reviewed_by:
        u = db.query(User).filter(User.id == extraction.reviewed_by).first()
        reviewer_name = u.name if u else None

    flags = extraction.validation_flags or []
    has_err = any(f.get("severity") == "error" for f in flags)
    has_warn = any(f.get("severity") == "warning" for f in flags)
    edits_count = db.query(ExtractionEdit).filter(ExtractionEdit.document_extraction_id == extraction.id).count()

    return DocumentExtractionOut(
        id=extraction.id,
        document_id=doc.id,
        template_version_id=tmpl_v.id,
        template_name=tmpl_v.template.name,
        template_version_number=tmpl_v.version_number,
        document_type=tmpl_v.template.document_type,
        data=extraction.data or {},
        validation_flags=[ValidationFlagOut(**f) for f in flags],
        status=extraction.status,
        version=extraction.version,
        has_errors=has_err,
        has_warnings=has_warn,
        reviewed_by=extraction.reviewed_by,
        reviewer_name=reviewer_name,
        reviewed_at=extraction.reviewed_at,
        original_file_url=f"/api/documents/{doc.id}/file",
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        schema_json=tmpl_v.schema_json or {},
        edits_count=edits_count,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


@router.post("/{document_id}/review/save", response_model=DocumentExtractionOut)
def save_extraction_corrections(
    document_id: int,
    payload: SaveReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(EXTRACTION_EDIT)),
):
    """
    Save field corrections from human review:
    1. Enforces optimistic concurrency via version match.
    2. Records field-level diffs into extraction_edits audit trail.
    3. IMMUTABLY preserves original raw_text OCR output.
    4. Re-runs deterministic validation on updated data.
    5. Updates validation flags and status.
    """
    doc = db.query(Document).filter(Document.id == document_id, Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")

    _assert_document_access(doc, auth_context, required_action="edit")

    extraction = (
        db.query(DocumentExtraction)
        .filter(DocumentExtraction.document_id == doc.id)
        .with_for_update()
        .first()
    )
    if not extraction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction record not found")

    # Optimistic concurrency check
    if extraction.version != payload.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Extraction was modified by another reviewer (current version: {extraction.version}, provided: {payload.version}). Please reload.",
        )

    # Disallow editing finalized approved documents
    if extraction.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved document extractions are finalized and cannot be modified",
        )

    old_data = extraction.data or {}
    new_data = payload.data or {}

    # Compute granular field changes
    diffs = _compute_leaf_diffs(old_data, new_data)

    for d in diffs:
        edit_record = ExtractionEdit(
            document_extraction_id=extraction.id,
            field_path=d["field_path"],
            old_value=d["old_value"],
            new_value=d["new_value"],
            edited_by=auth_context.user_id,
            edited_at=datetime.utcnow(),
        )
        db.add(edit_record)

    # Re-run deterministic validation
    tmpl_v = extraction.template_version
    val_res = validate_extraction(new_data, tmpl_v)
    flags_dict = [f.to_dict() for f in val_res.flags]
    new_status = "needs_review" if val_res.has_errors else "extracted"

    # Strictly preserve raw_text OCR unchanged
    extraction.data = new_data
    extraction.validation_flags = flags_dict
    extraction.status = new_status
    extraction.version += 1
    extraction.updated_at = datetime.utcnow()

    # Sync document structured_data and search columns
    doc.structured_data = json.dumps(new_data)
    from app.services.search_service import sync_document_search_metadata
    sync_document_search_metadata(doc, new_data)

    # Automatically regenerate current supplier copy if one exists so changes (like signatures) reflect immediately
    try:
        from app.services.supplier_copy_service import regenerate_supplier_copy, get_current_supplier_copy
        if get_current_supplier_copy(db, doc.id):
            regenerate_supplier_copy(db=db, ctx=auth_context, doc_id=doc.id)
    except Exception:
        pass

    db.commit()
    db.refresh(extraction)

    audit.record_event(
        db=db,
        action=AUDIT_EXTRACTION_EDIT,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.EXTRACTION,
        object_id=extraction.id,
        metadata={
            "document_id": doc.id,
            "version": extraction.version,
            "changed_fields_count": len(diffs),
            "flags_count": len(flags_dict),
            "status": extraction.status,
        },
    )

    # Return updated detail
    flags = extraction.validation_flags or []
    has_err = any(f.get("severity") == "error" for f in flags)
    has_warn = any(f.get("severity") == "warning" for f in flags)
    edits_count = db.query(ExtractionEdit).filter(ExtractionEdit.document_extraction_id == extraction.id).count()

    return DocumentExtractionOut(
        id=extraction.id,
        document_id=doc.id,
        template_version_id=tmpl_v.id,
        template_name=tmpl_v.template.name,
        template_version_number=tmpl_v.version_number,
        document_type=tmpl_v.template.document_type,
        data=extraction.data or {},
        validation_flags=[ValidationFlagOut(**f) for f in flags],
        status=extraction.status,
        version=extraction.version,
        has_errors=has_err,
        has_warnings=has_warn,
        reviewed_by=extraction.reviewed_by,
        reviewer_name=None,
        reviewed_at=extraction.reviewed_at,
        original_file_url=f"/api/documents/{doc.id}/file",
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        schema_json=tmpl_v.schema_json or {},
        edits_count=edits_count,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


@router.post("/{document_id}/review/approve", response_model=DocumentExtractionOut)
def approve_document_extraction(
    document_id: int,
    payload: ApproveReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(EXTRACTION_APPROVE)),
):
    """
    Approve extraction results:
    1. Checks for unresolved error-level validation flags.
    2. Blocks approval if errors exist unless authorized override with reason is provided.
    3. Finalizes extraction status to 'approved' and marks document COMPLETED.
    """
    doc = db.query(Document).filter(Document.id == document_id, Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")

    _assert_document_access(doc, auth_context, required_action="edit")

    extraction = db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()
    if not extraction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction record not found")

    flags = extraction.validation_flags or []
    has_errors = any(f.get("severity") == "error" for f in flags)

    if has_errors:
        if not payload.override:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot approve document with unresolved error-level validation failures. Correct the fields or provide an authorized override reason.",
            )
        # Check override permission
        if EXTRACTION_OVERRIDE not in auth_context.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to override validation errors (extraction.override_validation required)",
            )
        if not payload.override_reason or len(payload.override_reason.strip()) < 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid explanation of at least 5 characters is required to override validation errors",
            )

        audit.record_event(
            db=db,
            action=AUDIT_EXTRACTION_OVERRIDE,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.EXTRACTION,
            object_id=extraction.id,
            metadata={
                "document_id": doc.id,
                "reason": payload.override_reason.strip(),
                "error_flags_count": len([f for f in flags if f.get("severity") == "error"]),
            },
        )

    extraction.status = "approved"
    extraction.reviewed_by = auth_context.user_id
    extraction.reviewed_at = datetime.utcnow()
    extraction.updated_at = datetime.utcnow()

    doc.ocr_status = OcrStatus.COMPLETED

    db.commit()
    db.refresh(extraction)

    audit.record_event(
        db=db,
        action=AUDIT_EXTRACTION_APPROVE,
        request=request,
        auth_context=auth_context,
        object_type=ObjectType.EXTRACTION,
        object_id=extraction.id,
        metadata={
            "document_id": doc.id,
            "overridden": payload.override,
            "version": extraction.version,
        },
    )

    tmpl_v = extraction.template_version
    edits_count = db.query(ExtractionEdit).filter(ExtractionEdit.document_extraction_id == extraction.id).count()

    return DocumentExtractionOut(
        id=extraction.id,
        document_id=doc.id,
        template_version_id=tmpl_v.id,
        template_name=tmpl_v.template.name,
        template_version_number=tmpl_v.version_number,
        document_type=tmpl_v.template.document_type,
        data=extraction.data or {},
        validation_flags=[ValidationFlagOut(**f) for f in flags],
        status=extraction.status,
        version=extraction.version,
        has_errors=has_errors,
        has_warnings=any(f.get("severity") == "warning" for f in flags),
        reviewed_by=extraction.reviewed_by,
        reviewer_name=auth_context.user_name,
        reviewed_at=extraction.reviewed_at,
        original_file_url=f"/api/documents/{doc.id}/file",
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        schema_json=tmpl_v.schema_json or {},
        edits_count=edits_count,
        created_at=extraction.created_at,
        updated_at=extraction.updated_at,
    )


@router.get("/{document_id}/edits", response_model=List[ExtractionEditOut])
def get_document_extraction_edits(
    document_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(EXTRACTION_VIEW)),
):
    """Retrieve full chronological field-level edit history for a document extraction."""
    doc = db.query(Document).filter(Document.id == document_id, Document.deleted_at.is_(None)).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found")

    _assert_document_access(doc, auth_context, required_action="view")

    extraction = db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()
    if not extraction:
        return []

    edits = (
        db.query(ExtractionEdit)
        .filter(ExtractionEdit.document_extraction_id == extraction.id)
        .order_by(ExtractionEdit.id.desc())
        .all()
    )

    results = []
    for e in edits:
        editor_name = None
        if e.edited_by:
            u = db.query(User).filter(User.id == e.edited_by).first()
            editor_name = u.name if u else None

        results.append(ExtractionEditOut(
            id=e.id,
            field_path=e.field_path,
            old_value=e.old_value,
            new_value=e.new_value,
            edited_by=e.edited_by,
            editor_name=editor_name,
            edited_at=e.edited_at,
        ))

    return results
