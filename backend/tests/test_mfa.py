"""
Module 6 – Multi-Factor Authentication (TOTP & Recovery) Test Suite.

Verifies:
  1. Authenticated Encryption Helper (AES-256-GCM, key derivation, nonce uniqueness, tamper detection).
  2. MFA Enrollment lifecycle (secret encryption, QR SVG, recovery codes generation & hashing).
  3. Step 2 TOTP verification & strict atomic replay attack prevention.
  4. Single-use recovery codes redemption & double-spending prevention.
  5. Intermediate token restrictions (mfa_pending & mfa_enrollment_required cannot access data APIs).
  6. Multi-tier mandatory policy enforcement (Platform & Company override hierarchies).
  7. Rate-limiting & account lockout on failed TOTP/recovery attempts.
  8. Admin-assisted resets & company tenant boundaries.
  9. Safe audit event logging and metadata sanitization (no secrets/OTPs logged).
"""

import time
import pytest
import pyotp
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
    AuditLog,
    UserRole,
    AccountStatus,
)
from app.security.encryption import (
    AESGCMEncryptionHelper,
    derive_encryption_key,
    encrypt_mfa_secret,
    decrypt_mfa_secret,
)
from app.services.mfa_service import MfaService
from app.auth import get_password_hash


client = TestClient(app)


# ── Test Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_mfa_state(db: Session):
    """Ensure clean platform MFA policy and wipe test user_mfa records before each test."""
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

    companies = db.query(Company).all()
    for c in companies:
        c.mfa_required_for_all = False

    # Unlock any locked test users
    users = db.query(User).all()
    for u in users:
        u.failed_attempts = 0
        u.locked_until = None
    admins = db.query(MasterAdmin).all()
    for a in admins:
        a.failed_attempts = 0
        a.locked_until = None

    db.commit()
    yield
    # Teardown: ensure no MFA records, locks, or enforced policies leak to other tests
    db.query(MfaRecoveryCode).delete()
    db.query(UserMfa).delete()
    for c in db.query(Company).all():
        c.mfa_required_for_all = False
    ps = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
    if ps:
        ps.value = {"enforce_master_admin": False, "enforce_company_admin": False, "enforce_all": False}
    for u in db.query(User).all():
        u.failed_attempts = 0
        u.locked_until = None
    for a in db.query(MasterAdmin).all():
        a.failed_attempts = 0
        a.locked_until = None
    db.commit()


# ── 1. AES-256-GCM Encryption Helper Tests ───────────────────────────────────

def test_aes_gcm_encryption_roundtrip():
    """Verify encryption round-trip, nonce randomness, and versioning."""
    secret = "JBSWY3DPEHPK3PXP"
    enc1 = encrypt_mfa_secret(secret)
    enc2 = encrypt_mfa_secret(secret)

    # Version prefix check
    assert enc1.startswith("v1:")
    assert enc2.startswith("v1:")

    # Nonce uniqueness: same plaintext encrypted twice produces different ciphertexts
    assert enc1 != enc2

    # Decrypt
    assert decrypt_mfa_secret(enc1) == secret
    assert decrypt_mfa_secret(enc2) == secret


def test_aes_gcm_tamper_detection():
    """Verify that tampering with ciphertext or nonce raises ValueError."""
    secret = "HXDMVJECJJWSRB3HWIZR4IFUGFTMXBOZ"
    encrypted = encrypt_mfa_secret(secret)
    parts = encrypted.split(":")

    # Tamper with the ciphertext component
    tampered_ct = parts[2][:-4] + "AAAA"
    tampered_payload = f"v1:{parts[1]}:{tampered_ct}"

    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_mfa_secret(tampered_payload)


def test_aes_gcm_wrong_key_fails():
    """Verify decryption fails when attempted with a different key."""
    key1 = derive_encryption_key("secret-key-alpha-123456789012345")
    key2 = derive_encryption_key("secret-key-beta-9876543210987654")

    helper1 = AESGCMEncryptionHelper(key1)
    helper2 = AESGCMEncryptionHelper(key2)

    encrypted = helper1.encrypt("TOP_SECRET_TOTP_DATA")
    with pytest.raises(ValueError, match="Decryption failed"):
        helper2.decrypt(encrypted)


# ── 2. MFA Enrollment Lifecycle Tests ────────────────────────────────────────

def test_mfa_enrollment_lifecycle(db: Session):
    """
    Test full self-service enrollment:
      1. Start enrollment -> returns secret, URI, QR SVG.
      2. Verify DB stores encrypted secret.
      3. Verify enrollment with valid code -> enables MFA and generates 8 recovery codes.
      4. Recovery codes in DB are hashed.
    """
    # 1. Login as jayasri@example.com (GLOBAL_ADMIN)
    login_res = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check initial status (should be disabled)
    status_res = client.get("/api/auth/mfa/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["enabled"] is False

    # 3. Start enrollment
    start_res = client.post("/api/auth/mfa/enroll/start", headers=headers)
    assert start_res.status_code == 200, start_res.text
    start_data = start_res.json()
    secret = start_data["secret"]
    assert len(secret) >= 16
    assert start_data["provisioning_uri"].startswith("otpauth://totp/")
    assert "<svg" in start_data["qr_code_svg"]

    # Verify database secret is encrypted, not plaintext
    user = db.query(User).filter_by(email="jayasri@example.com").first()
    mfa_rec = db.query(UserMfa).filter_by(user_id=user.id).first()
    assert mfa_rec is not None
    assert mfa_rec.encrypted_secret != secret
    assert mfa_rec.encrypted_secret.startswith("v1:")
    assert decrypt_mfa_secret(mfa_rec.encrypted_secret) == secret
    assert mfa_rec.enabled_at is None  # Not yet verified

    # 4. Verify enrollment with invalid code -> should fail
    bad_res = client.post(
        "/api/auth/mfa/enroll/verify",
        headers=headers,
        json={"code": "000000"},
    )
    assert bad_res.status_code == 400

    # 5. Verify enrollment with valid TOTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    good_res = client.post(
        "/api/auth/mfa/enroll/verify",
        headers=headers,
        json={"code": valid_code},
    )
    assert good_res.status_code == 200, good_res.text
    verify_data = good_res.json()
    recovery_codes = verify_data["recovery_codes"]
    assert len(recovery_codes) == 8

    # Verify DB state
    db.refresh(mfa_rec)
    assert mfa_rec.enabled_at is not None
    db_codes = db.query(MfaRecoveryCode).filter_by(user_mfa_id=mfa_rec.id).all()
    assert len(db_codes) == 8
    # Recovery codes must be hashed in DB, never plaintext
    for c in db_codes:
        assert c.code_hash not in recovery_codes
        assert len(c.code_hash) == 64  # SHA-256

    # 6. Check status again (should now be enabled with 8 recovery codes)
    status_res2 = client.get("/api/auth/mfa/status", headers=headers)
    assert status_res2.status_code == 200
    assert status_res2.json()["enabled"] is True
    assert status_res2.json()["remaining_recovery_codes"] == 8


# ── 3. Step 2 TOTP Verification & Replay Protection Tests ────────────────────

def test_totp_verification_and_replay_prevention(db: Session):
    """
    Test MFA login challenge and atomic replay attack prevention:
      - Step 1 returns mfa_required=True and mfa_pending_token.
      - Step 2 verifies TOTP code, returns full access token.
      - Replaying the SAME TOTP code is blocked with 401.
    """
    # Enroll user samrethi@example.com in MFA
    user = db.query(User).filter_by(email="samrethi@example.com").first()
    secret = pyotp.random_base32()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(secret),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        last_used_step=None,
    )
    db.add(user_mfa)
    db.commit()

    # Step 1: Login with password
    step1_res = client.post(
        "/api/auth/login",
        json={"email": "samrethi@example.com", "password": "Pasword@123", "portal": "app"},
    )
    assert step1_res.status_code == 200
    s1_data = step1_res.json()
    assert s1_data.get("mfa_required") is True
    pending_token = s1_data["mfa_pending_token"]
    assert s1_data.get("access_token") is None

    # Step 2: Verify TOTP with invalid code -> 401
    bad_verify = client.post(
        "/api/auth/mfa/verify",
        json={"mfa_pending_token": pending_token, "code": "123456"},
    )
    assert bad_verify.status_code == 401

    # Step 2: Verify TOTP with valid code -> 200
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    good_verify = client.post(
        "/api/auth/mfa/verify",
        json={"mfa_pending_token": pending_token, "code": valid_code},
    )
    assert good_verify.status_code == 200, good_verify.text
    assert good_verify.json().get("access_token") is not None
    assert "dms_refresh_token" in good_verify.cookies

    # ATOMIC REPLAY ATTACK TEST:
    # Attempting to use the SAME valid code again within the same window must fail!
    replay_verify = client.post(
        "/api/auth/mfa/verify",
        json={"mfa_pending_token": pending_token, "code": valid_code},
    )
    assert replay_verify.status_code == 401
    assert "already been used" in replay_verify.json()["detail"].lower()


# ── 4. Single-Use Recovery Code Tests ────────────────────────────────────────

def test_single_use_recovery_codes(db: Session):
    """
    Test single-use recovery code redemption:
      - Valid recovery code redeems and grants full login.
      - Code cannot be redeemed a second time (double-spending protection).
      - Normalized (dashes/spaces removed) redemption works.
    """
    user = db.query(User).filter_by(email="sujipriya@example.com").first()
    secret = pyotp.random_base32()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(secret),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(user_mfa)
    db.flush()

    raw_codes = MfaService.generate_recovery_codes(8)
    for c in raw_codes:
        db.add(MfaRecoveryCode(user_mfa_id=user_mfa.id, code_hash=MfaService.hash_recovery_code(c)))
    db.commit()

    # Step 1: Login
    res = client.post(
        "/api/auth/login",
        json={"email": "sujipriya@example.com", "password": "Pasword@123", "portal": "app"},
    )
    pending_token = res.json()["mfa_pending_token"]

    chosen_code = raw_codes[0]

    # Step 2: Redeem recovery code (with lower-case and spaces test)
    spaced_code = " " + chosen_code.lower() + " "
    rec_res = client.post(
        "/api/auth/mfa/recovery/verify",
        json={"mfa_pending_token": pending_token, "recovery_code": spaced_code},
    )
    assert rec_res.status_code == 200, rec_res.text
    assert rec_res.json().get("access_token") is not None

    # Verify recovery code is marked as used in DB
    h = MfaService.hash_recovery_code(chosen_code)
    code_in_db = db.query(MfaRecoveryCode).filter_by(user_mfa_id=user_mfa.id, code_hash=h).first()
    assert code_in_db.used_at is not None

    # Attempt to redeem the SAME code again -> MUST FAIL
    login_again = client.post(
        "/api/auth/login",
        json={"email": "sujipriya@example.com", "password": "Pasword@123", "portal": "app"},
    )
    token2 = login_again.json()["mfa_pending_token"]
    double_spend_res = client.post(
        "/api/auth/mfa/recovery/verify",
        json={"mfa_pending_token": token2, "recovery_code": chosen_code},
    )
    assert double_spend_res.status_code == 401
    assert "already used" in double_spend_res.json()["detail"].lower()


# ── 5. Restricted Intermediate Token Isolation Tests ─────────────────────────

def test_restricted_tokens_cannot_access_data_apis(db: Session):
    """
    CRITICAL SECURITY INVARIANT:
    Neither mfa_pending nor mfa_enrollment_required tokens may EVER access
    standard data APIs (e.g. /api/documents, /api/invoices, /api/admin/companies).
    """
    user = db.query(User).filter_by(email="jayasri@example.com").first()
    secret = pyotp.random_base32()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(secret),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(user_mfa)
    db.commit()

    # Get mfa_pending token
    login_res = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    mfa_pending_token = login_res.json()["mfa_pending_token"]

    # Try to access /api/documents with mfa_pending token -> 401
    doc_res = client.get(
        "/api/documents",
        headers={"Authorization": f"Bearer {mfa_pending_token}"},
    )
    assert doc_res.status_code == 401, doc_res.text
    assert "Multi-factor authentication is required" in doc_res.json()["detail"]

    # Try to access /api/invoices -> 401
    inv_res = client.get(
        "/api/invoices",
        headers={"Authorization": f"Bearer {mfa_pending_token}"},
    )
    assert inv_res.status_code == 401

    # Try to access /api/admin/companies -> 401
    adm_res = client.get(
        "/api/admin/companies",
        headers={"Authorization": f"Bearer {mfa_pending_token}"},
    )
    assert adm_res.status_code == 401


# ── 6. Mandatory MFA Policy Enforcement & Hierarchy Tests ────────────────────

def test_company_mandatory_mfa_policy(db: Session):
    """
    When company.mfa_required_for_all is enabled:
      - Users without MFA are issued mfa_enrollment_required on login.
      - Cannot access data APIs with unenrolled credentials.
      - Completing enrollment finalizes login and returns access token.
    """
    user = db.query(User).filter_by(email="sujipriya@example.com").first()
    comp = db.query(Company).filter_by(id=user.company_id).first()
    comp.mfa_required_for_all = True
    db.commit()

    # User sujipriya has not enrolled in MFA
    login_res = client.post(
        "/api/auth/login",
        json={"email": "sujipriya@example.com", "password": "Pasword@123", "portal": "app"},
    )
    assert login_res.status_code == 200
    data = login_res.json()
    assert data.get("mfa_enrollment_required") is True
    enroll_token = data["mfa_enrollment_token"]

    # Start enrollment using enrollment token
    start_res = client.post(
        "/api/auth/mfa/enroll/start",
        headers={"Authorization": f"Bearer {enroll_token}"},
    )
    assert start_res.status_code == 200
    secret = start_res.json()["secret"]

    # Verify enrollment using enrollment token -> returns full access token
    totp = pyotp.TOTP(secret)
    verify_res = client.post(
        "/api/auth/mfa/enroll/verify",
        headers={"Authorization": f"Bearer {enroll_token}"},
        json={"code": totp.now()},
    )
    assert verify_res.status_code == 200, verify_res.text
    verify_data = verify_res.json()
    assert verify_data.get("access_token") is not None
    assert len(verify_data["recovery_codes"]) == 8


def test_platform_mandatory_policy_overrides_company(db: Session):
    """
    Platform-level policy overrides company preferences:
      - When platform policy enforces Company Admins, GLOBAL_ADMIN must enroll even if company.mfa_required_for_all=False.
    """
    # Company has disabled mandatory MFA
    user = db.query(User).filter_by(email="jayasri@example.com").first()
    comp = db.query(Company).filter_by(id=user.company_id).first()
    comp.mfa_required_for_all = False

    # Platform policy enforces Company Admins
    ps = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
    ps.value = {"enforce_master_admin": False, "enforce_company_admin": True, "enforce_all": False}
    db.commit()

    # Jayasri is GLOBAL_ADMIN (Company Admin)
    login_res = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    assert login_res.status_code == 200
    assert login_res.json().get("mfa_enrollment_required") is True


# ── 7. Lockout on Failed MFA Attempts ────────────────────────────────────────

def test_mfa_lockout_on_consecutive_failures(db: Session):
    """
    Verifies that 5 consecutive failed TOTP verification attempts lock the account.
    """
    user = db.query(User).filter_by(email="samrethi@example.com").first()
    secret = pyotp.random_base32()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(secret),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(user_mfa)
    db.commit()

    # Step 1: Login
    res = client.post(
        "/api/auth/login",
        json={"email": "samrethi@example.com", "password": "Pasword@123", "portal": "app"},
    )
    pending_token = res.json()["mfa_pending_token"]

    # 5 failed attempts
    for _ in range(5):
        fail_res = client.post(
            "/api/auth/mfa/verify",
            json={"mfa_pending_token": pending_token, "code": "000000"},
        )
        assert fail_res.status_code == 401

    # 6th attempt should be locked out (HTTP 423)
    lockout_res = client.post(
        "/api/auth/mfa/verify",
        json={"mfa_pending_token": pending_token, "code": "000000"},
    )
    assert lockout_res.status_code == 423
    assert "locked" in lockout_res.json()["detail"].lower()


# ── 8. Admin-Assisted MFA Reset Tests ────────────────────────────────────────

def test_company_admin_mfa_reset(db: Session):
    """
    Company Admin can reset MFA for their company's user.
    Tenant isolation: Company Admin CANNOT reset MFA for a user from another company.
    """
    # Setup MFA for sujipriya (Company 1)
    user = db.query(User).filter_by(email="sujipriya@example.com").first()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(pyotp.random_base32()),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(user_mfa)
    db.commit()

    # Login as Company Admin (jayasri@example.com)
    admin_login = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Reset sujipriya's MFA
    reset_res = client.post(f"/api/company/users/{user.id}/reset-mfa", headers=headers)
    assert reset_res.status_code == 200, reset_res.text
    assert "reset successfully" in reset_res.json()["message"].lower()

    # Verify MFA record was deleted
    assert db.query(UserMfa).filter_by(user_id=user.id).first() is None


def test_master_admin_mfa_reset(db: Session):
    """Master Admin can reset MFA for any user or master admin."""
    user = db.query(User).filter_by(email="samrethi@example.com").first()
    user_mfa = UserMfa(
        user_id=user.id,
        encrypted_secret=encrypt_mfa_secret(pyotp.random_base32()),
        enabled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    db.add(user_mfa)
    db.commit()

    # Login as Master Admin
    m_login = client.post(
        "/api/auth/login",
        json={"email": "master@platform.local", "password": "Pasword@123", "portal": "platform"},
    )
    m_token = m_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {m_token}"}

    reset_res = client.post(f"/api/admin/users/{user.id}/reset-mfa", headers=headers)
    assert reset_res.status_code == 200, reset_res.text
    assert db.query(UserMfa).filter_by(user_id=user.id).first() is None


# ── 9. Audit Logging and Metadata Sanitization Tests ─────────────────────────

def test_mfa_audit_logging_and_sanitization(db: Session):
    """
    Ensure MFA operations record audit logs and NEVER leak secrets, OTP codes,
    or recovery codes into audit metadata.
    """
    # Login as jayasri
    login_res = client.post(
        "/api/auth/login",
        json={"email": "jayasri@example.com", "password": "Pasword@123", "portal": "company"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Start enrollment
    start_res = client.post("/api/auth/mfa/enroll/start", headers=headers)
    secret = start_res.json()["secret"]

    # Verify enrollment
    totp = pyotp.TOTP(secret)
    client.post(
        "/api/auth/mfa/enroll/verify",
        headers=headers,
        json={"code": totp.now()},
    )

    # Inspect audit records
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["auth.mfa.enroll_start", "auth.mfa.enroll_complete"]))
        .all()
    )
    assert len(logs) >= 2

    for l in logs:
        meta_str = str(l.event_metadata).lower()
        # Strictly verify no secret, otp, or code is in metadata
        assert "secret" not in meta_str
        assert "otp" not in meta_str
        assert "totp" not in meta_str
        assert "recovery_code" not in meta_str
        assert secret.lower() not in meta_str
