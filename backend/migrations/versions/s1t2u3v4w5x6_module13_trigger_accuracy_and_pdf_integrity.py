"""module13_trigger_accuracy_and_pdf_integrity

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-11-12 18:30:00.000000

Integrity hardening for Module 13:
1. Timestamp immutability:
   - created_at is protected from direct SQL UPDATE across invoices and outbound_sales_invoices.
   - updated_at remains maintainable through legitimate operational updates.
2. Issued PDF integrity:
   - In pending_issuance, storing generated PDF metadata is allowed.
   - In approved and cancelled statuses, pdf_storage_key, pdf_sha256, pdf_generated_at,
     pdf_filename, and file_size are strictly immutable.
   - Cancelled invoices retain original issued PDF reference and hash.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 's1t2u3v4w5x6'
down_revision = 'r1s2t3u4v5w6'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Update trg_fn_prevent_issued_invoice_update on invoices
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_invoice_update()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Universal created_at immutability: creation timestamp can never be changed via UPDATE
            IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'created_at is immutable on invoice %. Creation timestamp cannot be modified.', OLD.id;
            END IF;

            -- Enforce immutability for generated outbound sales invoices that have entered issuance or been approved/cancelled
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

                -- 6. Issued PDF metadata immutability on approved and cancelled invoices
                -- (Storing PDF metadata is allowed in pending_issuance; immutable thereafter)
                IF OLD.status IN ('approved', 'cancelled') THEN
                    IF NEW.pdf_filename IS DISTINCT FROM OLD.pdf_filename OR
                       NEW.file_size IS DISTINCT FROM OLD.file_size THEN
                        RAISE EXCEPTION 'PDF filename and file size are immutable on approved or cancelled invoice %.', OLD.id;
                    END IF;
                END IF;

                -- 7. Permitted status transitions:
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

    # 2. Update trg_fn_prevent_issued_outbound_detail_mutation on outbound_sales_invoices
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_fn_prevent_issued_outbound_detail_mutation()
        RETURNS TRIGGER AS $$
        DECLARE
            v_status VARCHAR(50);
        BEGIN
            SELECT status INTO v_status FROM invoices WHERE id = OLD.invoice_id;

            IF TG_OP = 'DELETE' THEN
                IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
                    RAISE EXCEPTION 'Cannot physically delete outbound sales details for issued invoice % (status: %). Details are immutable.', OLD.invoice_id, v_status;
                END IF;
                RETURN OLD;
            END IF;

            -- Universal created_at immutability: creation timestamp can never be modified via UPDATE
            IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'created_at is immutable on outbound sales invoice %. Creation timestamp cannot be modified.', OLD.invoice_id;
            END IF;

            IF v_status IN ('pending_issuance', 'approved', 'cancelled') THEN
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

                -- Issued PDF integrity:
                -- In pending_issuance: storing PDF storage key, SHA-256 hash, and generated_at is allowed.
                -- In approved or cancelled: PDF storage reference, SHA-256 hash, and generated_at are strictly immutable.
                IF v_status IN ('approved', 'cancelled') THEN
                    IF NEW.pdf_storage_key IS DISTINCT FROM OLD.pdf_storage_key OR
                       NEW.pdf_sha256 IS DISTINCT FROM OLD.pdf_sha256 OR
                       NEW.pdf_generated_at IS DISTINCT FROM OLD.pdf_generated_at THEN
                        RAISE EXCEPTION 'PDF storage key, SHA-256 hash, and generation timestamp are immutable on issued sales invoice % (status: %).', OLD.invoice_id, v_status;
                    END IF;

                    IF NEW.approved_at IS DISTINCT FROM OLD.approved_at OR
                       NEW.approved_by IS DISTINCT FROM OLD.approved_by THEN
                        RAISE EXCEPTION 'Approval metadata is immutable on approved or cancelled sales invoice % (status: %).', OLD.invoice_id, v_status;
                    END IF;
                END IF;

                -- Once cancelled, cancellation metadata is terminal
                IF v_status = 'cancelled' AND OLD.cancelled_at IS NOT NULL THEN
                    IF NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at OR
                       NEW.cancelled_by IS DISTINCT FROM OLD.cancelled_by OR
                       NEW.cancellation_reason IS DISTINCT FROM OLD.cancellation_reason THEN
                        RAISE EXCEPTION 'Cancellation metadata is immutable on cancelled sales invoice %.', OLD.invoice_id;
                    END IF;
                END IF;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            ELSE
                RETURN NEW;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade():
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
                   NEW.due_date IS DISTINCT FROM OLD.due_date OR
                   NEW.currency IS DISTINCT FROM OLD.currency OR
                   NEW.created_by IS DISTINCT FROM OLD.created_by OR
                   NEW.document_id IS DISTINCT FROM OLD.document_id THEN
                    RAISE EXCEPTION 'Invoice dates, terms, currency, and audit identity are immutable on issued invoice %.', OLD.id;
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
    """)
