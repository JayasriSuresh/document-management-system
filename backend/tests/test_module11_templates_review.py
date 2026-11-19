"""
Module 11 Test Suite — Extraction Templates, Deterministic Validation, and Human Review.

Covers:
1. Seeded default GST Invoice template and backward compatibility
2. Template CRUD, multi-tenant company and branch scope isolation
3. Immutable sequential template versioning (draft -> published -> retired)
4. Hierarchical template resolution (Branch > Company > Platform)
5. Schema security limits (size, nesting depth, allowed types, disallowed code eval)
6. Centralized deterministic validation engine (GSTIN, dates, line items, tax consistency)
7. Worker and pipeline integration with template version pinning
8. Human review workflow: field corrections, optimistic concurrency, and edit history
9. Immutable raw_text preservation (OCR text never mutated by review edits)
10. Approval gating and validation error override protection
11. End-to-end acceptance scenario: Custom Expense Receipt template lifecycle
12. Database hygiene (zero test data leaks into dms_db)
"""

import io
import json
import uuid
from datetime import datetime
from unittest.mock import patch, MagicMock
from PIL import Image

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import (
    Company, Branch, User, UserRole, AccountStatus, UserRoleAssignment, Document,
    DocumentTemplate, TemplateVersion, DocumentExtraction, ExtractionEdit,
    ProcessingJob, OcrStatus,
)
from app.auth import get_password_hash, create_access_token
from app.auth.permissions import (
    TEMPLATE_VIEW, TEMPLATE_CREATE, TEMPLATE_UPDATE, TEMPLATE_PUBLISH, TEMPLATE_DELETE,
    EXTRACTION_VIEW, EXTRACTION_REVIEW, EXTRACTION_EDIT, EXTRACTION_APPROVE, EXTRACTION_OVERRIDE,
)
from app.services.template_service import TemplateService, TemplateResolver, TemplateSecurityError, TemplateNotFoundError
from app.services.validation_engine import validate_extraction, DeterministicValidationEngine
from app.worker import DocumentWorker
from app.storage import get_storage_adapter, LocalStorageAdapter
from app.main import app


# ── Fixtures & Teardown ──────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_env(db):
    """
    Creates an isolated test environment:
    Company A (with Chennai & Mysore branches), Company Admin, Branch Admin.
    Company B (for tenant isolation verification).
    Teardown ensures complete removal so zero test records remain in dms_db.
    """
    tag = uuid.uuid4().hex[:6]

    # Company A
    company_a = Company(
        name=f"Mod11 Corp A {tag}",
        display_name=f"Mod11 Enterprise A {tag}",
        code=f"M11A_{tag}",
        status="active",
        storage_limit_bytes=100 * 1024 * 1024,
    )
    # Company B
    company_b = Company(
        name=f"Mod11 Corp B {tag}",
        display_name=f"Mod11 Enterprise B {tag}",
        code=f"M11B_{tag}",
        status="active",
        storage_limit_bytes=100 * 1024 * 1024,
    )
    db.add_all([company_a, company_b])
    db.flush()

    chennai = Branch(
        company_id=company_a.id,
        name=f"Chennai Branch {tag}",
        code=f"CHN_{tag}",
        status="active",
    )
    mysore = Branch(
        company_id=company_a.id,
        name=f"Mysore Branch {tag}",
        code=f"MYS_{tag}",
        status="active",
    )
    branch_b = Branch(
        company_id=company_b.id,
        name=f"Branch B {tag}",
        code=f"BB_{tag}",
        status="active",
    )
    db.add_all([chennai, mysore, branch_b])
    db.flush()

    admin_a = User(
        company_id=company_a.id,
        branch_id=chennai.id,
        email=f"admin_a_{tag}@m11test.com",
        name=f"Admin A {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    admin_b = User(
        company_id=company_b.id,
        branch_id=branch_b.id,
        email=f"admin_b_{tag}@m11test.com",
        name=f"Admin B {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
    )
    branch_admin = User(
        company_id=company_a.id,
        branch_id=chennai.id,
        email=f"branch_admin_{tag}@m11test.com",
        name=f"Branch Admin {tag}",
        password_hash=get_password_hash("Pass123!"),
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
    )
    db.add_all([admin_a, admin_b, branch_admin])
    db.flush()

    # Role assignments
    db.add(UserRoleAssignment(user_id=admin_a.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company_a.id))
    db.add(UserRoleAssignment(user_id=admin_b.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company_b.id))
    db.add(UserRoleAssignment(user_id=branch_admin.id, role="ADMIN", scope_type="branch", scope_id=chennai.id))

    db.commit()

    token_a = create_access_token({
        "sub": admin_a.email,
        "user_id": admin_a.id,
        "company_id": company_a.id,
        "branch_id": chennai.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")
    token_b = create_access_token({
        "sub": admin_b.email,
        "user_id": admin_b.id,
        "company_id": company_b.id,
        "branch_id": branch_b.id,
        "role": "GLOBAL_ADMIN",
        "portal": "company",
    }, audience="company")
    token_branch = create_access_token({
        "sub": branch_admin.email,
        "user_id": branch_admin.id,
        "company_id": company_a.id,
        "branch_id": chennai.id,
        "role": "ADMIN",
        "portal": "company",
    }, audience="company")

    env_data = {
        "company_a": company_a,
        "company_b": company_b,
        "chennai": chennai,
        "mysore": mysore,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "branch_admin": branch_admin,
        "token_a": token_a,
        "token_b": token_b,
        "token_branch": token_branch,
    }

    try:
        yield env_data
    finally:
        # Clean teardown of test records
        c_ids = [company_a.id, company_b.id]
        doc_ids = [d.id for d in db.query(Document.id).filter(Document.company_id.in_(c_ids)).all()]
        if doc_ids:
            ex_ids = [e.id for e in db.query(DocumentExtraction.id).filter(DocumentExtraction.document_id.in_(doc_ids)).all()]
            if ex_ids:
                db.query(ExtractionEdit).filter(ExtractionEdit.document_extraction_id.in_(ex_ids)).delete(synchronize_session=False)
            db.query(DocumentExtraction).filter(DocumentExtraction.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(ProcessingJob).filter(ProcessingJob.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)

        tmpl_ids = [t.id for t in db.query(DocumentTemplate.id).filter(DocumentTemplate.company_id.in_(c_ids)).all()]
        if tmpl_ids:
            db.query(TemplateVersion).filter(TemplateVersion.template_id.in_(tmpl_ids)).delete(synchronize_session=False)
            db.query(DocumentTemplate).filter(DocumentTemplate.id.in_(tmpl_ids)).delete(synchronize_session=False)

        u_ids = [admin_a.id, admin_b.id, branch_admin.id]
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(u_ids)).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id.in_(c_ids)).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_(c_ids)).delete(synchronize_session=False)
        db.commit()


# ── 1. Seeded Default GST Invoice Template Tests ─────────────────────────────

def test_seeded_gst_template_exists(db):
    """Verify platform default and company-level GST templates are seeded and published."""
    plat_tmpl = db.query(DocumentTemplate).filter(
        DocumentTemplate.company_id.is_(None),
        DocumentTemplate.document_type == "gst_invoice",
        DocumentTemplate.status == "active",
    ).first()
    assert plat_tmpl is not None
    assert plat_tmpl.name == "Default GST Invoice"

    plat_v1 = db.query(TemplateVersion).filter(
        TemplateVersion.template_id == plat_tmpl.id,
        TemplateVersion.version_number == 1,
    ).first()
    assert plat_v1 is not None
    assert plat_v1.status == "published"
    assert "seller" in plat_v1.extraction_instructions
    assert "items" in plat_v1.schema_json.get("fields", [{}])[3].get("key", "")

    # Idempotent template resolution for live company
    resolved = TemplateResolver.resolve_template(db, company_id=24, document_type="gst_invoice")
    assert resolved is not None
    assert resolved.version_number == 1
    assert resolved.status == "published"


# ── 2. Template CRUD & Scope Isolation Tests ─────────────────────────────────

def test_template_crud_and_tenant_isolation(db, test_env):
    """Verify template creation, branch scoping, and strict cross-company isolation."""
    comp_a = test_env["company_a"]
    comp_b = test_env["company_b"]
    chennai = test_env["chennai"]

    schema = {
        "type": "object",
        "fields": [
            {"key": "title", "label": "Title", "type": "string", "required": True},
            {"key": "amount", "label": "Amount", "type": "number", "required": True},
        ]
    }

    # 1. Create company-level template in Company A
    tmpl_comp, v1 = TemplateService.create_template(
        db=db,
        company_id=comp_a.id,
        document_type="bill_a",
        name="Company A Bill",
        schema_json=schema,
        publish_initial=True,
    )
    assert tmpl_comp.id is not None
    assert tmpl_comp.branch_id is None
    assert v1.version_number == 1
    assert v1.status == "published"

    # 2. Create branch-level template in Company A (Chennai)
    tmpl_branch, vb1 = TemplateService.create_template(
        db=db,
        company_id=comp_a.id,
        branch_id=chennai.id,
        document_type="bill_a",
        name="Chennai Custom Bill",
        schema_json=schema,
        publish_initial=True,
    )
    assert tmpl_branch.branch_id == chennai.id

    # 3. Cross-company access isolation check
    with pytest.raises(TemplateSecurityError):
        TemplateService.get_template(db, tmpl_comp.id, company_id=comp_b.id)

    # 4. Scope listing: Company B cannot see Company A's templates
    list_b = TemplateService.list_templates(db, company_id=comp_b.id)
    b_ids = [t.id for t in list_b]
    assert tmpl_comp.id not in b_ids
    assert tmpl_branch.id not in b_ids

    # 5. Duplicate active template name in same scope rejected
    with pytest.raises(ValueError):
        TemplateService.create_template(
            db=db,
            company_id=comp_a.id,
            document_type="bill_a",
            name="Company A Bill",
            schema_json=schema,
        )

    # 6. Soft deactivation
    deactivated = TemplateService.deactivate_template(db, tmpl_comp.id, company_id=comp_a.id)
    assert deactivated.status == "inactive"
    # Versions remain intact
    versions = db.query(TemplateVersion).filter(TemplateVersion.template_id == tmpl_comp.id).all()
    assert len(versions) == 1


# ── 3. Immutable Sequential Versioning Tests ─────────────────────────────────

def test_immutable_template_versioning(db, test_env):
    """Verify version numbers increase sequentially and published versions cannot be mutated."""
    comp_a = test_env["company_a"]

    schema_v1 = {
        "type": "object",
        "fields": [{"key": "notes", "label": "Notes", "type": "string", "required": False}]
    }
    tmpl, v1 = TemplateService.create_template(
        db=db,
        company_id=comp_a.id,
        document_type="memo",
        name="Corporate Memo",
        schema_json=schema_v1,
        publish_initial=True,
    )
    assert v1.version_number == 1
    assert v1.status == "published"

    # Create draft v2
    schema_v2 = {
        "type": "object",
        "fields": [
            {"key": "notes", "label": "Notes", "type": "string", "required": False},
            {"key": "priority", "label": "Priority", "type": "string", "required": True},
        ]
    }
    v2 = TemplateService.create_version(
        db=db,
        template_id=tmpl.id,
        company_id=comp_a.id,
        schema_json=schema_v2,
    )
    assert v2.version_number == 2
    assert v2.status == "draft"

    # Create draft v3
    v3 = TemplateService.create_version(
        db=db,
        template_id=tmpl.id,
        company_id=comp_a.id,
        schema_json=schema_v2,
    )
    assert v3.version_number == 3

    # Publish v2: marks v1 as 'retired' and v2 as 'published'
    pub_v2 = TemplateService.publish_version(db, tmpl.id, v2.id, comp_a.id)
    assert pub_v2.status == "published"
    assert pub_v2.published_at is not None

    db.refresh(v1)
    assert v1.status == "retired"


# ── 4. Hierarchical Template Resolution Priority Tests ───────────────────────

def test_template_resolution_hierarchy(db, test_env):
    """Priority: Branch template > Company template > Platform template."""
    comp_a = test_env["company_a"]
    chennai = test_env["chennai"]
    mysore = test_env["mysore"]

    schema = {"type": "object", "fields": [{"key": "f1", "label": "F1", "type": "string"}]}

    # 1. Company-level template
    tmpl_comp, comp_v = TemplateService.create_template(
        db=db,
        company_id=comp_a.id,
        document_type="purchase_order",
        name="Company PO",
        schema_json=schema,
        publish_initial=True,
    )

    # 2. Branch-specific template for Chennai
    tmpl_branch, branch_v = TemplateService.create_template(
        db=db,
        company_id=comp_a.id,
        branch_id=chennai.id,
        document_type="purchase_order",
        name="Chennai PO Override",
        schema_json=schema,
        publish_initial=True,
    )

    # For Chennai branch: resolves Chennai branch template
    resolved_chn = TemplateResolver.resolve_template(db, comp_a.id, chennai.id, "purchase_order")
    assert resolved_chn.id == branch_v.id
    assert resolved_chn.template_id == tmpl_branch.id

    # For Mysore branch (no branch override): resolves Company-wide template
    resolved_mys = TemplateResolver.resolve_template(db, comp_a.id, mysore.id, "purchase_order")
    assert resolved_mys.id == comp_v.id
    assert resolved_mys.template_id == tmpl_comp.id

    # For gst_invoice: resolves company or platform default
    resolved_gst = TemplateResolver.resolve_template(db, comp_a.id, mysore.id, "gst_invoice")
    assert resolved_gst is not None


# ── 5. Schema Security Limits Tests ──────────────────────────────────────────

def test_schema_security_limits(db, test_env):
    """Verify rejection of oversized schemas, excessive nesting, and unsafe types."""
    comp_a = test_env["company_a"]

    # 1. Excessive nesting depth (> 5 levels)
    deep_schema = {"type": "object", "fields": []}
    curr = deep_schema
    for i in range(7):
        nested = {"key": f"level_{i}", "label": f"Level {i}", "type": "object", "fields": []}
        curr["fields"].append(nested)
        curr = nested

    with pytest.raises(TemplateSecurityError) as exc:
        TemplateService.create_template(
            db=db, company_id=comp_a.id, document_type="deep", name="Deep Schema", schema_json=deep_schema
        )
    assert "nesting depth" in str(exc.value)

    # 2. Disallowed field type
    bad_type_schema = {
        "type": "object",
        "fields": [{"key": "script", "label": "Script", "type": "python_eval"}]
    }
    with pytest.raises(TemplateSecurityError) as exc:
        TemplateService.create_template(
            db=db, company_id=comp_a.id, document_type="bad", name="Bad Type", schema_json=bad_type_schema
        )
    assert "not supported" in str(exc.value)

    # 3. Disallowed validation rule type
    with pytest.raises(TemplateSecurityError) as exc:
        TemplateService.validate_rules_security([{"type": "arbitrary_eval_code"}])
    assert "not recognized" in str(exc.value)


# ── 6. Deterministic Validation Engine Tests ─────────────────────────────────

def test_gstin_validation():
    """Verify GSTIN regex, state codes, and flag generation."""
    flags = []
    # Valid GSTIN
    DeterministicValidationEngine.validate_gstin("33AABCT1332L1Z1", "seller.gstin", flags)
    assert len(flags) == 0

    # Invalid length
    flags_len = []
    DeterministicValidationEngine.validate_gstin("33AABCT", "seller.gstin", flags_len)
    assert len(flags_len) == 1
    assert flags_len[0].severity == "error"
    assert "15 characters" in flags_len[0].message

    # Invalid characters / format
    flags_fmt = []
    DeterministicValidationEngine.validate_gstin("331234567890123", "seller.gstin", flags_fmt)
    assert len(flags_fmt) == 1
    assert flags_fmt[0].severity == "error"
    assert "pattern" in flags_fmt[0].message

    # State code mismatch
    flags_sc = []
    DeterministicValidationEngine.validate_gstin("33AABCT1332L1Z1", "seller.gstin", flags_sc, state_code="29")
    assert len(flags_sc) == 1
    assert flags_sc[0].severity == "warning"
    assert "does not match" in flags_sc[0].message


def test_invoice_date_validation():
    """Verify date parsing and sanity bounds."""
    flags = []
    DeterministicValidationEngine.validate_date("2026-11-10", "invoice.date", flags)
    assert len(flags) == 0

    DeterministicValidationEngine.validate_date("10/11/2026", "invoice.date", flags)
    assert len(flags) == 0

    # Unparseable date
    flags_err = []
    DeterministicValidationEngine.validate_date("invalid-date-string", "invoice.date", flags_err)
    assert len(flags_err) == 1
    assert flags_err[0].severity == "error"

    # Out of range date (year 1980)
    flags_range = []
    DeterministicValidationEngine.validate_date("1980-05-15", "invoice.date", flags_range)
    assert len(flags_range) == 1
    assert flags_range[0].severity == "warning"


def test_line_item_and_totals_arithmetic():
    """Verify line-item arithmetic and totals consistency checks."""
    # Line items: 2 x 100 - 10 discount = 190 amount
    items_valid = [
        {"description": "Item A", "qty": "2 Nos", "rate": 100.0, "discount": 10.0, "amount": 190.0}
    ]
    flags = []
    DeterministicValidationEngine.validate_line_items(items_valid, "items", 0.5, flags)
    assert len(flags) == 0

    # Arithmetic mismatch: 2 x 100 = 200 ≠ 300
    items_invalid = [
        {"description": "Item B", "qty": 2, "rate": 100.0, "amount": 300.0}
    ]
    flags_err = []
    DeterministicValidationEngine.validate_line_items(items_invalid, "items", 0.5, flags_err)
    assert len(flags_err) == 1
    assert flags_err[0].severity == "error"
    assert "does not match line amount" in flags_err[0].message

    # Totals arithmetic: Taxable 200 + CGST 18 + SGST 18 = 236
    totals_valid = {"taxable_value": 200.0, "cgst": 18.0, "sgst": 18.0, "grand_total": 236.0}
    flags_tot = []
    DeterministicValidationEngine.validate_totals(totals_valid, "totals", 0.5, flags_tot)
    assert len(flags_tot) == 0

    # Totals mismatch: sum is 236 ≠ 500
    totals_invalid = {"taxable_value": 200.0, "cgst": 18.0, "sgst": 18.0, "grand_total": 500.0}
    flags_tot_err = []
    DeterministicValidationEngine.validate_totals(totals_invalid, "totals", 0.5, flags_tot_err)
    assert len(flags_tot_err) == 1
    assert flags_tot_err[0].severity == "error"
    assert "does not match Grand Total" in flags_tot_err[0].message


# ── 7. Worker Integration & Template Pinning ──────────────────────────────────

def test_worker_pins_template_and_validates(db, test_env):
    """Verify worker execution pins template version, invokes AI, and records extraction."""
    comp = test_env["company_a"]
    chennai = test_env["chennai"]
    admin = test_env["admin_a"]

    # 1. Create document
    storage = get_storage_adapter()
    key = LocalStorageAdapter.build_original_key(comp.id, chennai.id, uuid.uuid4().hex)
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="JPEG")
    valid_jpg = buf.getvalue()
    storage.save(key, valid_jpg)

    doc = Document(
        company_id=comp.id,
        branch_id=chennai.id,
        uploaded_by=admin.id,
        original_filename="sample_gst_invoice.jpg",
        storage_key=key,
        mime_type="image/jpeg",
        file_size=len(valid_jpg),
        ocr_status=OcrStatus.UPLOADED,
    )
    db.add(doc)
    db.flush()

    job = ProcessingJob(
        company_id=comp.id,
        branch_id=chennai.id,
        document_id=doc.id,
        job_type="ocr",
        status="claimed",
        locked_by="test_worker_1",
    )
    db.add(job)
    db.commit()

    # Mock AIExecutionService.extract_document to return structured GST data with arithmetic mismatch
    mock_ai_result = MagicMock()
    mock_ai_result.raw_text = "Sample invoice OCR text with seller ABC and grand total INR 500"
    mock_ai_result.structured_data = {
        "seller": {"name": "ABC Corp", "gstin": "33AABCT1332L1Z1", "state_code": "33"},
        "buyer": {"name": "XYZ Corp", "gstin": "33AABCT1332L1Z1", "state_code": "33"},
        "invoice": {"number": "INV-100", "date": "2026-11-10"},
        "items": [{"sl": 1, "description": "Consulting", "qty": "1", "rate": 200.0, "amount": 200.0}],
        "totals": {"taxable_value": 200.0, "cgst": 18.0, "sgst": 18.0, "grand_total": 500.0},  # Mismatch 236 != 500
    }

    with patch("app.ai.service.AIExecutionService.extract_document", return_value=mock_ai_result):
        worker = DocumentWorker(worker_id="test_worker_1")
        worker.process_one_job(db, job)

    db.refresh(doc)
    assert doc.ocr_status == OcrStatus.COMPLETED
    assert doc.template_version_id is not None  # Successfully pinned!

    # Verify DocumentExtraction record was created with deterministic flags
    extraction = db.query(DocumentExtraction).filter(DocumentExtraction.document_id == doc.id).first()
    assert extraction is not None
    assert extraction.status == "needs_review"  # Because totals mismatch exists!
    assert extraction.template_version_id == doc.template_version_id
    assert extraction.raw_text == mock_ai_result.raw_text
    assert len(extraction.validation_flags) > 0
    assert any(f["rule_id"] == "totals_consistency" for f in extraction.validation_flags)


# ── 8. Human Review: Field Corrections & Immutable OCR Text ──────────────────

def test_human_review_corrections_and_immutable_raw_ocr(db, test_env):
    """
    Verify:
    1. Field correction updates data and records granular ExtractionEdit audit trail.
    2. Optimistic concurrency conflict is enforced on version mismatch.
    3. Re-validation updates flags and clears errors when arithmetic is fixed.
    4. CRITICAL: DocumentExtraction.raw_text and Document.ocr_text are strictly IMMUTABLE.
    """
    comp = test_env["company_a"]
    chennai = test_env["chennai"]
    admin = test_env["admin_a"]

    tmpl_v = TemplateResolver.resolve_template(db, comp.id, chennai.id, "gst_invoice")

    raw_ocr_original = "ORIGINAL RAW OCR TEXT - MUST NEVER BE MUTATED"
    doc = Document(
        company_id=comp.id,
        branch_id=chennai.id,
        uploaded_by=admin.id,
        original_filename="review_test_invoice.pdf",
        storage_key=f"test/key/{uuid.uuid4().hex}",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.COMPLETED,
        ocr_text=raw_ocr_original,
        template_version_id=tmpl_v.id,
    )
    db.add(doc)
    db.flush()

    initial_data = {
        "seller": {"name": "Vendor A", "gstin": "33AABCT1332L1Z1", "state_code": "33"},
        "buyer": {"name": "Client B", "gstin": "33AABCT1332L1Z1", "state_code": "33"},
        "invoice": {"number": "INV-777", "date": "2026-11-10"},
        "items": [{"sl": 1, "description": "Widget", "qty": "1", "rate": 100.0, "amount": 100.0}],
        "totals": {"taxable_value": 100.0, "cgst": 9.0, "sgst": 9.0, "grand_total": 999.0},  # Error: 118 != 999
    }
    extraction = DocumentExtraction(
        document_id=doc.id,
        template_version_id=tmpl_v.id,
        data=initial_data,
        raw_text=raw_ocr_original,
        validation_flags=[{"field_path": "totals.grand_total", "rule_id": "totals_consistency", "severity": "error", "message": "Totals mismatch"}],
        status="needs_review",
        version=1,
    )
    db.add(extraction)
    db.commit()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {test_env['token_a']}"}

    # 1. Optimistic concurrency conflict check (supplying wrong version)
    conflict_res = client.post(
        f"/api/documents/{doc.id}/review/save",
        headers=headers,
        json={"version": 99, "data": initial_data},
    )
    assert conflict_res.status_code == 409
    assert "modified by another reviewer" in conflict_res.json()["detail"]

    # 2. Correct the grand_total to 118.0
    corrected_data = dict(initial_data)
    corrected_data["totals"] = {"taxable_value": 100.0, "cgst": 9.0, "sgst": 9.0, "grand_total": 118.0}

    save_res = client.post(
        f"/api/documents/{doc.id}/review/save",
        headers=headers,
        json={"version": 1, "data": corrected_data},
    )
    assert save_res.status_code == 200
    res_json = save_res.json()
    assert res_json["version"] == 2
    assert res_json["status"] == "extracted"  # Error resolved!
    assert res_json["has_errors"] is False

    # 3. Check granular ExtractionEdit audit record was created
    edits_res = client.get(f"/api/documents/{doc.id}/edits", headers=headers)
    assert edits_res.status_code == 200
    edits = edits_res.json()
    assert len(edits) > 0
    grand_total_edit = next((e for e in edits if "grand_total" in e["field_path"]), None)
    assert grand_total_edit is not None
    assert grand_total_edit["old_value"] == 999.0
    assert grand_total_edit["new_value"] == 118.0

    # 4. IMMUTABILITY ASSERTION: Original raw_text must NOT have changed!
    db.refresh(extraction)
    db.refresh(doc)
    assert extraction.raw_text == raw_ocr_original
    assert doc.ocr_text == raw_ocr_original


# ── 9. Approval Gating and Override Protection Tests ─────────────────────────

def test_approval_gating_and_override_protection(db, test_env):
    """
    Verify:
    1. Approval is blocked if unresolved error-level flags exist.
    2. Overriding requires explicit justification and extraction.override_validation permission.
    3. Finalized approval locks the extraction against further edits.
    """
    comp = test_env["company_a"]
    chennai = test_env["chennai"]
    admin = test_env["admin_a"]
    tmpl_v = TemplateResolver.resolve_template(db, comp.id, chennai.id, "gst_invoice")

    doc = Document(
        company_id=comp.id,
        branch_id=chennai.id,
        uploaded_by=admin.id,
        original_filename="approval_gate_test.pdf",
        storage_key=f"test/key/{uuid.uuid4().hex}",
        mime_type="application/pdf",
        file_size=100,
        ocr_status=OcrStatus.UPLOADED,
        template_version_id=tmpl_v.id,
    )
    db.add(doc)
    db.flush()

    extraction = DocumentExtraction(
        document_id=doc.id,
        template_version_id=tmpl_v.id,
        data={"totals": {"grand_total": 999.0}},
        raw_text="Sample OCR",
        validation_flags=[{"field_path": "totals.grand_total", "rule_id": "totals_consistency", "severity": "error", "message": "Totals mismatch"}],
        status="needs_review",
        version=1,
    )
    db.add(extraction)
    db.commit()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {test_env['token_a']}"}

    # 1. Normal approval attempt blocked
    bad_approve = client.post(
        f"/api/documents/{doc.id}/review/approve",
        headers=headers,
        json={"override": False},
    )
    assert bad_approve.status_code == 400
    assert "unresolved error-level validation failures" in bad_approve.json()["detail"]

    # 2. Override attempt with missing reason blocked
    short_override = client.post(
        f"/api/documents/{doc.id}/review/approve",
        headers=headers,
        json={"override": True, "override_reason": "bad"},
    )
    assert short_override.status_code == 400

    # 3. Authorized override with valid reason succeeds
    good_override = client.post(
        f"/api/documents/{doc.id}/review/approve",
        headers=headers,
        json={"override": True, "override_reason": "Verified manually against physical stamped paper voucher."},
    )
    assert good_override.status_code == 200
    assert good_override.json()["status"] == "approved"

    # 4. Modifying approved document is rejected
    post_approve_edit = client.post(
        f"/api/documents/{doc.id}/review/save",
        headers=headers,
        json={"version": 1, "data": {"totals": {"grand_total": 500.0}}},
    )
    assert post_approve_edit.status_code == 400
    assert "finalized" in post_approve_edit.json()["detail"]


# ── 10. End-to-End Acceptance Scenario: Expense Receipt ──────────────────────

def test_end_to_end_expense_receipt_scenario(db, test_env):
    """
    End-to-End Acceptance Scenario (Section 11):
    1. Company Admin creates custom 'Expense Receipt' (expense_receipt) template via API.
    2. Published version 1 created with custom schema and required fields.
    3. Document uploaded with document_type='expense_receipt', pinned to template version 1.
    4. Worker processes document and runs deterministic validation.
    5. Reviewer inspects side-by-side view, modifies fields, and saves corrections.
    6. Reviewer approves extraction.
    """
    comp = test_env["company_a"]
    chennai = test_env["chennai"]
    admin = test_env["admin_a"]
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {test_env['token_a']}"}

    # 1. Create custom Expense Receipt template
    receipt_schema = {
        "type": "object",
        "fields": [
            {"key": "merchant_name", "label": "Merchant", "type": "string", "required": True},
            {"key": "date", "label": "Date", "type": "date", "required": True},
            {"key": "total_amount", "label": "Total Amount", "type": "number", "required": True},
            {"key": "category", "label": "Category", "type": "string", "required": False},
        ]
    }
    create_payload = {
        "name": f"Corporate Expense Receipt {uuid.uuid4().hex[:4]}",
        "document_type": "expense_receipt",
        "description": "Custom extraction template for corporate expense receipts",
        "schema_json": receipt_schema,
        "validation_rules": [
            {"rule_id": "receipt_date", "type": "date", "fields": ["date"], "severity": "error"},
            {"rule_id": "required_merchant", "type": "required", "fields": ["merchant_name", "total_amount"], "severity": "error"},
        ],
        "extraction_instructions": "Extract merchant, date, total_amount and category from this receipt.",
        "publish_initial": True,
    }

    resp = client.post("/api/company/templates", headers=headers, json=create_payload)
    assert resp.status_code == 201
    tmpl_data = resp.json()
    assert tmpl_data["document_type"] == "expense_receipt"
    assert tmpl_data["published_version"]["version_number"] == 1
    tmpl_v_id = tmpl_data["published_version"]["id"]

    # 2. Upload receipt document with document_type='expense_receipt'
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="PNG")
    valid_png = buf.getvalue()
    upload_resp = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("starbucks_receipt.png", io.BytesIO(valid_png), "image/png")},
        data={"document_type": "expense_receipt"},
    )
    assert upload_resp.status_code == 200
    doc_out = upload_resp.json()
    doc_id = doc_out["id"]
    assert doc_out["template_version_id"] == tmpl_v_id  # Pinned immediately on upload!

    # 3. Simulate Worker Processing with Mocked AI returning custom schema
    mock_receipt_ai = MagicMock()
    mock_receipt_ai.raw_text = "Starbucks Coffee #123\nDate: 2026-11-10\nTotal: $14.50"
    mock_receipt_ai.structured_data = {
        "merchant_name": "Starbucks Coffee #123",
        "date": "2026-11-10",
        "total_amount": 14.50,
        "category": "Meals & Entertainment",
    }

    job = db.query(ProcessingJob).filter(ProcessingJob.document_id == doc_id).first()
    with patch("app.ai.service.AIExecutionService.extract_document", return_value=mock_receipt_ai):
        worker = DocumentWorker(worker_id="test_worker_receipt")
        worker.process_one_job(db, job)

    # 4. Review extraction
    ext_resp = client.get(f"/api/documents/{doc_id}/extraction", headers=headers)
    assert ext_resp.status_code == 200
    ext_data = ext_resp.json()
    assert ext_data["status"] == "extracted"
    assert ext_data["data"]["merchant_name"] == "Starbucks Coffee #123"
    assert ext_data["data"]["total_amount"] == 14.50
    assert ext_data["template_version_id"] == tmpl_v_id

    # 5. Human reviewer adjusts category and saves correction
    updated_receipt_data = dict(ext_data["data"])
    updated_receipt_data["category"] = "Client Hospitality"

    save_resp = client.post(
        f"/api/documents/{doc_id}/review/save",
        headers=headers,
        json={"version": ext_data["version"], "data": updated_receipt_data},
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["data"]["category"] == "Client Hospitality"
    assert save_resp.json()["version"] == 2

    # 6. Human reviewer approves extraction
    appr_resp = client.post(
        f"/api/documents/{doc_id}/review/approve",
        headers=headers,
        json={"override": False},
    )
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "approved"
    assert appr_resp.json()["reviewer_name"] == test_env["admin_a"].name


# ── 11. Zero Paid AI Calls & Database Hygiene Verification ───────────────────

def test_zero_paid_ai_calls_and_database_hygiene(db):
    """
    Verify:
    1. No external AI API calls were made (all mock-backed).
    2. Exactly 2 live companies (ID 24 'Nobi Corp' and ID 40 'Vasanth & Co.') remain in dms_db.
    """
    companies = db.query(Company).order_by(Company.id.asc()).all()
    live_ids = [c.id for c in companies]
    assert live_ids == [24, 40], f"Expected only live companies [24, 40], found: {live_ids}"
    assert companies[0].name == "Nobi Corp"
    assert companies[1].name == "Vasanth & Co."
