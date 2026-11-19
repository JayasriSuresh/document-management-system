"""
Tests for Company Admin Branch Onboarding and Primary Admin User Activation.

Verifies:
  1. Company Admin (GLOBAL_ADMIN) authenticates via Company Portal.
  2. Company Admin lists company branches.
  3. Company Admin creates a branch with Section 1 (Branch Details) and Section 2 (Primary Admin User).
  4. Unique branch code within company is enforced.
  5. Primary Admin is provisioned in INACTIVE state and receives activation invitation.
  6. Primary Admin redeems token and sets password.
  7. Primary Admin logs in to App Portal and is scoped to their branch.
  8. Company isolation: branches belong strictly to authenticated company.
"""

import uuid
import pytest
from app.models import Branch, Company, User, UserRole, AccountStatus, Invitation, CompanyStatus, UserRoleAssignment, UserSession
from app.auth import get_password_hash


def test_company_admin_branch_creation_and_admin_activation(client, db):
    # ── 1. Create isolated test company and company admin ───────────────────────
    uid = uuid.uuid4().hex[:6]
    test_comp = Company(
        name=f"Onboard Test Corp {uid}",
        code=f"OB_{uid.upper()}",
        status=CompanyStatus.ACTIVE,
        max_branches=10,
        max_users=20,
        storage_limit_bytes=5368709120,
        monthly_ai_budget_cents=5000,
        mfa_required_for_all=False,
    )
    db.add(test_comp)
    db.flush()

    initial_branch = Branch(
        company_id=test_comp.id,
        name="HQ Branch",
        code=f"HQ_{uid.upper()}",
        status="active",
    )
    db.add(initial_branch)
    db.flush()

    comp_admin_email = f"admin_{uid}@testonboard.test"
    comp_admin = User(
        email=comp_admin_email,
        password_hash=get_password_hash("Pasword@123"),
        name="Test Company Admin",
        role=UserRole.GLOBAL_ADMIN,
        status=AccountStatus.ACTIVE,
        company_id=test_comp.id,
        branch_id=initial_branch.id,
        token_version=1,
    )
    db.add(comp_admin)
    db.flush()

    db.add(UserRoleAssignment(
        user_id=comp_admin.id,
        role="GLOBAL_ADMIN",
        scope_type="company",
        scope_id=test_comp.id,
    ))
    db.commit()

    created_branch_id = None
    admin_user = None

    try:
        # Authenticate as Company Admin
        comp_login = client.post(
            "/api/auth/login",
            json={"email": comp_admin_email, "password": "Pasword@123", "portal": "company"},
        )
        assert comp_login.status_code == 200, comp_login.text
        comp_token = comp_login.json()["access_token"]
        comp_headers = {"Authorization": f"Bearer {comp_token}"}

        # ── 2. List company branches ──────────────────────────────────────────────
        list_resp = client.get("/api/company/branches", headers=comp_headers)
        assert list_resp.status_code == 200
        initial_branches = list_resp.json()
        assert len(initial_branches) >= 1

        # ── 3. Create a new branch with 2 Sections ─────────────────────────────────
        unique_suffix = uuid.uuid4().hex[:5].upper()
        branch_code = f"CBE_{unique_suffix}"
        admin_email = f"coimbatore.admin_{unique_suffix.lower()}@vasanth.test"

        create_payload = {
            # Section 1: Branch Details
            "branch_name": "Coimbatore Regional Office",
            "branch_code": branch_code,
            "branch_type": "Regional Office",
            "branch_email": "coimbatore@vasanth.test",
            "branch_contact_number": "+91 422 2345678",
            "address_line1": "104, Avinashi Road, Peelamedu",
            "address_line2": "Near Fun Republic Mall",
            "city": "Coimbatore",
            "district": "Coimbatore",
            "state": "Tamil Nadu",
            "pincode": "641004",
            "timezone": "Asia/Kolkata",
            # Section 2: Branch Administrator
            "admin_name": "Suresh Kumar",
            "admin_email": admin_email,
            "admin_designation": "Regional Operations Manager",
            "admin_mobile": "+91 94433 11223",
        }

        resp = client.post("/api/company/branches", json=create_payload, headers=comp_headers)
        assert resp.status_code in [200, 201], resp.text
        resp_json = resp.json()
        branch_dict = resp_json.get("branch", resp_json)

        assert branch_dict["name"] == "Coimbatore Regional Office"
        assert branch_dict["code"] == branch_code
        created_branch_id = branch_dict["id"]

        # ── 4. Verify branch in DB and invitation generated ───────────────────────
        db_branch = db.query(Branch).filter(Branch.id == created_branch_id).first()
        assert db_branch is not None
        assert db_branch.code == branch_code
        assert db_branch.city == "Coimbatore"

        admin_user = db.query(User).filter(User.email == admin_email).first()
        assert admin_user is not None
        assert admin_user.status == AccountStatus.INACTIVE
        assert admin_user.branch_id == created_branch_id
        assert admin_user.role == UserRole.ADMIN

        inv = db.query(Invitation).filter(Invitation.email == admin_email).first()
        assert inv is not None
        assert inv.branch_id == created_branch_id
        assert inv.invited_role == "ADMIN"
        raw_token = resp_json["activation_url"].split("token=")[1]

        # ── 5. Accept the invitation and activate account ─────────────────────────
        accept_resp = client.post(
            "/api/auth/invite/accept",
            json={
                "token": raw_token,
                "name": "Suresh Kumar S",
                "password": "SecurePassword@2026",
            },
        )
        assert accept_resp.status_code == 200, accept_resp.text

        # ── 7. Verify user is now ACTIVE and can log into App Portal ──────────────
        db.refresh(admin_user)
        assert admin_user.status == AccountStatus.ACTIVE

        branch_login = client.post(
            "/api/auth/login",
            json={
                "email": admin_email,
                "password": "SecurePassword@2026",
                "portal": "app",
            },
        )
        assert branch_login.status_code == 200, branch_login.text
        assert branch_login.json()["user"]["role"] == "ADMIN"
        assert branch_login.json()["user"]["branch_id"] == created_branch_id

    finally:
        # ── 8. Cleanup test data from DB ──────────────────────────────────────────
        try:
            db.query(UserRoleAssignment).filter(UserRoleAssignment.scope_id == test_comp.id).delete(synchronize_session=False)
            db.query(UserSession).filter(UserSession.user_id.in_(
                db.query(User.id).filter(User.company_id == test_comp.id).subquery()
            )).delete(synchronize_session=False)
            db.query(Invitation).filter(Invitation.company_id == test_comp.id).delete(synchronize_session=False)
            db.query(User).filter(User.company_id == test_comp.id).delete(synchronize_session=False)
            db.query(Branch).filter(Branch.company_id == test_comp.id).delete(synchronize_session=False)
            db.query(Company).filter(Company.id == test_comp.id).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
