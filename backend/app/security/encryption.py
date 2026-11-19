"""
Authenticated Encryption Helper (AES-256-GCM).

Provides authenticated, tamper-evident symmetric encryption for security-critical
data such as MFA TOTP secrets, tokens, and sensitive tenant configuration.
Designed to be reusable for Module 6 and Module 10.

Format:
  v1:<base64_nonce>:<base64_ciphertext_and_tag>
"""

import base64
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from app.config import settings


_SALT = b"dms-mfa-encryption-salt-v1"
_INFO = b"dms-mfa-aes-256-gcm-key"


def derive_encryption_key(secret_or_key: Optional[str] = None) -> bytes:
    """
    Derives a cryptographically strong 256-bit (32 bytes) key using HKDF-SHA256.
    If no explicit key is provided, derives deterministically from settings.MFA_ENCRYPTION_KEY
    or settings.SECRET_KEY.
    """
    raw = secret_or_key or settings.MFA_ENCRYPTION_KEY or settings.SECRET_KEY
    if not raw:
        raise ValueError("No encryption key or SECRET_KEY configured for encryption.")

    # If already a 64-character hex string representing 32 bytes
    if isinstance(raw, str) and len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass

    # Derive 32 bytes using HKDF-SHA256
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        info=_INFO,
    )
    return hkdf.derive(raw.encode("utf-8") if isinstance(raw, str) else raw)


class AESGCMEncryptionHelper:
    """
    Provides AES-256-GCM authenticated encryption and decryption.
    """

    def __init__(self, key: Optional[bytes] = None):
        self._key = key or derive_encryption_key()
        if len(self._key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte (256-bit) key.")
        self._aesgcm = AESGCM(self._key)

    def encrypt(self, plaintext: str | bytes, associated_data: Optional[bytes] = None) -> str:
        """
        Encrypts plaintext with a fresh 12-byte nonce.
        Returns a versioned string: "v1:<b64_nonce>:<b64_ciphertext>"
        """
        if isinstance(plaintext, str):
            data = plaintext.encode("utf-8")
        else:
            data = plaintext

        # 96-bit (12-byte) nonce recommended by NIST SP 800-38D
        nonce = os.urandom(12)
        ciphertext_and_tag = self._aesgcm.encrypt(nonce, data, associated_data)

        nonce_b64 = base64.urlsafe_b64encode(nonce).decode("ascii")
        ciphertext_b64 = base64.urlsafe_b64encode(ciphertext_and_tag).decode("ascii")

        return f"v1:{nonce_b64}:{ciphertext_b64}"

    def decrypt(self, encrypted_payload: str, associated_data: Optional[bytes] = None) -> str:
        """
        Decrypts an encrypted payload formatted as "v1:<b64_nonce>:<b64_ciphertext>".
        Raises ValueError if the payload is malformed, tampered, or decryption fails.
        """
        if not encrypted_payload or not isinstance(encrypted_payload, str):
            raise ValueError("Invalid encrypted payload.")

        parts = encrypted_payload.split(":")
        if len(parts) != 3 or parts[0] != "v1":
            raise ValueError("Unsupported or malformed encrypted payload format.")

        try:
            nonce = base64.urlsafe_b64decode(parts[1].encode("ascii"))
            ciphertext_and_tag = base64.urlsafe_b64decode(parts[2].encode("ascii"))
        except Exception as e:
            raise ValueError(f"Failed to decode base64 components: {e}") from e

        try:
            decrypted = self._aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data)
            return decrypted.decode("utf-8")
        except Exception as e:
            raise ValueError("Decryption failed: ciphertext may be tampered or key is invalid.") from e


# Singleton helper using default derived key
default_encryption_helper = AESGCMEncryptionHelper()


def encrypt_mfa_secret(secret: str) -> str:
    """Helper to encrypt an MFA TOTP secret."""
    return default_encryption_helper.encrypt(secret)


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    """Helper to decrypt an MFA TOTP secret."""
    return default_encryption_helper.decrypt(encrypted_secret)


def mask_api_key(key: str) -> str:
    """Mask sensitive API key, showing only the last 4 characters if key length >= 8, or '************'."""
    if not key or not isinstance(key, str):
        return "************"
    clean = key.strip()
    if len(clean) <= 4:
        return "************"
    tail = clean[-4:]
    return f"************{tail}"


def encrypt_api_key(key: str) -> str:
    """Encrypt an AI API key with AES-256-GCM."""
    return default_encryption_helper.encrypt(key)


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an AI API key with AES-256-GCM."""
    return default_encryption_helper.decrypt(encrypted_key)

