"""
Branch Admin User Management (Staff & Uploader Management) Comprehensive Test Suite.

Verifies:
  1. Branch Admin can list users in their authorized branch.
  2. Branch Admin cannot list users from an unauthorized branch.
  3. Branch Admin can invite STAFF.
  4. Branch Admin can invite UPLOADER.
  5. Branch Admin cannot invite another Branch Admin (role escalation blocked).
  6. Branch Admin cannot invite a Company Admin (role escalation blocked).
  7. Branch Admin cannot provide another company's ID to bypass tenant isolation.
  8. Branch Admin cannot invite into an unauthorized branch.
  9. Branch Admin can edit eligible staff details (name, email, mobile).
  10. Branch Admin cannot change user roles.
  11. Branch Admin cannot move users to another branch.
  12. Branch Admin can deactivate STAFF.
  13. Branch Admin can deactivate UPLOADER.
  14. Deactivation revokes sessions and increments token_version.
  15. Branch Admin can reactivate eligible accounts.
  16. Branch Admin cannot manage users outside their authorized scope (or administrators).
  17. Multi-branch Branch Admin can manage users in all authorized branches.
  18. Company Admin retains company-wide user management functionality.
  19. Staff and Uploader cannot access Branch Admin user management endpoints (403).
  20. All applicable actions produce audit events.
"""

import uuid
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models import (
    AccountStatus,
    AuditLog,
    Branch,
    Company,
    Invitation,
    User,
    UserRole,
    UserRoleAssignment,
    UserSession,
)
from app.auth import get_password_hash
from app.services.session_service import session_service

client = TestClient(app)


# ── Fixtures & Helpers ───────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _login(email: str, password: str = "Pasword@123", portal: str = None) -> tuple[str, dict]:
    if portal is None:
        if "master" in email or "platform" in email:
            portal = "platform"
        elif email in ("jayasri@example.com", "jayasri.suresh077@gmail.com"):
            portal = "company"
        else:
            portal = "app"
    res = client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    token = res.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def ensure_clean_test_state(db: Session):
    """Reset known test users and ensure test branches exist."""
    # Ensure Company 40 exists
    c40 = db.query(Company).filter_by(id=40).first()
    if not c40:
        c40 = Company(id=40, name="Test Company 40", code="TC40", max_users=100)
        db.add(c40)
        db.commit()
    else:
        c40.max_users = 100
        db.commit()

    # Ensure Branch 4932 (Primary) and Branch 5648 (Secondary) exist in Company 40
    b4932 = db.query(Branch).filter_by(id=4932).first()
    if not b4932:
        b4932 = Branch(id=4932, company_id=40, name="Chennai Primary", code="CHN-01", status="active")
        db.add(b4932)
        db.commit()

    b5648 = db.query(Branch).filter_by(id=5648).first()
    if not b5648:
        b5648 = Branch(id=5648, company_id=40, name="Chennai Secondary", code="CHN-02", status="active")
        db.add(b5648)
        db.commit()

    # Ensure Company Admin, Branch Admin, and Staff exist
    pwd_hash = get_password_hash("Pasword@123")
    ca = db.query(User).filter_by(email="jayasri@example.com").first()
    if not ca:
        ca = User(company_id=40, branch_id=4932, name="Jayasri CA", email="jayasri@example.com", password_hash=pwd_hash, role=UserRole.GLOBAL_ADMIN, status=AccountStatus.ACTIVE)
        db.add(ca)
        db.flush()
    else:
        ca.status = AccountStatus.ACTIVE
        ca.role = UserRole.GLOBAL_ADMIN
        ca.password_hash = pwd_hash

    ba = db.query(User).filter_by(email="samrethi@example.com").first()
    if not ba:
        ba = User(company_id=40, branch_id=4932, name="Samrethi BA", email="samrethi@example.com", password_hash=pwd_hash, role=UserRole.ADMIN, status=AccountStatus.ACTIVE)
        db.add(ba)
        db.flush()
    else:
        ba.status = AccountStatus.ACTIVE
        ba.role = UserRole.ADMIN
        ba.branch_id = 4932
        ba.password_hash = pwd_hash

    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    if not staff:
        staff = User(company_id=40, branch_id=4932, name="Sujipriya Staff", email="sujipriya@example.com", password_hash=pwd_hash, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
        db.add(staff)
        db.flush()
    else:
        staff.status = AccountStatus.ACTIVE
        staff.role = UserRole.STAFF
        staff.branch_id = 4932
        staff.password_hash = pwd_hash

    # Reset assignments for BA
    db.query(UserRoleAssignment).filter_by(user_id=ba.id).delete()
    db.add(UserRoleAssignment(user_id=ba.id, role="ADMIN", scope_type="branch", scope_id=4932))

    # Reset assignments for Staff
    db.query(UserRoleAssignment).filter_by(user_id=staff.id).delete()
    db.add(UserRoleAssignment(user_id=staff.id, role="STAFF", scope_type="branch", scope_id=4932))
    db.add(UserRoleAssignment(user_id=staff.id, role="UPLOADER", scope_type="branch", scope_id=4932))

    db.commit()


# ── 1 & 2. Branch-Scoped User Listing ────────────────────────────────────────

def test_branch_admin_can_list_users_in_authorized_branch(db: Session):
    """1. Branch Admin can list users in their authorized branch."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    res = client.get("/api/branch/users?branch_id=4932&page_size=100", headers=ba_headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "items" in data
    assert data.get("total_count", data.get("total", 0)) >= 1
    emails = [u["email"] for u in data["items"]]
    assert "sujipriya@example.com" in emails
    # Sensitive credentials must not be present
    first_item = data["items"][0]
    assert "password_hash" not in first_item
    assert "recovery_codes" not in first_item
    assert "mfa_secret" not in first_item


def test_branch_admin_cannot_list_users_from_unauthorized_branch(db: Session):
    """2. Branch Admin cannot list users from an unauthorized branch (403 Forbidden)."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    # Branch 5648 is currently NOT in BA's assignments
    res = client.get("/api/branch/users?branch_id=5648", headers=ba_headers)
    assert res.status_code == 403
    assert "outside your authorized branch scope" in res.json()["detail"]


# ── 3 & 4. Invite STAFF and UPLOADER ─────────────────────────────────────────

def test_branch_admin_can_invite_staff(db: Session):
    """3. Branch Admin can invite STAFF to authorized branch."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    new_email = f"staff_inv_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": "New Branch Staff",
        "email": new_email,
        "role": "STAFF",
        "branch_id": 4932,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    assert res.status_code == 200, res.text
    assert "Invitation successfully dispatched" in res.json()["message"]

    # Verify invitation in DB
    inv = db.query(Invitation).filter_by(email=new_email).first()
    assert inv is not None
    assert inv.branch_id == 4932
    assert inv.invited_role == UserRole.STAFF


def test_branch_admin_can_invite_uploader(db: Session):
    """4. Branch Admin can invite UPLOADER to authorized branch."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    new_email = f"uploader_inv_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "name": "New Branch Uploader",
        "email": new_email,
        "role": "UPLOADER",
        "branch_id": 4932,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    assert res.status_code == 200, res.text
    assert "Invitation successfully dispatched" in res.json()["message"]

    inv = db.query(Invitation).filter_by(email=new_email).first()
    assert inv is not None
    assert inv.branch_id == 4932
    assert inv.invited_role == UserRole.UPLOADER


# ── 5, 6, 7, 8. Invitation Escalation & Isolation Protection ────────────────

def test_branch_admin_cannot_invite_another_branch_admin(db: Session):
    """5. Branch Admin cannot invite another Branch Admin (role escalation blocked)."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    payload = {
        "name": "Escalated Admin",
        "email": f"escalated_ba_{uuid.uuid4().hex[:6]}@example.com",
        "role": "ADMIN",
        "branch_id": 4932,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    assert res.status_code == 403
    assert "Role escalation prohibited" in res.json()["detail"]


def test_branch_admin_cannot_invite_company_admin(db: Session):
    """6. Branch Admin cannot invite a Company Admin (role escalation blocked)."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    payload = {
        "name": "Escalated Global Admin",
        "email": f"escalated_ga_{uuid.uuid4().hex[:6]}@example.com",
        "role": "GLOBAL_ADMIN",
        "branch_id": 4932,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    assert res.status_code == 403
    assert "Role escalation prohibited" in res.json()["detail"]


def test_branch_admin_cannot_provide_another_company_id_to_bypass_tenant_isolation(db: Session):
    """7. Branch Admin cannot provide another company's branch or access other company's users."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    # Branch 1337 belongs to Company 24, not Company 40
    payload = {
        "name": "Cross Tenant User",
        "email": f"cross_tenant_{uuid.uuid4().hex[:6]}@example.com",
        "role": "STAFF",
        "branch_id": 1337,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    # Blocked with 403 Forbidden because Branch 1337 is outside BA's authorized branches
    assert res.status_code in (400, 403)


def test_branch_admin_cannot_invite_into_unauthorized_branch(db: Session):
    """8. Branch Admin cannot invite into an unauthorized branch in the same company."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    # Branch 5648 belongs to Company 40, but is not in Samrethi's assignments
    payload = {
        "name": "Unauthorized Branch User",
        "email": f"unauth_branch_{uuid.uuid4().hex[:6]}@example.com",
        "role": "STAFF",
        "branch_id": 5648,
    }
    res = client.post("/api/branch/users/invite", json=payload, headers=ba_headers)
    assert res.status_code == 403
    assert "outside your authorized branch scope" in res.json()["detail"] or "not authorized to invite" in res.json()["detail"]


# ── 9, 10, 11. Edit User Details ─────────────────────────────────────────────

def test_branch_admin_can_edit_eligible_staff_details(db: Session):
    """9. Branch Admin can edit eligible staff details (name, email, mobile)."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()

    payload = {
        "name": "Sujipriya Updated Name",
        "mobile": "+91 9999988888",
    }
    res = client.put(f"/api/branch/users/{staff.id}", json=payload, headers=ba_headers)
    assert res.status_code == 200, res.text
    assert "updated successfully" in res.json()["message"]

    db.refresh(staff)
    assert staff.name == "Sujipriya Updated Name"
    assert staff.mobile == "+91 9999988888"


def test_branch_admin_cannot_change_user_roles(db: Session):
    """10. Branch Admin cannot change user roles via branch update endpoint."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()

    # Payload attempts to pass 'role' field
    payload = {
        "name": "Sujipriya Hacker",
        "role": "ADMIN",
    }
    # BranchUserUpdateRequest schema does not accept role, role is ignored or prohibited
    res = client.put(f"/api/branch/users/{staff.id}", json=payload, headers=ba_headers)
    assert res.status_code == 200
    db.refresh(staff)
    assert staff.role == UserRole.STAFF  # Role must NOT have changed


def test_branch_admin_cannot_move_users_to_another_branch(db: Session):
    """11. Branch Admin cannot move users to another branch."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()

    payload = {
        "name": "Sujipriya Moved",
        "branch_id": 5648,
    }
    res = client.put(f"/api/branch/users/{staff.id}", json=payload, headers=ba_headers)
    assert res.status_code == 200
    db.refresh(staff)
    assert staff.branch_id == 4932  # Branch ID must NOT have changed


# ── 12, 13, 14, 15. Activate & Deactivate Users ─────────────────────────────

def test_branch_admin_can_deactivate_staff(db: Session):
    """12. Branch Admin can deactivate STAFF."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    assert staff.status == AccountStatus.ACTIVE

    res = client.post(f"/api/branch/users/{staff.id}/deactivate", headers=ba_headers)
    assert res.status_code == 200, res.text
    assert "deactivated" in res.json()["message"]

    db.refresh(staff)
    assert staff.status == AccountStatus.INACTIVE


def test_branch_admin_can_deactivate_uploader(db: Session):
    """13. Branch Admin can deactivate UPLOADER."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    # Create uploader user in Branch 4932
    pwd_hash = get_password_hash("Pasword@123")
    up_user = User(company_id=40, branch_id=4932, name="Test Uploader", email=f"up_{uuid.uuid4().hex[:6]}@example.com", password_hash=pwd_hash, role=UserRole.UPLOADER, status=AccountStatus.ACTIVE)
    db.add(up_user)
    db.flush()
    db.add(UserRoleAssignment(user_id=up_user.id, role="UPLOADER", scope_type="branch", scope_id=4932))
    db.commit()

    res = client.post(f"/api/branch/users/{up_user.id}/deactivate", headers=ba_headers)
    assert res.status_code == 200
    db.refresh(up_user)
    assert up_user.status == AccountStatus.INACTIVE


def test_deactivation_revokes_sessions_and_increments_token_version(db: Session):
    """14. Deactivation revokes sessions and increments token_version."""
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    staff.status = AccountStatus.ACTIVE
    initial_tv = staff.token_version
    db.commit()

    # Create active session for staff
    st_token, _ = _login("sujipriya@example.com", portal="app")
    active_sessions_before = db.query(UserSession).filter(
        UserSession.identity_type == "user",
        UserSession.user_id == staff.id,
        UserSession.revoked_at.is_(None),
    ).count()
    assert active_sessions_before >= 1

    # BA deactivates staff
    _, ba_headers = _login("samrethi@example.com", portal="app")
    res = client.post(f"/api/branch/users/{staff.id}/deactivate", headers=ba_headers)
    assert res.status_code == 200

    db.refresh(staff)
    assert staff.status == AccountStatus.INACTIVE
    assert staff.token_version > initial_tv

    active_sessions_after = db.query(UserSession).filter(
        UserSession.identity_type == "user",
        UserSession.user_id == staff.id,
        UserSession.revoked_at.is_(None),
    ).count()
    assert active_sessions_after == 0


def test_branch_admin_can_reactivate_eligible_accounts(db: Session):
    """15. Branch Admin can reactivate eligible accounts."""
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    staff.status = AccountStatus.INACTIVE
    db.commit()

    _, ba_headers = _login("samrethi@example.com", portal="app")
    res = client.post(f"/api/branch/users/{staff.id}/activate", headers=ba_headers)
    assert res.status_code == 200, res.text
    assert "reactivated successfully" in res.json()["message"]

    db.refresh(staff)
    assert staff.status == AccountStatus.ACTIVE


# ── 16. Scope & Admin Immunity Protection ────────────────────────────────────

def test_branch_admin_cannot_manage_users_outside_scope_or_admins(db: Session):
    """16. Branch Admin cannot modify or deactivate administrators or users in unauthorized branches."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    ca = db.query(User).filter_by(email="jayasri@example.com").first()

    # Attempt to deactivate Company Admin -> 403 Forbidden
    res = client.post(f"/api/branch/users/{ca.id}/deactivate", headers=ba_headers)
    assert res.status_code == 403
    assert "cannot deactivate administrator accounts" in res.json()["detail"]

    # Attempt to edit Company Admin -> 403 Forbidden
    res_edit = client.put(f"/api/branch/users/{ca.id}", json={"name": "Hacked CA"}, headers=ba_headers)
    assert res_edit.status_code == 403
    assert "cannot modify administrator accounts" in res_edit.json()["detail"]

    # User in completely unauthorized branch
    other_branch_user = User(company_id=40, branch_id=5648, name="Other Branch Staff", email=f"other_{uuid.uuid4().hex[:6]}@example.com", password_hash=ca.password_hash, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    db.add(other_branch_user)
    db.commit()

    res_unauth = client.post(f"/api/branch/users/{other_branch_user.id}/deactivate", headers=ba_headers)
    assert res_unauth.status_code == 403
    assert "authorized branches" in res_unauth.json()["detail"]


# ── 17. Multi-Branch Branch Admin ───────────────────────────────────────────

def test_multibranch_admin_can_manage_users_in_all_authorized_branches(db: Session):
    """17. Multi-branch Branch Admin can manage users in all authorized branches."""
    ba = db.query(User).filter_by(email="samrethi@example.com").first()
    # Add secondary branch assignment to BA for branch 5648
    db.add(UserRoleAssignment(user_id=ba.id, role="ADMIN", scope_type="branch", scope_id=5648))
    db.commit()

    # User in branch 5648
    pwd_hash = get_password_hash("Pasword@123")
    user_b2 = User(company_id=40, branch_id=5648, name="Branch 2 Staff", email=f"b2_staff_{uuid.uuid4().hex[:6]}@example.com", password_hash=pwd_hash, role=UserRole.STAFF, status=AccountStatus.ACTIVE)
    db.add(user_b2)
    db.commit()

    _, ba_headers = _login("samrethi@example.com", portal="app")

    # 1. BA can list branch 5648 users
    res_list = client.get("/api/branch/users?branch_id=5648", headers=ba_headers)
    assert res_list.status_code == 200
    emails = [u["email"] for u in res_list.json()["items"]]
    assert user_b2.email in emails

    # 2. BA can edit branch 5648 staff
    res_edit = client.put(f"/api/branch/users/{user_b2.id}", json={"name": "B2 Staff Updated"}, headers=ba_headers)
    assert res_edit.status_code == 200

    # 3. BA can deactivate branch 5648 staff
    res_deact = client.post(f"/api/branch/users/{user_b2.id}/deactivate", headers=ba_headers)
    assert res_deact.status_code == 200

    db.refresh(user_b2)
    assert user_b2.status == AccountStatus.INACTIVE


# ── 18. Company Admin Retains Company-Wide Functionality ────────────────────

def test_company_admin_retains_company_wide_user_management(db: Session):
    """18. Company Admin retains company-wide user management functionality."""
    _, ca_headers = _login("jayasri@example.com", portal="company")

    # CA can list all company users via company route
    res = client.get("/api/company/users", headers=ca_headers)
    assert res.status_code == 200
    assert res.json().get("total_count", res.json().get("total", 0)) >= 1

    # CA can also call branch route across any branch
    res_branch = client.get("/api/branch/users?branch_id=5648", headers=ca_headers)
    assert res_branch.status_code == 200


# ── 19. Staff and Uploader Cannot Access Branch Management Endpoints ────────

def test_staff_and_uploader_cannot_access_branch_admin_user_management(db: Session):
    """19. Staff and Uploader cannot access Branch Admin user management endpoints (403)."""
    _, st_headers = _login("sujipriya@example.com", portal="app")

    # Listing users
    res_list = client.get("/api/branch/users", headers=st_headers)
    assert res_list.status_code == 403

    # Inviting users
    res_inv = client.post("/api/branch/users/invite", json={"name": "X", "email": "x@x.com", "role": "STAFF", "branch_id": 4932}, headers=st_headers)
    assert res_inv.status_code == 403

    # Deactivating users
    res_deact = client.post("/api/branch/users/1/deactivate", headers=st_headers)
    assert res_deact.status_code == 403


# ── 20. Audit Logging ────────────────────────────────────────────────────────

def test_audit_events_recorded_for_all_branch_user_actions(db: Session):
    """20. All applicable actions produce audit events."""
    _, ba_headers = _login("samrethi@example.com", portal="app")
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()

    # Action 1: Update
    client.put(f"/api/branch/users/{staff.id}", json={"name": "Audit Test Name"}, headers=ba_headers)

    # Action 2: Deactivate
    client.post(f"/api/branch/users/{staff.id}/deactivate", headers=ba_headers)

    # Action 3: Reactivate
    client.post(f"/api/branch/users/{staff.id}/activate", headers=ba_headers)

    # Action 4: Invite
    inv_email = f"audit_inv_{uuid.uuid4().hex[:6]}@example.com"
    client.post("/api/branch/users/invite", json={"name": "Audit Invitee", "email": inv_email, "role": "STAFF", "branch_id": 4932}, headers=ba_headers)

    # Verify audit logs in DB
    recent_logs = (
        db.query(AuditLog)
        .filter(AuditLog.company_id == 40)
        .order_by(AuditLog.id.desc())
        .limit(10)
        .all()
    )
    actions = [l.action for l in recent_logs]
    assert "user.update" in actions
    assert "user.deactivate" in actions
    assert "user.reactivate" in actions
    assert "user.create" in actions
    assert "auth.invitation.create" in actions
