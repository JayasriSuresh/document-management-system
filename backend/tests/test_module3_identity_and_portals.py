"""
Module 3: Cross-Portal Authentication, Session Lifecycle, and Identity Tests.

Verifies:
  1. Portal Separation Matrix:
     - Master Admin -> Platform only (aud="platform")
     - Company Admin -> Company only (aud="company")
     - Branch Staff/Admin -> App only (aud="app")
     - Cross-portal login rejection
  2. Strict JWT Audience and Portal Dependencies
  3. Durable Refresh Sessions, Token Rotation & Replay Attack Detection
  4. Logout and Logout-All Invalidation
  5. Account Lockout & Status Enforcement
  6. Workspace Invitations & Role Escalation Guards
  7. Password Recovery with Anti-Enumeration & Session Revocation
"""

import time
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import create_access_token, decode_token, get_password_hash
from app.config import settings
from app.main import app
from app.models import (
    AccountStatus,
    Branch,
    Company,
    CompanyStatus,
    Invitation,
    MasterAdmin,
    PasswordReset,
    User,
    UserRole,
    UserSession,
)
from app.services.session_service import hash_token, session_service


# ── FIXTURES ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def portal_client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def test_identities(db):
    """
    Ensure all portal identities exist with known credentials:
      - MasterAdmin: master@platform.local / Pasword@123
      - Company Admin: jayasri@example.com / Pasword@123 (Vasanth & Co, Chennai)
      - Branch Admin: samrethi@example.com / Pasword@123 (Vasanth & Co, Chennai)
      - Staff: sujipriya@example.com / Pasword@123 (Vasanth & Co, Chennai)
    """
    hashed = get_password_hash("Pasword@123")

    # 1. Master Admin
    m_admin = db.query(MasterAdmin).filter(MasterAdmin.email == "master@platform.local").first()
    if not m_admin:
        m_admin = MasterAdmin(
            name="Platform Root Admin",
            email="master@platform.local",
            password_hash=hashed,
            status=AccountStatus.ACTIVE,
            token_version=1,
            failed_attempts=0,
            locked_until=None,
        )
        db.add(m_admin)
    else:
        m_admin.status = AccountStatus.ACTIVE
        m_admin.failed_attempts = 0
        m_admin.locked_until = None
        m_admin.password_hash = hashed

    # Reset test users
    for email, role in [
        ("jayasri@example.com", UserRole.GLOBAL_ADMIN),
        ("samrethi@example.com", UserRole.ADMIN),
        ("sujipriya@example.com", UserRole.STAFF),
    ]:
        u = db.query(User).filter(User.email == email).first()
        if u:
            u.status = AccountStatus.ACTIVE
            u.failed_attempts = 0
            u.locked_until = None
            u.must_change_password = False
            u.password_hash = hashed

    db.commit()
    return {
        "master_email": "master@platform.local",
        "company_admin_email": "jayasri@example.com",
        "branch_admin_email": "samrethi@example.com",
        "staff_email": "sujipriya@example.com",
        "password": "Pasword@123",
    }


# ── SECTION A: PORTAL LOGIN & CROSS-PORTAL ENFORCEMENT ────────────────────────

def test_master_admin_can_login_platform_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["master_email"],
            "password": test_identities["password"],
            "portal": "platform",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["portal"] == "platform"
    assert data["user"]["role"] == "MASTER_ADMIN"
    assert "access_token" in data

    payload = decode_token(data["access_token"], audience=settings.JWT_AUDIENCE_PLATFORM)
    assert payload["aud"] == "platform"
    assert payload["identity_type"] == "master_admin"


def test_master_admin_cannot_login_company_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["master_email"],
            "password": test_identities["password"],
            "portal": "company",
        },
    )
    # MasterAdmin does not exist in tenant users table
    assert resp.status_code == 401


def test_master_admin_cannot_login_app_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["master_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    assert resp.status_code == 401


def test_company_admin_can_login_company_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["company_admin_email"],
            "password": test_identities["password"],
            "portal": "company",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["portal"] == "company"
    assert data["user"]["role"] == "GLOBAL_ADMIN"

    payload = decode_token(data["access_token"], audience=settings.JWT_AUDIENCE_COMPANY)
    assert payload["aud"] == "company"
    assert payload["role"] == "GLOBAL_ADMIN"


def test_company_admin_cannot_login_platform_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["company_admin_email"],
            "password": test_identities["password"],
            "portal": "platform",
        },
    )
    # Tenant user not in master_admins table
    assert resp.status_code == 401


def test_company_admin_cannot_login_app_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["company_admin_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    # Global Admin is barred from Branch App Portal
    assert resp.status_code == 403
    assert "branch workspace" in resp.json()["detail"].lower()


def test_branch_staff_can_login_app_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["portal"] == "app"
    assert data["user"]["role"] == "STAFF"

    payload = decode_token(data["access_token"], audience=settings.JWT_AUDIENCE_APP)
    assert payload["aud"] == "app"


def test_branch_staff_cannot_login_company_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "company",
        },
    )
    assert resp.status_code == 403
    assert "company admin" in resp.json()["detail"].lower()


def test_branch_staff_cannot_login_platform_portal(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "platform",
        },
    )
    assert resp.status_code == 401


def test_invalid_portal_identifier_rejected(portal_client, test_identities):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "superuser_portal",
        },
    )
    assert resp.status_code == 400
    assert "invalid portal" in resp.json()["detail"].lower()


# ── SECTION B: JWT AUDIENCE & REJECTION MATRIX ────────────────────────────────

def test_jwt_wrong_audience_strictly_rejected(test_identities):
    token = create_access_token({"sub": "admin"}, audience="platform")

    # Asking for "company" audience must fail
    with pytest.raises(HTTPException) as exc:
        decode_token(token, audience="company")
    assert exc.value.status_code == 401
    assert "audience" in exc.value.detail.lower()

    # Asking for "app" audience must fail
    with pytest.raises(HTTPException) as exc:
        decode_token(token, audience="app")
    assert exc.value.status_code == 401


# ── SECTION C: DURABLE SESSIONS & TOKEN ROTATION ──────────────────────────────

def test_login_creates_database_session_and_cookie(portal_client, test_identities, db):
    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    assert resp.status_code == 200
    cookie = resp.cookies.get("dms_refresh_token")
    assert cookie is not None

    # Check DB: raw token must NOT be in DB
    raw_match = db.query(UserSession).filter(UserSession.token_hash == cookie).first()
    assert raw_match is None, "Raw refresh token must never be stored in database!"

    # SHA-256 hash MUST be in DB
    hashed = hash_token(cookie)
    session = db.query(UserSession).filter(UserSession.token_hash == hashed).first()
    assert session is not None
    assert session.identity_type == "user"
    assert session.revoked_at is None


def test_refresh_rotates_token_and_preserves_family(portal_client, test_identities, db):
    # 1. Login
    login_resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    old_cookie = login_resp.cookies.get("dms_refresh_token")

    # 2. Refresh
    portal_client.cookies.set("dms_refresh_token", old_cookie)
    ref_resp = portal_client.post("/api/auth/refresh")
    assert ref_resp.status_code == 200
    new_data = ref_resp.json()
    assert "access_token" in new_data

    new_cookie = ref_resp.cookies.get("dms_refresh_token")
    assert new_cookie != old_cookie

    # 3. Verify in DB
    old_session = db.query(UserSession).filter(UserSession.token_hash == hash_token(old_cookie)).first()
    new_session = db.query(UserSession).filter(UserSession.token_hash == hash_token(new_cookie)).first()

    assert old_session.revoked_at is not None
    assert old_session.revoke_reason == "rotated"
    assert new_session.revoked_at is None
    assert new_session.family_id == old_session.family_id
    assert new_session.parent_session_id == old_session.id


def test_refresh_token_replay_attack_revokes_token_family(portal_client, test_identities, db):
    # 1. Login
    login_resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["branch_admin_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    token_1 = login_resp.cookies.get("dms_refresh_token")

    # 2. Legitimate refresh: rotates token_1 -> token_2
    portal_client.cookies.set("dms_refresh_token", token_1)
    ref1 = portal_client.post("/api/auth/refresh")
    token_2 = ref1.cookies.get("dms_refresh_token")

    # 3. Attacker replays token_1!
    portal_client.cookies.set("dms_refresh_token", token_1)
    replay_resp = portal_client.post("/api/auth/refresh")
    assert replay_resp.status_code == 401
    assert "compromised" in replay_resp.json()["detail"].lower()

    # 4. Replay detection must have revoked ALL sessions in family (including token_2)
    s2 = db.query(UserSession).filter(UserSession.token_hash == hash_token(token_2)).first()
    assert s2.revoked_at is not None
    assert s2.revoke_reason == "replay_attack_detected"

    # Subsequent refresh with token_2 must now fail as well
    portal_client.cookies.set("dms_refresh_token", token_2)
    ref2 = portal_client.post("/api/auth/refresh")
    assert ref2.status_code == 401


def test_logout_revokes_current_session(portal_client, test_identities, db):
    login_resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    cookie = login_resp.cookies.get("dms_refresh_token")

    portal_client.cookies.set("dms_refresh_token", cookie)
    logout_resp = portal_client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    # Cookie must be cleared in response
    assert logout_resp.cookies.get("dms_refresh_token") is None

    # DB session must be revoked
    session = db.query(UserSession).filter(UserSession.token_hash == hash_token(cookie)).first()
    assert session.revoked_at is not None
    assert session.revoke_reason == "logout"

    # Attempting to refresh should now be rejected
    portal_client.cookies.set("dms_refresh_token", cookie)
    ref = portal_client.post("/api/auth/refresh")
    assert ref.status_code == 401


def test_logout_all_revokes_all_sessions_and_increments_token_version(portal_client, test_identities, db):
    # Login twice to create two sessions
    resp1 = portal_client.post(
        "/api/auth/login",
        json={"email": test_identities["staff_email"], "password": test_identities["password"], "portal": "app"},
    )
    resp2 = portal_client.post(
        "/api/auth/login",
        json={"email": test_identities["staff_email"], "password": test_identities["password"], "portal": "app"},
    )
    token = resp2.json()["access_token"]
    user_before = db.query(User).filter(User.email == test_identities["staff_email"]).first()
    tv_before = user_before.token_version

    # Call logout-all
    logout_all_resp = portal_client.post("/api/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
    assert logout_all_resp.status_code == 200

    # Token version must be incremented
    db.refresh(user_before)
    assert user_before.token_version == tv_before + 1

    # Old access token must now be rejected immediately on /me
    me_resp = portal_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 401
    assert "revoked" in me_resp.json()["detail"].lower()


# ── SECTION D: ACCOUNT LIFECYCLE & LOCKOUT ────────────────────────────────────

def test_account_lockout_after_five_failed_attempts(portal_client, test_identities, db):
    email = test_identities["staff_email"]

    # 5 failed login attempts
    for _ in range(5):
        resp = portal_client.post(
            "/api/auth/login",
            json={"email": email, "password": "WrongPassword", "portal": "app"},
        )
        assert resp.status_code == 401

    # 6th attempt must be locked (HTTP 423)
    resp6 = portal_client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword", "portal": "app"},
    )
    assert resp6.status_code == 423
    assert "locked" in resp6.json()["detail"].lower()

    # Even with the correct password, it must remain locked!
    resp_correct = portal_client.post(
        "/api/auth/login",
        json={"email": email, "password": test_identities["password"], "portal": "app"},
    )
    assert resp_correct.status_code == 423

    # Clean up lockout in DB
    u = db.query(User).filter(User.email == email).first()
    u.locked_until = None
    u.failed_attempts = 0
    db.commit()


def test_inactive_account_blocked_from_login(portal_client, test_identities, db):
    u = db.query(User).filter(User.email == test_identities["staff_email"]).first()
    u.status = AccountStatus.INACTIVE
    db.commit()

    resp = portal_client.post(
        "/api/auth/login",
        json={
            "email": test_identities["staff_email"],
            "password": test_identities["password"],
            "portal": "app",
        },
    )
    assert resp.status_code == 403
    assert "inactive" in resp.json()["detail"].lower()

    # Restore
    u.status = AccountStatus.ACTIVE
    db.commit()


# ── SECTION E: WORKSPACE INVITATIONS ──────────────────────────────────────────

def test_invitation_flow_and_atomic_acceptance(portal_client, test_identities, db):
    # 1. Company Admin logs in
    admin_login = portal_client.post(
        "/api/auth/login",
        json={"email": test_identities["company_admin_email"], "password": test_identities["password"], "portal": "company"},
    )
    admin_token = admin_login.json()["access_token"]

    # 2. Issue invitation for new employee
    invitee_email = "new_engineer@vasanth.co"
    # Ensure not existing from prior test runs
    db.query(User).filter(User.email == invitee_email).delete()
    db.query(Invitation).filter(Invitation.email == invitee_email).delete()
    db.commit()

    company = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    branch = db.query(Branch).filter(Branch.company_id == company.id).first()

    invite_resp = portal_client.post(
        "/api/auth/invite",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": invitee_email,
            "branch_id": branch.id,
            "invited_role": "STAFF",
        },
    )
    assert invite_resp.status_code == 200

    # 3. Fetch invitation token from DB for test
    inv = db.query(Invitation).filter(Invitation.email == invitee_email).first()
    assert inv is not None
    assert inv.accepted_at is None

    # Simulate acceptance using raw token retrieved from memory/service or by generating one
    # Let's test acceptance endpoint directly
    from app.services.invitation_service import hash_token
    import secrets
    raw_token = secrets.token_hex(32)
    inv.token_hash = hash_token(raw_token)
    db.commit()

    accept_resp = portal_client.post(
        "/api/auth/invite/accept",
        json={
            "token": raw_token,
            "name": "New Engineer",
            "password": "SecurePassword@2026",
        },
    )
    assert accept_resp.status_code == 200

    # 4. Verify created user in DB
    new_user = db.query(User).filter(User.email == invitee_email).first()
    assert new_user is not None
    assert new_user.name == "New Engineer"
    assert new_user.role == UserRole.STAFF
    vasanth = db.query(Company).filter(Company.code == "VASANTH_CO").first()
    assert new_user.company_id == vasanth.id  # Vasanth & Co

    # 5. Verify created user can now log into App Portal!
    user_login = portal_client.post(
        "/api/auth/login",
        json={"email": invitee_email, "password": "SecurePassword@2026", "portal": "app"},
    )
    assert user_login.status_code == 200


def test_invitation_role_escalation_blocked(portal_client, test_identities):
    # Branch admin logs in
    admin_login = portal_client.post(
        "/api/auth/login",
        json={"email": test_identities["branch_admin_email"], "password": test_identities["password"], "portal": "app"},
    )
    admin_token = admin_login.json()["access_token"]

    # Branch admin tries to invite a GLOBAL_ADMIN
    resp = portal_client.post(
        "/api/auth/invite",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "email": "escalate@example.com",
            "branch_id": 1,
            "invited_role": "GLOBAL_ADMIN",
        },
    )
    assert resp.status_code == 403
    assert "cannot invite global admins" in resp.json()["detail"].lower()


# ── SECTION F: PASSWORD RECOVERY ──────────────────────────────────────────────

def test_password_reset_request_anti_enumeration(portal_client):
    # Existing user
    resp1 = portal_client.post(
        "/api/auth/password/reset-request",
        json={"email": "sujipriya@example.com", "portal": "app"},
    )
    # Non-existing user
    resp2 = portal_client.post(
        "/api/auth/password/reset-request",
        json={"email": "ghost_user_999@unknown.org", "portal": "app"},
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Must return EXACT same message to prevent username enumeration!
    assert resp1.json()["message"] == resp2.json()["message"]


def test_password_reset_flow_and_session_revocation(portal_client, test_identities, db):
    email = test_identities["staff_email"]

    # 1. Login to get an active session
    login_resp = portal_client.post(
        "/api/auth/login",
        json={"email": email, "password": test_identities["password"], "portal": "app"},
    )
    old_token = login_resp.json()["access_token"]

    # 2. Create password reset token in DB
    import secrets
    raw_token = secrets.token_hex(32)
    u = db.query(User).filter(User.email == email).first()
    pr = PasswordReset(
        identity_type="user",
        user_id=u.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )
    db.add(pr)
    db.commit()

    # 3. Redeem reset token
    new_pw = "BrandNewPassword@2026"
    reset_resp = portal_client.post(
        "/api/auth/password/reset",
        json={"token": raw_token, "new_password": new_pw},
    )
    assert reset_resp.status_code == 200

    # 4. Old access token must now be rejected
    me_resp = portal_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert me_resp.status_code == 401

    # 5. User can log in with new password
    new_login = portal_client.post(
        "/api/auth/login",
        json={"email": email, "password": new_pw, "portal": "app"},
    )
    assert new_login.status_code == 200

    # Restore default password for test cleanliness
    u.password_hash = get_password_hash(test_identities["password"])
    db.commit()
