"""
Tests for app.auth and /api/auth endpoints.
"""

from datetime import timedelta
import jwt
import pytest
from fastapi import HTTPException

from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_token,
    require_admin,
)
from app.config import settings
from app.models import User, UserRole


def test_password_hashing():
    pw = "SuperSecurePassword123!"
    hashed = get_password_hash(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_roundtrip():
    payload = {"user_id": 42, "tenant_id": 1, "role": "ADMIN"}
    token = create_access_token(payload)
    decoded = decode_token(token)

    assert decoded["user_id"] == 42
    assert decoded["tenant_id"] == 1
    assert decoded["role"] == "ADMIN"
    assert decoded["aud"] == settings.JWT_AUDIENCE
    assert "exp" in decoded


def test_jwt_expired_token():
    payload = {"user_id": 42}
    expired_token = create_access_token(payload, expires_delta=timedelta(seconds=-10))

    with pytest.raises(HTTPException) as exc:
        decode_token(expired_token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_jwt_invalid_audience():
    # Token signed with our secret but wrong audience
    token = jwt.encode(
        {"user_id": 42, "aud": "wrong-portal"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc:
        decode_token(token)
    assert exc.value.status_code == 401
    assert "audience" in exc.value.detail.lower()


def test_jwt_tampered_token():
    token = create_access_token({"user_id": 42})
    tampered = token[:-4] + "xxxx"

    with pytest.raises(HTTPException) as exc:
        decode_token(tampered)
    assert exc.value.status_code == 401


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"email": "samrethi@example.com", "password": "Pasword@123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "samrethi@example.com"
    assert data["user"]["role"] == "ADMIN"


def test_login_invalid_password(client):
    resp = client.post("/api/auth/login", json={"email": "samrethi@example.com", "password": "WrongPassword"})
    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()


def test_login_unknown_user(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Pasword@123"})
    assert resp.status_code == 401


def test_me_endpoint(client, auth_headers):
    headers = auth_headers("jayasri@example.com")
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    user = resp.json()
    assert user["email"] == "jayasri@example.com"
    assert user["role"] == "GLOBAL_ADMIN"


def test_me_endpoint_unauthorized(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_require_admin_role_check():
    class DummyUser:
        def __init__(self, role):
            self.role = role

    # Admin allowed
    admin = DummyUser(UserRole.ADMIN)
    assert require_admin(admin) == admin

    # Global Admin allowed
    global_admin = DummyUser(UserRole.GLOBAL_ADMIN)
    assert require_admin(global_admin) == global_admin

    # Staff denied
    staff = DummyUser(UserRole.STAFF)
    with pytest.raises(HTTPException) as exc:
        require_admin(staff)
    assert exc.value.status_code == 403
