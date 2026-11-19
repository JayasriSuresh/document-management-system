"""
Database seeding utility updated for Company -> Branch hierarchy.

In development/testing:
  Seeds default company (Vasanth & Co.), branches (Chennai, Mysore) and test users.

In production:
  Refuses to seed default demo accounts or drop tables unless explicitly instructed
  via environment flags, preventing accidental data loss or default credentials in prod.
"""

import sys
import os
import shutil
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
from app.models import (
    Company,
    CompanyStatus,
    Branch,
    Tenant,
    User,
    UserRole,
    Document,
    OcrStatus,
    MasterAdmin,
    AccountStatus,
    CompanyOnboarding,
    AuditLog,
    UserMfa,
    MfaRecoveryCode,
    PlatformSetting,
    AIUsageLedger,
    UserSession,
    UserRoleAssignment,
    PasswordReset,
    Invitation,
)
from app.auth import get_password_hash
from app.config import settings
from sqlalchemy import text, inspect


def reset_db():
    if settings.is_production and os.getenv("DANGEROUSLY_ALLOW_PRODUCTION_RESET") != "1":
        raise RuntimeError(
            "CRITICAL: Refusing to drop tables in production! "
            "Set DANGEROUSLY_ALLOW_PRODUCTION_RESET=1 only if you explicitly intend to wipe production data."
        )
    print("Dropping all tables with CASCADE...")
    with engine.connect() as conn:
        # Drop all tables cleanly with CASCADE in dev
        conn.execute(text("""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """))
        conn.commit()
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    # Re-stamp alembic head
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config("alembic.ini")
        command.stamp(alembic_cfg, "head")
    except Exception as e:
        print(f"Note: Could not stamp alembic: {e}")



def seed_production():
    """Production initialization: creates an initial company, branch & admin if none exist."""
    admin_email = os.getenv("SEED_ADMIN_EMAIL")
    admin_password = os.getenv("SEED_ADMIN_PASSWORD")
    company_name = os.getenv("SEED_COMPANY_NAME", "Vasanth & Co.")
    company_code = os.getenv("SEED_COMPANY_CODE", "VASANTH_CO")
    branch_name = os.getenv("SEED_BRANCH_NAME", "Chennai")
    branch_code = os.getenv("SEED_BRANCH_CODE", "CHENNAI")

    if not admin_email or not admin_password:
        print("Production seeding requires SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD.")
        print("Skipping automatic seed.")
        return

    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.code == company_code).first()
        if not company:
            company = Company(name=company_name, code=company_code, status=CompanyStatus.ACTIVE)
            db.add(company)
            db.flush()

        branch = db.query(Branch).filter(Branch.company_id == company.id, Branch.code == branch_code).first()
        if not branch:
            branch = Branch(company_id=company.id, name=branch_name, code=branch_code)
            db.add(branch)
            db.flush()

        existing_user = db.query(User).filter(User.email == admin_email).first()
        if not existing_user:
            admin_user = User(
                company_id=company.id,
                branch_id=branch.id,
                name="System Administrator",
                email=admin_email,
                password_hash=get_password_hash(admin_password),
                role=UserRole.GLOBAL_ADMIN,
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Initial production admin created: {admin_email} for company {company_name}")
        else:
            print(f"Admin {admin_email} already exists. Skipping.")
    finally:
        db.close()


def seed(force=False):
    if settings.is_production:
        if os.getenv("SEED_ALLOW_IN_PRODUCTION") != "1":
            print("⚠️ APP_ENV is 'production'. Demo seeding with default credentials is disabled.")
            print("To bootstrap an admin user, set SEED_ADMIN_EMAIL, SEED_ADMIN_PASSWORD and SEED_ALLOW_IN_PRODUCTION=1.")
            return
        return seed_production()

    inspector = inspect(engine)
    if inspector.has_table("users"):
        check_db = SessionLocal()
        try:
            if check_db.query(User).count() > 0 and not force:
                print("Database already has data. Skipping re-seed. Use `python seed.py --reset` to force reset.")
                return
        finally:
            check_db.close()

    reset_db()

    db = SessionLocal()
    try:
        # 1. Create Default Company: Vasanth & Co.
        vasanth = Company(
            name="Vasanth & Co.",
            code="VASANTH_CO",
            status=CompanyStatus.ACTIVE,
        )
        db.add(vasanth)
        db.flush()

        # 2. Create Branches
        chennai = Branch(company_id=vasanth.id, name="Chennai", code="CHENNAI")
        mysore = Branch(company_id=vasanth.id, name="Mysore", code="MYSORE")
        db.add_all([chennai, mysore])
        db.flush()

        # 3. Create Users & Master Admin — development only
        default_pw = os.getenv("DEV_SEED_PASSWORD", "Pasword@123")
        hashed_pw = get_password_hash(default_pw)

        # 3a. Platform Master Admin (Independent of company)
        master_root = MasterAdmin(
            name="Platform Root Administrator",
            email="master@platform.local",
            password_hash=hashed_pw,
            status=AccountStatus.ACTIVE,
            token_version=1,
            must_change_password=False,
            failed_attempts=0,
        )
        db.add(master_root)

        # 3b. Company Users
        jayasri = User(
            company_id=vasanth.id,
            branch_id=chennai.id,
            name="Jayasri",
            email="jayasri@example.com",
            password_hash=hashed_pw,
            role=UserRole.GLOBAL_ADMIN,
        )
        samrethi = User(
            company_id=vasanth.id,
            branch_id=chennai.id,
            name="Samrethi",
            email="samrethi@example.com",
            password_hash=hashed_pw,
            role=UserRole.ADMIN,
        )
        sujipriya = User(
            company_id=vasanth.id,
            branch_id=chennai.id,
            name="Sujipriya",
            email="sujipriya@example.com",
            password_hash=hashed_pw,
            role=UserRole.STAFF,
        )

        hindu_priya = User(
            company_id=vasanth.id,
            branch_id=mysore.id,
            name="Hindu Priya",
            email="hindupriya@example.com",
            password_hash=hashed_pw,
            role=UserRole.ADMIN,
        )
        boomika = User(
            company_id=vasanth.id,
            branch_id=mysore.id,
            name="Boomika",
            email="boomika@example.com",
            password_hash=hashed_pw,
            role=UserRole.STAFF,
        )

        db.add_all([jayasri, samrethi, sujipriya, hindu_priya, boomika])
        db.flush()

        # Make sure storage dir exists
        os.makedirs(settings.STORAGE_PATH, exist_ok=True)
        # Clear existing non-invoice storage
        for f in os.listdir(settings.STORAGE_PATH):
            if not f.startswith("generated_invoice_"):
                try:
                    os.remove(os.path.join(settings.STORAGE_PATH, f))
                except OSError:
                    pass

        source_image = os.path.join(os.path.dirname(__file__), "test_11.jpg")
        if not os.path.exists(source_image):
            with open(source_image, "wb") as f:
                f.write(b"dummy")

        user_test_image = "/home/ubuntu/Downloads/17905982699145377177312188690039 (1) (1).jpg"

        now = datetime.utcnow()
        recent = now - timedelta(days=10)
        old = now - timedelta(days=40)

        doc_definitions = [
            {"uploader": samrethi, "name": "17905982699145377177312188690039 (1) (1).jpg", "time": now, "deleted": False, "src": user_test_image, "ocr_status": OcrStatus.UPLOADED, "ocr_text": None},
            {"uploader": samrethi,   "name": "chennai_admin_doc.jpg",  "time": recent, "deleted": False, "src": source_image},
            {"uploader": sujipriya,  "name": "sujipriya_recent.jpg",   "time": recent, "deleted": False, "src": source_image},
            {"uploader": sujipriya,  "name": "sujipriya_old.jpg",      "time": old,    "deleted": False, "src": source_image},
            {"uploader": sujipriya,  "name": "sujipriya_deleted.jpg",  "time": recent, "deleted": True,  "src": source_image},
            {"uploader": hindu_priya, "name": "mysore_admin_doc.jpg",  "time": recent, "deleted": False, "src": source_image},
            {"uploader": boomika,     "name": "boomika_recent.jpg",    "time": recent, "deleted": False, "src": source_image},
            {"uploader": boomika,     "name": "boomika_old.jpg",       "time": old,    "deleted": False, "src": source_image},
        ]

        for doc_def in doc_definitions:
            u = doc_def["uploader"]
            src_file = doc_def.get("src", source_image)
            storage_key = f"{uuid.uuid4()}.jpg"
            if os.path.exists(src_file):
                shutil.copy(src_file, os.path.join(settings.STORAGE_PATH, storage_key))
            else:
                shutil.copy(source_image, os.path.join(settings.STORAGE_PATH, storage_key))

            doc = Document(
                company_id=u.company_id,
                branch_id=u.branch_id,
                uploaded_by=u.id,
                original_filename=doc_def["name"],
                storage_key=storage_key,
                mime_type="image/jpeg",
                file_size=os.path.getsize(src_file) if os.path.exists(src_file) else os.path.getsize(source_image),
                ocr_text=doc_def.get("ocr_text", "Dummy seeded document — re-process to extract real text."),
                ocr_status=doc_def.get("ocr_status", OcrStatus.COMPLETED),
                created_at=doc_def["time"],
                deleted_at=datetime.utcnow() if doc_def["deleted"] else None
            )
            db.add(doc)

        db.commit()
        print("✅ Seed complete! Seeded Vasanth & Co., branches (Chennai, Mysore) and realistic user data.")
    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    force_reset = "--reset" in sys.argv
    seed(force=force_reset)
