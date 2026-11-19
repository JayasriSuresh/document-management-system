"""module11_templates_review

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-11-10 16:30:00.000000

Module 11 – Extraction Templates and Human Verification:
- document_templates: template definition scoped to company and optional branch
- template_versions: immutable sequential versioning for schemas and deterministic rules
- documents.template_version_id: version pinning for document lifecycle
- document_extractions: structured extraction records with review status and flags
- extraction_edits: granular transactional audit trail of human corrections
- idempotent seed of Default GST Invoice template v1 and backfill of existing documents
"""
import json
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, Sequence[str], None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GST_SCHEMA_JSON = {
    "type": "object",
    "fields": [
        {
            "key": "seller",
            "label": "Seller Details",
            "type": "object",
            "required": True,
            "fields": [
                {"key": "name", "label": "Seller Name", "type": "string", "required": True},
                {"key": "gstin", "label": "Seller GSTIN", "type": "string", "required": False},
                {"key": "address", "label": "Seller Address", "type": "string", "required": False},
                {"key": "state", "label": "Seller State", "type": "string", "required": False},
                {"key": "state_code", "label": "State Code", "type": "string", "required": False},
                {"key": "phone", "label": "Phone", "type": "string", "required": False},
                {"key": "email", "label": "Email", "type": "string", "required": False}
            ]
        },
        {
            "key": "buyer",
            "label": "Buyer Details",
            "type": "object",
            "required": False,
            "fields": [
                {"key": "name", "label": "Buyer Name", "type": "string", "required": False},
                {"key": "gstin", "label": "Buyer GSTIN", "type": "string", "required": False},
                {"key": "address", "label": "Buyer Address", "type": "string", "required": False},
                {"key": "state", "label": "Buyer State", "type": "string", "required": False},
                {"key": "state_code", "label": "State Code", "type": "string", "required": False},
                {"key": "phone", "label": "Phone", "type": "string", "required": False}
            ]
        },
        {
            "key": "invoice",
            "label": "Invoice Metadata",
            "type": "object",
            "required": True,
            "fields": [
                {"key": "number", "label": "Invoice Number", "type": "string", "required": True},
                {"key": "date", "label": "Invoice Date", "type": "date", "required": True},
                {"key": "payment_terms", "label": "Payment Terms", "type": "string", "required": False},
                {"key": "reference_no", "label": "Reference No", "type": "string", "required": False},
                {"key": "buyers_order_no", "label": "Buyer's Order No", "type": "string", "required": False},
                {"key": "terms_of_delivery", "label": "Terms of Delivery", "type": "string", "required": False},
                {"key": "other_references", "label": "Other References", "type": "string", "required": False}
            ]
        },
        {
            "key": "items",
            "label": "Line Items",
            "type": "array",
            "required": False,
            "item_fields": [
                {"key": "sl", "label": "S.No", "type": "integer"},
                {"key": "description", "label": "Description", "type": "string", "required": True},
                {"key": "batch", "label": "Batch", "type": "string"},
                {"key": "hsn", "label": "HSN/SAC", "type": "string"},
                {"key": "gst_rate", "label": "GST Rate (%)", "type": "number"},
                {"key": "qty", "label": "Quantity", "type": "string"},
                {"key": "rate", "label": "Unit Rate", "type": "number"},
                {"key": "discount", "label": "Discount", "type": "number"},
                {"key": "amount", "label": "Taxable Amount", "type": "number"}
            ]
        },
        {
            "key": "totals",
            "label": "Tax & Totals",
            "type": "object",
            "required": True,
            "fields": [
                {"key": "taxable_value", "label": "Taxable Value", "type": "number", "required": False},
                {"key": "cgst", "label": "CGST", "type": "number", "required": False},
                {"key": "sgst", "label": "SGST", "type": "number", "required": False},
                {"key": "igst", "label": "IGST", "type": "number", "required": False},
                {"key": "round_off", "label": "Round Off", "type": "number", "required": False},
                {"key": "total_qty", "label": "Total Quantity", "type": "string", "required": False},
                {"key": "grand_total", "label": "Grand Total", "type": "number", "required": True},
                {"key": "amount_in_words", "label": "Amount In Words", "type": "string", "required": False}
            ]
        },
        {
            "key": "bank",
            "label": "Bank Details",
            "type": "object",
            "required": False,
            "fields": [
                {"key": "holder", "label": "Account Holder", "type": "string"},
                {"key": "bank_name", "label": "Bank Name", "type": "string"},
                {"key": "account_no", "label": "Account Number", "type": "string"},
                {"key": "branch", "label": "Branch", "type": "string"},
                {"key": "ifsc", "label": "IFSC Code", "type": "string"}
            ]
        }
    ]
}

GST_VALIDATION_RULES = [
    {
        "rule_id": "gstin_format",
        "name": "Indian GSTIN Format Validation",
        "type": "gstin",
        "fields": ["seller.gstin", "buyer.gstin"],
        "severity": "error"
    },
    {
        "rule_id": "invoice_date_format",
        "name": "Invoice Date Format Validation",
        "type": "date",
        "fields": ["invoice.date"],
        "severity": "error"
    },
    {
        "rule_id": "line_item_math",
        "name": "Line Item Quantity x Rate Arithmetic",
        "type": "line_item_arithmetic",
        "items_path": "items",
        "tolerance": 0.5,
        "severity": "error"
    },
    {
        "rule_id": "totals_consistency",
        "name": "Taxable Value + Taxes = Grand Total",
        "type": "totals_sum",
        "totals_path": "totals",
        "tolerance": 0.5,
        "severity": "error"
    },
    {
        "rule_id": "gst_tax_consistency",
        "name": "CGST/SGST vs IGST Consistency",
        "type": "gst_consistency",
        "seller_path": "seller",
        "buyer_path": "buyer",
        "totals_path": "totals",
        "severity": "warning"
    }
]

GST_EXTRACTION_INSTRUCTIONS = (
    "You are an expert Indian GST invoice extraction and normalization AI.\n"
    "Extract EVERY field from the invoice image and return ONLY valid JSON matching this schema:\n"
    "{\n"
    '  "seller":  {"name":"","address":"","gstin":"","state":"","state_code":"","phone":"","email":""},\n'
    '  "buyer":   {"name":"","address":"","gstin":"","state":"","state_code":"","phone":""},\n'
    '  "invoice": {"number":"","date":"","payment_terms":"","reference_no":"","buyers_order_no":"","terms_of_delivery":"","other_references":""},\n'
    '  "delivery":{"name":"","address":""},\n'
    '  "items":   [{"sl":1,"description":"","batch":"","hsn":"","gst_rate":null,"qty":"","rate":null,"discount":null,"amount":null}],\n'
    '  "totals":  {"taxable_value":null,"cgst":null,"sgst":null,"igst":null,"round_off":null,"total_qty":"","grand_total":null,"amount_in_words":""},\n'
    '  "bank":    {"holder":"","bank_name":"","account_no":"","branch":"","ifsc":""},\n'
    '  "declaration":"",\n'
    '  "warranty_note":"",\n'
    '  "footer":[]\n'
    "}\n"
    "Keep seller and buyer data strictly separate — do NOT copy buyer contact/GSTIN into seller fields.\n"
    "Do NOT invent placeholder values."
)


def upgrade() -> None:
    # 1. document_templates
    op.create_table(
        'document_templates',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE', name='fk_document_templates_company_id'), nullable=True, index=True),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='SET NULL', name='fk_document_templates_branch_id'), nullable=True, index=True),
        sa.Column('document_type', sa.String(length=64), nullable=False, index=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False, server_default='extraction'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_document_templates_created_by'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_doc_templates_lookup', 'document_templates', ['company_id', 'branch_id', 'document_type', 'status'])

    # 2. template_versions
    op.create_table(
        'template_versions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('template_id', sa.Integer(), sa.ForeignKey('document_templates.id', ondelete='CASCADE', name='fk_template_versions_template_id'), nullable=False, index=True),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('schema_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('validation_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('extraction_instructions', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='draft'),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_template_versions_created_by'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('template_id', 'version_number', name='uq_template_version_number')
    )
    op.create_index('ix_template_versions_lookup', 'template_versions', ['template_id', 'status'])

    # 3. Add template_version_id to documents
    op.add_column(
        'documents',
        sa.Column('template_version_id', sa.Integer(), sa.ForeignKey('template_versions.id', ondelete='SET NULL', name='fk_documents_template_version_id'), nullable=True)
    )
    op.create_index('ix_documents_template_version_id', 'documents', ['template_version_id'])

    # 4. document_extractions
    op.create_table(
        'document_extractions',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('documents.id', ondelete='CASCADE', name='fk_document_extractions_document_id'), nullable=False, unique=True, index=True),
        sa.Column('template_version_id', sa.Integer(), sa.ForeignKey('template_versions.id', ondelete='RESTRICT', name='fk_document_extractions_template_version_id'), nullable=False, index=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('validation_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='extracted'),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_document_extractions_reviewed_by'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )

    # 5. extraction_edits
    op.create_table(
        'extraction_edits',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('document_extraction_id', sa.Integer(), sa.ForeignKey('document_extractions.id', ondelete='CASCADE', name='fk_extraction_edits_document_extraction_id'), nullable=False, index=True),
        sa.Column('field_path', sa.String(length=255), nullable=False),
        sa.Column('old_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('new_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('edited_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL', name='fk_extraction_edits_edited_by'), nullable=True),
        sa.Column('edited_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_extraction_edits_extraction_id', 'extraction_edits', ['document_extraction_id'])

    # 6. Seed Default GST Template idempotently
    bind = op.get_bind()

    # Platform default template (company_id is NULL)
    res = bind.execute(text("SELECT id FROM document_templates WHERE company_id IS NULL AND document_type = 'gst_invoice'")).fetchone()
    if not res:
        ins_t = bind.execute(
            text("""
                INSERT INTO document_templates (company_id, branch_id, document_type, name, kind, description, status, created_at, updated_at)
                VALUES (NULL, NULL, 'gst_invoice', 'Default GST Invoice', 'extraction', 'Platform default Indian GST invoice extraction template', 'active', now(), now())
                RETURNING id
            """)
        ).fetchone()
        platform_tid = ins_t[0]
        # Seed version 1 published
        bind.execute(
            text("""
                INSERT INTO template_versions (template_id, version_number, schema_json, validation_rules, extraction_instructions, status, published_at, created_at)
                VALUES (:tid, 1, CAST(:schema AS jsonb), CAST(:rules AS jsonb), :instructions, 'published', now(), now())
            """),
            {
                "tid": platform_tid,
                "schema": json.dumps(GST_SCHEMA_JSON),
                "rules": json.dumps(GST_VALIDATION_RULES),
                "instructions": GST_EXTRACTION_INSTRUCTIONS,
            }
        )

    # For each existing company, seed company-level default GST template
    companies = bind.execute(text("SELECT id, name FROM companies")).fetchall()
    for comp in companies:
        cid = comp[0]
        t_row = bind.execute(
            text("SELECT id FROM document_templates WHERE company_id = :cid AND branch_id IS NULL AND document_type = 'gst_invoice'"),
            {"cid": cid}
        ).fetchone()
        if not t_row:
            ins_comp_t = bind.execute(
                text("""
                    INSERT INTO document_templates (company_id, branch_id, document_type, name, kind, description, status, created_at, updated_at)
                    VALUES (:cid, NULL, 'gst_invoice', 'Default GST Invoice', 'extraction', 'Standard Indian GST invoice template', 'active', now(), now())
                    RETURNING id
                """),
                {"cid": cid}
            ).fetchone()
            comp_tid = ins_comp_t[0]
            v_res = bind.execute(
                text("""
                    INSERT INTO template_versions (template_id, version_number, schema_json, validation_rules, extraction_instructions, status, published_at, created_at)
                    VALUES (:tid, 1, CAST(:schema AS jsonb), CAST(:rules AS jsonb), :instructions, 'published', now(), now())
                    RETURNING id
                """),
                {
                    "tid": comp_tid,
                    "schema": json.dumps(GST_SCHEMA_JSON),
                    "rules": json.dumps(GST_VALIDATION_RULES),
                    "instructions": GST_EXTRACTION_INSTRUCTIONS,
                }
            ).fetchone()
            comp_vid = v_res[0]
        else:
            comp_tid = t_row[0]
            v_row = bind.execute(
                text("SELECT id FROM template_versions WHERE template_id = :tid AND version_number = 1"),
                {"tid": comp_tid}
            ).fetchone()
            comp_vid = v_row[0] if v_row else None

        # Backfill existing documents for this company
        if comp_vid:
            bind.execute(
                text("UPDATE documents SET template_version_id = :vid WHERE company_id = :cid AND template_version_id IS NULL"),
                {"vid": comp_vid, "cid": cid}
            )

    # Backfill document_extractions for any document with structured_data or ocr_text
    docs = bind.execute(
        text("SELECT id, template_version_id, ocr_text, structured_data FROM documents WHERE template_version_id IS NOT NULL")
    ).fetchall()
    for doc in docs:
        doc_id, vid, ocr_text, struct_data = doc[0], doc[1], doc[2], doc[3]
        ex_check = bind.execute(
            text("SELECT id FROM document_extractions WHERE document_id = :did"),
            {"did": doc_id}
        ).fetchone()
        if not ex_check:
            parsed_data = {}
            if struct_data:
                try:
                    parsed_data = json.loads(struct_data)
                except Exception:
                    parsed_data = {"raw": struct_data}
            bind.execute(
                text("""
                    INSERT INTO document_extractions (document_id, template_version_id, data, raw_text, validation_flags, status, version, created_at, updated_at)
                    VALUES (:did, :vid, CAST(:data AS jsonb), :raw, '[]'::jsonb, 'extracted', 1, now(), now())
                """),
                {
                    "did": doc_id,
                    "vid": vid,
                    "data": json.dumps(parsed_data),
                    "raw": ocr_text or "",
                }
            )


def downgrade() -> None:
    op.drop_index('ix_extraction_edits_extraction_id', table_name='extraction_edits')
    op.drop_table('extraction_edits')
    op.drop_table('document_extractions')
    op.drop_index('ix_documents_template_version_id', table_name='documents')
    op.drop_column('documents', 'template_version_id')
    op.drop_index('ix_template_versions_lookup', table_name='template_versions')
    op.drop_table('template_versions')
    op.drop_index('ix_doc_templates_lookup', table_name='document_templates')
    op.drop_table('document_templates')
