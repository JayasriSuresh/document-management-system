"""
Module 8 Integration and Security Test Suite:
Company Admin Portal (Branches, Users, Roles, Multi-Branch, Security, Archive, Audit, Quotas).
"""

import io
import uuid
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.auth.role_permissions import ROLE_GLOBAL_ADMIN, ROLE_ADMIN, ROLE_STAFF, ROLE_MASTER_ADMIN
from app.models import (
    AccountStatus,
    AuditLog,
    Branch,
    Company,
    CompanyStatus,
    Document,
    Invitation,
    User,
    UserRole,
    UserRoleAssignment,
    UserSession,
)


@pytest.fixture
def test_setup(db: Session, client: TestClient):
    """
    Sets up two isolated companies for testing with unique tenant codes.
    """
    uid = uuid.uuid4().hex[:6]
    pwd = get_password_hash("Pasword@123")

    # Company A
    comp_a = Company(
        name=f"Alpha Corp {uid}",
        code=f"ALPHA_{uid}",
        status=CompanyStatus.ACTIVE,
        max_branches=3,
        max_users=4,
        storage_limit_bytes=5368709120,
        monthly_ai_budget_cents=5000,
        mfa_required_for_all=False,
    )
    db.add(comp_a)
    db.flush()

    branch_a1 = Branch(company_id=comp_a.id, name=f"Alpha HQ {uid}", code=f"AHQ_{uid}", status="active")
    branch_a2 = Branch(company_id=comp_a.id, name=f"Alpha B2 {uid}", code=f"AB2_{uid}", status="active")
    db.add_all([branch_a1, branch_a2])
    db.flush()

    admin_a = User(
        company_id=comp_a.id, branch_id=branch_a1.id, name="Alice Admin",
        email=f"alice_{uid}@alpha.test", password_hash=pwd, role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE, token_version=1,
    )
    admin_a2 = User(
        company_id=comp_a.id, branch_id=branch_a1.id, name="Aaron Admin",
        email=f"aaron_{uid}@alpha.test", password_hash=pwd, role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE, token_version=1,
    )
    staff_a = User(
        company_id=comp_a.id, branch_id=branch_a1.id, name="Alan Staff",
        email=f"alan_{uid}@alpha.test", password_hash=pwd, role=UserRole.STAFF,
        status=AccountStatus.ACTIVE, token_version=1,
    )
    db.add_all([admin_a, admin_a2, staff_a])
    db.flush()

    db.add(UserRoleAssignment(user_id=admin_a.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_a.id))
    db.add(UserRoleAssignment(user_id=admin_a2.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_a.id))
    db.add(UserRoleAssignment(user_id=staff_a.id, role="STAFF", scope_type="branch", scope_id=branch_a1.id))

    # Company B
    comp_b = Company(
        name=f"Beta Ltd {uid}",
        code=f"BETA_{uid}",
        status=CompanyStatus.ACTIVE,
        max_branches=2,
        max_users=3,
        storage_limit_bytes=5368709120,
        monthly_ai_budget_cents=5000,
        mfa_required_for_all=False,
    )
    db.add(comp_b)
    db.flush()

    branch_b1 = Branch(company_id=comp_b.id, name=f"Beta HQ {uid}", code=f"BHQ_{uid}", status="active")
    db.add(branch_b1)
    db.flush()

    admin_b = User(
        company_id=comp_b.id, branch_id=branch_b1.id, name="Bob Admin",
        email=f"bob_{uid}@beta.test", password_hash=pwd, role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE, token_version=1,
    )
    db.add(admin_b)
    db.flush()
    db.add(UserRoleAssignment(user_id=admin_b.id, role="GLOBAL_ADMIN", scope_type="company", scope_id=comp_b.id))

    db.commit()

    # Login tokens
    resp_a = client.post("/api/auth/login", json={"email": admin_a.email, "password": "Pasword@123", "portal": "company"})
    token_a = resp_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_b = client.post("/api/auth/login", json={"email": admin_b.email, "password": "Pasword@123", "portal": "company"})
    token_b = resp_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp_staff = client.post("/api/auth/login", json={"email": staff_a.email, "password": "Pasword@123", "portal": "app"})
    token_staff = resp_staff.json()["access_token"]
    headers_staff = {"Authorization": f"Bearer {token_staff}"}

    setup_data = {
        "uid": uid,
        "comp_a": comp_a,
        "comp_b": comp_b,
        "branch_a1": branch_a1,
        "branch_a2": branch_a2,
        "branch_b1": branch_b1,
        "admin_a": admin_a,
        "admin_a2": admin_a2,
        "admin_b": admin_b,
        "staff_a": staff_a,
        "headers_a": headers_a,
        "headers_b": headers_b,
        "headers_staff": headers_staff,
    }

    yield setup_data

    # Cleanup
    try:
        # Invoices and documents first (they reference users and company)
        db.query(Invoice).filter(Invoice.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Document).filter(Document.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Invitation).filter(Invitation.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        u_ids = [admin_a.id, admin_a2.id, staff_a.id, admin_b.id]
        mfa_ids = [m.id for m in db.query(UserMfa).filter(UserMfa.user_id.in_(u_ids)).all()]
        if mfa_ids:
            db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_mfa_id.in_(mfa_ids)).delete(synchronize_session=False)
        db.query(UserMfa).filter(UserMfa.user_id.in_(u_ids)).delete(synchronize_session=False)
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
        db.query(UserSession).filter(UserSession.user_id.in_(u_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Branch).filter(Branch.company_id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.query(Company).filter(Company.id.in_([comp_a.id, comp_b.id])).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


# ── PHASE 10.1: COMPANY ISOLATION TESTS ──────────────────────────────────────

def test_company_isolation_branches(client: TestClient, test_setup):
    """Company A cannot list or view Company B branches."""
    headers_a = test_setup["headers_a"]
    branch_b1 = test_setup["branch_b1"]

    res = client.get("/api/company/branches", headers=headers_a)
    assert res.status_code == 200
    branch_ids = [b["id"] for b in res.json()]
    assert branch_b1.id not in branch_ids

    res_single = client.get(f"/api/company/branches/{branch_b1.id}", headers=headers_a)
    assert res_single.status_code == 404


def test_company_isolation_users(client: TestClient, test_setup):
    """Company A cannot list or update Company B users."""
    headers_a = test_setup["headers_a"]
    admin_b = test_setup["admin_b"]

    res = client.get("/api/company/users", headers=headers_a)
    assert res.status_code == 200
    user_emails = [u["email"] for u in res.json()["items"]]
    assert admin_b.email not in user_emails

    res_up = client.put(f"/api/company/users/{admin_b.id}", json={"name": "Hacked"}, headers=headers_a)
    assert res_up.status_code == 404


def test_company_profile_view_and_update(client: TestClient, test_setup):
    """Company Admin can view and update own profile, but cannot change company code or ID."""
    headers_a = test_setup["headers_a"]
    comp_a = test_setup["comp_a"]

    res = client.get("/api/company/profile", headers=headers_a)
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == comp_a.name
    assert data["code"] == comp_a.code

    res_put = client.put(
        "/api/company/profile",
        json={
            "display_name": "Alpha Global",
            "contact_person": "Alice Chief",
            "website": "https://alpha.example.com",
            "address": "123 Tech Park, Alpha City",
        },
        headers=headers_a,
    )
    assert res_put.status_code == 200
    updated = res_put.json()
    assert updated["display_name"] == "Alpha Global"
    assert updated["contact_person"] == "Alice Chief"
    assert updated["code"] == comp_a.code


# ── PHASE 10.2: BRANCH LIFECYCLE & DEACTIVATION SAFEGUARDS ───────────────────

def test_branch_lifecycle_and_deactivation_rules(client: TestClient, db: Session, test_setup):
    """
    Branch lifecycle:
      - Attempt deactivating branch with active users -> BLOCKED (HTTP 400)
      - Update branch
      - Deactivate empty branch -> SUCCEEDS
      - Reactivate branch -> SUCCEEDS
      - Branch quota enforcement -> Exceeding max_branches BLOCKED
    """
    headers_a = test_setup["headers_a"]
    branch_a1 = test_setup["branch_a1"]
    branch_a2 = test_setup["branch_a2"]
    uid = test_setup["uid"]

    # 1. Attempt deactivating branch_a1 which has active users -> MUST FAIL
    res_deact = client.post(f"/api/company/branches/{branch_a1.id}/deactivate", headers=headers_a)
    assert res_deact.status_code == 400
    assert "active user" in res_deact.json()["detail"].lower()

    # 2. Update branch_a2
    res_up = client.put(
        f"/api/company/branches/{branch_a2.id}",
        json={"branch_type": "Regional Hub", "city": "Bangalore"},
        headers=headers_a,
    )
    assert res_up.status_code == 200
    assert res_up.json()["branch_type"] == "Regional Hub"

    # 3. Deactivate empty branch_a2 (no active users assigned) -> MUST SUCCEED
    res_deact_a2 = client.post(f"/api/company/branches/{branch_a2.id}/deactivate", headers=headers_a)
    assert res_deact_a2.status_code == 200
    assert res_deact_a2.json()["status"] == "inactive"

    # 4. Reactivate branch_a2 -> MUST SUCCEED
    res_act_a2 = client.post(f"/api/company/branches/{branch_a2.id}/activate", headers=headers_a)
    assert res_act_a2.status_code == 200
    assert res_act_a2.json()["status"] == "active"

    # 5. Branch Quota: Alpha Corp currently has 2 branches, max_branches=3. Create 3rd branch
    res_b3 = client.post(
        "/api/company/branches",
        json={
            "branch_name": f"Alpha Branch 3 {uid}",
            "branch_code": f"AB3_{uid}",
            "branch_contact_number": "9876543210",
            "address_line1": "Road 3",
            "city": "Chennai",
            "district": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600001",
            "admin_name": "Branch 3 Admin",
            "admin_email": f"admin3_{uid}@alpha.test",
            "admin_mobile": "9876543210",
        },
        headers=headers_a,
    )
    assert res_b3.status_code == 200

    # 6. Attempt creating 4th branch (exceeds max_branches=3) -> MUST FAIL (HTTP 400)
    res_b4 = client.post(
        "/api/company/branches",
        json={
            "branch_name": f"Alpha Branch 4 {uid}",
            "branch_code": f"AB4_{uid}",
            "branch_contact_number": "9876543210",
            "address_line1": "Road 4",
            "city": "Chennai",
            "district": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600001",
            "admin_name": "Branch 4 Admin",
            "admin_email": f"admin4_{uid}@alpha.test",
            "admin_mobile": "9876543210",
        },
        headers=headers_a,
    )
    assert res_b4.status_code == 400
    assert "branch limit reached" in res_b4.json()["detail"].lower()


# ── PHASE 10.3 & 10.4: USER MANAGEMENT, ROLES & PRIVILEGE ESCALATION ─────────

def test_user_invite_quota_and_escalation_prevention(client: TestClient, db: Session, test_setup):
    """
    User invitation:
      - Attempting to invite MASTER_ADMIN -> BLOCKED (HTTP 403)
      - Assigning cross-company branch -> BLOCKED (HTTP 400)
      - Assigning multiple branches to STAFF -> BLOCKED (HTTP 400)
      - Valid invite -> SUCCEEDS
      - Exceeding max_users quota -> BLOCKED (HTTP 400)
    """
    headers_a = test_setup["headers_a"]
    branch_a1 = test_setup["branch_a1"]
    branch_a2 = test_setup["branch_a2"]
    branch_b1 = test_setup["branch_b1"]
    uid = test_setup["uid"]

    # 1. Privilege escalation: Company Admin attempts to invite Master Admin -> REJECTED
    res_esc = client.post(
        "/api/company/users/invite",
        json={
            "name": "Evil Root",
            "email": f"evil_{uid}@root.test",
            "role": "MASTER_ADMIN",
            "branch_id": branch_a1.id,
        },
        headers=headers_a,
    )
    assert res_esc.status_code == 403

    # 2. Cross-company branch assignment -> REJECTED
    res_cross = client.post(
        "/api/company/users/invite",
        json={
            "name": "Cross Staff",
            "email": f"cross_{uid}@alpha.test",
            "role": "STAFF",
            "branch_id": branch_b1.id,
        },
        headers=headers_a,
    )
    assert res_cross.status_code == 400

    # 3. Multiple branches assigned to STAFF -> REJECTED (Uploader single-branch invariant)
    res_staff_multi = client.post(
        "/api/company/users/invite",
        json={
            "name": "Multi Staff",
            "email": f"mstaff_{uid}@alpha.test",
            "role": "STAFF",
            "branch_id": branch_a1.id,
            "additional_branch_ids": [branch_a2.id],
        },
        headers=headers_a,
    )
    assert res_staff_multi.status_code == 400
    assert "single branch" in res_staff_multi.json()["detail"].lower()

    # 4. Valid multi-branch invite for ADMIN -> SUCCEEDS (Alpha Corp currently has 3 users, max_users=4)
    res_inv = client.post(
        "/api/company/users/invite",
        json={
            "name": "Multi Admin",
            "email": f"madmin_{uid}@alpha.test",
            "role": "ADMIN",
            "branch_id": branch_a1.id,
            "additional_branch_ids": [branch_a2.id],
        },
        headers=headers_a,
    )
    assert res_inv.status_code == 200

    # 5. User quota enforcement: Alpha Corp now has 3 active + 1 pending invite = 4 (limit reached)
    res_quota = client.post(
        "/api/company/users/invite",
        json={
            "name": "Extra User",
            "email": f"extra_{uid}@alpha.test",
            "role": "STAFF",
            "branch_id": branch_a1.id,
        },
        headers=headers_a,
    )
    assert res_quota.status_code == 400
    assert "user limit reached" in res_quota.json()["detail"].lower()


# ── PHASE 10.5: LAST ACTIVE COMPANY ADMIN PROTECTION ─────────────────────────

def test_last_active_company_admin_protection(client: TestClient, db: Session, test_setup):
    """
    CRITICAL RULE:
      - Company A has 2 active Global Admins: Alice and Aaron.
      - Deactivating 1 Global Admin (Aaron) -> SUCCEEDS.
      - Attempting to deactivate the last remaining Global Admin (Alice) -> BLOCKED (HTTP 400).
      - Attempting to demote the last remaining Global Admin (Alice) to STAFF -> BLOCKED (HTTP 400).
    """
    headers_a = test_setup["headers_a"]
    admin_a = test_setup["admin_a"]
    admin_a2 = test_setup["admin_a2"]

    # 1. Deactivating Aaron (1st of 2 admins) -> MUST SUCCEED
    res_deact1 = client.post(f"/api/company/users/{admin_a2.id}/deactivate", headers=headers_a)
    assert res_deact1.status_code == 200

    # 2. Attempting to deactivate Alice (last remaining active admin) -> MUST BE REJECTED
    res_deact_last = client.post(f"/api/company/users/{admin_a.id}/deactivate", headers=headers_a)
    assert res_deact_last.status_code == 400
    assert "last active company administrator" in res_deact_last.json()["detail"].lower()

    # 3. Attempting to change Alice's role to STAFF -> MUST BE REJECTED
    res_demote = client.put(f"/api/company/users/{admin_a.id}", json={"role": "STAFF"}, headers=headers_a)
    assert res_demote.status_code == 400
    assert "last active company administrator" in res_demote.json()["detail"].lower()


# ── PHASE 10.6: FORCE LOGOUT AND MFA RESET ───────────────────────────────────

def test_force_logout_and_mfa_reset(client: TestClient, db: Session, test_setup):
    """
    - Force logout invalidates user sessions and increments token_version.
    - Admin-assisted MFA reset resets secret and locks without exposing secret.
    """
    headers_a = test_setup["headers_a"]
    staff_a = test_setup["staff_a"]

    # 1. Staff is currently logged in with headers_staff
    headers_staff = test_setup["headers_staff"]
    res_doc = client.get("/api/documents", headers=headers_staff)
    assert res_doc.status_code == 200

    # 2. Company Admin force logouts Staff
    res_force = client.post(f"/api/company/users/{staff_a.id}/force-logout", headers=headers_a)
    assert res_force.status_code == 200

    # 3. Staff's old token MUST now be rejected with 401
    res_rejected = client.get("/api/documents", headers=headers_staff)
    assert res_rejected.status_code == 401

    # 4. MFA reset request for staff
    res_mfa_reset = client.post(f"/api/company/users/{staff_a.id}/mfa-reset-request", headers=headers_a)
    assert res_mfa_reset.status_code == 200
    assert "mfa" in res_mfa_reset.json()["message"].lower()


# ── PHASE 10.7: COMPANY DOCUMENT ARCHIVE & AUDIT LOGS ────────────────────────

def test_company_document_archive_and_audit_logs(client: TestClient, db: Session, test_setup):
    """
    - Company Admin can view documents across all branches via /api/company/documents.
    - Staff cannot access Company Admin archive.
    - Company Admin can inspect company audit logs via /api/company/audit-logs.
    """
    headers_a = test_setup["headers_a"]
    headers_b = test_setup["headers_b"]
    headers_staff = test_setup["headers_staff"]
    comp_a = test_setup["comp_a"]

    # 1. Staff cannot access Company Admin archive route
    res_staff_deny = client.get("/api/company/documents", headers=headers_staff)
    assert res_staff_deny.status_code == 403

    # 2. Company Admin accesses archive
    res_archive = client.get("/api/company/documents", headers=headers_a)
    assert res_archive.status_code == 200
    assert isinstance(res_archive.json(), list)

    # 3. Company Admin accesses company audit logs
    res_audit = client.get("/api/company/audit-logs", headers=headers_a)
    assert res_audit.status_code == 200
    data = res_audit.json()
    assert "items" in data
    assert "total_count" in data
    for item in data["items"]:
        assert item["company_id"] == comp_a.id

    # 4. Company B cannot see Company A's audit logs
    res_audit_b = client.get("/api/company/audit-logs", headers=headers_b)
    assert res_audit_b.status_code == 200
    for item in res_audit_b.json()["items"]:
        assert item["company_id"] != comp_a.id
