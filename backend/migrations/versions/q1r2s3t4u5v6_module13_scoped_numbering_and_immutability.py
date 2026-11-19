"""module13_scoped_numbering_and_immutability

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-11-12 17:40:00.000000

Follow-up migration for Module 13:
1. Re-scopes outbound sales invoice numbering to per-GST-registration:
   - Adds invoices.gst_registration_id with foreign key to gst_registrations.
   - Adds unique constraint uq_invoices_comp_id_gst on (company_id, id, gst_registration_id).
   - Updates fk_outbound_invoice_tenant to composite (company_id, invoice_id, gst_registration_id).
   - Replaces uq_company_sales_invoice_number with uq_gst_reg_sales_invoice_number.
2. Implements issued invoice header and detail immutability triggers:
   - trg_invoices_prevent_update on invoices.
   - trg_outbound_sales_prevent_update on outbound_sales_invoices.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'q1r2s3t4u5v6'
down_revision = 'p1q2r3s4t5u6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Add invoices.gst_registration_id if not present
    has_col = conn.execute(sa.text("""
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'invoices' AND column_name = 'gst_registration_id';
    """)).scalar()
    if not has_col:
        op.add_column('invoices', sa.Column('gst_registration_id', sa.Integer(), nullable=True))

    # Backfill gst_registration_id for generated invoices from outbound_sales_invoices
    op.execute("""
        UPDATE invoices i
        SET gst_registration_id = o.gst_registration_id
        FROM outbound_sales_invoices o
        WHERE o.invoice_id = i.id AND i.gst_registration_id IS NULL;
    """)

    # 2. Add fk_invoices_gst_registration if not present
    has_fk = conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_invoices_gst_registration';
    """)).scalar()
    if not has_fk:
        op.create_foreign_key(
            'fk_invoices_gst_registration',
            'invoices',
            'gst_registrations',
            ['company_id', 'gst_registration_id'],
            ['company_id', 'id'],
            ondelete='RESTRICT'
        )

    # 3. Add uq_invoices_comp_id_gst if not present
    has_uq_gst = conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_invoices_comp_id_gst';
    """)).scalar()
    if not has_uq_gst:
        op.create_unique_constraint(
            'uq_invoices_comp_id_gst',
            'invoices',
            ['company_id', 'id', 'gst_registration_id']
        )

    # 4. Update fk_outbound_invoice_tenant to composite (company_id, invoice_id, gst_registration_id)
    curr_def = conn.execute(sa.text("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'fk_outbound_invoice_tenant';
    """)).scalar()
    if curr_def and 'gst_registration_id' not in curr_def:
        op.drop_constraint('fk_outbound_invoice_tenant', 'outbound_sales_invoices', type_='foreignkey')
        op.create_foreign_key(
            'fk_outbound_invoice_tenant',
            'outbound_sales_invoices',
            'invoices',
            ['company_id', 'invoice_id', 'gst_registration_id'],
            ['company_id', 'id', 'gst_registration_id'],
            ondelete='CASCADE'
        )
    elif not curr_def:
        op.create_foreign_key(
            'fk_outbound_invoice_tenant',
            'outbound_sales_invoices',
            'invoices',
            ['company_id', 'invoice_id', 'gst_registration_id'],
            ['company_id', 'id', 'gst_registration_id'],
            ondelete='CASCADE'
        )

    # 5. Drop uq_company_sales_invoice_number if present
    has_old_idx = conn.execute(sa.text("""
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_company_sales_invoice_number';
    """)).scalar()
    if has_old_idx:
        op.drop_index('uq_company_sales_invoice_number', table_name='invoices')

    # Create uq_gst_reg_sales_invoice_number if not present
    has_new_idx = conn.execute(sa.text("""
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_gst_reg_sales_invoice_number';
    """)).scalar()
    if not has_new_idx:
        op.create_index(
            'uq_gst_reg_sales_invoice_number',
            'invoices',
            ['gst_registration_id', 'invoice_number'],
            unique=True,
            postgresql_where=sa.text("kind = 'generated' AND invoice_number IS NOT NULL")
        )

    # Ensure index on supplier_invoice_copies.invoice_id
    op.execute("CREATE INDEX IF NOT EXISTS ix_supplier_invoice_copies_invoice_id ON supplier_invoice_copies (invoice_id);")

    # 6. Create trigger functions and triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_invoice_update()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Only enforce for generated outbound sales invoices that have entered issuance or been approved/cancelled
            IF OLD.kind = 'generated' AND OLD.status IN ('pending_issuance', 'approved', 'cancelled') THEN
                -- 1. Number immutability: once assigned, invoice_number cannot be modified
                IF OLD.invoice_number IS NOT NULL AND (NEW.invoice_number IS DISTINCT FROM OLD.invoice_number) THEN
                    RAISE EXCEPTION 'Invoice number is immutable on issued invoice %. Attempted to change from % to %.',
                        OLD.id, OLD.invoice_number, NEW.invoice_number;
                END IF;

                -- 2. Party snapshots immutability
                IF NEW.seller_name IS DISTINCT FROM OLD.seller_name OR
                   NEW.seller_gstin IS DISTINCT FROM OLD.seller_gstin OR
                   NEW.buyer_name IS DISTINCT FROM OLD.buyer_name OR
                   NEW.buyer_gstin IS DISTINCT FROM OLD.buyer_gstin OR
                   NEW.gst_registration_id IS DISTINCT FROM OLD.gst_registration_id OR
                   NEW.company_id IS DISTINCT FROM OLD.company_id OR
                   NEW.branch_id IS DISTINCT FROM OLD.branch_id THEN
                    RAISE EXCEPTION 'Party and registration details are immutable on issued invoice %.', OLD.id;
                END IF;

                -- 3. Invoice date & currency immutability
                IF NEW.invoice_date IS DISTINCT FROM OLD.invoice_date OR
                   NEW.currency IS DISTINCT FROM OLD.currency THEN
                    RAISE EXCEPTION 'Invoice date and currency are immutable on issued invoice %.', OLD.id;
                END IF;

                -- 4. Financial amounts immutability
                IF NEW.taxable_amount IS DISTINCT FROM OLD.taxable_amount OR
                   NEW.cgst_amount IS DISTINCT FROM OLD.cgst_amount OR
                   NEW.sgst_amount IS DISTINCT FROM OLD.sgst_amount OR
                   NEW.igst_amount IS DISTINCT FROM OLD.igst_amount OR
                   NEW.round_off IS DISTINCT FROM OLD.round_off OR
                   NEW.grand_total IS DISTINCT FROM OLD.grand_total THEN
                    RAISE EXCEPTION 'Financial amounts are immutable on issued invoice %. grand_total cannot be changed from % to %.',
                        OLD.id, OLD.grand_total, NEW.grand_total;
                END IF;

                -- 5. Kind immutability
                IF NEW.kind IS DISTINCT FROM OLD.kind THEN
                    RAISE EXCEPTION 'Invoice kind is immutable on issued invoice %.', OLD.id;
                END IF;

                -- 6. Permitted status transitions:
                -- pending_issuance -> approved
                -- approved -> cancelled
                -- cancelled -> cancelled
                IF NEW.status IS DISTINCT FROM OLD.status THEN
                    IF OLD.status = 'pending_issuance' AND NEW.status != 'approved' THEN
                        RAISE EXCEPTION 'Invalid status transition on invoice % from pending_issuance to %. Only approved is permitted.', OLD.id, NEW.status;
                    ELSIF OLD.status = 'approved' AND NEW.status != 'cancelled' THEN
                        RAISE EXCEPTION 'Invalid status transition on invoice % from approved to %. Only cancelled is permitted.', OLD.id, NEW.status;
                    ELSIF OLD.status = 'cancelled' THEN
                        RAISE EXCEPTION 'Cannot change status of cancelled invoice %. Status is terminal.', OLD.id;
                    END IF;
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_invoices_prevent_update ON invoices;
        CREATE TRIGGER trg_invoices_prevent_update
        BEFORE UPDATE ON invoices
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_invoice_update();

        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_outbound_detail_update()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
        BEGIN
            SELECT status INTO v_status FROM invoices WHERE id = OLD.invoice_id;
            IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
                -- Structural and addressing fields cannot be changed once issued
                IF NEW.company_id IS DISTINCT FROM OLD.company_id OR
                   NEW.gst_registration_id IS DISTINCT FROM OLD.gst_registration_id OR
                   NEW.customer_id IS DISTINCT FROM OLD.customer_id OR
                   NEW.billing_address_id IS DISTINCT FROM OLD.billing_address_id OR
                   NEW.shipping_address_id IS DISTINCT FROM OLD.shipping_address_id OR
                   NEW.financial_year IS DISTINCT FROM OLD.financial_year OR
                   NEW.series_code IS DISTINCT FROM OLD.series_code OR
                   NEW.sequence_number IS DISTINCT FROM OLD.sequence_number OR
                   NEW.place_of_supply_state_code IS DISTINCT FROM OLD.place_of_supply_state_code THEN
                    RAISE EXCEPTION 'Addressing, GST registration, customer, and sequence fields are immutable on issued sales invoice % (status: %).', OLD.invoice_id, v_status;
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_update ON outbound_sales_invoices;
        CREATE TRIGGER trg_outbound_sales_prevent_update
        BEFORE UPDATE ON outbound_sales_invoices
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_outbound_detail_update();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_update ON outbound_sales_invoices;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_issued_outbound_detail_update();")
    op.execute("DROP TRIGGER IF EXISTS trg_invoices_prevent_update ON invoices;")
    op.execute("DROP FUNCTION IF EXISTS trg_fn_prevent_issued_invoice_update();")

    op.drop_index('uq_gst_reg_sales_invoice_number', table_name='invoices')
    op.create_index(
        'uq_company_sales_invoice_number',
        'invoices',
        ['company_id', 'invoice_number'],
        unique=True,
        postgresql_where=sa.text("kind = 'generated' AND invoice_number IS NOT NULL")
    )

    op.drop_constraint('fk_outbound_invoice_tenant', 'outbound_sales_invoices', type_='foreignkey')
    op.create_foreign_key(
        'fk_outbound_invoice_tenant',
        'outbound_sales_invoices',
        'invoices',
        ['company_id', 'invoice_id'],
        ['company_id', 'id'],
        ondelete='CASCADE'
    )

    op.drop_constraint('uq_invoices_comp_id_gst', 'invoices', type_='unique')
    op.drop_constraint('fk_invoices_gst_registration', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'gst_registration_id')
