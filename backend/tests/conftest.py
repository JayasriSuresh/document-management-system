"""
Pytest fixtures for DMS test suite.

Provides:
  - test_client: FastAPI TestClient configured for the test app
  - db_session: SQLAlchemy session tied to test database
  - seed_data: Helper fixture that provides known tenants and users for testing
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, Base, engine
from app.models import Tenant, User, UserRole, Document, OcrStatus, UserMfa, MfaRecoveryCode, Company, PlatformSetting, MasterAdmin
from app.auth import get_password_hash, create_access_token


@pytest.fixture(scope="session")
def client():
    """Shared TestClient instance."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="function")
def db():
    """Provides a transactional database session for each test function."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function", autouse=True)
def reset_test_state(db):
    """Ensure test documents, MFA policies, and user accounts are in known clean state."""
    db.query(Document).filter(
        Document.original_filename.in_([
            "chennai_admin_doc.jpg",
            "mysore_admin_doc.jpg",
            "sujipriya_recent.jpg",
            "boomika_recent.jpg",
        ])
    ).update({Document.deleted_at: None, Document.deleted_by: None}, synchronize_session=False)

    # Reset platform MFA policy so standard test logins don't block on MFA
    ps = db.query(PlatformSetting).filter(PlatformSetting.key == "mfa_policy").first()
    if ps:
        ps.value = {"enforce_master_admin": False, "enforce_company_admin": False, "enforce_all": False}
    for c in db.query(Company).all():
        c.mfa_required_for_all = False

    db.commit()


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_seed_artifacts():
    """Ensure no test companies or onboardings are left behind after any test session."""
    yield
    from sqlalchemy import text
    from app.database import SessionLocal
    from app.models import (
        Company, Branch, User, Document, Invoice, InvoiceItem, SupplierInvoiceCopy,
        CompanyOnboarding, UserRoleAssignment, UserSession, UserMfa, MfaRecoveryCode,
        Invitation, ProcessingJob, AIProcessingLog, AIUsageLedger, BranchAIConfig,
        CompanyAISetting, CompanyAIConsent, DocumentExtraction, ExtractionEdit
    )
    clean_db = SessionLocal()
    try:
        clean_db.execute(text("SET session_replication_role = 'replica';"))

        # Clean up ANY company that is not Company 24 or Company 40 (stable test tenants)
        test_comps = clean_db.query(Company).filter(Company.id.notin_([24, 40])).all()
        test_ids = [c.id for c in test_comps]
        if test_ids:
            clean_db.query(AIProcessingLog).filter(AIProcessingLog.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(AIUsageLedger).filter(AIUsageLedger.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(BranchAIConfig).filter(BranchAIConfig.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(CompanyAISetting).filter(CompanyAISetting.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(CompanyAIConsent).filter(CompanyAIConsent.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(ProcessingJob).filter(ProcessingJob.company_id.in_(test_ids)).delete(synchronize_session=False)

            subq_inv = clean_db.query(Invoice.id).filter(Invoice.company_id.in_(test_ids)).subquery()
            clean_db.query(SupplierInvoiceCopy).filter(SupplierInvoiceCopy.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(InvoiceItem).filter(InvoiceItem.invoice_id.in_(subq_inv)).delete(synchronize_session=False)
            clean_db.query(Invoice).filter(Invoice.company_id.in_(test_ids)).delete(synchronize_session=False)

            subq_docs = clean_db.query(Document.id).filter(Document.company_id.in_(test_ids)).subquery()
            subq_extractions = clean_db.query(DocumentExtraction.id).filter(DocumentExtraction.document_id.in_(subq_docs)).subquery()
            clean_db.query(ExtractionEdit).filter(ExtractionEdit.document_extraction_id.in_(subq_extractions)).delete(synchronize_session=False)
            clean_db.query(DocumentExtraction).filter(DocumentExtraction.document_id.in_(subq_docs)).delete(synchronize_session=False)
            clean_db.query(Document).filter(Document.company_id.in_(test_ids)).delete(synchronize_session=False)

            clean_db.query(Invitation).filter(Invitation.company_id.in_(test_ids)).delete(synchronize_session=False)
            test_users = clean_db.query(User).filter(User.company_id.in_(test_ids)).all()
            user_ids = [u.id for u in test_users]
            if user_ids:
                clean_db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id.in_(user_ids)).delete(synchronize_session=False)
                clean_db.query(UserSession).filter(UserSession.user_id.in_(user_ids)).delete(synchronize_session=False)
                mfa_ids = [m.id for m in clean_db.query(UserMfa).filter(UserMfa.user_id.in_(user_ids)).all()]
                if mfa_ids:
                    clean_db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_mfa_id.in_(mfa_ids)).delete(synchronize_session=False)
                clean_db.query(UserMfa).filter(UserMfa.user_id.in_(user_ids)).delete(synchronize_session=False)
                clean_db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
            clean_db.query(Branch).filter(Branch.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(CompanyOnboarding).filter(CompanyOnboarding.company_id.in_(test_ids)).delete(synchronize_session=False)
            clean_db.query(Company).filter(Company.id.in_(test_ids)).delete(synchronize_session=False)

        # Residual unlinked onboardings
        clean_db.query(CompanyOnboarding).filter(CompanyOnboarding.id != 4).delete(synchronize_session=False)

        # Ensure no synthetic AI processing logs in Company 24
        clean_db.query(AIProcessingLog).filter(
            AIProcessingLog.company_id == 24,
            AIProcessingLog.id.notin_([55, 56])
        ).delete(synchronize_session=False)

        clean_db.execute(text("SET session_replication_role = 'origin';"))
        clean_db.commit()
    except Exception:
        clean_db.rollback()
    finally:
        clean_db.close()


@pytest.fixture(scope="function")
def auth_headers(client):
    """Factory fixture returning auth headers for any email."""
    def _get_headers(email: str, password: str = "Pasword@123"):
        resp = client.post("/api/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            raise ValueError(f"Failed to login {email}: {resp.text}")
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _get_headers
