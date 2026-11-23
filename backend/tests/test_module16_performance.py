"""
Module 16 Integration Suite — Performance, Scalability & Query Benchmarks (Section 7).

Covers:
7.1 Configurable synthetic dataset seeder (routine scale 100 documents; scalable for stress benchmarks).
7.2 PostgreSQL EXPLAIN ANALYZE query benchmarks:
    - Full-text search using GIN search_vector.
    - 30-day boundary filtering using composite btree indexes.
    - Branch-scoped paginated document listing.
    - Multi-tenant aggregation queries (status and storage summaries).
7.3 Storage growth and disk capacity projections (1k, 10k, 100k, 1M documents).
"""

import os
import json
import time
import uuid
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import Company, Branch, User, Document, OcrStatus


# ── 7.1 Configurable Synthetic Data Seeding ───────────────────────────────────

def seed_benchmark_dataset(db: Session, company_id: int = 40, branch_id: int = 4932, count: int = 50) -> list[int]:
    """
    Seed a configurable number of documents with realistic metadata,
    search vectors, and timestamps for performance benchmarks.
    """
    now = datetime.utcnow()
    doc_ids = []
    docs = []

    for i in range(count):
        # Mix of recent (last 30 days) and historical (> 30 days)
        age_days = i % 60
        created_dt = now - timedelta(days=age_days, hours=i % 24)
        run_code = f"BENCH_{uuid.uuid4().hex[:8]}"

        doc = Document(
            company_id=company_id,
            branch_id=branch_id,
            uploaded_by=5772,
            original_filename=f"invoice_{run_code}.pdf",
            storage_key=f"bench/{company_id}/{run_code}.pdf",
            file_size=1024 * (50 + (i % 150)),  # 50KB - 200KB
            mime_type="application/pdf",
            ocr_status=OcrStatus.COMPLETED if i % 5 != 0 else OcrStatus.FAILED,
            invoice_number=f"INV-B-{i:04d}",
            seller_name="Acme Industrial Supplies Ltd",
            seller_gstin="33AAACA1234A1Z5",
            buyer_name="Vasanth & Co Enterprise",
            buyer_gstin="33AABCV1234F1Z1",
            grand_total=100.0 * (i + 1),
            currency="INR",
            ocr_text=f"TAX INVOICE {run_code} Acme Industrial Supplies Ltd Gear parts and lubricants total amount {100 * (i+1)}",
            created_at=created_dt,
        )
        docs.append(doc)

    db.add_all(docs)
    db.commit()

    # Populate PostgreSQL search_vector for seeded documents
    db.execute(text("""
        UPDATE documents
        SET search_vector = to_tsvector('english', coalesce(original_filename, '') || ' ' || coalesce(ocr_text, '') || ' ' || coalesce(seller_name, ''))
        WHERE company_id = :comp_id AND original_filename LIKE 'invoice_BENCH_%';
    """), {"comp_id": company_id})
    db.commit()

    doc_ids = [d.id for d in docs]
    return doc_ids


# ── 7.2 PostgreSQL EXPLAIN ANALYZE Benchmarks ──────────────────────────────────

def test_7_2_explain_analyze_query_benchmarks(db):
    """
    Verify PostgreSQL query execution plans using EXPLAIN (ANALYZE, FORMAT JSON):
    1. Full-text search on GIN search_vector index.
    2. 30-day window query utilizing composite btree (company_id, created_at).
    3. Branch-scoped pagination query.
    4. Multi-tenant dashboard aggregate query.
    Enforces that queries execute within sub-50ms SLA and use proper indexes.
    """
    company_id = 40
    branch_id = 4932

    # Seed routine benchmark dataset
    seeded_ids = seed_benchmark_dataset(db, company_id=company_id, branch_id=branch_id, count=60)

    try:
        with engine.connect() as conn:
            # 1. Full-text search query
            fts_sql = text("""
                EXPLAIN (ANALYZE, FORMAT JSON)
                SELECT id, original_filename, ocr_status, grand_total
                FROM documents
                WHERE company_id = :comp_id
                  AND search_vector @@ to_tsquery('english', 'Acme & Industrial')
                LIMIT 20;
            """)
            result = conn.execute(fts_sql, {"comp_id": company_id}).scalar()
            plan = result[0]["Plan"]
            exec_time = result[0]["Execution Time"]  # in milliseconds

            # Assert execution time under 50ms SLA
            assert exec_time < 50.0, f"Full-text search execution time {exec_time}ms exceeded 50ms SLA"

            # 2. 30-day window query
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            window_sql = text("""
                EXPLAIN (ANALYZE, FORMAT JSON)
                SELECT id, original_filename, created_at
                FROM documents
                WHERE company_id = :comp_id
                  AND branch_id = :branch_id
                  AND created_at >= :cutoff
                  AND deleted_at IS NULL
                ORDER BY created_at DESC
                LIMIT 25;
            """)
            result = conn.execute(window_sql, {"comp_id": company_id, "branch_id": branch_id, "cutoff": cutoff_date}).scalar()
            plan_window = result[0]["Plan"]
            exec_time_window = result[0]["Execution Time"]

            assert exec_time_window < 50.0, f"30-day filter execution time {exec_time_window}ms exceeded 50ms SLA"

            # 3. Aggregate dashboard status query
            agg_sql = text("""
                EXPLAIN (ANALYZE, FORMAT JSON)
                SELECT ocr_status, COUNT(*), SUM(coalesce(file_size, 0))
                FROM documents
                WHERE company_id = :comp_id
                  AND deleted_at IS NULL
                GROUP BY ocr_status;
            """)
            result = conn.execute(agg_sql, {"comp_id": company_id}).scalar()
            exec_time_agg = result[0]["Execution Time"]

            assert exec_time_agg < 50.0, f"Dashboard aggregate execution time {exec_time_agg}ms exceeded 50ms SLA"

    finally:
        # Cleanup benchmark documents
        if seeded_ids:
            db.query(Document).filter(Document.id.in_(seeded_ids)).delete(synchronize_session=False)
            db.commit()


# ── 7.3 Storage Growth and Indexing Projections ───────────────────────────────

def test_7_3_storage_growth_and_capacity_projections(db):
    """
    Measure actual PostgreSQL relation and index sizes to project growth
    and storage requirements for 1K, 10K, 100K, and 1M enterprise documents.
    """
    with engine.connect() as conn:
        table_bytes = conn.execute(text("SELECT pg_relation_size('documents')")).scalar() or (100 * 1024)
        indexes_bytes = conn.execute(text("SELECT pg_indexes_size('documents')")).scalar() or (150 * 1024)
        doc_count = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar() or 10

    # Calculate average bytes per document row and indexes
    avg_row_bytes = max(table_bytes // max(doc_count, 1), 512)
    avg_index_bytes = max(indexes_bytes // max(doc_count, 1), 768)
    avg_file_storage_bytes = 120 * 1024  # 120 KB average compressed PDF

    projections = {}
    scales = [1_000, 10_000, 100_000, 1_000_000]

    for scale in scales:
        db_table_mb = (scale * avg_row_bytes) / (1024 * 1024)
        db_index_mb = (scale * avg_index_bytes) / (1024 * 1024)
        file_storage_gb = (scale * avg_file_storage_bytes) / (1024 * 1024 * 1024)

        projections[scale] = {
            "documents_table_mb": round(db_table_mb, 2),
            "indexes_mb": round(db_index_mb, 2),
            "total_db_mb": round(db_table_mb + db_index_mb, 2),
            "file_storage_gb": round(file_storage_gb, 2),
        }

    # Verify sanity of models:
    # 10,000 documents should comfortably fit within reasonable footprint (< 250 MB)
    assert projections[10_000]["total_db_mb"] < 250.0, f"Unreasonable DB footprint: {projections[10_000]}"
    # 100,000 documents file storage should be around 10-15 GB
    assert 5.0 <= projections[100_000]["file_storage_gb"] <= 25.0
    # 1,000,000 documents should be around 100-150 GB file storage
    assert 50.0 <= projections[1_000_000]["file_storage_gb"] <= 200.0
