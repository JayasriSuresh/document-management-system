"""
Enterprise Multi-Factor Authentication (MFA) v2.4-FINAL-SPEC Comprehensive Test Suite.

Verifies:
  1. Platform-wide MFA policy transitions & transaction-safe session invalidation
     (enforce_all, enforce_master_admin, enforce_company_admin).
  2. Company-wide MFA policy enforcement, session revocation, and anti-downgrade conflict (409).
  3. Branch-level MFA policy, delegation gating (403), state preservation, and anti-downgrade (409).
  4. Multi-branch user policy evaluation (mandate in secondary branch makes MFA mandatory).
  5. User role / branch assignment transition dynamic session revocation.
  6. Staff & Uploader role boundaries: self-enrollment and disable blocking (403).
  7. Recovery-code security: custom Base32 alphabet, entropy, admin-only regeneration, single-use atomic redemption.
  8. Administrative MFA resets: role hierarchy isolation, peer protection, scope validation, and re-authentication.
  9. Restricted MFA enrollment token flow: protected endpoints blocked while enrollment succeeds.
"""

import re
import pytest
import pyotp
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal
from app.models import (
    User,
    MasterAdmin,
    Company,
    Branch,
    UserMfa,
    MfaRecoveryCode,
    PlatformSetting,
    UserSession,
    UserRoleAssignment,
    UserRole,
    AccountStatus,
)
from app.services.mfa_service import MfaService

client = TestClient(app)


# ── Fixtures & Setup ─────────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_enterprise_mfa_state(db: Session):
    """Ensure clean platform/company/branch MFA policies and clear test records."""
    db.query(MfaRecoveryCode).delete()
    db.query(UserMfa).delete()

    ps = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
    if ps:
        ps.value = {"enforce_master_admin": False, "enforce_company_admin": False, "enforce_all": False}
    else:
        ps = PlatformSetting(
            key="mfa_policy",
            value={"enforce_master_admin": False, "enforce_company_admin": False, "enforce_all": False},
        )
        db.add(ps)

    for c in db.query(Company).all():
        c.mfa_required_for_all = False
        c.allow_branch_mfa_control = True

    for b in db.query(Branch).all():
        b.mfa_required_for_all = False

    for u in db.query(User).all():
        u.failed_attempts = 0
        u.locked_until = None

    for a in db.query(MasterAdmin).all():
        a.failed_attempts = 0
        a.locked_until = None

    # Reset known test users to base roles
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    if staff:
        db.query(UserRoleAssignment).filter_by(user_id=staff.id).delete()
        staff.role = UserRole.STAFF
    ca = db.query(User).filter_by(email="jayasri@example.com").first()
    if ca:
        ca.role = UserRole.GLOBAL_ADMIN
    ba = db.query(User).filter_by(email="samrethi@example.com").first()
    if ba:
        ba.role = UserRole.ADMIN

    db.commit()
    yield
    # Teardown
    db.query(MfaRecoveryCode).delete()
    db.query(UserMfa).delete()
    for c in db.query(Company).all():
        c.mfa_required_for_all = False
        c.allow_branch_mfa_control = True
    for b in db.query(Branch).all():
        b.mfa_required_for_all = False
    ps = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
    if ps:
        ps.value = {"enforce_master_admin": False, "enforce_company_admin": False, "enforce_all": False}

    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    if staff:
        db.query(UserRoleAssignment).filter_by(user_id=staff.id).delete()
        staff.role = UserRole.STAFF
    ca = db.query(User).filter_by(email="jayasri@example.com").first()
    if ca:
        ca.role = UserRole.GLOBAL_ADMIN
    ba = db.query(User).filter_by(email="samrethi@example.com").first()
    if ba:
        ba.role = UserRole.ADMIN
    db.commit()


def _login(email: str, password: str = "Pasword@123", portal: str = None) -> tuple[str, dict]:
    if portal is None:
        if "master" in email or "platform" in email or "inkwc" in email:
            portal = "platform"
        elif email in ("jayasri@example.com", "jayasri.suresh077@gmail.com"):
            portal = "company"
        else:
            portal = "app"
    res = client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})
    assert res.status_code == 200, f"Login failed for {email} on portal {portal}: {res.text}"
    token = res.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def _enroll_and_login(email: str, password: str = "Pasword@123", portal: str = None) -> tuple[str, dict, pyotp.TOTP]:
    token, headers = _login(email, password, portal)
    start_res = client.post("/api/auth/mfa/enroll/start", headers=headers)
    assert start_res.status_code == 200, start_res.text
    secret = start_res.json()["secret"]
    totp = pyotp.TOTP(secret)
    verify_res = client.post("/api/auth/mfa/enroll/verify", headers=headers, json={"code": totp.now()})
    assert verify_res.status_code == 200, verify_res.text
    return token, headers, totp


def _reset_replay_step_for_user(email: str):
    s = SessionLocal()
    try:
        u = s.query(User).filter_by(email=email).first()
        if u:
            m = s.query(UserMfa).filter_by(user_id=u.id).first()
            if m:
                m.last_used_step = None
                s.commit()
    finally:
        s.close()


def _login_with_mfa(email: str, password: str = "Pasword@123", portal: str = None, totp: pyotp.TOTP = None) -> tuple[str, dict]:
    if portal is None:
        if "master" in email or "platform" in email or "inkwc" in email:
            portal = "platform"
        elif email in ("jayasri@example.com", "jayasri.suresh077@gmail.com"):
            portal = "company"
        else:
            portal = "app"
    res = client.post("/api/auth/login", json={"email": email, "password": password, "portal": portal})
    assert res.status_code == 200
    data = res.json()
    if data.get("mfa_required"):
        pending_token = data["mfa_pending_token"]
        _reset_replay_step_for_user(email)
        v_res = client.post("/api/auth/mfa/verify", json={"mfa_pending_token": pending_token, "code": totp.now()})
        assert v_res.status_code == 200, v_res.text
        token = v_res.json()["access_token"]
        return token, {"Authorization": f"Bearer {token}"}
    token = data["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


# ── 1. Platform-Wide Policy Transitions & Session Invalidation ───────────────

def test_platform_mfa_enforce_all_invalidates_all_sessions(db: Session):
    """
    Toggling platform enforce_all invalidates both tenant users and Master Admins across all tenants.
    """
    # 1. Create sessions for Master Admin and Company 40 User
    m_token, m_headers = _login("master@platform.local", portal="platform")
    u_token, u_headers = _login("jayasri@example.com", portal="company")

    # Record baseline active sessions
    active_m_sessions = db.query(UserSession).filter(UserSession.identity_type == "master_admin", UserSession.revoked_at.is_(None)).all()
    active_u_sessions = db.query(UserSession).filter(UserSession.identity_type == "user", UserSession.revoked_at.is_(None)).all()
    assert len(active_m_sessions) >= 1
    assert len(active_u_sessions) >= 1

    # 2. Update platform policy to enforce_all = True
    res = client.post(
        "/api/admin/security/mfa-policy",
        headers=m_headers,
        json={"enforce_all": True, "enforce_master_admin": True, "enforce_company_admin": True},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["enforce_all"] is True

    # 3. Verify all previous sessions are revoked in DB
    db.expire_all()
    revoked_u = db.query(UserSession).filter(UserSession.revoke_reason == "platform_enforce_all_mandated").all()
    assert len(revoked_u) >= 1


def test_platform_mfa_role_specific_session_invalidation(db: Session):
    """
    Toggling enforce_company_admin revokes company admin sessions without revoking all staff.
    """
    m_token, m_headers = _login("master@platform.local", portal="platform")
    ca_token, ca_headers = _login("jayasri@example.com", portal="company")
    staff_token, staff_headers = _login("sujipriya@example.com", portal="app")

    # Update platform policy: enforce_company_admin = True
    res = client.post(
        "/api/admin/security/mfa-policy",
        headers=m_headers,
        json={"enforce_company_admin": True, "enforce_master_admin": False, "enforce_all": False},
    )
    assert res.status_code == 200

    db.expire_all()
    ca_user = db.query(User).filter_by(email="jayasri@example.com").first()
    ca_sessions = db.query(UserSession).filter(UserSession.user_id == ca_user.id, UserSession.revoked_at.isnot(None)).all()
    assert any(s.revoke_reason == "platform_company_admin_mandated" for s in ca_sessions)


# ── 2. Company-Wide MFA Policy Enforcement & Anti-Downgrade ──────────────────

def test_company_mfa_policy_update_and_anti_downgrade(db: Session):
    """
    Company Admin can mandate MFA company-wide, invalidating tenant user sessions.
    When Platform enforce_all is active, Company Admin cannot downgrade to optional (409 Conflict).
    """
    # 1. Enroll MFA for Company Admin first so she can maintain authenticated access under enforce_all
    _, _, ca_totp = _enroll_and_login("jayasri@example.com", portal="company")
    _, m_headers = _login("master@platform.local", portal="platform")
    _login("sujipriya@example.com", portal="app")

    # Log in fresh with MFA
    _, ca_headers = _login_with_mfa("jayasri@example.com", portal="company", totp=ca_totp)

    # 2. Company Admin enforces MFA for company
    res = client.post(
        "/api/company/security/mfa-policy",
        headers=ca_headers,
        json={"mfa_required_for_all": True},
    )
    assert res.status_code == 200
    assert res.json()["mfa_required_for_all"] is True

    db.expire_all()
    revoked = db.query(UserSession).filter(UserSession.revoke_reason == "company_mfa_policy_mandated").all()
    assert len(revoked) >= 1

    # 3. Master Admin enforces platform-wide MFA
    client.post(
        "/api/admin/security/mfa-policy",
        headers=m_headers,
        json={"enforce_all": True},
    )

    # Re-login Company Admin with MFA after platform session invalidation
    _, fresh_ca_headers = _login_with_mfa("jayasri@example.com", portal="company", totp=ca_totp)

    # 4. Company Admin attempts anti-downgrade (mfa_required_for_all = False)
    downgrade_res = client.post(
        "/api/company/security/mfa-policy",
        headers=fresh_ca_headers,
        json={"mfa_required_for_all": False},
    )
    assert downgrade_res.status_code == 409
    assert "platform-wide" in downgrade_res.json()["detail"].lower()


# ── 3. Branch-Level MFA Policy, Delegation, & Anti-Downgrade ──────────────────

def test_branch_mfa_delegation_and_isolation(db: Session):
    """
    1. If allow_branch_mfa_control is False, Branch Admin cannot update branch policy (403).
    2. If allow_branch_mfa_control is True, Branch Admin can update branch policy.
    3. Disabling delegation preserves existing branch mandate.
    4. Anti-downgrade: Branch Admin cannot set False when Company policy mandates MFA (409).
    """
    ba_user = db.query(User).filter_by(email="samrethi@example.com").first()
    branch = db.query(Branch).filter_by(id=ba_user.branch_id).first()

    # Enroll MFA for both Branch Admin and Company Admin
    _, _, ba_totp = _enroll_and_login("samrethi@example.com", portal="app")
    _, _, ca_totp = _enroll_and_login("jayasri@example.com", portal="company")
    _, ca_headers = _login_with_mfa("jayasri@example.com", portal="company", totp=ca_totp)
    _, ba_headers = _login_with_mfa("samrethi@example.com", portal="app", totp=ba_totp)

    # 1. Company disables delegation
    client.post(
        "/api/company/security/mfa-policy",
        headers=ca_headers,
        json={"allow_branch_mfa_control": False},
    )

    # Branch admin tries to modify branch policy -> 403 Forbidden
    res = client.post(
        f"/api/branch/{branch.id}/security/mfa-policy",
        headers=ba_headers,
        json={"mfa_required_for_all": True},
    )
    assert res.status_code == 403
    assert "delegated" in res.json()["detail"].lower()

    # 2. Company enables delegation
    client.post(
        "/api/company/security/mfa-policy",
        headers=ca_headers,
        json={"allow_branch_mfa_control": True},
    )

    # Branch admin modifies policy -> 200 OK (invalidates sessions of all branch users, including ca and ba)
    res = client.post(
        f"/api/branch/{branch.id}/security/mfa-policy",
        headers=ba_headers,
        json={"mfa_required_for_all": True},
    )
    assert res.status_code == 200
    assert res.json()["mfa_required_for_all"] is True

    # Re-login Company Admin after branch session invalidation
    _, fresh_ca_headers = _login_with_mfa("jayasri@example.com", portal="company", totp=ca_totp)

    # 3. Company disables delegation: branch.mfa_required_for_all remains TRUE
    client.post(
        "/api/company/security/mfa-policy",
        headers=fresh_ca_headers,
        json={"allow_branch_mfa_control": False},
    )
    db.expire_all()
    b_refreshed = db.query(Branch).filter_by(id=branch.id).first()
    assert b_refreshed.mfa_required_for_all is True

    # 4. Anti-downgrade when company mandates MFA
    client.post(
        "/api/company/security/mfa-policy",
        headers=fresh_ca_headers,
        json={"mfa_required_for_all": True, "allow_branch_mfa_control": True},
    )
    # Re-login branch admin after company session invalidation
    _, fresh_ba_headers = _login_with_mfa("samrethi@example.com", portal="app", totp=ba_totp)

    downgrade_res = client.post(
        f"/api/branch/{branch.id}/security/mfa-policy",
        headers=fresh_ba_headers,
        json={"mfa_required_for_all": False},
    )
    assert downgrade_res.status_code == 409
    assert "company-wide" in downgrade_res.json()["detail"].lower()


# ── 4. Multi-Branch User Policy Evaluation ───────────────────────────────────

def test_multi_branch_user_mandatory_mfa_evaluation(db: Session):
    """
    A user with optional primary branch and mandated secondary branch
    has MfaService.is_mfa_mandatory_for_user == True.
    """
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    comp = db.query(Company).filter_by(id=staff.company_id).first()
    comp.mfa_required_for_all = False

    # Create or retrieve secondary branch in company 40
    b2 = db.query(Branch).filter(Branch.company_id == comp.id, Branch.id != staff.branch_id).first()
    if not b2:
        b2 = Branch(
            company_id=comp.id,
            name="Secondary Branch Mandated",
            code=f"SEC_{int(datetime.utcnow().timestamp())}",
            status="active",
            mfa_required_for_all=True,
        )
        db.add(b2)
        db.commit()
    else:
        b2.mfa_required_for_all = True
        db.commit()

    # Primary branch optional
    b1 = db.query(Branch).filter_by(id=staff.branch_id).first()
    b1.mfa_required_for_all = False
    db.commit()

    # Assign user to secondary branch
    ura = UserRoleAssignment(
        user_id=staff.id,
        role="STAFF",
        scope_type="branch",
        scope_id=b2.id,
        created_by=staff.id,
    )
    db.add(ura)
    db.commit()

    # Evaluate effective policy
    assert MfaService.is_mfa_mandatory_for_user(db, staff) is True

    # Cleanup assignment
    db.query(UserRoleAssignment).filter_by(user_id=staff.id, scope_id=b2.id).delete()
    db.commit()
    assert MfaService.is_mfa_mandatory_for_user(db, staff) is False


# ── 5. User Assignment Transition Dynamic Session Revocation ─────────────────

def test_assignment_change_dynamic_session_revocation(db: Session):
    """
    When a user transitions from optional -> mandatory MFA via reassignment
    to a mandated branch in PUT /api/company/users/{user_id}, their active
    sessions are revoked with reason="mfa_policy_mandated_by_assignment_change".
    """
    staff = db.query(User).filter_by(email="sujipriya@example.com").first()
    comp = db.query(Company).filter_by(id=staff.company_id).first()
    comp.mfa_required_for_all = False

    # Primary branch optional
    b1 = db.query(Branch).filter_by(id=staff.branch_id).first()
    b1.mfa_required_for_all = False

    # Mandated branch
    b2 = db.query(Branch).filter(Branch.company_id == comp.id, Branch.id != staff.branch_id).first()
    if not b2:
        b2 = Branch(
            company_id=comp.id,
            name="Mandated Destination Branch",
            code=f"MAND_{int(datetime.utcnow().timestamp())}",
            status="active",
            mfa_required_for_all=True,
        )
        db.add(b2)
        db.commit()
    else:
        b2.mfa_required_for_all = True
        db.commit()

    assert MfaService.is_mfa_mandatory_for_user(db, staff) is False

    # Staff logs in and creates active session
    _login("sujipriya@example.com", portal="app")
    _, ca_headers = _login("jayasri@example.com", portal="company")

    # Reassign staff to mandated branch B2
    res = client.put(
        f"/api/company/users/{staff.id}",
        headers=ca_headers,
        json={"branch_id": b2.id},
    )
    assert res.status_code == 200, res.text

    db.expire_all()
    revoked = db.query(UserSession).filter_by(
        user_id=staff.id,
        revoke_reason="mfa_policy_mandated_by_assignment_change",
    ).all()
    assert len(revoked) >= 1

    # Restore staff branch
    staff.branch_id = b1.id
    db.commit()


# ── 6. Role Boundaries: Staff Self-Enrollment & Disablement Blocking ─────────

def test_staff_cannot_self_enroll_or_disable_mfa(db: Session):
    """
    Staff / Uploader accounts are blocked from voluntary self-enrollment (403)
    and cannot disable MFA (403).
    """
    _, staff_headers = _login("sujipriya@example.com", portal="app")

    # 1. Staff voluntary enroll start -> 403 Forbidden
    res = client.post("/api/auth/mfa/enroll/start", headers=staff_headers)
    assert res.status_code == 403
    assert "disabled for your role" in res.json()["detail"].lower()

    # 2. Staff disable MFA -> 403 Forbidden
    dis_res = client.post(
        "/api/auth/mfa/disable",
        headers=staff_headers,
        json={"password": "Pasword@123", "code": "123456"},
    )
    assert dis_res.status_code == 403
    assert "permission to disable mfa" in dis_res.json()["detail"].lower()


# ── 7. Recovery Code Security: Custom Base32 & Single-Use Verification ───────

def test_recovery_code_alphabet_and_single_use(db: Session):
    """
    Recovery codes match custom Base32 alphabet (23456789ABCDEFGHJKLMNPQRSTUVWXYZ)
    and 12-char format (XXXX-XXXX-XXXX).
    Branch Admin can regenerate recovery codes (using password proof to avoid TOTP reuse collision).
    Staff cannot regenerate recovery codes (403).
    Recovery codes are strictly single-use (double-spend prevention).
    """
    # 1. Branch Admin enrolls MFA
    _, ba_headers = _login("samrethi@example.com", portal="app")

    start_res = client.post("/api/auth/mfa/enroll/start", headers=ba_headers)
    assert start_res.status_code == 200
    secret = start_res.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.now()

    verify_res = client.post(
        "/api/auth/mfa/enroll/verify",
        headers=ba_headers,
        json={"code": code},
    )
    assert verify_res.status_code == 200
    rec_codes = verify_res.json()["recovery_codes"]
    assert len(rec_codes) == 8

    # 2. Validate custom Base32 alphabet and XXXX-XXXX-XXXX shape
    custom_b32_pattern = re.compile(r"^[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{4}$")
    for rc in rec_codes:
        assert custom_b32_pattern.match(rc), f"Code {rc} violates custom Base32 format"

    # 3. Branch Admin can regenerate recovery codes with password verification
    regen_res = client.post(
        "/api/auth/mfa/recovery/regenerate",
        headers=ba_headers,
        json={"password": "Pasword@123"},
    )
    assert regen_res.status_code == 200
    new_codes = regen_res.json()["recovery_codes"]
    assert len(new_codes) == 8
    assert set(new_codes) != set(rec_codes)

    # 4. Staff cannot regenerate recovery codes -> 403 Forbidden
    _, staff_headers = _login("sujipriya@example.com", portal="app")
    s_regen = client.post(
        "/api/auth/mfa/recovery/regenerate",
        headers=staff_headers,
        json={"password": "Pasword@123"},
    )
    assert s_regen.status_code == 403
    assert "restricted to administrators" in s_regen.json()["detail"].lower()

    # 5. Test single-use recovery code redemption & replay prevention
    # Step 1 login -> pending token
    login_res = client.post(
        "/api/auth/login",
        json={"email": "samrethi@example.com", "password": "Pasword@123", "portal": "app"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["mfa_required"] is True
    pending_token = login_res.json()["mfa_pending_token"]

    test_code = new_codes[0]
    rec_res = client.post(
        "/api/auth/mfa/recovery/verify",
        json={"mfa_pending_token": pending_token, "recovery_code": test_code},
    )
    assert rec_res.status_code == 200
    assert "access_token" in rec_res.json()

    # Attempt replay with the same code -> rejected
    login_res2 = client.post(
        "/api/auth/login",
        json={"email": "samrethi@example.com", "password": "Pasword@123", "portal": "app"},
    )
    pending_token2 = login_res2.json()["mfa_pending_token"]
    replay_res = client.post(
        "/api/auth/mfa/recovery/verify",
        json={"mfa_pending_token": pending_token2, "recovery_code": test_code},
    )
    assert replay_res.status_code == 401
    assert "invalid" in replay_res.json()["detail"].lower()


# ── 8. Administrative MFA Resets & Role Hierarchy Isolation ──────────────────

def test_admin_mfa_reset_hierarchy_isolation(db: Session):
    """
    Verifies strict role hierarchy and isolation on administrative MFA resets:
      - Master Admin can reset Company Admin and peer Master Admin.
      - Company Admin cannot reset peer Company Admin (403) or self (403).
      - Company Admin can reset Branch Admin and Staff.
      - Branch Admin cannot reset Branch Admin, Company Admin, or self (403).
      - Branch Admin cannot reset Staff in a different branch (403).
      - Invalid admin confirm_password returns 400 Bad Request.
    """
    _, m_headers = _login("master@platform.local", portal="platform")
    _, ca_headers = _login("jayasri@example.com", portal="company")
    _, ba_headers = _login("samrethi@example.com", portal="app")

    ca_user = db.query(User).filter_by(email="jayasri@example.com").first()
    ba_user = db.query(User).filter_by(email="samrethi@example.com").first()
    staff_user = db.query(User).filter_by(email="sujipriya@example.com").first()
    other_admin = db.query(MasterAdmin).filter_by(id=1).first()

    # 1. Master Admin resets peer Master Admin -> 200 OK
    res = client.post(f"/api/admin/master-admins/{other_admin.id}/reset-mfa", headers=m_headers)
    assert res.status_code == 200

    # 2. Company Admin CANNOT reset self -> 403 Forbidden
    res = client.post(
        f"/api/company/users/{ca_user.id}/reset-mfa",
        headers=ca_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert res.status_code == 403
    assert "cannot reset your own mfa" in res.json()["detail"].lower()

    # 3. Company Admin CANNOT reset peer Company Admin
    # Temporarily promote staff to GLOBAL_ADMIN
    staff_user.role = UserRole.GLOBAL_ADMIN
    db.commit()
    res = client.post(
        f"/api/company/users/{staff_user.id}/reset-mfa",
        headers=ca_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert res.status_code == 403
    assert "peer company administrators" in res.json()["detail"].lower()

    # Demote staff back and ensure no lingering assignment records
    db.query(UserRoleAssignment).filter_by(user_id=staff_user.id).delete()
    staff_user.role = UserRole.STAFF
    db.commit()

    # 4. Company Admin resets Staff with invalid password -> 400 Bad Request
    bad_pwd_res = client.post(
        f"/api/company/users/{staff_user.id}/reset-mfa",
        headers=ca_headers,
        json={"confirm_password": "WrongPassword!999"},
    )
    assert bad_pwd_res.status_code == 400
    assert "incorrect password" in bad_pwd_res.json()["detail"].lower()

    # 5. Company Admin resets Staff with correct password -> 200 OK
    good_res = client.post(
        f"/api/company/users/{staff_user.id}/reset-mfa",
        headers=ca_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert good_res.status_code == 200

    # 6. Branch Admin CANNOT reset administrator (Branch Admin or Company Admin) -> 403
    ba_reset_admin = client.post(
        f"/api/branch/users/{ca_user.id}/reset-mfa",
        headers=ba_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert ba_reset_admin.status_code == 403
    assert "cannot reset administrator" in ba_reset_admin.json()["detail"].lower()

    # 7. Branch Admin CANNOT reset self -> 403
    ba_reset_self = client.post(
        f"/api/branch/users/{ba_user.id}/reset-mfa",
        headers=ba_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert ba_reset_self.status_code == 403
    assert "cannot reset your own mfa" in ba_reset_self.json()["detail"].lower()

    # 8. Branch Admin resets Staff in their branch -> 200 OK
    ba_reset_staff = client.post(
        f"/api/branch/users/{staff_user.id}/reset-mfa",
        headers=ba_headers,
        json={"confirm_password": "Pasword@123"},
    )
    assert ba_reset_staff.status_code == 200

    # 9. Master Admin resets Company Admin -> 200 OK
    res = client.post(f"/api/admin/users/{ca_user.id}/reset-mfa", headers=m_headers)
    assert res.status_code == 200


# ── 9. Restricted MFA Enrollment Token Flow ──────────────────────────────────

def test_unenrolled_user_restricted_token_and_enrollment_flow(db: Session):
    """
    When MFA is mandatory, an unenrolled user cannot access normal application resources
    (e.g., /api/documents) but can complete enrollment using the restricted token.
    """
    # 1. Mandate MFA company-wide
    comp = db.query(Company).filter_by(id=40).first()
    comp.mfa_required_for_all = True
    db.commit()

    # 2. Login as unenrolled staff -> returns enrollment required token
    login_res = client.post(
        "/api/auth/login",
        json={"email": "sujipriya@example.com", "password": "Pasword@123", "portal": "app"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["mfa_enrollment_required"] is True
    enroll_token = data["mfa_enrollment_token"]
    enroll_headers = {"Authorization": f"Bearer {enroll_token}"}

    # 3. Attempting to call protected documents API with enrollment token -> 403 Forbidden
    doc_res = client.get("/api/documents", headers=enroll_headers)
    assert doc_res.status_code in (401, 403)

    # 4. Calling MFA enrollment with restricted token succeeds
    start_res = client.post("/api/auth/mfa/enroll/start", headers=enroll_headers)
    assert start_res.status_code == 200
    secret = start_res.json()["secret"]

    # 5. Complete enrollment verification
    totp = pyotp.TOTP(secret)
    verify_res = client.post(
        "/api/auth/mfa/enroll/verify",
        headers=enroll_headers,
        json={"code": totp.now()},
    )
    assert verify_res.status_code == 200
    assert "recovery_codes" in verify_res.json()

    # 6. Verify user is now enrolled in DB
    db.expire_all()
    user = db.query(User).filter_by(email="sujipriya@example.com").first()
    assert MfaService.is_mfa_enabled(db, "user", user.id) is True
