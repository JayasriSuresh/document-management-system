"""
Integration tests for the Company Onboarding and Master Admin Review lifecycle.

Verifies:
  1. Master Admin initiates onboarding (company name, contact name, contact email).
  2. Applicant retrieves pre-filled form with unique token.
  3. Applicant uploads verification documents (PAN card, address proof, etc.).
  4. Applicant submits full Sections A through G data.
  5. Master Admin views application under review.
  6. Master Admin requests changes (comments logged, status updated to changes_requested).
  7. Applicant views prefilled form with master admin feedback displayed.
  8. Applicant modifies fields and resubmits.
  9. Master Admin approves application -> Company, Branch, and First Administrator are created.
 10. Newly provisioned Global Admin logs in at the Company Portal.
"""

import io
import uuid
import pytest
from app.database import SessionLocal
from app.models import (
    Company, Branch, User, UserRole, CompanyOnboarding, OnboardingStatus, MasterAdmin,
    Invoice, Document, UserRoleAssignment, UserSession, UserMfa, MfaRecoveryCode
)


def test_complete_onboarding_and_review_lifecycle(client, db):
    test_id = uuid.uuid4().hex[:6]
    company_name = f"Acme Global Solutions {test_id}"
    contact_email = f"arun.{test_id}@acmesolutions.test"
    legal_name = f"Acme Global Solutions {test_id} Private Limited"

    try:
        # ── 1. Authenticate as Master Admin ───────────────────────────────────────
        login_resp = client.post(
            "/api/auth/login",
            json={"email": "master@platform.local", "password": "Pasword@123", "portal": "platform"},
        )
        assert login_resp.status_code == 200, login_resp.text
        master_token = login_resp.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {master_token}"}

        # Verify profile
        me_resp = client.get("/api/auth/me", headers=admin_headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["role"] == "MASTER_ADMIN"

        # ── 2. Master Admin initiates onboarding ───────────────────────────────────
        initiate_resp = client.post(
            "/api/admin/onboarding/initiate",
            headers=admin_headers,
            json={
                "company_name": company_name,
                "contact_name": "Arun Kumar",
                "contact_email": contact_email,
            },
        )
        assert initiate_resp.status_code == 200, initiate_resp.text
        init_data = initiate_resp.json()
        token = init_data["token"]
        onboarding_id = init_data["id"]
        assert init_data["status"] == "pending_submission"
        assert "token=" in init_data["onboarding_url"]

        # ── 3. Applicant retrieves onboarding form ────────────────────────────────
        fetch_resp = client.get(f"/api/onboarding/{token}")
        assert fetch_resp.status_code == 200
        form_data = fetch_resp.json()
        assert form_data["initial_company_name"] == company_name
        assert form_data["contact_email"] == contact_email
        assert form_data["legal_company_name"] == company_name

        # ── 4. Applicant uploads verification documents ───────────────────────────
        pan_file = io.BytesIO(b"%PDF-1.4 dummy pan card file content")
        pan_resp = client.post(
            f"/api/onboarding/{token}/upload-document",
            data={"document_type": "pan_document"},
            files={"file": ("pan_card.pdf", pan_file, "application/pdf")},
        )
        assert pan_resp.status_code == 200, pan_resp.text
        assert "pan_document" in pan_resp.json()["uploaded_documents"]

        addr_file = io.BytesIO(b"%PDF-1.4 electricity bill address proof")
        addr_resp = client.post(
            f"/api/onboarding/{token}/upload-document",
            data={"document_type": "address_proof"},
            files={"file": ("address_proof.pdf", addr_file, "application/pdf")},
        )
        assert addr_resp.status_code == 200, addr_resp.text

        # Stream document
        doc_stream = client.get(f"/api/onboarding/{token}/documents/pan_document")
        assert doc_stream.status_code == 200
        assert b"%PDF-1.4 dummy pan card" in doc_stream.content

        # ── 5. Applicant submits form (Sections A - G) ─────────────────────────────
        submit_payload = {
            # Section A
            "legal_company_name": legal_name,
            "trade_name": "Acme Global",
            "business_type": "Private Limited Company (Pvt Ltd)",
            "business_description": "Cloud document automation and intelligent scanning solutions.",
            "year_of_establishment": "2021",
            "company_website": "https://acmeglobal.test",
            # Section B
            "pan_number": "AABCA1234F",
            "gstin": "33AABCA1234F1Z5",
            "gst_type": "Regular",
            "cin": "U72900TN2021PTC123456",
            "udyam_number": "UDYAM-TN-01-0012345",
            "tan": "CHNA12345E",
            # Section C
            "address_line1": "Level 4, Zenith IT Park",
            "address_line2": "Taramani Main Road",
            "city": "Chennai",
            "district": "Chennai",
            "state": "Tamil Nadu",
            "pincode": "600113",
            "country": "India",
            # Section D
            "auth_contact_name": "Arun Kumar",
            "auth_contact_designation": "Vice President - Operations",
            "auth_contact_email": contact_email,
            "auth_contact_mobile": "9876543210",
            # Section E
            "has_multiple_branches": True,
            "branch_details": [
                {
                    "name": "Headquarters",
                    "code": "HQ01",
                    "branch_type": "Head Office",
                    "address_line1": "Level 4, Zenith IT Park",
                    "city": "Chennai",
                    "district": "Chennai",
                    "state": "Tamil Nadu",
                    "pincode": "600113",
                    "branch_contact_number": "04422540001",
                    "gstin": "33AABCA1234F1Z5",
                },
                {
                    "name": "Bengaluru Innovation Hub",
                    "code": "BLR01",
                    "branch_type": "Regional Office",
                    "address_line1": "Outer Ring Road, Bellandur",
                    "city": "Bengaluru",
                    "district": "Bengaluru",
                    "state": "Karnataka",
                    "pincode": "560103",
                    "branch_contact_number": "08041234567",
                    "gstin": "29AABCA1234F1Z3",
                },
                {
                    "name": "Hyderabad Operations",
                    "code": "HYD01",
                    "branch_type": "Branch",
                    "address_line1": "HITEC City, Madhapur",
                    "city": "Hyderabad",
                    "district": "Hyderabad",
                    "state": "Telangana",
                    "pincode": "500081",
                    "branch_contact_number": "04067890123",
                    "gstin": "36AABCA1234F1Z7",
                },
            ],
            # Section F
            "admin_name": "Arun Kumar",
            "admin_email": contact_email,
            "admin_password": "SecurePassword@123",
            "confirm_password": "SecurePassword@123",
            "admin_mobile": "9876543210",
            "admin_designation": "Vice President - Operations",
            # Section G
            "primary_document_types": ["Invoices", "Purchase Orders"],
            "expected_monthly_volume": "1000-5000",
            "languages": ["English", "Tamil"],
            "timezone": "Asia/Kolkata",
            "currency": "INR",
        }
        submit_resp = client.post(f"/api/onboarding/{token}/submit", json=submit_payload)
        assert submit_resp.status_code == 200, submit_resp.text
        assert "successfully" in submit_resp.json()["message"]

        check_sub = client.get(f"/api/onboarding/{token}")
        assert check_sub.json()["status"] == "submitted"

        # ── 6. Master Admin views application under review ─────────────────────────
        list_resp = client.get("/api/admin/onboarding", headers=admin_headers)
        assert list_resp.status_code == 200
        apps = list_resp.json()
        assert any(a["id"] == onboarding_id for a in apps)

        detail_resp = client.get(f"/api/admin/onboarding/{onboarding_id}", headers=admin_headers)
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["legal_company_name"] == legal_name
        assert detail["pan_number"] == "AABCA1234F"
        assert "pan_document" in detail["uploaded_documents"]

        # ── 7. Master Admin requests changes ──────────────────────────────────────
        change_resp = client.post(
            f"/api/admin/onboarding/{onboarding_id}/request-changes",
            headers=admin_headers,
            json={"comments": "Please update your registered office PIN code to 600113 and verify PAN name."},
        )
        assert change_resp.status_code == 200

        # ── 8. Applicant views prefilled form with feedback and resubmits ─────────
        refetch_resp = client.get(f"/api/onboarding/{token}")
        assert refetch_resp.status_code == 200
        refetch_data = refetch_resp.json()
        assert refetch_data["status"] == "changes_requested"
        assert "Please update your registered office PIN code" in refetch_data["review_comments"]
        # Verify all previously submitted fields are preserved!
        assert refetch_data["pan_number"] == "AABCA1234F"
        assert refetch_data["cin"] == "U72900TN2021PTC123456"
        assert refetch_data["has_admin_password"] is True

        # Resubmit with updated info (password optional when preserving previous password)
        submit_payload["trade_name"] = "Acme Global Technologies"
        submit_payload["admin_password"] = None
        submit_payload["confirm_password"] = None
        resubmit_resp = client.post(f"/api/onboarding/{token}/submit", json=submit_payload)
        assert resubmit_resp.status_code == 200

        check_resubmitted = client.get(f"/api/onboarding/{token}")
        assert check_resubmitted.json()["status"] == "submitted"

        # ── 9. Master Admin approves application ──────────────────────────────────
        approve_resp = client.post(f"/api/admin/onboarding/{onboarding_id}/approve", headers=admin_headers)
        assert approve_resp.status_code == 200, approve_resp.text
        assert "successfully approved" in approve_resp.json()["message"]

        # Verify Company, Branch, and First Administrator exist in DB
        created_company = db.query(Company).filter(Company.name == legal_name).first()
        assert created_company is not None
        assert created_company.gstin == "33AABCA1234F1Z5"

        branches = db.query(Branch).filter(Branch.company_id == created_company.id).all()
        branch_names = [b.name for b in branches]
        assert "Headquarters" in branch_names
        assert "Bengaluru Innovation Hub" in branch_names
        assert "Hyderabad Operations" in branch_names

        admin_user = db.query(User).filter(User.email == contact_email).first()
        assert admin_user is not None
        assert admin_user.role == UserRole.GLOBAL_ADMIN
        assert admin_user.company_id == created_company.id

        # ── 10. Newly provisioned Global Admin logs in at Company Portal ───────────
        comp_login = client.post(
            "/api/auth/login",
            json={
                "email": contact_email,
                "password": "SecurePassword@123",
                "portal": "company",
            },
        )
        assert comp_login.status_code == 200, comp_login.text
        login_res = comp_login.json()

        # Module 7 security requires mandatory MFA enrollment for newly onboarded company admins
        if login_res.get("mfa_enrollment_required"):
            assert login_res["mfa_enrollment_token"] is not None
            assert login_res["portal"] == "company"
            # Disable policy temporarily in test to verify standard session issuance
            created_company.mfa_required_for_all = False
            db.commit()
            comp_login = client.post(
                "/api/auth/login",
                json={
                    "email": contact_email,
                    "password": "SecurePassword@123",
                    "portal": "company",
                },
            )
            assert comp_login.status_code == 200
            login_res = comp_login.json()

        comp_token = login_res["access_token"]
        assert login_res["user"]["role"] == "GLOBAL_ADMIN"
        assert login_res["user"]["company_name"] == legal_name

        # Verify Global Admin can query /me
        me_comp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {comp_token}"})
        assert me_comp.status_code == 200
        assert me_comp.json()["company_name"] == legal_name

    finally:
        # Teardown: ensure test data never pollutes the database
        cleanup_db = SessionLocal()
        try:
            comp = cleanup_db.query(Company).filter(
                (Company.name == legal_name) | (Company.name == company_name)
            ).first()
            if comp:
                comp_id = comp.id
                cleanup_db.query(Invoice).filter(Invoice.company_id == comp_id).delete(synchronize_session=False)
                cleanup_db.query(Document).filter(Document.company_id == comp_id).delete(synchronize_session=False)
                test_users = cleanup_db.query(User).filter(User.company_id == comp_id).all()
                u_ids = [u.id for u in test_users]
                if u_ids:
                    cleanup_db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(u_ids)).delete(synchronize_session=False)
                    cleanup_db.query(UserSession).filter(UserSession.user_id.in_(u_ids)).delete(synchronize_session=False)
                    cleanup_db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_mfa_id.in_(
                        cleanup_db.query(UserMfa.id).filter(UserMfa.user_id.in_(u_ids))
                    )).delete(synchronize_session=False)
                    cleanup_db.query(UserMfa).filter(UserMfa.user_id.in_(u_ids)).delete(synchronize_session=False)
                    cleanup_db.query(User).filter(User.id.in_(u_ids)).delete(synchronize_session=False)
                cleanup_db.query(Branch).filter(Branch.company_id == comp_id).delete(synchronize_session=False)
                cleanup_db.delete(comp)

            # Delete the onboarding record
            cleanup_db.query(CompanyOnboarding).filter(
                (CompanyOnboarding.initial_company_name == company_name) |
                (CompanyOnboarding.legal_company_name == legal_name) |
                (CompanyOnboarding.contact_email == contact_email)
            ).delete(synchronize_session=False)
            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
        finally:
            cleanup_db.close()
