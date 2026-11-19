"""
Module 11 – Document Templates Router.

Endpoints for managing document extraction templates and immutable versions:
- List templates (scoped to company and authorized branches)
- Create template with initial version
- Update template metadata
- Soft deactivate template
- Create draft version (sequential version numbering)
- Publish template version (retires older published versions)
- View version history
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
    TEMPLATE_VIEW,
    TEMPLATE_CREATE,
    TEMPLATE_UPDATE,
    TEMPLATE_PUBLISH,
    TEMPLATE_DELETE,
)
from app.audit.service import audit
from app.audit.events import (
    TEMPLATE_CREATE as AUDIT_TEMPLATE_CREATE,
    TEMPLATE_UPDATE as AUDIT_TEMPLATE_UPDATE,
    TEMPLATE_VERSION_CREATE as AUDIT_VERSION_CREATE,
    TEMPLATE_VERSION_PUBLISH as AUDIT_VERSION_PUBLISH,
    TEMPLATE_DEACTIVATE as AUDIT_TEMPLATE_DEACTIVATE,
    ObjectType,
)
from app.models import DocumentTemplate, TemplateVersion, Branch
from app.services.template_service import TemplateService, TemplateSecurityError, TemplateNotFoundError

logger = logging.getLogger("dms.routers.templates")

router = APIRouter(prefix="/api/company/templates", tags=["Extraction Templates"])


# ── Pydantic Request / Response Schemas ───────────────────────────────────────

class TemplateVersionSummary(BaseModel):
    id: int
    version_number: int
    status: str
    published_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[int] = None

    model_config = {"from_attributes": True}


class TemplateVersionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    template_id: int
    version_number: int
    schema_json: Dict[str, Any]
    validation_rules: List[Dict[str, Any]]
    extraction_instructions: Optional[str] = None
    status: str
    published_at: Optional[datetime] = None
    created_at: datetime
    created_by: Optional[int] = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    document_type: str
    name: str
    kind: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    published_version: Optional[TemplateVersionSummary] = None
    versions_count: int = 0


class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    document_type: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    branch_id: Optional[int] = None
    schema_json: Dict[str, Any]
    validation_rules: Optional[List[Dict[str, Any]]] = None
    extraction_instructions: Optional[str] = None
    publish_initial: bool = True


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None


class VersionCreateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    schema_json: Dict[str, Any]
    validation_rules: Optional[List[Dict[str, Any]]] = None
    extraction_instructions: Optional[str] = None


# ── Helper to format template output ─────────────────────────────────────────

def _format_template_out(tmpl: DocumentTemplate, db: Session) -> TemplateOut:
    pub_v = (
        db.query(TemplateVersion)
        .filter(TemplateVersion.template_id == tmpl.id, TemplateVersion.status == "published")
        .order_by(TemplateVersion.version_number.desc())
        .first()
    )
    v_count = db.query(TemplateVersion).filter(TemplateVersion.template_id == tmpl.id).count()

    branch_name = None
    if tmpl.branch_id:
        b = db.query(Branch).filter(Branch.id == tmpl.branch_id).first()
        branch_name = b.name if b else None

    return TemplateOut(
        id=tmpl.id,
        company_id=tmpl.company_id,
        branch_id=tmpl.branch_id,
        branch_name=branch_name,
        document_type=tmpl.document_type,
        name=tmpl.name,
        kind=tmpl.kind,
        description=tmpl.description,
        status=tmpl.status,
        created_at=tmpl.created_at,
        updated_at=tmpl.updated_at,
        published_version=TemplateVersionSummary.model_validate(pub_v) if pub_v else None,
        versions_count=v_count,
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("", response_model=List[TemplateOut])
def list_templates(
    branch_id: Optional[int] = Query(None, description="Filter by branch ID"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    include_inactive: bool = Query(False, description="Include inactive/deactivated templates"),
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_VIEW)),
):
    """List templates accessible to the authenticated company and branch scope."""
    status_filter = None if include_inactive else "active"
    user_branch_ids = None if auth_context.is_global_admin else auth_context.assigned_branch_ids

    # If branch-scoped user requests a specific branch they don't have access to
    if branch_id and not auth_context.is_global_admin and branch_id not in (user_branch_ids or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied to templates for branch {branch_id}",
        )

    templates = TemplateService.list_templates(
        db=db,
        company_id=auth_context.company_id,
        branch_id=branch_id,
        user_branch_ids=user_branch_ids,
        status=status_filter,
    )

    if document_type:
        templates = [t for t in templates if t.document_type == document_type.strip().lower()]

    return [_format_template_out(t, db) for t in templates]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplateCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_CREATE)),
):
    """Create a new extraction template and its version 1."""
    # Branch scope authorization check
    if payload.branch_id:
        if not auth_context.is_global_admin and payload.branch_id not in auth_context.assigned_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot create template in branch {payload.branch_id} outside your assigned branches",
            )
    else:
        # Company-wide template creation requires global admin or company admin
        if not auth_context.is_global_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Creating company-wide templates requires company administrator privileges",
            )

    try:
        template, version = TemplateService.create_template(
            db=db,
            company_id=auth_context.company_id,
            document_type=payload.document_type,
            name=payload.name,
            schema_json=payload.schema_json,
            validation_rules=payload.validation_rules,
            extraction_instructions=payload.extraction_instructions,
            branch_id=payload.branch_id,
            description=payload.description,
            created_by=auth_context.user_id,
            publish_initial=payload.publish_initial,
        )

        audit.record_event(
            db=db,
            action=AUDIT_TEMPLATE_CREATE,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.TEMPLATE,
            object_id=template.id,
            metadata={
                "name": template.name,
                "document_type": template.document_type,
                "branch_id": template.branch_id,
                "version_number": version.version_number,
                "status": version.status,
            },
        )
        return _format_template_out(template, db)

    except TemplateSecurityError as tse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(tse))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_VIEW)),
):
    """Retrieve details for a specific template."""
    try:
        template = TemplateService.get_template(db, template_id, auth_context.company_id)
        # Branch scope authorization check
        if template.branch_id and not auth_context.is_global_admin:
            if template.branch_id not in auth_context.assigned_branch_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to branch template")
        return _format_template_out(template, db)
    except (TemplateNotFoundError, TemplateSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{template_id}", response_model=TemplateOut)
def update_template_metadata(
    template_id: int,
    payload: TemplateUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_UPDATE)),
):
    """Update template metadata (name, description). Does NOT mutate published versions."""
    try:
        template = TemplateService.get_template(db, template_id, auth_context.company_id)
        if template.company_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit platform default templates")
        if template.branch_id and not auth_context.is_global_admin:
            if template.branch_id not in auth_context.assigned_branch_ids:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to branch template")

        updated = TemplateService.update_template_metadata(
            db=db,
            template_id=template_id,
            company_id=auth_context.company_id,
            name=payload.name,
            description=payload.description,
        )

        audit.record_event(
            db=db,
            action=AUDIT_TEMPLATE_UPDATE,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.TEMPLATE,
            object_id=template.id,
            metadata={"name": updated.name, "description": updated.description},
        )
        return _format_template_out(updated, db)
    except (TemplateNotFoundError, TemplateSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{template_id}", response_model=TemplateOut)
def deactivate_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_DELETE)),
):
    """Soft deactivate a template. Historical documents and versions are preserved."""
    try:
        template = TemplateService.get_template(db, template_id, auth_context.company_id)
        if template.company_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot deactivate platform default templates")

        deactivated = TemplateService.deactivate_template(db, template_id, auth_context.company_id)
        audit.record_event(
            db=db,
            action=AUDIT_TEMPLATE_DEACTIVATE,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.TEMPLATE,
            object_id=template.id,
            metadata={"name": deactivated.name, "status": "inactive"},
        )
        return _format_template_out(deactivated, db)
    except (TemplateNotFoundError, TemplateSecurityError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── Version Management Routes ────────────────────────────────────────────────

@router.get("/{template_id}/versions", response_model=List[TemplateVersionSummary])
def list_template_versions(
    template_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_VIEW)),
):
    """List all sequential versions for a template."""
    template = TemplateService.get_template(db, template_id, auth_context.company_id)
    versions = (
        db.query(TemplateVersion)
        .filter(TemplateVersion.template_id == template.id)
        .order_by(TemplateVersion.version_number.desc())
        .all()
    )
    return versions


@router.get("/{template_id}/versions/{version_id}", response_model=TemplateVersionDetail)
def get_template_version_detail(
    template_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_VIEW)),
):
    """Retrieve full schema and validation rules for a specific version."""
    TemplateService.get_template(db, template_id, auth_context.company_id)
    version = db.query(TemplateVersion).filter(
        TemplateVersion.id == version_id,
        TemplateVersion.template_id == template_id,
    ).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    return version


@router.post("/{template_id}/versions", response_model=TemplateVersionDetail, status_code=status.HTTP_201_CREATED)
def create_draft_version(
    template_id: int,
    payload: VersionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_UPDATE)),
):
    """
    Create a new draft version for a template.
    Version numbers increase sequentially. Existing published versions are not modified.
    """
    template = TemplateService.get_template(db, template_id, auth_context.company_id)
    if template.company_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot add versions to platform default templates")

    try:
        new_version = TemplateService.create_version(
            db=db,
            template_id=template_id,
            company_id=auth_context.company_id,
            schema_json=payload.schema_json,
            validation_rules=payload.validation_rules,
            extraction_instructions=payload.extraction_instructions,
            created_by=auth_context.user_id,
        )

        audit.record_event(
            db=db,
            action=AUDIT_VERSION_CREATE,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.TEMPLATE,
            object_id=template_id,
            metadata={"version_number": new_version.version_number, "status": "draft"},
        )
        return new_version
    except TemplateSecurityError as tse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(tse))


@router.post("/{template_id}/versions/{version_id}/publish", response_model=TemplateVersionDetail)
def publish_template_version(
    template_id: int,
    version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(require_permission(TEMPLATE_PUBLISH)),
):
    """
    Publish a draft version.
    Validates schema & rules, marks older published versions as retired, and activates the new version.
    """
    try:
        pub_v = TemplateService.publish_version(
            db=db,
            template_id=template_id,
            version_id=version_id,
            company_id=auth_context.company_id,
        )

        audit.record_event(
            db=db,
            action=AUDIT_VERSION_PUBLISH,
            request=request,
            auth_context=auth_context,
            object_type=ObjectType.TEMPLATE,
            object_id=template_id,
            metadata={"version_number": pub_v.version_number, "version_id": pub_v.id},
        )
        return pub_v
    except TemplateNotFoundError as tnf:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(tnf))
    except TemplateSecurityError as tse:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(tse))
