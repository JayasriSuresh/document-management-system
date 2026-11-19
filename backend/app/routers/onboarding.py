"""
Public Onboarding Router for Prospective Companies.

Allows invited companies to:
  - View onboarding state and prefilled data via secure token
  - Upload compliance and verification documents (PAN, GST, Incorporation, Address Proof)
  - Stream/download previously uploaded verification documents
  - Submit / Resubmit company onboarding details for Master Admin review
"""

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.audit import audit
from app.audit.events import ActorType
from app.auth import get_password_hash
from app.config import settings
from app.database import get_db
from app.models import CompanyOnboarding, OnboardingStatus
from app.schemas import (
    CompanyOnboardingOut,
    CompanyOnboardingSubmit,
    GenericMessageResponse,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

ONBOARDING_STORAGE_DIR = Path("./storage/onboarding")
ONBOARDING_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_DOC_TYPES = {
    "pan_document": "PAN Card / PAN Document",
    "gst_certificate": "GST Registration Certificate",
    "incorporation_certificate": "Certificate of Incorporation",
    "udyam_certificate": "Udyam MSME Certificate",
    "address_proof": "Company Address Proof",
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _to_onboarding_out(onboarding: CompanyOnboarding) -> CompanyOnboardingOut:
    """Helper to convert CompanyOnboarding model to CompanyOnboardingOut schema."""
    onboarding_url = f"{settings.FRONTEND_URL.rstrip('/')}/company/onboard?token={onboarding.token}"
    return CompanyOnboardingOut(
        id=onboarding.id,
        token=onboarding.token,
        status=onboarding.status,
        initial_company_name=onboarding.initial_company_name,
        contact_name=onboarding.contact_name,
        contact_email=onboarding.contact_email,
        onboarding_url=onboarding_url,
        legal_company_name=onboarding.legal_company_name or onboarding.initial_company_name,
        trade_name=onboarding.trade_name,
        business_type=onboarding.business_type,
        business_description=onboarding.business_description,
        year_of_establishment=onboarding.year_of_establishment,
        company_website=onboarding.company_website,
        pan_number=onboarding.pan_number,
        gstin=onboarding.gstin,
        gst_type=onboarding.gst_type,
        cin=onboarding.cin,
        llpin=onboarding.llpin,
        udyam_number=onboarding.udyam_number,
        tan=onboarding.tan,
        address_line1=onboarding.address_line1,
        address_line2=onboarding.address_line2,
        city=onboarding.city,
        state=onboarding.state,
        district=onboarding.district,
        pincode=onboarding.pincode,
        country=onboarding.country or "India",
        auth_contact_name=onboarding.auth_contact_name or onboarding.contact_name,
        auth_contact_designation=onboarding.auth_contact_designation,
        auth_contact_email=onboarding.auth_contact_email or onboarding.contact_email,
        auth_contact_mobile=onboarding.auth_contact_mobile,
        auth_contact_alternate_mobile=onboarding.auth_contact_alternate_mobile,
        has_multiple_branches=bool(onboarding.has_multiple_branches),
        branch_details=onboarding.branch_details or [],
        admin_name=onboarding.admin_name or onboarding.contact_name,
        admin_email=onboarding.admin_email or onboarding.contact_email,
        admin_mobile=onboarding.admin_mobile,
        admin_designation=onboarding.admin_designation,
        has_admin_password=bool(onboarding.admin_password_hash),
        primary_document_types=onboarding.primary_document_types or [],
        expected_monthly_volume=onboarding.expected_monthly_volume,
        languages=onboarding.languages or ["English"],
        timezone=onboarding.timezone or "Asia/Kolkata",
        currency=onboarding.currency or "INR",
        uploaded_documents=onboarding.uploaded_documents or {},
        review_comments=onboarding.review_comments,
        review_history=onboarding.review_history or [],
        company_id=onboarding.company_id,
        created_at=onboarding.created_at,
        updated_at=onboarding.updated_at,
        submitted_at=onboarding.submitted_at,
        reviewed_at=onboarding.reviewed_at,
    )


@router.get("/{token}", response_model=CompanyOnboardingOut)
def get_onboarding_form_data(token: str, db: Session = Depends(get_db)):
    """Fetch the onboarding form record by token."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.token == token).first()
    if not onboarding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired onboarding link. Please contact the administrator.",
        )
    return _to_onboarding_out(onboarding)


def _validate_magic_bytes(contents: bytes) -> bool:
    """Validate file signatures for PDF, PNG, JPEG, and WebP."""
    if len(contents) < 4:
        return False
    if contents.startswith(b"%PDF"):
        return True
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if contents.startswith(b"\xff\xd8\xff"):
        return True
    if len(contents) >= 12 and contents.startswith(b"RIFF") and contents[8:12] == b"WEBP":
        return True
    return False


@router.post("/{token}/upload-document")
async def upload_onboarding_document(
    token: str,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a verification document (PAN, GST, Incorporation, Address Proof)."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.token == token).first()
    if not onboarding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Onboarding application not found.",
        )

    if onboarding.status == OnboardingStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application has already been approved. Modifications are not allowed.",
        )

    if document_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type. Allowed types: {list(ALLOWED_DOC_TYPES.keys())}",
        )

    # Validate file format
    content_type = file.content_type or ""
    if content_type.lower() not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload PDF, JPEG, PNG, or WebP files.",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum allowed limit (10 MB).",
        )

    # Validate file magic bytes signature
    if not _validate_magic_bytes(contents):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match its declared type. Corrupted or invalid file signature.",
        )

    # Secure storage filename
    ext = os.path.splitext(file.filename or "")[1].lower() or ".bin"
    safe_filename = f"{onboarding.id}_{document_type}_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = ONBOARDING_STORAGE_DIR / safe_filename

    with open(dest_path, "wb") as f:
        f.write(contents)

    docs = onboarding.uploaded_documents or {}
    docs[document_type] = {
        "filename": file.filename,
        "storage_key": safe_filename,
        "file_size": len(contents),
        "mime_type": content_type,
        "uploaded_at": datetime.utcnow().isoformat(),
        "display_name": ALLOWED_DOC_TYPES[document_type],
    }
    onboarding.uploaded_documents = docs
    flag_modified(onboarding, "uploaded_documents")
    db.commit()

    return {
        "message": f"{ALLOWED_DOC_TYPES[document_type]} uploaded successfully.",
        "document_type": document_type,
        "document": docs[document_type],
        "uploaded_documents": onboarding.uploaded_documents,
    }


@router.get("/{token}/documents/{document_type}")
def stream_onboarding_document(token: str, document_type: str, db: Session = Depends(get_db)):
    """Stream or download an uploaded verification document."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.token == token).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    docs = onboarding.uploaded_documents or {}
    if document_type not in docs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested document not found.")

    doc_meta = docs[document_type]
    file_path = ONBOARDING_STORAGE_DIR / doc_meta["storage_key"]
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File is missing from storage.")

    return FileResponse(
        path=file_path,
        media_type=doc_meta.get("mime_type", "application/octet-stream"),
        filename=doc_meta.get("filename", f"{document_type}.bin"),
        content_disposition_type="attachment",
    )


@router.post("/{token}/submit", response_model=GenericMessageResponse)
def submit_onboarding_form(
    token: str,
    payload: CompanyOnboardingSubmit,
    request: Request,
    db: Session = Depends(get_db),
):
    """Submit the complete onboarding application for review."""
    onboarding = db.query(CompanyOnboarding).filter(CompanyOnboarding.token == token).first()
    if not onboarding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    if onboarding.status == OnboardingStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Application has already been approved. You cannot resubmit.",
        )

    # Handle Password validation
    if payload.admin_password:
        if len(payload.admin_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin password must be at least 8 characters long.",
            )
        if payload.admin_password != payload.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin password and confirmation password do not match.",
            )
        onboarding.admin_password_hash = get_password_hash(payload.admin_password)
    elif not onboarding.admin_password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrator password is required for account creation.",
        )

    # Validate essential fields
    if not payload.legal_company_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Legal Company Name is required.")
    if not payload.business_type.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business Type is required.")
    if not payload.pan_number.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PAN Number is required.")
    if not payload.address_line1.strip() or not payload.city.strip() or not payload.state.strip() or not payload.pincode.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Complete registered office address is required.")
    if not payload.auth_contact_name.strip() or not payload.auth_contact_mobile.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Authorized contact person details are required.")
    if not payload.admin_name.strip() or not payload.admin_email.strip() or not payload.admin_mobile.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="First company administrator details are required.")

    # Section A
    onboarding.legal_company_name = payload.legal_company_name.strip()
    onboarding.trade_name = payload.trade_name.strip() if payload.trade_name else None
    onboarding.business_type = payload.business_type.strip()
    onboarding.business_description = payload.business_description.strip() if payload.business_description else None
    onboarding.year_of_establishment = payload.year_of_establishment.strip() if payload.year_of_establishment else None
    onboarding.company_website = payload.company_website.strip() if payload.company_website else None

    # Section B
    onboarding.pan_number = payload.pan_number.strip().upper()
    onboarding.gstin = payload.gstin.strip().upper() if payload.gstin else None
    onboarding.gst_type = payload.gst_type.strip() if payload.gst_type else None
    onboarding.cin = payload.cin.strip().upper() if payload.cin else None
    onboarding.llpin = payload.llpin.strip().upper() if payload.llpin else None
    onboarding.udyam_number = payload.udyam_number.strip().upper() if payload.udyam_number else None
    onboarding.tan = payload.tan.strip().upper() if payload.tan else None

    # Section C
    onboarding.address_line1 = payload.address_line1.strip()
    onboarding.address_line2 = payload.address_line2.strip() if payload.address_line2 else None
    onboarding.city = payload.city.strip()
    onboarding.state = payload.state.strip()
    onboarding.district = payload.district.strip()
    onboarding.pincode = payload.pincode.strip()
    onboarding.country = payload.country.strip() if payload.country else "India"

    # Section D
    onboarding.auth_contact_name = payload.auth_contact_name.strip()
    onboarding.auth_contact_designation = payload.auth_contact_designation.strip()
    onboarding.auth_contact_email = payload.auth_contact_email.strip().lower()
    onboarding.auth_contact_mobile = payload.auth_contact_mobile.strip()
    onboarding.auth_contact_alternate_mobile = payload.auth_contact_alternate_mobile.strip() if payload.auth_contact_alternate_mobile else None

    # Section E
    onboarding.has_multiple_branches = payload.has_multiple_branches
    onboarding.branch_details = payload.branch_details or []

    # Section F
    onboarding.admin_name = payload.admin_name.strip()
    onboarding.admin_email = payload.admin_email.strip().lower()
    onboarding.admin_mobile = payload.admin_mobile.strip()
    onboarding.admin_designation = payload.admin_designation.strip()

    # Section G
    onboarding.primary_document_types = payload.primary_document_types or []
    onboarding.expected_monthly_volume = payload.expected_monthly_volume
    onboarding.languages = payload.languages or ["English"]
    onboarding.timezone = payload.timezone or "Asia/Kolkata"
    onboarding.currency = payload.currency or "INR"

    # Move status to SUBMITTED
    onboarding.status = OnboardingStatus.SUBMITTED
    onboarding.submitted_at = datetime.utcnow()

    audit.record(
        db=db,
        actor_type=ActorType.ANONYMOUS,
        actor_id=None,
        action="onboarding.submit",
        object_type="onboarding",
        object_id=onboarding.id,
        metadata={
            "legal_company_name": onboarding.legal_company_name,
            "contact_email": onboarding.auth_contact_email,
        },
        ip=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        request_id=getattr(getattr(request, "state", None), "request_id", None) if request else None,
    )

    db.commit()

    return GenericMessageResponse(
        message="Onboarding application submitted successfully! It is now under review by the Master Admin team."
    )

