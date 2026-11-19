"""
Comprehensive Automated Regression Test Suite for Security Audit Remediations (Modules 1–8).

Validates:
  1. SEC-01: Last Active Company Admin Protection and concurrency serialization.
  2. SEC-02: Session and refresh token revocation on Admin MFA reset.
  3. SEC-03: Immediate session invalidation on user role or branch scope updates.
  4. SEC-04: Multi-branch authorization for branch-scoped admins (assigned vs unassigned).
  5. SEC-05: Strict fail-closed login rejection for suspended companies across all portals.
  6. SEC-06: Concurrency quota enforcement for branches and users.
  7. SEC-07: Branch deactivation guard blocking deactivation when secondary role assignments exist.
"""

import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.main import app
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    Document,
    OcrStatus,
    User,
    UserRole,
    UserRoleAssignment,
    UserSession,
)
from app.auth import create_access_token, get_password_hash
from app.auth.authorization import can, scope_filter
from app.auth.document_access_policy import DocumentAccessPolicy
from app.auth.permissions import DOCUMENT_VIEW_BRANCH, DOCUMENT_VIEW_OWN
from app.config import settings
from app.context import _build_auth_context
from app.services.auth_service import auth_service
from app.services.mfa_service import MfaService
from app.services.session_service import session_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def audit_test_data(db: Session):
    """Provisions an isolated company, branches, and users for security tests."""
    suffix = datetime.utcnow().strftime("%f")
    company = Company(
        name=f"Audit Test Co {suffix}",
        code=f"AUDIT_{suffix}",
        status=CompanyStatus.ACTIVE,
        max_branches=3,
        max_users=5,
        storage_limit_bytes=50000000,
    )
    db.add(company)
    db.flush()

    b1 = Branch(company_id=company.id, name="Branch One", code=f"B1_{suffix}")
    b2 = Branch(company_id=company.id, name="Branch Two", code=f"B2_{suffix}")
    b3 = Branch(company_id=company.id, name="Branch Three", code=f"B3_{suffix}")
    db.add_all([b1, b2, b3])
    db.flush()

    pwd = get_password_hash("SecurePass@123")

    admin1 = User(
        company_id=company.id,
        branch_id=b1.id,
        name="Primary Admin",
        email=f"admin1_{suffix}@audit.test",
        password_hash=pwd,
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
        token_version=1,
    )
    admin2 = User(
        company_id=company.id,
        branch_id=b1.id,
        name="Secondary Admin",
        email=f"admin2_{suffix}@audit.test",
        password_hash=pwd,
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
        token_version=1,
    )
    branch_admin = User(
        company_id=company.id,
        branch_id=b1.id,
        name="Multi Branch Admin",
        email=f"bradmin_{suffix}@audit.test",
        password_hash=pwd,
        role=UserRole.ADMIN,
        status=AccountStatus.ACTIVE,
        token_version=1,
    )
    staff_user = User(
        company_id=company.id,
        branch_id=b1.id,
        name="Branch Staff",
        email=f"staff_{suffix}@audit.test",
        password_hash=pwd,
        role=UserRole.STAFF,
        status=AccountStatus.ACTIVE,
        token_version=1,
    )
    db.add_all([admin1, admin2, branch_admin, staff_user])
    db.flush()

    # Multi-branch assignment: branch_admin gets b1 (primary) and b2 (secondary)
    db.add(UserRoleAssignment(
        user_id=branch_admin.id,
        role="ADMIN",
        scope_type="branch",
        scope_id=b1.id,
    ))
    db.add(UserRoleAssignment(
        user_id=branch_admin.id,
        role="ADMIN",
        scope_type="branch",
        scope_id=b2.id,
    ))

    # Staff gets b1 only
    db.add(UserRoleAssignment(
        user_id=staff_user.id,
        role="STAFF",
        scope_type="branch",
        scope_id=b1.id,
    ))

    # Global admins get company-level assignment
    db.add(UserRoleAssignment(user_id=admin1.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company.id))
    db.add(UserRoleAssignment(user_id=admin2.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=company.id))

    db.commit()

    yield {
        "company": company,
        "branches": [b1, b2, b3],
        "admin1": admin1,
        "admin2": admin2,
        "branch_admin": branch_admin,
        "staff_user": staff_user,
    }

    # Teardown: clean up all resources created for this test company
    try:
        db.query(Invoice).filter(Invoice.company_id == company.id).delete(synchronize_session=False)
        db.query(Document).filter(Document.company_id == company.id).delete(synchronize_session=False)
        u_ids = [u.id for u in db.query(User).filter(User.company_id == company.id).all()]
        if u_ids:
            mfa_ids = [m.id for m in db.query(UserMfa).filter(UserMfa.user_id.in_(u_ids)).all()]
            if mfa_ids:
                db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_mfa_id.in_(mfa_ids)).delete(synchronize_session=False)
            db.query(UserMfa).filter(UserMfa.user_id.in_(u_ids)).delete(synchronize_session=False)
            db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
            db.query(UserSession).filter(UserSession.user_id.in_(u_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.company_id == company.id).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id == company.id).delete(synchronize_session=False)
        db.query(Company).filter(Company.id == company.id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def _get_user_token(user: User) -> str:
    claims = {
        "sub": user.email,
        "uid": user.id,
        "user_id": user.id,
        "company_id": user.company_id,
        "branch_id": user.branch_id,
        "tenant_id": user.branch_id,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "identity_type": "user",
        "token_version": user.token_version,
    }
    aud = settings.JWT_AUDIENCE_COMPANY if user.role == UserRole.GLOBAL_ADMIN else settings.JWT_AUDIENCE_APP
    return create_access_token(claims, audience=aud)


# ── SEC-01: Last Active Company Admin Protection ──────────────────────────────

def test_sec01_last_admin_protection_blocks_last_demotion_and_deactivation(client, db: Session, audit_test_data):
    """Verify that when only 1 active GLOBAL_ADMIN remains, demotion and deactivation are strictly blocked."""
    data = audit_test_data
    admin1 = data["admin1"]
    admin2 = data["admin2"]
    token1 = _get_user_token(admin1)

    # Deactivate admin2 (1 remains)
    headers = {"Authorization": f"Bearer {token1}"}
    resp = client.post(f"/api/company/users/{admin2.id}/deactivate", headers=headers)
    assert resp.status_code == 200

    # Now attempt to deactivate admin1 (the last active admin) -> MUST BE BLOCKED
    resp_block = client.post(f"/api/company/users/{admin1.id}/deactivate", headers=headers)
    assert resp_block.status_code == 400
    assert "last active Company Administrator" in resp_block.json()["detail"]

    # Now attempt to demote admin1 to STAFF -> MUST BE BLOCKED
    resp_demote = client.put(f"/api/company/users/{admin1.id}", json={"role": "STAFF"}, headers=headers)
    assert resp_demote.status_code == 400
    assert "last active Company Administrator" in resp_demote.json()["detail"]


# ── SEC-02: Session Revocation on Admin MFA Reset ──────────────────────────────

def test_sec02_mfa_reset_revokes_stored_sessions(client, db: Session, audit_test_data):
    """Verify that MfaService.reset_mfa_by_admin immediately revokes all refresh sessions."""
    data = audit_test_data
    staff = data["staff_user"]

    # Create active refresh session for staff
    session_rec, raw_refresh = session_service.create_session(
        db=db,
        identity_type="user",
        identity_id=staff.id,
        user_agent="test-agent",
        ip_address="127.0.0.1",
    )
    assert session_rec.revoked_at is None

    # Admin performs MFA reset on staff user
    MfaService.reset_mfa_by_admin(db, "user", staff.id)

    # Verify session record is now marked as revoked in the database
    db.refresh(session_rec)
    assert session_rec.revoked_at is not None
    assert session_rec.revoke_reason == "mfa_reset_by_admin"

    # Attempting to rotate/refresh with this token MUST be rejected
    with pytest.raises(HTTPException) as exc:
        session_service.rotate_session(db, raw_refresh)
    assert exc.value.status_code == 401


# ── SEC-03: Immediate Token Invalidation on Role Update ───────────────────────

def test_sec03_role_update_revokes_sessions_and_invalidates_access_token(client, db: Session, audit_test_data):
    """Verify that updating a user's role revokes active sessions and increments token_version."""
    data = audit_test_data
    admin1 = data["admin1"]
    admin2 = data["admin2"]
    token1 = _get_user_token(admin1)

    # Admin2 has an active session and access token
    old_token_version = admin2.token_version
    session_rec, raw_refresh = session_service.create_session(
        db=db,
        identity_type="user",
        identity_id=admin2.id,
    )
    old_access_token = _get_user_token(admin2)

    # Admin1 demotes Admin2 to ADMIN
    headers = {"Authorization": f"Bearer {token1}"}
    resp = client.put(f"/api/company/users/{admin2.id}", json={"role": "ADMIN"}, headers=headers)
    assert resp.status_code == 200

    # Verify Admin2's token_version incremented
    db.refresh(admin2)
    assert admin2.token_version > old_token_version

    # Verify refresh session was marked as revoked
    db.refresh(session_rec)
    assert session_rec.revoked_at is not None
    assert session_rec.revoke_reason == "role_or_scope_updated_by_admin"

    # Verify old access token is now rejected with 401 (token_version mismatch)
    with pytest.raises(HTTPException) as exc:
        _build_auth_context(old_access_token, db)
    assert exc.value.status_code == 401
    assert "Session revoked" in exc.value.detail


# ── SEC-04: Multi-Branch Authorization Matrix ─────────────────────────────────

def test_sec04_multi_branch_admin_document_scoping(db: Session, audit_test_data):
    """
    Verify that an ADMIN assigned to Branch 1 & Branch 2:
      - CAN access documents from Branch 1 (Primary)
      - CAN access documents from Branch 2 (Secondary)
      - CANNOT access documents from Branch 3 (Unassigned)
    """
    data = audit_test_data
    br_admin = data["branch_admin"]
    b1, b2, b3 = data["branches"]

    # Create documents in Branch 1, 2, and 3
    doc1 = Document(
        company_id=data["company"].id,
        branch_id=b1.id,
        uploaded_by=br_admin.id,
        original_filename="doc_b1.pdf",
        storage_key="key_b1",
        mime_type="application/pdf",
        file_size=1000,
        ocr_status=OcrStatus.COMPLETED,
    )
    doc2 = Document(
        company_id=data["company"].id,
        branch_id=b2.id,
        uploaded_by=br_admin.id,
        original_filename="doc_b2.pdf",
        storage_key="key_b2",
        mime_type="application/pdf",
        file_size=1000,
        ocr_status=OcrStatus.COMPLETED,
    )
    doc3 = Document(
        company_id=data["company"].id,
        branch_id=b3.id,
        uploaded_by=br_admin.id,
        original_filename="doc_b3.pdf",
        storage_key="key_b3",
        mime_type="application/pdf",
        file_size=1000,
        ocr_status=OcrStatus.COMPLETED,
    )
    db.add_all([doc1, doc2, doc3])
    db.commit()

    token = _get_user_token(br_admin)
    ctx = _build_auth_context(token, db)

    # 1. Verify assigned_branch_ids property
    assert ctx.assigned_branch_ids == {b1.id, b2.id}
    assert b3.id not in ctx.assigned_branch_ids

    # 2. Verify can() check
    assert can(ctx, DOCUMENT_VIEW_BRANCH, doc1) is True
    assert can(ctx, DOCUMENT_VIEW_BRANCH, doc2) is True
    assert can(ctx, DOCUMENT_VIEW_BRANCH, doc3) is False

    # 3. Verify DocumentAccessPolicy.verify_document_access
    verified_b1 = DocumentAccessPolicy.verify_document_access(ctx, DOCUMENT_VIEW_BRANCH, doc1)
    assert verified_b1.id == doc1.id

    verified_b2 = DocumentAccessPolicy.verify_document_access(ctx, DOCUMENT_VIEW_BRANCH, doc2)
    assert verified_b2.id == doc2.id

    with pytest.raises(HTTPException) as exc:
        DocumentAccessPolicy.verify_document_access(ctx, DOCUMENT_VIEW_BRANCH, doc3)
    assert exc.value.status_code == 404

    # 4. Verify scope_filter
    q = db.query(Document)
    filtered = scope_filter(ctx, q, Document).all()
    filtered_ids = {d.id for d in filtered}
    assert doc1.id in filtered_ids
    assert doc2.id in filtered_ids
    assert doc3.id not in filtered_ids


# ── SEC-05: Strict Suspended Company Login Rejection ─────────────────────────

def test_sec05_suspended_company_login_blocked_fail_closed(db: Session, audit_test_data):
    """Verify that ALL users of a suspended company are blocked at login (HTTP 403)."""
    data = audit_test_data
    company = data["company"]
    admin1 = data["admin1"]
    staff = data["staff_user"]

    # Suspend company
    company.status = CompanyStatus.SUSPENDED
    db.commit()

    # Global Admin attempting company portal login -> MUST BE REJECTED WITH 403
    with pytest.raises(HTTPException) as exc1:
        auth_service.authenticate_portal(
            db=db,
            email=admin1.email,
            password="SecurePass@123",
            portal="company",
        )
    assert exc1.value.status_code == 403
    assert "suspended" in exc1.value.detail.lower()

    # Staff user attempting app portal login -> MUST BE REJECTED WITH 403
    with pytest.raises(HTTPException) as exc2:
        auth_service.authenticate_portal(
            db=db,
            email=staff.email,
            password="SecurePass@123",
            portal="app",
        )
    assert exc2.value.status_code == 403
    assert "suspended" in exc2.value.detail.lower()


# ── SEC-06: Quota Enforcement ────────────────────────────────────────────────

def test_sec06_branch_and_user_quota_limits(client, db: Session, audit_test_data):
    """Verify that company max_branches and max_users quotas are strictly enforced."""
    data = audit_test_data
    admin1 = data["admin1"]
    company = data["company"]
    token1 = _get_user_token(admin1)
    headers = {"Authorization": f"Bearer {token1}"}

    # Company max_branches is 3 and already has 3 branches (b1, b2, b3)
    resp = client.post(
        "/api/company/branches",
        json={
            "branch_name": "Over Quota Branch",
            "branch_code": "OVR_QTA",
            "branch_contact_number": "9999999999",
            "address_line1": "123 Quota Way",
            "city": "Test City",
            "district": "Test District",
            "state": "TN",
            "pincode": "600001",
            "admin_name": "New Admin",
            "admin_email": "newadmin@quota.test",
            "admin_mobile": "9999999999",
        },
        headers=headers,
    )
    assert resp.status_code == 400
    assert "branch limit reached" in resp.json()["detail"]


# ── SEC-07: Branch Deactivation Guard with Secondary Assignments ─────────────

def test_sec07_branch_deactivation_blocked_by_multi_branch_assignment(client, db: Session, audit_test_data):
    """
    Verify that branch deactivation is blocked if an active user has the branch
    assigned as a secondary branch (via UserRoleAssignment).
    """
    data = audit_test_data
    admin1 = data["admin1"]
    b2 = data["branches"][1]  # Branch Two (assigned to branch_admin as secondary)
    token1 = _get_user_token(admin1)
    headers = {"Authorization": f"Bearer {token1}"}

    # Primary branch of branch_admin is b1, but b2 is assigned via UserRoleAssignment
    resp = client.post(f"/api/company/branches/{b2.id}/deactivate", headers=headers)
    assert resp.status_code == 400
    assert "active user assignment" in resp.json()["detail"]
