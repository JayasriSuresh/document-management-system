"""module12_search_upgrade

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-11-11 12:00:00.000000

Module 12 – Search Upgrade:
- PostgreSQL pg_trgm extension for trigram similarity and partial matching
- documents search and metadata columns:
    * invoice_number (varchar 128)
    * invoice_date (date)
    * seller_name (varchar 255)
    * seller_gstin (varchar 32)
    * buyer_name (varchar 255)
    * buyer_gstin (varchar 32)
    * grand_total (numeric 15, 2)
    * currency (varchar 10)
    * search_vector (tsvector)
- GIN index on search_vector
- Trigram GIN indexes on invoice_number, seller_name, seller_gstin, original_filename
- Composite B-tree indexes for tenant isolation, date filtering, and status filtering
- Database trigger trg_documents_search_vector for automatic search_vector maintenance
- Idempotent backfill of existing documents
"""
import json
import re
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'o1p2q3r4s5t6'
down_revision: Union[str, Sequence[str], None] = 'n1o2p3q4r5s6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def parse_indian_amount(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = re.sub(r'(?i)[₹\s]|rs\.?|inr|,', '', val).strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def parse_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return None
    clean = date_str.strip()
    fmts = [
        '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
        '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
        '%d-%b-%Y', '%d-%b-%y', '%d %b %Y', '%d %b %y',
        '%d-%B-%Y', '%d-%B-%y', '%d %B %Y', '%d %B %y',
        '%b %d, %Y', '%B %d, %Y',
    ]
    for f in fmts:
        try:
            return datetime.strptime(clean, f).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(clean.title(), f).date()
        except ValueError:
            pass
    return None


def upgrade() -> None:
    # 1. Enable pg_trgm extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # 2. Add search and metadata columns to documents table
    op.add_column('documents', sa.Column('invoice_number', sa.String(length=128), nullable=True))
    op.add_column('documents', sa.Column('invoice_date', sa.Date(), nullable=True))
    op.add_column('documents', sa.Column('seller_name', sa.String(length=255), nullable=True))
    op.add_column('documents', sa.Column('seller_gstin', sa.String(length=32), nullable=True))
    op.add_column('documents', sa.Column('buyer_name', sa.String(length=255), nullable=True))
    op.add_column('documents', sa.Column('buyer_gstin', sa.String(length=32), nullable=True))
    op.add_column('documents', sa.Column('grand_total', sa.Numeric(precision=15, scale=2), nullable=True))
    op.add_column('documents', sa.Column('currency', sa.String(length=10), server_default='INR', nullable=True))
    op.add_column('documents', sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True))

    # 3. Create full-text GIN index on search_vector
    op.create_index('ix_documents_search_vector', 'documents', ['search_vector'], postgresql_using='gin')

    # 4. Create trigram GIN indexes for fast partial and misspelled matching
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_trgm_invoice_number ON documents USING gin(invoice_number gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_trgm_seller_name ON documents USING gin(seller_name gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_trgm_seller_gstin ON documents USING gin(seller_gstin gin_trgm_ops);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_trgm_original_filename ON documents USING gin(original_filename gin_trgm_ops);")

    # 5. Composite B-Tree indexes for tenant-scoped structured filtering
    op.create_index('ix_documents_company_grand_total', 'documents', ['company_id', 'grand_total'])
    op.create_index('ix_documents_company_invoice_date', 'documents', ['company_id', 'invoice_date'])
    op.create_index('ix_documents_company_status', 'documents', ['company_id', 'ocr_status'])
    op.create_index('ix_documents_invoice_number', 'documents', ['invoice_number'])

    # 6. Create trigger function and trigger for automatic search_vector maintenance
    op.execute("""
    CREATE OR REPLACE FUNCTION documents_search_vector_trigger() RETURNS trigger AS $$
    BEGIN
        NEW.search_vector :=
            setweight(to_tsvector('simple', COALESCE(NEW.invoice_number, '') || ' ' || regexp_replace(COALESCE(NEW.invoice_number, ''), '[^a-zA-Z0-9]+', ' ', 'g')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(NEW.seller_gstin, '') || ' ' || regexp_replace(COALESCE(NEW.seller_gstin, ''), '[^a-zA-Z0-9]+', ' ', 'g')), 'A') ||
            setweight(to_tsvector('simple', COALESCE(NEW.buyer_gstin, '') || ' ' || regexp_replace(COALESCE(NEW.buyer_gstin, ''), '[^a-zA-Z0-9]+', ' ', 'g')), 'A') ||
            setweight(to_tsvector('english', COALESCE(NEW.seller_name, '')), 'B') ||
            setweight(to_tsvector('english', COALESCE(NEW.buyer_name, '')), 'B') ||
            setweight(to_tsvector('simple', COALESCE(NEW.original_filename, '') || ' ' || regexp_replace(COALESCE(NEW.original_filename, ''), '[^a-zA-Z0-9]+', ' ', 'g')), 'B') ||
            setweight(to_tsvector('english', SUBSTRING(COALESCE(NEW.ocr_text, '') FROM 1 FOR 500000)), 'D');
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    DROP TRIGGER IF EXISTS trg_documents_search_vector ON documents;
    CREATE TRIGGER trg_documents_search_vector
    BEFORE INSERT OR UPDATE OF ocr_text, invoice_number, seller_name, seller_gstin, buyer_name, buyer_gstin, original_filename
    ON documents
    FOR EACH ROW
    EXECUTE FUNCTION documents_search_vector_trigger();
    """)

    # 7. Backfill existing records
    conn = op.get_bind()
    docs = conn.execute(sa.text("SELECT id, original_filename, ocr_text, structured_data FROM documents")).fetchall()
    for d in docs:
        doc_id = d[0]
        orig_fn = d[1] or ""
        ocr_text = d[2] or ""
        raw_struct = d[3]

        data = {}
        if raw_struct:
            try:
                data = json.loads(raw_struct)
            except Exception:
                pass

        # Also check document_extractions if available
        ext_row = conn.execute(
            sa.text("SELECT data FROM document_extractions WHERE document_id = :did ORDER BY id DESC LIMIT 1"),
            {"did": doc_id}
        ).first()
        if ext_row and ext_row[0]:
            ext_data = ext_row[0]
            if isinstance(ext_data, dict):
                data.update(ext_data)

        inv = data.get("invoice", {})
        seller = data.get("seller", {})
        buyer = data.get("buyer", {})
        totals = data.get("totals", {})

        inv_num = inv.get("number") or data.get("invoice_number") or data.get("bill_no")
        inv_date_str = inv.get("date") or data.get("invoice_date") or data.get("date")
        inv_date = parse_date(inv_date_str) if inv_date_str else None

        s_name = seller.get("name") or data.get("seller_name") or data.get("merchant_name")
        s_gstin = seller.get("gstin") or data.get("seller_gstin") or data.get("gst_reg_no")

        b_name = buyer.get("name") or data.get("buyer_name") or data.get("customer_name")
        b_gstin = buyer.get("gstin") or data.get("buyer_gstin")

        tot_val = totals.get("grand_total")
        if tot_val is None:
            tot_val = data.get("total_amount")
        grand_total = parse_indian_amount(tot_val)

        # Trigger will fire on update and compute search_vector
        conn.execute(
            sa.text("""
                UPDATE documents
                SET invoice_number = :inv_num,
                    invoice_date = :inv_date,
                    seller_name = :s_name,
                    seller_gstin = :s_gstin,
                    buyer_name = :b_name,
                    buyer_gstin = :b_gstin,
                    grand_total = :grand_total,
                    ocr_text = :ocr_text
                WHERE id = :doc_id
            """),
            {
                "inv_num": inv_num,
                "inv_date": inv_date,
                "s_name": s_name,
                "s_gstin": s_gstin,
                "b_name": b_name,
                "b_gstin": b_gstin,
                "grand_total": grand_total,
                "ocr_text": ocr_text,
                "doc_id": doc_id,
            }
        )


def downgrade() -> None:
    # 1. Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trg_documents_search_vector ON documents;")
    op.execute("DROP FUNCTION IF EXISTS documents_search_vector_trigger();")

    # 2. Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_documents_trgm_invoice_number;")
    op.execute("DROP INDEX IF EXISTS ix_documents_trgm_seller_name;")
    op.execute("DROP INDEX IF EXISTS ix_documents_trgm_seller_gstin;")
    op.execute("DROP INDEX IF EXISTS ix_documents_trgm_original_filename;")
    op.drop_index('ix_documents_invoice_number', table_name='documents')
    op.drop_index('ix_documents_company_status', table_name='documents')
    op.drop_index('ix_documents_company_invoice_date', table_name='documents')
    op.drop_index('ix_documents_company_grand_total', table_name='documents')
    op.drop_index('ix_documents_search_vector', table_name='documents')

    # 3. Drop columns
    op.drop_column('documents', 'search_vector')
    op.drop_column('documents', 'currency')
    op.drop_column('documents', 'grand_total')
    op.drop_column('documents', 'buyer_gstin')
    op.drop_column('documents', 'buyer_name')
    op.drop_column('documents', 'seller_gstin')
    op.drop_column('documents', 'seller_name')
    op.drop_column('documents', 'invoice_date')
    op.drop_column('documents', 'invoice_number')
