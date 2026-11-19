"""
GST Registrations Router (Module 13).
Manages company GST registrations across Indian states and union territories.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.audit import events
from app.audit.service import audit
from app.auth.dependencies import require_permission, requires
from app.auth.permissions import GST_REGISTRATION_VIEW, GST_REGISTRATION_MANAGE
from app.context import AuthContext, MasterAdminContext, get_auth_context
from app.database import get_db
from app.models import GstRegistration
from app.schemas import GstRegistrationCreate, GstRegistrationUpdate, GstRegistrationOut
from app.services.gstin_validator import validate_gstin, INDIAN_GST_STATE_CODES

router = APIRouter(prefix="/api/gst-registrations", tags=["gst_registrations"])


@router.get("", response_model=List[GstRegistrationOut])
@requires(GST_REGISTRATION_VIEW)
def list_gst_registrations(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """List all GST registrations belonging to the current user's company."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if GST_REGISTRATION_VIEW not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    registrations = (
        db.query(GstRegistration)
        .filter(GstRegistration.company_id == ctx.company_id)
        .order_by(GstRegistration.is_default.desc(), GstRegistration.created_at.asc())
        .all()
    )
    return registrations


@router.post("", response_model=GstRegistrationOut, status_code=status.HTTP_201_CREATED)
@requires(GST_REGISTRATION_MANAGE)
def create_gst_registration(
    data: GstRegistrationCreate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Create a new GST registration for the company after strict checksum and state validation."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if GST_REGISTRATION_MANAGE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    cleaned_gstin = data.gstin.strip().upper()
    is_valid, err_msg = validate_gstin(cleaned_gstin)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err_msg)

    # Check for duplicate GSTIN
    existing = (
        db.query(GstRegistration)
        .filter(GstRegistration.company_id == ctx.company_id, GstRegistration.gstin == cleaned_gstin)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"GSTIN '{cleaned_gstin}' is already registered for this company.",
        )

    state_code = cleaned_gstin[:2]
    state_name = INDIAN_GST_STATE_CODES.get(state_code, data.state_name or "Unknown")

    # If this is marked default, unset existing default
    if data.is_default:
        db.query(GstRegistration).filter(
            GstRegistration.company_id == ctx.company_id,
            GstRegistration.is_default == True,
        ).update({"is_default": False})

    # If first registration for company, make it default automatically
    count = db.query(GstRegistration).filter(GstRegistration.company_id == ctx.company_id).count()
    is_def = data.is_default or (count == 0)

    reg = GstRegistration(
        company_id=ctx.company_id,
        gstin=cleaned_gstin,
        legal_name=data.legal_name.strip(),
        trade_name=data.trade_name.strip() if data.trade_name else None,
        state_code=state_code,
        state_name=state_name,
        registered_address=data.registered_address.strip() if data.registered_address else None,
        is_default=is_def,
        is_active=True,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)

    audit.record_event(
        db=db,
        action=events.GST_REGISTRATION_CREATE,
        auth_context=ctx,
        object_type=events.ObjectType.GST_REGISTRATION.value,
        object_id=reg.id,
        metadata={"gstin": cleaned_gstin, "state_code": state_code},
    )

    return reg


@router.get("/{reg_id}", response_model=GstRegistrationOut)
@requires(GST_REGISTRATION_VIEW)
def get_gst_registration(
    reg_id: int,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Retrieve a specific company GST registration."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if GST_REGISTRATION_VIEW not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    reg = (
        db.query(GstRegistration)
        .filter(GstRegistration.company_id == ctx.company_id, GstRegistration.id == reg_id)
        .first()
    )
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GST registration not found")

    return reg


@router.put("/{reg_id}", response_model=GstRegistrationOut)
@requires(GST_REGISTRATION_MANAGE)
def update_gst_registration(
    reg_id: int,
    data: GstRegistrationUpdate,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Update non-identifying fields of a GST registration."""
    if isinstance(ctx, MasterAdminContext):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    if GST_REGISTRATION_MANAGE not in ctx.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    reg = (
        db.query(GstRegistration)
        .filter(GstRegistration.company_id == ctx.company_id, GstRegistration.id == reg_id)
        .first()
    )
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GST registration not found")

    if data.legal_name is not None:
        reg.legal_name = data.legal_name.strip()
    if data.trade_name is not None:
        reg.trade_name = data.trade_name.strip()
    if data.registered_address is not None:
        reg.registered_address = data.registered_address.strip()
    if data.is_active is not None:
        reg.is_active = data.is_active
    if data.is_default is not None and data.is_default:
        db.query(GstRegistration).filter(
            GstRegistration.company_id == ctx.company_id,
            GstRegistration.id != reg.id,
        ).update({"is_default": False})
        reg.is_default = True

    db.commit()
    db.refresh(reg)

    audit.record_event(
        db=db,
        action=events.GST_REGISTRATION_UPDATE,
        auth_context=ctx,
        object_type=events.ObjectType.GST_REGISTRATION.value,
        object_id=reg.id,
    )

    return reg
