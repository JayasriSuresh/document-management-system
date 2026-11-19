"""
Module 11 – Extraction Templates Service and Template Resolver.

Manages document extraction templates, versioning, security constraints,
and scope-aware hierarchical template resolution:
  Priority: Active Branch Template -> Active Company Template -> Platform Default Template.
"""

from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.models import DocumentTemplate, TemplateVersion, Document, Company, Branch

logger = logging.getLogger("dms.template_service")

# ── Security & Constraint Limits ─────────────────────────────────────────────
MAX_SCHEMA_SIZE_BYTES = 100_000       # 100 KB max schema JSON
MAX_NESTING_DEPTH = 5                 # Maximum object/array nesting
MAX_FIELD_COUNT = 150                 # Maximum total fields
MAX_VALIDATION_RULES = 50             # Maximum validation rules per version
ALLOWED_TYPES = frozenset({"string", "number", "integer", "boolean", "date", "enum", "object", "array"})
ALLOWED_RULE_TYPES = frozenset({
    "gstin", "date", "line_item_arithmetic", "totals_sum", "gst_consistency",
    "required", "regex", "numeric_range"
})


class TemplateSecurityError(Exception):
    """Raised when a template schema or rule violates security constraints."""
    pass


class TemplateNotFoundError(Exception):
    """Raised when a required template or version cannot be located."""
    pass


class TemplateService:
    @staticmethod
    def validate_schema_security(schema: Dict[str, Any], depth: int = 1, field_count: Optional[List[int]] = None) -> None:
        """
        Recursively validate schema structure, allowed types, and security limits.
        Disallows arbitrary executable expressions and enforces nesting limits.
        """
        if field_count is None:
            field_count = [0]

        if depth > MAX_NESTING_DEPTH:
            raise TemplateSecurityError(f"Schema exceeds maximum nesting depth of {MAX_NESTING_DEPTH}")

        raw_size = len(json.dumps(schema))
        if raw_size > MAX_SCHEMA_SIZE_BYTES:
            raise TemplateSecurityError(f"Schema size ({raw_size} bytes) exceeds limit of {MAX_SCHEMA_SIZE_BYTES} bytes")

        fields = schema.get("fields", [])
        if not isinstance(fields, list):
            raise TemplateSecurityError("Schema 'fields' must be a list")

        for f in fields:
            field_count[0] += 1
            if field_count[0] > MAX_FIELD_COUNT:
                raise TemplateSecurityError(f"Schema exceeds maximum field count of {MAX_FIELD_COUNT}")

            f_key = f.get("key")
            if not f_key or not re.match(r'^[a-zA-Z0-9_\.]+$', str(f_key)):
                raise TemplateSecurityError(f"Invalid field key '{f_key}'. Only alphanumeric, underscores, and dots allowed")

            f_type = str(f.get("type", "string")).lower()
            if f_type not in ALLOWED_TYPES:
                raise TemplateSecurityError(f"Field type '{f_type}' is not supported. Allowed: {sorted(ALLOWED_TYPES)}")

            # Recursive validation for nested objects and arrays
            if f_type == "object" and "fields" in f:
                TemplateService.validate_schema_security(f, depth + 1, field_count)
            elif f_type == "array" and "item_fields" in f:
                item_fields_schema = {"fields": f.get("item_fields", [])}
                TemplateService.validate_schema_security(item_fields_schema, depth + 1, field_count)

    @staticmethod
    def validate_rules_security(rules: List[Dict[str, Any]]) -> None:
        """Validate that validation rules use only allowlisted deterministic rule engines."""
        if not isinstance(rules, list):
            raise TemplateSecurityError("Validation rules must be a list")

        if len(rules) > MAX_VALIDATION_RULES:
            raise TemplateSecurityError(f"Exceeds maximum validation rule count of {MAX_VALIDATION_RULES}")

        for r in rules:
            r_type = str(r.get("type", "")).lower()
            if r_type not in ALLOWED_RULE_TYPES:
                raise TemplateSecurityError(f"Validation rule type '{r_type}' is not recognized. Allowed: {sorted(ALLOWED_RULE_TYPES)}")

    @staticmethod
    def list_templates(
        db: Session,
        company_id: int,
        branch_id: Optional[int] = None,
        user_branch_ids: Optional[List[int]] = None,
        status: Optional[str] = "active",
    ) -> List[DocumentTemplate]:
        """
        List templates scoped to company:
        Includes platform default templates, company-level templates, and accessible branch templates.
        """
        query = db.query(DocumentTemplate).filter(
            or_(
                DocumentTemplate.company_id == company_id,
                DocumentTemplate.company_id.is_(None),  # Platform defaults
            )
        )

        if status:
            query = query.filter(DocumentTemplate.status == status)

        # Branch filtering
        if branch_id is not None:
            query = query.filter(
                or_(
                    DocumentTemplate.branch_id == branch_id,
                    DocumentTemplate.branch_id.is_(None),
                )
            )
        elif user_branch_ids is not None:
            # If user has specific branch assignments
            query = query.filter(
                or_(
                    DocumentTemplate.branch_id.is_(None),
                    DocumentTemplate.branch_id.in_(user_branch_ids),
                )
            )

        return query.order_by(DocumentTemplate.name.asc()).all()

    @staticmethod
    def get_template(db: Session, template_id: int, company_id: int) -> DocumentTemplate:
        """Retrieve a template with company tenant-isolation check."""
        template = db.query(DocumentTemplate).filter(DocumentTemplate.id == template_id).first()
        if not template:
            raise TemplateNotFoundError(f"Template {template_id} not found")

        # Allow platform default templates (company_id is None) or matching company
        if template.company_id is not None and template.company_id != company_id:
            raise TemplateSecurityError(f"Access denied to template {template_id} from another company")

        return template

    @staticmethod
    def create_template(
        db: Session,
        company_id: int,
        document_type: str,
        name: str,
        schema_json: Dict[str, Any],
        validation_rules: Optional[List[Dict[str, Any]]] = None,
        extraction_instructions: Optional[str] = None,
        branch_id: Optional[int] = None,
        description: Optional[str] = None,
        created_by: Optional[int] = None,
        publish_initial: bool = True,
    ) -> Tuple[DocumentTemplate, TemplateVersion]:
        """
        Create a new document template and its version 1.
        Validates security limits and scope uniqueness.
        """
        rules = validation_rules or []
        TemplateService.validate_schema_security(schema_json)
        TemplateService.validate_rules_security(rules)

        # Validate branch belongs to company
        if branch_id:
            branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
            if not branch:
                raise ValueError(f"Branch {branch_id} does not belong to company {company_id}")

        # Check for active template name conflict in same scope
        existing = db.query(DocumentTemplate).filter(
            DocumentTemplate.company_id == company_id,
            DocumentTemplate.branch_id == branch_id,
            DocumentTemplate.name == name,
            DocumentTemplate.status == "active",
        ).first()
        if existing:
            raise ValueError(f"An active template named '{name}' already exists in this scope")

        template = DocumentTemplate(
            company_id=company_id,
            branch_id=branch_id,
            document_type=document_type.strip().lower(),
            name=name.strip(),
            kind="extraction",
            description=description,
            status="active",
            created_by=created_by,
        )
        db.add(template)
        db.flush()

        initial_status = "published" if publish_initial else "draft"
        published_at = datetime.utcnow() if publish_initial else None

        version = TemplateVersion(
            template_id=template.id,
            version_number=1,
            schema_json=schema_json,
            validation_rules=rules,
            extraction_instructions=extraction_instructions,
            status=initial_status,
            published_at=published_at,
            created_by=created_by,
        )
        db.add(version)
        db.commit()
        db.refresh(template)
        db.refresh(version)
        return template, version

    @staticmethod
    def update_template_metadata(
        db: Session,
        template_id: int,
        company_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DocumentTemplate:
        """Update template metadata (name, description). Does NOT mutate published versions."""
        template = TemplateService.get_template(db, template_id, company_id)
        if name:
            template.name = name.strip()
        if description is not None:
            template.description = description
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def deactivate_template(db: Session, template_id: int, company_id: int) -> DocumentTemplate:
        """
        Soft deactivate template (status='inactive').
        Preserves existing documents and template versions.
        """
        template = TemplateService.get_template(db, template_id, company_id)
        template.status = "inactive"
        template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def create_version(
        db: Session,
        template_id: int,
        company_id: int,
        schema_json: Dict[str, Any],
        validation_rules: Optional[List[Dict[str, Any]]] = None,
        extraction_instructions: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> TemplateVersion:
        """
        Create a new draft version for a template.
        Version numbers increment sequentially.
        """
        template = TemplateService.get_template(db, template_id, company_id)
        rules = validation_rules or []
        TemplateService.validate_schema_security(schema_json)
        TemplateService.validate_rules_security(rules)

        # Get highest version number
        last_v = (
            db.query(TemplateVersion.version_number)
            .filter(TemplateVersion.template_id == template.id)
            .order_by(TemplateVersion.version_number.desc())
            .first()
        )
        next_version_num = (last_v[0] + 1) if last_v else 1

        new_version = TemplateVersion(
            template_id=template.id,
            version_number=next_version_num,
            schema_json=schema_json,
            validation_rules=rules,
            extraction_instructions=extraction_instructions,
            status="draft",
            created_by=created_by,
        )
        db.add(new_version)
        db.commit()
        db.refresh(new_version)
        return new_version

    @staticmethod
    def publish_version(db: Session, template_id: int, version_id: int, company_id: int) -> TemplateVersion:
        """
        Publish a template version:
        1. Verifies version belongs to template and company.
        2. Validates schema and rules.
        3. Marks prior published versions as 'retired'.
        4. Sets version status to 'published' with timestamp.
        """
        template = TemplateService.get_template(db, template_id, company_id)
        version = db.query(TemplateVersion).filter(
            TemplateVersion.id == version_id,
            TemplateVersion.template_id == template.id,
        ).first()
        if not version:
            raise TemplateNotFoundError(f"Version {version_id} not found for template {template_id}")

        if version.status == "published":
            return version  # Already published

        TemplateService.validate_schema_security(version.schema_json)
        TemplateService.validate_rules_security(version.validation_rules or [])

        # Retire previously published versions for this template
        db.query(TemplateVersion).filter(
            TemplateVersion.template_id == template.id,
            TemplateVersion.status == "published",
        ).update({"status": "retired"})

        version.status = "published"
        version.published_at = datetime.utcnow()
        template.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def get_version(db: Session, version_id: int, company_id: Optional[int] = None) -> TemplateVersion:
        """Retrieve a specific template version with optional tenant verification."""
        version = db.query(TemplateVersion).filter(TemplateVersion.id == version_id).first()
        if not version:
            raise TemplateNotFoundError(f"Template version {version_id} not found")

        if company_id is not None and version.template.company_id is not None:
            if version.template.company_id != company_id:
                raise TemplateSecurityError("Access denied to template version from another company")

        return version


class TemplateResolver:
    """
    Hierarchical template resolver:
    1. Active branch template -> latest published version.
    2. Active company template -> latest published version.
    3. Platform default template -> latest published version.
    """

    @staticmethod
    def resolve_template(
        db: Session,
        company_id: int,
        branch_id: Optional[int] = None,
        document_type: str = "gst_invoice",
    ) -> TemplateVersion:
        """Resolve the active published template version for a given context."""
        doc_type = document_type.strip().lower()

        # 1. Branch-specific template
        if branch_id:
            branch_tmpl = (
                db.query(DocumentTemplate)
                .filter(
                    DocumentTemplate.company_id == company_id,
                    DocumentTemplate.branch_id == branch_id,
                    DocumentTemplate.document_type == doc_type,
                    DocumentTemplate.status == "active",
                )
                .first()
            )
            if branch_tmpl:
                pub_v = (
                    db.query(TemplateVersion)
                    .filter(
                        TemplateVersion.template_id == branch_tmpl.id,
                        TemplateVersion.status == "published",
                    )
                    .order_by(TemplateVersion.version_number.desc())
                    .first()
                )
                if pub_v:
                    return pub_v

        # 2. Company-wide template (branch_id is None)
        comp_tmpl = (
            db.query(DocumentTemplate)
            .filter(
                DocumentTemplate.company_id == company_id,
                DocumentTemplate.branch_id.is_(None),
                DocumentTemplate.document_type == doc_type,
                DocumentTemplate.status == "active",
            )
            .first()
        )
        if comp_tmpl:
            pub_v = (
                db.query(TemplateVersion)
                .filter(
                    TemplateVersion.template_id == comp_tmpl.id,
                    TemplateVersion.status == "published",
                )
                .order_by(TemplateVersion.version_number.desc())
                .first()
            )
            if pub_v:
                return pub_v

        # 3. Platform default template (company_id is None)
        plat_tmpl = (
            db.query(DocumentTemplate)
            .filter(
                DocumentTemplate.company_id.is_(None),
                DocumentTemplate.branch_id.is_(None),
                DocumentTemplate.document_type == doc_type,
                DocumentTemplate.status == "active",
            )
            .first()
        )
        if plat_tmpl:
            pub_v = (
                db.query(TemplateVersion)
                .filter(
                    TemplateVersion.template_id == plat_tmpl.id,
                    TemplateVersion.status == "published",
                )
                .order_by(TemplateVersion.version_number.desc())
                .first()
            )
            if pub_v:
                return pub_v

        raise TemplateNotFoundError(
            f"No active published template found for document_type='{doc_type}', company_id={company_id}, branch_id={branch_id}"
        )
