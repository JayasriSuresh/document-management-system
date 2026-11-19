"""module13_mandatory_gst_reg_and_snapshot_immutability

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-11-12 18:00:00.000000

Final integrity hardening for Module 13:
1. Enforces mandatory GST registration for all generated outbound sales invoices:
   - CHECK (kind <> 'generated' OR gst_registration_id IS NOT NULL) on invoices.
   - Preserves supplier invoice copies (kind = 'copy') where gst_registration_id may be NULL.
2. Complete field-by-field snapshot immutability hardening:
   - Updates trg_fn_prevent_issued_invoice_update to protect due_date, created_by, document_id.
   - Upgrades trg_fn_prevent_issued_outbound_detail_mutation and trigger on outbound_sales_invoices
     to fire BEFORE UPDATE OR DELETE, blocking direct DELETE and protecting invoice_id,
     place_of_supply_state_name, reverse_charge, is_b2c, version, and discard flags.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'r1s2t3u4v5w6'
down_revision = 'q1r2s3t4u5v6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add CHECK constraint requiring gst_registration_id for generated invoices
    op.create_check_constraint(
        'chk_invoices_gst_registration_requirement',
        'invoices',
        "kind <> 'generated' OR gst_registration_id IS NOT NULL"
    )

    # 2. Update trg_fn_prevent_issued_invoice_update on invoices
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

                -- 3. Invoice dates, due date, currency, and audit identity immutability
                IF NEW.invoice_date IS DISTINCT FROM OLD.invoice_date OR
                   NEW.due_date IS DISTINCT FROM OLD.due_date OR
                   NEW.currency IS DISTINCT FROM OLD.currency OR
                   NEW.created_by IS DISTINCT FROM OLD.created_by OR
                   NEW.document_id IS DISTINCT FROM OLD.document_id THEN
                    RAISE EXCEPTION 'Invoice dates, terms, currency, and audit identity are immutable on issued invoice %.', OLD.id;
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
    """)

    # 3. Upgrade outbound_sales_invoices trigger to block direct DELETE and protect all snapshot/classification fields
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_outbound_detail_mutation()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
        BEGIN
            SELECT status INTO v_status FROM invoices WHERE id = OLD.invoice_id;
            IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Cannot physically delete outbound sales details for issued invoice % (status: %). Details are immutable.', OLD.invoice_id, v_status;
                END IF;

                -- Addressing, customer, GST registration, tax classification, and sequence fields cannot be changed once issued
                IF NEW.invoice_id IS DISTINCT FROM OLD.invoice_id OR
                   NEW.company_id IS DISTINCT FROM OLD.company_id OR
                   NEW.gst_registration_id IS DISTINCT FROM OLD.gst_registration_id OR
                   NEW.customer_id IS DISTINCT FROM OLD.customer_id OR
                   NEW.billing_address_id IS DISTINCT FROM OLD.billing_address_id OR
                   NEW.shipping_address_id IS DISTINCT FROM OLD.shipping_address_id OR
                   NEW.financial_year IS DISTINCT FROM OLD.financial_year OR
                   NEW.series_code IS DISTINCT FROM OLD.series_code OR
                   NEW.sequence_number IS DISTINCT FROM OLD.sequence_number OR
                   NEW.place_of_supply_state_code IS DISTINCT FROM OLD.place_of_supply_state_code OR
                   NEW.place_of_supply_state_name IS DISTINCT FROM OLD.place_of_supply_state_name OR
                   NEW.reverse_charge IS DISTINCT FROM OLD.reverse_charge OR
                   NEW.is_b2c IS DISTINCT FROM OLD.is_b2c OR
                   NEW.version IS DISTINCT FROM OLD.version OR
                   NEW.is_discarded IS DISTINCT FROM OLD.is_discarded OR
                   NEW.discarded_at IS DISTINCT FROM OLD.discarded_at OR
                   NEW.discarded_by IS DISTINCT FROM OLD.discarded_by OR
                   NEW.discard_reason IS DISTINCT FROM OLD.discard_reason THEN
                    RAISE EXCEPTION 'Addressing, GST registration, customer, tax classification, and sequence fields are immutable on issued sales invoice % (status: %).', OLD.invoice_id, v_status;
                END IF;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_update ON outbound_sales_invoices;
        DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_mutation ON outbound_sales_invoices;
        CREATE TRIGGER trg_outbound_sales_prevent_mutation
        BEFORE UPDATE OR DELETE ON outbound_sales_invoices
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_outbound_detail_mutation();
    """)


def downgrade():
    op.drop_constraint('chk_invoices_gst_registration_requirement', 'invoices', type_='check')

    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_invoice_update()
        RETURNS TRIGGER AS $$
        BEGIN
            IF OLD.kind = 'generated' AND OLD.status IN ('pending_issuance', 'approved', 'cancelled') THEN
                IF OLD.invoice_number IS NOT NULL AND (NEW.invoice_number IS DISTINCT FROM OLD.invoice_number) THEN
                    RAISE EXCEPTION 'Invoice number is immutable on issued invoice %. Attempted to change from % to %.',
                        OLD.id, OLD.invoice_number, NEW.invoice_number;
                END IF;

                IF NEW.seller_name IS DISTINCT FROM OLD.seller_name OR
                   NEW.seller_gstin IS DISTINCT FROM OLD.seller_gstin OR
                   NEW.buyer_name IS DISTINCT FROM OLD.buyer_name OR
                   NEW.buyer_gstin IS DISTINCT FROM OLD.buyer_gstin OR
                   NEW.gst_registration_id IS DISTINCT FROM OLD.gst_registration_id OR
                   NEW.company_id IS DISTINCT FROM OLD.company_id OR
                   NEW.branch_id IS DISTINCT FROM OLD.branch_id THEN
                    RAISE EXCEPTION 'Party and registration details are immutable on issued invoice %.', OLD.id;
                END IF;

                IF NEW.invoice_date IS DISTINCT FROM OLD.invoice_date OR
                   NEW.currency IS DISTINCT FROM OLD.currency THEN
                    RAISE EXCEPTION 'Invoice date and currency are immutable on issued invoice %.', OLD.id;
                END IF;

                IF NEW.taxable_amount IS DISTINCT FROM OLD.taxable_amount OR
                   NEW.cgst_amount IS DISTINCT FROM OLD.cgst_amount OR
                   NEW.sgst_amount IS DISTINCT FROM OLD.sgst_amount OR
                   NEW.igst_amount IS DISTINCT FROM OLD.igst_amount OR
                   NEW.round_off IS DISTINCT FROM OLD.round_off OR
                   NEW.grand_total IS DISTINCT FROM OLD.grand_total THEN
                    RAISE EXCEPTION 'Financial amounts are immutable on issued invoice %. grand_total cannot be changed from % to %.',
                        OLD.id, OLD.grand_total, NEW.grand_total;
                END IF;

                IF NEW.kind IS DISTINCT FROM OLD.kind THEN
                    RAISE EXCEPTION 'Invoice kind is immutable on issued invoice %.', OLD.id;
                END IF;

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

        DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_mutation ON outbound_sales_invoices;
        DROP TRIGGER IF EXISTS trg_outbound_sales_prevent_update ON outbound_sales_invoices;

        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_outbound_detail_update()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
        BEGIN
            SELECT status INTO v_status FROM invoices WHERE id = OLD.invoice_id;
            IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
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

        CREATE TRIGGER trg_outbound_sales_prevent_update
        BEFORE UPDATE ON outbound_sales_invoices
        FOR EACH ROW
        EXECUTE FUNCTION trg_fn_prevent_issued_outbound_detail_update();
    """)
