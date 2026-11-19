"""
Module 6 – Multi-Factor Authentication (TOTP & Recovery) Service.

Handles RFC 6238 TOTP operations, SVG QR code generation, AES-256-GCM secret
encryption, atomic replay prevention, single-use recovery code redemption,
and multi-tier policy enforcement.
"""

import io
import re
import time
import base64
import secrets
import string
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import pyotp
import pyqrcode
from PIL import Image
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models import (
    User,
    MasterAdmin,
    Company,
    UserMfa,
    MfaRecoveryCode,
    PlatformSetting,
    AccountStatus,
)
from app.security.encryption import encrypt_mfa_secret, decrypt_mfa_secret


DEFAULT_PLATFORM_MFA_POLICY = {
    "enforce_master_admin": False,
    "enforce_company_admin": False,
    "enforce_all": False,
}


class MfaService:
    @staticmethod
    def generate_secret() -> str:
        """Generate a random Base32 TOTP secret."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(secret: str, account_name: str, issuer_name: Optional[str] = None) -> str:
        """Construct RFC 6238 otpauth:// URI."""
        totp = pyotp.TOTP(secret)
        issuer = issuer_name or settings.MFA_ISSUER_NAME
        return totp.provisioning_uri(name=account_name, issuer_name=issuer)

    @staticmethod
    def generate_qr_svg(provisioning_uri: str) -> str:
        """
        Generate QR code as an SVG string with white background, ISO standard
        quiet zone (4 modules), and native viewBox so it scales cleanly
        without clipping across any screen or modal size.
        """
        qr = pyqrcode.create(provisioning_uri, error="M")
        buffer = io.BytesIO()
        qr.svg(buffer, scale=6, quiet_zone=4, background="#ffffff", omithw=True)
        return buffer.getvalue().decode("utf-8")

    @staticmethod
    def generate_qr_png_data_url(provisioning_uri: str) -> str:
        """
        Generate crystal-clear, high-contrast PNG Data URL for 100% scanner compatibility
        across all phone camera models, operating systems, and monitor DPI settings.
        """
        qr = pyqrcode.create(provisioning_uri, error="M")
        matrix = qr.code
        quiet_zone = 4
        scale = 8  # 8 solid, unblurred pixels per module
        size = len(matrix) + 2 * quiet_zone

        img = Image.new("RGB", (size * scale, size * scale), color=(255, 255, 255))
        pixels = img.load()

        for r, row in enumerate(matrix):
            for c, val in enumerate(row):
                if val == 1:
                    x_start = (c + quiet_zone) * scale
                    y_start = (r + quiet_zone) * scale
                    for dy in range(scale):
                        for dx in range(scale):
                            pixels[x_start + dx, y_start + dy] = (0, 0, 0)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def generate_recovery_codes(count: int = 8) -> List[str]:
        """Generate human-readable, cryptographically random recovery codes (XXXX-XXXX-XXXX)."""
        alphabet = string.ascii_uppercase + string.digits
        # exclude ambiguous characters like 0, O, 1, I
        alphabet = alphabet.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
        codes = []
        for _ in range(count):
            p1 = "".join(secrets.choice(alphabet) for _ in range(4))
            p2 = "".join(secrets.choice(alphabet) for _ in range(4))
            p3 = "".join(secrets.choice(alphabet) for _ in range(4))
            codes.append(f"{p1}-{p2}-{p3}")
        return codes

    @staticmethod
    def hash_recovery_code(code: str) -> str:
        """Normalize and compute SHA-256 hash of a recovery code."""
        normalized = code.strip().replace("-", "").replace(" ", "").upper()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    # ── Policy Evaluation ────────────────────────────────────────────────────

    @classmethod
    def get_platform_mfa_policy(cls, db: Session) -> Dict[str, bool]:
        """Fetch platform-wide MFA enforcement settings."""
        setting = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
        if not setting or not isinstance(setting.value, dict):
            return dict(DEFAULT_PLATFORM_MFA_POLICY)
        policy = dict(DEFAULT_PLATFORM_MFA_POLICY)
        policy.update(setting.value)
        return policy

    @classmethod
    def set_platform_mfa_policy(cls, db: Session, policy_data: Dict[str, bool], admin_id: int) -> Dict[str, bool]:
        """Update platform-wide MFA policy (Master Admin only)."""
        setting = db.query(PlatformSetting).filter_by(key="mfa_policy").first()
        current = cls.get_platform_mfa_policy(db)
        current.update(policy_data)
        if not setting:
            setting = PlatformSetting(
                key="mfa_policy",
                value=current,
                updated_by=admin_id,
                updated_at=datetime.utcnow(),
            )
            db.add(setting)
        else:
            setting.value = current
            setting.updated_by = admin_id
            setting.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(setting)
        return setting.value

    @classmethod
    def is_mfa_mandatory_for_master_admin(cls, db: Session, master_admin: MasterAdmin) -> bool:
        """Check if platform policy mandates MFA for Master Admins."""
        policy = cls.get_platform_mfa_policy(db)
        return bool(policy.get("enforce_master_admin", False) or policy.get("enforce_all", False))

    @classmethod
    def is_mfa_mandatory_for_user(cls, db: Session, user: User) -> bool:
        """
        Check if MFA is mandatory for a company user.
        Platform policy overrides company policy:
        1. If platform policy enforce_all is True -> mandatory.
        2. If user is GLOBAL_ADMIN (Company Admin) and platform enforce_company_admin is True -> mandatory.
        3. If company.mfa_required_for_all is True -> mandatory for all users in that company.
        """
        policy = cls.get_platform_mfa_policy(db)
        if policy.get("enforce_all", False):
            return True

        user_role_val = getattr(user.role, "value", user.role)
        if user_role_val == "GLOBAL_ADMIN" and policy.get("enforce_company_admin", False):
            return True

        if user.company_id:
            company = db.query(Company).filter_by(id=user.company_id).first()
            if company and company.mfa_required_for_all:
                return True

        return False

    @classmethod
    def is_mfa_mandatory(
        cls,
        db: Session,
        identity_type: str,
        identity_id: int,
    ) -> bool:
        if identity_type == "master_admin":
            admin = db.query(MasterAdmin).filter_by(id=identity_id).first()
            return cls.is_mfa_mandatory_for_master_admin(db, admin) if admin else True
        else:
            user = db.query(User).filter_by(id=identity_id).first()
            return cls.is_mfa_mandatory_for_user(db, user) if user else False

    # ── Status ───────────────────────────────────────────────────────────────

    @classmethod
    def get_user_mfa_record(cls, db: Session, identity_type: str, identity_id: int) -> Optional[UserMfa]:
        if identity_type == "master_admin":
            return db.query(UserMfa).filter_by(master_admin_id=identity_id).first()
        return db.query(UserMfa).filter_by(user_id=identity_id).first()

    @classmethod
    def is_mfa_enabled(cls, db: Session, identity_type: str, identity_id: int) -> bool:
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        return bool(rec and rec.enabled_at is not None)

    @classmethod
    def get_mfa_status(cls, db: Session, identity_type: str, identity_id: int) -> Dict[str, Any]:
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        is_enabled = bool(rec and rec.enabled_at is not None)
        mandatory = cls.is_mfa_mandatory(db, identity_type, identity_id)

        remaining_codes = 0
        if is_enabled and rec:
            remaining_codes = (
                db.query(MfaRecoveryCode)
                .filter(MfaRecoveryCode.user_mfa_id == rec.id, MfaRecoveryCode.used_at.is_(None))
                .count()
            )

        return {
            "enabled": is_enabled,
            "mandatory": mandatory,
            "remaining_recovery_codes": remaining_codes,
            "enabled_at": rec.enabled_at if (rec and rec.enabled_at) else None,
        }

    # ── Enrollment Lifecycle ─────────────────────────────────────────────────

    @classmethod
    def start_enrollment(
        cls,
        db: Session,
        identity_type: str,
        identity_id: int,
        account_name: str,
        force_regenerate: bool = False,
    ) -> Dict[str, str]:
        """
        Initiates MFA setup: generates secret, encrypts with AES-256-GCM,
        stores unverified secret, generates QR code SVG and returns manual key.
        IDEMPOTENT: If an unverified pending enrollment is already in progress,
        reuses the existing pending secret so concurrent calls or re-renders
        do not invalidate the secret/QR code shown to the user.
        """
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)

        # If unverified enrollment is already active and not forcing regeneration, reuse existing secret
        if rec and rec.enabled_at is None and rec.encrypted_secret and not force_regenerate:
            try:
                secret = decrypt_mfa_secret(rec.encrypted_secret)
                if secret and len(secret) >= 16:
                    uri = cls.get_provisioning_uri(secret, account_name)
                    svg = cls.generate_qr_svg(uri)
                    png_data_url = cls.generate_qr_png_data_url(uri)
                    return {
                        "secret": secret,
                        "provisioning_uri": uri,
                        "qr_code_svg": svg,
                        "qr_code_data_url": png_data_url,
                    }
            except Exception:
                pass  # Fallback to generating a fresh secret below

        secret = cls.generate_secret()
        encrypted = encrypt_mfa_secret(secret)

        if not rec:
            rec = UserMfa(
                user_id=identity_id if identity_type != "master_admin" else None,
                master_admin_id=identity_id if identity_type == "master_admin" else None,
                encrypted_secret=encrypted,
                enabled_at=None,
                last_used_step=None,
            )
            db.add(rec)
            try:
                db.commit()
            except Exception:
                db.rollback()
                # Row was created by concurrent request; fetch and reuse or update
                rec = cls.get_user_mfa_record(db, identity_type, identity_id)
                if rec and rec.enabled_at is None and rec.encrypted_secret and not force_regenerate:
                    try:
                        secret = decrypt_mfa_secret(rec.encrypted_secret)
                    except Exception:
                        rec.encrypted_secret = encrypted
                        rec.enabled_at = None
                        rec.last_used_step = None
                        rec.updated_at = datetime.utcnow()
                        db.commit()
                elif rec:
                    rec.encrypted_secret = encrypted
                    rec.enabled_at = None
                    rec.last_used_step = None
                    rec.updated_at = datetime.utcnow()
                    db.commit()
        else:
            rec.encrypted_secret = encrypted
            rec.enabled_at = None
            rec.last_used_step = None
            rec.updated_at = datetime.utcnow()
            db.commit()

        if rec:
            db.refresh(rec)

        uri = cls.get_provisioning_uri(secret, account_name)
        svg = cls.generate_qr_svg(uri)
        png_data_url = cls.generate_qr_png_data_url(uri)

        return {
            "secret": secret,
            "provisioning_uri": uri,
            "qr_code_svg": svg,
            "qr_code_data_url": png_data_url,
        }

    @classmethod
    def verify_and_enable(
        cls, db: Session, identity_type: str, identity_id: int, code: str
    ) -> List[str]:
        """
        Verifies the TOTP code against the newly generated secret.
        If valid:
          - Marks enabled_at = NOW()
          - Records initial last_used_step for replay prevention
          - Generates and stores 8 hashed single-use recovery codes
          - Returns plaintext recovery codes once
        """
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA enrollment has not been started.",
            )

        try:
            secret = decrypt_mfa_secret(rec.encrypted_secret)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to decrypt MFA secret configuration.",
            )

        clean_code = str(code).strip().replace(" ", "").replace("-", "")
        totp = pyotp.TOTP(secret)
        current_step = int(time.time() // 30)

        # Check steps within +- 2 windows (up to +-60s clock skew)
        valid_step = None
        for step_offset in (0, -1, 1, -2, 2):
            check_step = current_step + step_offset
            if totp.verify(clean_code, for_time=check_step * 30):
                valid_step = check_step
                break

        if valid_step is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please check your authenticator app and try again.",
            )

        # Mark enabled & save last used step
        rec.enabled_at = datetime.utcnow()
        rec.last_used_step = valid_step
        rec.updated_at = datetime.utcnow()

        # Delete any previous recovery codes
        db.query(MfaRecoveryCode).filter_by(user_mfa_id=rec.id).delete()

        # Generate 8 single-use recovery codes
        plain_codes = cls.generate_recovery_codes(8)
        for c in plain_codes:
            code_rec = MfaRecoveryCode(
                user_mfa_id=rec.id,
                code_hash=cls.hash_recovery_code(c),
            )
            db.add(code_rec)

        db.commit()
        return plain_codes

    # ── TOTP Verification & Replay Protection ────────────────────────────────

    @classmethod
    def verify_totp_code(
        cls, db: Session, identity_type: str, identity_id: int, code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies TOTP code with strict atomic replay protection.
        Uses row-level locking (SELECT ... FOR UPDATE) to prevent race conditions.
        Returns: (success: bool, error_message: Optional[str])
        """
        # Lock user_mfa row
        query = db.query(UserMfa).with_for_update()
        if identity_type == "master_admin":
            rec = query.filter_by(master_admin_id=identity_id).first()
        else:
            rec = query.filter_by(user_id=identity_id).first()

        if not rec or rec.enabled_at is None:
            return False, "MFA is not enabled for this account."

        try:
            secret = decrypt_mfa_secret(rec.encrypted_secret)
        except Exception:
            return False, "Failed to decrypt MFA configuration."

        clean_code = str(code).strip().replace(" ", "").replace("-", "")
        totp = pyotp.TOTP(secret)
        current_step = int(time.time() // 30)

        # Check window: 0, -1, 1, -2, 2 (up to +-60s clock skew)
        matched_step = None
        for step_offset in (0, -1, 1, -2, 2):
            check_step = current_step + step_offset
            if totp.verify(clean_code, for_time=check_step * 30):
                matched_step = check_step
                break

        if matched_step is None:
            return False, "Invalid authentication code."

        # Replay attack prevention: step must be strictly greater than last_used_step
        if rec.last_used_step is not None and matched_step <= rec.last_used_step:
            return False, "Authentication code has already been used. Please wait for the next code."

        # Update last_used_step atomically
        rec.last_used_step = matched_step
        rec.updated_at = datetime.utcnow()
        db.commit()

        return True, None

    # ── Single-Use Recovery Code Redemption ──────────────────────────────────

    @classmethod
    def verify_recovery_code(
        cls, db: Session, identity_type: str, identity_id: int, recovery_code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verifies and redeems a single-use recovery code.
        Row-locks the specific recovery code record to prevent double-spending.
        Returns: (success: bool, error_message: Optional[str])
        """
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        if not rec or rec.enabled_at is None:
            return False, "MFA is not enabled for this account."

        code_hash = cls.hash_recovery_code(recovery_code)

        # Lock the matching recovery code
        code_rec = (
            db.query(MfaRecoveryCode)
            .filter(
                MfaRecoveryCode.user_mfa_id == rec.id,
                MfaRecoveryCode.code_hash == code_hash,
                MfaRecoveryCode.used_at.is_(None),
            )
            .with_for_update()
            .first()
        )

        if not code_rec:
            return False, "Invalid or already used recovery code."

        # Atomically mark as used
        code_rec.used_at = datetime.utcnow()
        db.commit()

        return True, None

    # ── Recovery Codes Regeneration ──────────────────────────────────────────

    @classmethod
    def regenerate_recovery_codes(
        cls, db: Session, identity_type: str, identity_id: int
    ) -> List[str]:
        """Invalidates all existing recovery codes and generates 8 new ones."""
        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        if not rec or rec.enabled_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MFA is not enabled for this account.",
            )

        # Delete existing codes
        db.query(MfaRecoveryCode).filter_by(user_mfa_id=rec.id).delete()

        # Generate new codes
        plain_codes = cls.generate_recovery_codes(8)
        for c in plain_codes:
            code_rec = MfaRecoveryCode(
                user_mfa_id=rec.id,
                code_hash=cls.hash_recovery_code(c),
            )
            db.add(code_rec)

        db.commit()
        return plain_codes

    # ── Disabling MFA ────────────────────────────────────────────────────────

    @classmethod
    def disable_mfa(cls, db: Session, identity_type: str, identity_id: int) -> None:
        """Disables MFA if not mandatory by policy."""
        if cls.is_mfa_mandatory(db, identity_type, identity_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MFA cannot be disabled because it is mandatory for your role or organization.",
            )

        rec = cls.get_user_mfa_record(db, identity_type, identity_id)
        if rec:
            db.delete(rec)
            db.commit()

    # ── Admin-Assisted MFA Reset ─────────────────────────────────────────────

    @classmethod
    def reset_mfa_by_admin(
        cls, db: Session, target_identity_type: str, target_identity_id: int
    ) -> None:
        """
        Resets MFA for a user or admin:
          - Deletes user_mfa (cascades to recovery codes)
          - Resets account failed_attempts and locks
          - Invalidates existing sessions
        """
        rec = cls.get_user_mfa_record(db, target_identity_type, target_identity_id)
        if rec:
            db.delete(rec)

        if target_identity_type == "master_admin":
            admin = db.query(MasterAdmin).filter_by(id=target_identity_id).first()
            if admin:
                admin.failed_attempts = 0
                admin.locked_until = None
        else:
            user = db.query(User).filter_by(id=target_identity_id).first()
            if user:
                user.failed_attempts = 0
                user.locked_until = None

        # Revoke all active sessions and increment token_version immediately
        from app.services.session_service import session_service
        session_service.revoke_all_sessions(
            db=db,
            identity_type=target_identity_type,
            identity_id=target_identity_id,
            reason="mfa_reset_by_admin",
        )

        db.commit()
