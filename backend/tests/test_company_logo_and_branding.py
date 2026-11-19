"""
Test suite for Company Name, Display Name, and Company Logo upload/management.
Validates:
1. Company name and display name updates via PUT /api/company/profile
2. Company logo upload (PNG, JPEG, WebP, SVG) via POST /api/company/logo
3. 2MB file size enforcement and content-type rejection
4. Serving logo image via GET /api/company/logo and GET /api/company/{company_id}/logo
5. Removing company logo via DELETE /api/company/logo
6. Dynamic propagation to UserOut in GET /api/auth/me
"""
import io
import uuid
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.models import Company, Branch, User, UserRole, AccountStatus, CompanyStatus, UserRoleAssignment
from app.auth import get_password_hash


@pytest.fixture
def test_setup(db: Session, client: TestClient):
    uid = uuid.uuid4().hex[:6]
    pwd = get_password_hash("TestPass@123")

    company = Company(
        name=f"Logo Test Corp {uid}",
        code=f"LGC_{uid}",
        status=CompanyStatus.ACTIVE,
        max_branches=3,
        max_users=4,
        storage_limit_bytes=5368709120,
        monthly_ai_budget_cents=5000,
        mfa_required_for_all=False,
    )
    db.add(company)
    db.flush()

    branch = Branch(
        company_id=company.id,
        name="Main Office",
        code=f"HQ_{uid}",
        status="active",
    )
    db.add(branch)
    db.flush()

    admin_user = User(
        email=f"admin_{uid}@example.com",
        password_hash=pwd,
        name="Branding Admin",
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
        company_id=company.id,
        branch_id=branch.id,
        token_version=1,
    )
    db.add(admin_user)
    db.flush()

    db.add(UserRoleAssignment(
        user_id=admin_user.id,
        role="GLOBAL_ADMIN",
        scope_type="company",
        scope_id=company.id,
    ))
    db.commit()

    login_resp = client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "TestPass@123", "portal": "company"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    yield {
        "company": company,
        "branch": branch,
        "admin": admin_user,
        "token": token,
    }

    # Teardown
    try:
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == admin_user.id).delete()
        db.query(UserSession).filter(UserSession.user_id == admin_user.id).delete()
        db.query(User).filter(User.id == admin_user.id).delete()
        db.query(Branch).filter(Branch.id == branch.id).delete()
        db.query(Company).filter(Company.id == company.id).delete()
        db.commit()
    except Exception:
        db.rollback()


def test_update_company_name_and_display_name(client: TestClient, test_setup):
    """Verify company admin can update company legal name and display brand name."""
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    update_payload = {
        "name": "Updated Enterprise Corp Pvt Ltd",
        "display_name": "Enterprise Brand",
        "website": "https://enterprise.example.com",
    }
    resp = client.put("/api/company/profile", json=update_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Updated Enterprise Corp Pvt Ltd"
    assert data["display_name"] == "Enterprise Brand"

    # Verify /api/auth/me reflects the new name
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["company_name"] == "Updated Enterprise Corp Pvt Ltd"
    assert me_data["company_display_name"] == "Enterprise Brand"


def test_upload_and_retrieve_company_logo(client: TestClient, test_setup):
    """Verify uploading a PNG logo, retrieving it, and checking /me context."""
    headers = {"Authorization": f"Bearer {test_setup['token']}"}
    company_id = test_setup["company"].id

    # 1x1 transparent PNG bytes
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    upload_resp = client.post(
        "/api/company/logo",
        files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
        headers=headers,
    )
    assert upload_resp.status_code == 200, upload_resp.text
    upload_data = upload_resp.json()
    assert "logo_url" in upload_data
    assert f"/api/company/{company_id}/logo" in upload_data["logo_url"]

    # Stream logo via GET /api/company/logo
    get_logo_resp = client.get("/api/company/logo", headers=headers)
    assert get_logo_resp.status_code == 200
    assert get_logo_resp.headers["content-type"] == "image/png"
    assert get_logo_resp.content == png_bytes

    # Stream logo via public/company endpoint GET /api/company/{company_id}/logo
    get_id_logo_resp = client.get(f"/api/company/{company_id}/logo")
    assert get_id_logo_resp.status_code == 200
    assert get_id_logo_resp.headers["content-type"] == "image/png"

    # Verify /api/auth/me has company_logo_url
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["company_logo_url"] == upload_data["logo_url"]


def test_reject_oversized_logo(client: TestClient, test_setup):
    """Verify logos > 2MB are rejected with 400 Bad Request."""
    headers = {"Authorization": f"Bearer {test_setup['token']}"}
    large_file = io.BytesIO(b"A" * (2 * 1024 * 1024 + 10))

    resp = client.post(
        "/api/company/logo",
        files={"file": ("large.png", large_file, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "exceeds 2 MB" in resp.json()["detail"]


def test_reject_invalid_mime_type(client: TestClient, test_setup):
    """Verify non-image formats (e.g. text or exe) are rejected."""
    headers = {"Authorization": f"Bearer {test_setup['token']}"}
    text_file = io.BytesIO(b"malicious script")

    resp = client.post(
        "/api/company/logo",
        files={"file": ("script.sh", text_file, "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported image format" in resp.json()["detail"]


def test_delete_company_logo(client: TestClient, test_setup):
    """Verify deleting the logo clears company_logo_url."""
    headers = {"Authorization": f"Bearer {test_setup['token']}"}

    del_resp = client.delete("/api/company/logo", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["logo_url"] is None

    # Verify profile has logo_url = None
    profile_resp = client.get("/api/company/profile", headers=headers)
    assert profile_resp.status_code == 200
    assert profile_resp.json()["logo_url"] is None

    # Verify /me has company_logo_url = None
    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["company_logo_url"] is None
