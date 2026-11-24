"""
Comprehensive API Tests for Module 13 Outbound Sales Invoices (Phase 4):
- Draft lifecycle (create, recalculate, update, discard).
- Two-phase approval and issuance (number allocation, PDF generation, SHA-256).
- Strict separation of duties under admin_only (creator cannot approve, even Global Admin).
- Different approver succeeds.
- Cancellation with mandatory reason.
- Master Admin hard rejection (404/403).
- Tenant and branch isolation.
"""

import pytest
from decimal import Decimal
from datetime import date

from app.models import Company, Branch, User, UserRole, GstRegistration, Customer, CustomerAddress, Invoice
from app.auth import get_password_hash
from app.database import SessionLocal


@pytest.fixture(scope="module")
def setup_test_data(client):
    """Sets up company 40 with two admins (one creator, one approver) and master data."""
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == 40).first()
        company.invoice_approval_policy = "admin_only"
        branch = db.query(Branch).filter(Branch.company_id == company.id).first()

        # Users
        admin_creator = db.query(User).filter(User.email == "samrethi@example.com").first()
        admin_approver = db.query(User).filter(User.email == "jayasri@example.com").first()
        staff_user = db.query(User).filter(User.email == "sujipriya@example.com").first()

        # GST Registration
        gst_reg = db.query(GstRegistration).filter(GstRegistration.company_id == company.id).first()
        if not gst_reg:
            gst_reg = GstRegistration(
                company_id=company.id,
                gstin="33BLAPS0819R1ZQ",
                legal_name="Vasanth & Co. Pvt Ltd",
                state_code="33",
                state_name="Tamil Nadu",
                registered_address="100 Tech Park, Chennai, Tamil Nadu",
                is_active=True,
                is_default=True,
            )
            db.add(gst_reg)
            db.flush()

        # Customer
        customer = db.query(Customer).filter(Customer.company_id == company.id).first()
        if not customer:
            customer = Customer(
                company_id=company.id,
                name="Kartwheel Consulting",
                gstin="33ALJPP7733P1ZE",
                pan="ALJPP7733P",
                is_b2c=False,
                is_active=True,
            )
            db.add(customer)
            db.flush()

            billing_addr = CustomerAddress(
                customer_id=customer.id,
                address_type="billing",
                address_line1="H-38/1400, 1st floor, 15th main road",
                city="Chennai",
                state_code="33",
                state_name="Tamil Nadu",
                pincode="600040",
                is_default=True,
            )
            db.add(billing_addr)

        db.commit()
        return {
            "company_id": company.id,
            "branch_id": admin_creator.branch_id if admin_creator else branch.id,
            "gst_reg_id": gst_reg.id,
            "customer_id": customer.id,
            "creator_email": "samrethi@example.com",
            "approver_email": "jayasri@example.com",
            "staff_email": "sujipriya@example.com",
        }
    finally:
        db.close()


def test_sales_invoice_full_lifecycle(client, auth_headers, setup_test_data):
    """
    Tests draft creation -> update -> submit -> separation of duties rejection ->
    valid approval -> PDF file verification -> cancellation.
    """
    creator_headers = auth_headers(setup_test_data["creator_email"])
    approver_headers = auth_headers(setup_test_data["approver_email"])

    # 1. Create Draft
    draft_payload = {
        "branch_id": setup_test_data["branch_id"],
        "gst_registration_id": setup_test_data["gst_reg_id"],
        "customer_id": setup_test_data["customer_id"],
        "place_of_supply": "33",
        "invoice_date": "2026-05-15",
        "notes": "Payment within 30 days",
        "apply_round_off": False,
        "items": [
            {
                "description": "High Performance Server",
                "hsn_sac_code": "8471",
                "item_type": "goods",
                "quantity": 2,
                "unit": "nos",
                "unit_price": 40000.00,
                "discount_percent": 0.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }

    resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=creator_headers)
    assert resp.status_code == 201, resp.text
    inv_data = resp.json()
    inv_id = inv_data["id"]

    assert inv_data["status"] == "draft"
    assert inv_data["invoice_number"] is None
    assert Decimal(str(inv_data["taxable_amount"])) == Decimal("80000.00")
    assert Decimal(str(inv_data["cgst_amount"])) == Decimal("7200.00")
    assert Decimal(str(inv_data["sgst_amount"])) == Decimal("7200.00")
    assert Decimal(str(inv_data["grand_total"])) == Decimal("94400.00")

    # 2. Update Draft (add discount)
    update_payload = {
        "notes": "Updated: 5% discount applied",
        "items": [
            {
                "description": "High Performance Server",
                "hsn_sac_code": "8471",
                "item_type": "goods",
                "quantity": 2,
                "unit": "nos",
                "unit_price": 40000.00,
                "discount_percent": 5.0,  # 4000 off 80000 -> Taxable 76000
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }
    resp = client.put(f"/api/sales-invoices/{inv_id}/draft", json=update_payload, headers=creator_headers)
    assert resp.status_code == 200
    updated_data = resp.json()
    assert Decimal(str(updated_data["taxable_amount"])) == Decimal("76000.00")
    assert Decimal(str(updated_data["cgst_amount"])) == Decimal("6840.00")
    assert Decimal(str(updated_data["sgst_amount"])) == Decimal("6840.00")
    assert Decimal(str(updated_data["grand_total"])) == Decimal("89680.00")

    # 3. Submit for approval
    resp = client.post(f"/api/sales-invoices/{inv_id}/submit", headers=creator_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending_approval"

    # 4. Strict Separation of Duties Test:
    # Creator (Company Global Admin) tries to approve their own invoice under admin_only -> MUST FAIL with 403!
    resp = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=creator_headers)
    assert resp.status_code == 403
    assert "Separation of duties violation" in resp.json()["detail"]

    # 5. Independent Approver approves and issues
    resp = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=approver_headers)
    assert resp.status_code == 200, resp.text
    approved_data = resp.json()
    assert approved_data["status"] == "approved"
    assert approved_data["invoice_number"].startswith("INV/2026-27/")
    assert approved_data["pdf_filename"] is not None
    assert approved_data["pdf_sha256"] is not None
    assert approved_data["approved_by_name"] in ["Admin Approver", "Jayasri"]

    # 6. Verify PDF download endpoint works
    resp = client.get(f"/api/invoices/{inv_id}/pdf", headers=creator_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 1000

    # 7. Cancel the approved invoice
    cancel_resp = client.post(
        f"/api/sales-invoices/{inv_id}/cancel",
        json={"reason": "Customer cancelled order before delivery"},
        headers=approver_headers,
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_staff_cannot_approve(client, auth_headers, setup_test_data):
    """Staff user can create and submit draft, but CANNOT approve (403)."""
    staff_headers = auth_headers(setup_test_data["staff_email"])

    draft_payload = {
        "branch_id": setup_test_data["branch_id"],
        "gst_registration_id": setup_test_data["gst_reg_id"],
        "customer_id": setup_test_data["customer_id"],
        "place_of_supply": "33",
        "items": [
            {
                "description": "Mouse & Keyboard",
                "quantity": 1,
                "unit_price": 1000.0,
                "gst_rate": 18.0,
            }
        ],
    }
    resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=staff_headers)
    assert resp.status_code == 201
    inv_id = resp.json()["id"]

    # Submit
    client.post(f"/api/sales-invoices/{inv_id}/submit", headers=staff_headers)

    # Try approve as staff
    resp = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=staff_headers)
    assert resp.status_code == 403
    assert "Permission denied" in resp.json()["detail"]


def test_master_admin_has_no_access_to_invoices(client, setup_test_data):
    """Platform Master Admin is hard-blocked (404/403) from tenant invoice content."""
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "master@platform.local", "password": "Pasword@123", "portal": "platform"},
    )
    assert login_resp.status_code == 200, login_resp.text
    master_token = login_resp.json()["access_token"]
    master_headers = {"Authorization": f"Bearer {master_token}"}

    # Accessing tenant invoices must fail with 404 or 403
    resp = client.get("/api/invoices", headers=master_headers)
    assert resp.status_code in (401, 403, 404)


def test_independent_numbering_across_gst_registrations(client, auth_headers, setup_test_data, db):
    """
    Issue 1:
    - Verifies that two different GST registrations under the same company maintain independent sequences.
    - Demonstrates that the same formatted invoice number (e.g. TEST/2026-27/0001) can be issued by both GST registrations without collision.
    - Demonstrates that attempting to duplicate the invoice number within the SAME GST registration fails database uniqueness.
    - Verifies parent-child consistency: parent invoice and outbound detail must share the same gst_registration_id.
    """
    from app.models import GstRegistration, NumberSequence, OutboundSalesInvoice
    from app.services.gstin_validator import compute_gstin_checksum
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text

    creator_headers = auth_headers(setup_test_data["creator_email"])
    approver_headers = auth_headers(setup_test_data["approver_email"])
    comp_id = setup_test_data["company_id"]
    branch_id = setup_test_data["branch_id"]

    # 1. Create or get GST Registration A (Tamil Nadu)
    gst_a = db.query(GstRegistration).filter(GstRegistration.company_id == comp_id, GstRegistration.state_code == "33").first()
    assert gst_a is not None

    # 2. Create or get GST Registration B (Karnataka)
    gst_b = db.query(GstRegistration).filter(GstRegistration.company_id == comp_id, GstRegistration.state_code == "29").first()
    if not gst_b:
        base_b = "29BLAPS0819R1Z"
        chk_b = compute_gstin_checksum(base_b)
        gst_b = GstRegistration(
            company_id=comp_id,
            gstin=base_b + chk_b,
            legal_name="Vasanth & Co. Karnataka Division",
            state_code="29",
            state_name="Karnataka",
            registered_address="500 Brigade Road, Bengaluru, Karnataka",
            is_active=True,
            is_default=False,
        )
        db.add(gst_b)
        db.commit()
        db.refresh(gst_b)

    import random, string
    while True:
        series_code = "S" + "".join(random.choices(string.ascii_uppercase, k=2))
        if not db.query(NumberSequence).filter_by(company_id=comp_id, financial_year="2026-27", series_code=series_code).first():
            break
    expected_number = f"{series_code}/2026-27/0001"

    # Dedicated sequence starting at 1 for both registrations
    seq_a = NumberSequence(
        company_id=comp_id, gst_registration_id=gst_a.id, financial_year="2026-27", series_code=series_code, next_value=1, padding=4
    )
    db.add(seq_a)

    seq_b = NumberSequence(
        company_id=comp_id, gst_registration_id=gst_b.id, financial_year="2026-27", series_code=series_code, next_value=1, padding=4
    )
    db.add(seq_b)
    db.commit()

    # Draft A: from GST Registration A with series_code
    payload_a = {
        "branch_id": branch_id,
        "gst_registration_id": gst_a.id,
        "customer_id": setup_test_data["customer_id"],
        "series_code": series_code,
        "place_of_supply": "33",
        "invoice_date": "2026-06-01",
        "items": [
            {
                "description": "Consulting Service A",
                "hsn_sac_code": "998314",
                "item_type": "services",
                "quantity": 1,
                "unit": "hrs",
                "unit_price": 10000.00,
                "discount_percent": 0.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }
    resp_a = client.post("/api/sales-invoices/drafts", json=payload_a, headers=creator_headers)
    assert resp_a.status_code == 201, resp_a.text
    id_a = resp_a.json()["id"]

    # Submit and approve Invoice A
    client.post(f"/api/sales-invoices/{id_a}/submit", headers=creator_headers)
    appr_a = client.post(f"/api/sales-invoices/{id_a}/approve", headers=approver_headers)
    assert appr_a.status_code == 200, appr_a.text
    inv_a_data = appr_a.json()
    assert inv_a_data["invoice_number"] == expected_number

    # Draft B: from GST Registration B with the same series_code
    payload_b = {
        "branch_id": branch_id,
        "gst_registration_id": gst_b.id,
        "customer_id": setup_test_data["customer_id"],
        "series_code": series_code,
        "place_of_supply": "29",
        "invoice_date": "2026-06-01",
        "items": [
            {
                "description": "Consulting Service B",
                "hsn_sac_code": "998314",
                "item_type": "services",
                "quantity": 1,
                "unit": "hrs",
                "unit_price": 12000.00,
                "discount_percent": 0.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }
    resp_b = client.post("/api/sales-invoices/drafts", json=payload_b, headers=creator_headers)
    assert resp_b.status_code == 201, resp_b.text
    id_b = resp_b.json()["id"]

    # Submit and approve Invoice B
    client.post(f"/api/sales-invoices/{id_b}/submit", headers=creator_headers)
    appr_b = client.post(f"/api/sales-invoices/{id_b}/approve", headers=approver_headers)
    assert appr_b.status_code == 200, appr_b.text
    inv_b_data = appr_b.json()

    # BOTH have expected_number because they are independent GST registrations!
    assert inv_b_data["invoice_number"] == expected_number
    assert inv_a_data["invoice_number"] == inv_b_data["invoice_number"]
    assert id_a != id_b

    # Verify database constraint: attempting to insert another generated invoice with
    # same number under GST Registration A MUST FAIL with unique constraint violation!
    with pytest.raises(IntegrityError) as exc_dup:
        db.execute(text(f"""
            INSERT INTO invoices (
                company_id, branch_id, gst_registration_id, kind, status,
                invoice_number, invoice_date, taxable_amount, cgst_amount,
                sgst_amount, igst_amount, round_off, grand_total, currency
            ) VALUES (
                {comp_id}, {branch_id}, {gst_a.id}, 'generated', 'approved',
                '{expected_number}', '2026-06-01', 10000.00, 900.00,
                900.00, 0.00, 0.00, 11800.00, 'INR'
            )
        """))
    db.rollback()
    assert "uq_gst_reg_sales_invoice_number" in str(exc_dup.value)

    # Verify parent-child consistency: parent invoices.gst_registration_id must match child outbound_sales_invoices.gst_registration_id
    rec_a = db.query(Invoice).filter(Invoice.id == id_a).first()
    assert rec_a.gst_registration_id == gst_a.id
    assert rec_a.sales_detail.gst_registration_id == gst_a.id

    rec_b = db.query(Invoice).filter(Invoice.id == id_b).first()
    assert rec_b.gst_registration_id == gst_b.id
    assert rec_b.sales_detail.gst_registration_id == gst_b.id

    # Create an unattached draft header with gst_a.id to test foreign key consistency
    draft_test_id = db.execute(text(f"""
        INSERT INTO invoices (
            company_id, branch_id, gst_registration_id, kind, status,
            invoice_date, currency
        ) VALUES (
            {comp_id}, {branch_id}, {gst_a.id}, 'generated', 'draft',
            '2026-06-01', 'INR'
        ) RETURNING id
    """)).scalar()

    # Attempting to insert an outbound detail referencing draft_test_id but with mismatched gst_b.id
    # MUST FAIL with fk_outbound_invoice_tenant violation!
    with pytest.raises(IntegrityError) as exc_fk:
        db.execute(text(f"""
            INSERT INTO outbound_sales_invoices (
                invoice_id, company_id, gst_registration_id, customer_id,
                financial_year, series_code, place_of_supply_state_code, place_of_supply_state_name
            ) VALUES (
                {draft_test_id}, {comp_id}, {gst_b.id}, {setup_test_data["customer_id"]},
                '2026-27', '{series_code}', '33', 'Tamil Nadu'
            )
        """))
    db.rollback()
    assert "fk_outbound_invoice_tenant" in str(exc_fk.value)


def test_database_immutability_triggers(db, setup_test_data, client, auth_headers):
    """
    Issue 2:
    Direct SQL integration tests proving database-level immutability for issued invoices:
    1. Updating financial fields fails.
    2. Updating seller or buyer snapshots fails.
    3. Changing invoice number fails.
    4. Updating line items fails.
    5. Deleting issued invoice fails.
    6. Valid cancellation transition succeeds.
    7. Cancellation retains original financial values and terminal status cannot be modified.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.models import InvoiceItem

    creator_headers = auth_headers(setup_test_data["creator_email"])
    approver_headers = auth_headers(setup_test_data["approver_email"])

    # Create a fresh issued invoice for these 7 direct tests
    draft_payload = {
        "branch_id": setup_test_data["branch_id"],
        "gst_registration_id": setup_test_data["gst_reg_id"],
        "customer_id": setup_test_data["customer_id"],
        "place_of_supply": "33",
        "invoice_date": "2026-07-10",
        "notes": "Immutability verification invoice",
        "apply_round_off": False,
        "items": [
            {
                "description": "Enterprise Security Audit",
                "hsn_sac_code": "998314",
                "item_type": "services",
                "quantity": 1,
                "unit": "nos",
                "unit_price": 50000.00,
                "discount_percent": 0.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }
    resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=creator_headers)
    assert resp.status_code == 201, resp.text
    inv_id = resp.json()["id"]

    client.post(f"/api/sales-invoices/{inv_id}/submit", headers=creator_headers)
    appr_resp = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=approver_headers)
    assert appr_resp.status_code == 200, appr_resp.text

    # Snapshot original financial values
    inv = db.query(Invoice).filter(Invoice.id == inv_id).first()
    orig_grand_total = inv.grand_total
    orig_taxable_amount = inv.taxable_amount
    orig_invoice_number = inv.invoice_number
    orig_seller_name = inv.seller_name
    orig_seller_gstin = inv.seller_gstin
    orig_buyer_name = inv.buyer_name
    orig_buyer_gstin = inv.buyer_gstin
    assert inv.status == "approved"
    assert orig_grand_total == Decimal("59000.00")

    # 1. Updating an issued invoice's financial fields fails
    with pytest.raises(DBAPIError) as exc_fin:
        db.execute(text(f"UPDATE invoices SET grand_total = 1000.00 WHERE id = {inv_id}"))
    db.rollback()
    assert "Financial amounts are immutable on issued invoice" in str(exc_fin.value)

    with pytest.raises(DBAPIError) as exc_tax:
        db.execute(text(f"UPDATE invoices SET taxable_amount = 500.00 WHERE id = {inv_id}"))
    db.rollback()
    assert "Financial amounts are immutable on issued invoice" in str(exc_tax.value)

    # 2. Updating its seller or buyer snapshots fails
    with pytest.raises(DBAPIError) as exc_seller:
        db.execute(text(f"UPDATE invoices SET seller_gstin = '33ABCDE1234F1Z5' WHERE id = {inv_id}"))
    db.rollback()
    assert "Party and registration details are immutable on issued invoice" in str(exc_seller.value)

    with pytest.raises(DBAPIError) as exc_buyer:
        db.execute(text(f"UPDATE invoices SET buyer_name = 'Fraudulent Entity' WHERE id = {inv_id}"))
    db.rollback()
    assert "Party and registration details are immutable on issued invoice" in str(exc_buyer.value)

    # 3. Changing its invoice number fails
    with pytest.raises(DBAPIError) as exc_num:
        db.execute(text(f"UPDATE invoices SET invoice_number = 'INV/FAKE/0001' WHERE id = {inv_id}"))
    db.rollback()
    assert "Invoice number is immutable on issued invoice" in str(exc_num.value)

    # 4. Updating an issued invoice's line items fails
    item = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == inv_id).first()
    assert item is not None
    with pytest.raises(DBAPIError) as exc_item:
        db.execute(text(f"UPDATE invoice_items SET line_total = 100.00 WHERE id = {item.id}"))
    db.rollback()
    assert "Line items are immutable" in str(exc_item.value)

    # 5. Deleting an issued invoice fails
    with pytest.raises(DBAPIError) as exc_del:
        db.execute(text(f"DELETE FROM invoices WHERE id = {inv_id}"))
    db.rollback()
    assert "Cannot physically delete issued or in-process invoice" in str(exc_del.value)

    # 5b. Deleting issued outbound sales detail directly fails
    with pytest.raises(DBAPIError) as exc_del_det:
        db.execute(text(f"DELETE FROM outbound_sales_invoices WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "Cannot physically delete outbound sales details for issued invoice" in str(exc_del_det.value)

    # 5c. Mutating due_date, created_by, or document_id fails
    with pytest.raises(DBAPIError) as exc_due:
        db.execute(text(f"UPDATE invoices SET due_date = '2026-12-31' WHERE id = {inv_id}"))
    db.rollback()
    assert "Invoice dates, terms, currency, and audit identity are immutable" in str(exc_due.value)

    with pytest.raises(DBAPIError) as exc_crby:
        db.execute(text(f"UPDATE invoices SET created_by = 999 WHERE id = {inv_id}"))
    db.rollback()
    assert "Invoice dates, terms, currency, and audit identity are immutable" in str(exc_crby.value)

    # 5d. Mutating outbound tax classification and snapshot fields fails
    with pytest.raises(DBAPIError) as exc_pos_name:
        db.execute(text(f"UPDATE outbound_sales_invoices SET place_of_supply_state_name = 'Goa' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "immutable on issued sales invoice" in str(exc_pos_name.value)

    with pytest.raises(DBAPIError) as exc_rcm:
        db.execute(text(f"UPDATE outbound_sales_invoices SET reverse_charge = true WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "immutable on issued sales invoice" in str(exc_rcm.value)

    with pytest.raises(DBAPIError) as exc_b2c:
        db.execute(text(f"UPDATE outbound_sales_invoices SET is_b2c = true WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "immutable on issued sales invoice" in str(exc_b2c.value)

    with pytest.raises(DBAPIError) as exc_disc:
        db.execute(text(f"UPDATE outbound_sales_invoices SET is_discarded = true WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "immutable on issued sales invoice" in str(exc_disc.value)

    # 5e. Mutating created_at on invoices or outbound_sales_invoices fails (timestamp immutability)
    with pytest.raises(DBAPIError) as exc_cr_inv:
        db.execute(text(f"UPDATE invoices SET created_at = '2020-01-01 00:00:00+00' WHERE id = {inv_id}"))
    db.rollback()
    assert "created_at is immutable" in str(exc_cr_inv.value)

    with pytest.raises(DBAPIError) as exc_cr_det:
        db.execute(text(f"UPDATE outbound_sales_invoices SET created_at = '2020-01-01 00:00:00+00' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "created_at is immutable" in str(exc_cr_det.value)

    # 5f. Mutating issued PDF metadata on approved invoice fails (issued PDF integrity)
    with pytest.raises(DBAPIError) as exc_pdf_key:
        db.execute(text(f"UPDATE outbound_sales_invoices SET pdf_storage_key = 'hacked_invoice.pdf' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "PDF storage key, SHA-256 hash, and generation timestamp are immutable" in str(exc_pdf_key.value)

    with pytest.raises(DBAPIError) as exc_pdf_hash:
        db.execute(text(f"UPDATE outbound_sales_invoices SET pdf_sha256 = '0000000000000000000000000000000000000000000000000000000000000000' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "PDF storage key, SHA-256 hash, and generation timestamp are immutable" in str(exc_pdf_hash.value)

    with pytest.raises(DBAPIError) as exc_pdf_hdr:
        db.execute(text(f"UPDATE invoices SET pdf_filename = 'tampered_header.pdf' WHERE id = {inv_id}"))
    db.rollback()
    assert "PDF filename and file size are immutable" in str(exc_pdf_hdr.value)

    # 5g. Operationally maintainable: updated_at CAN be updated via legitimate update
    db.execute(text(f"UPDATE invoices SET updated_at = NOW() WHERE id = {inv_id}"))
    db.commit()

    # 6. A valid cancellation transition still works
    cancel_resp = client.post(
        f"/api/sales-invoices/{inv_id}/cancel",
        json={"reason": "Audit immutability test cancellation"},
        headers=approver_headers,
    )
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert cancel_resp.json()["status"] == "cancelled"

    # 7. Cancellation does not alter original financial values or PDF references, and terminal status cannot be modified
    db.expire_all()
    cancelled_inv = db.query(Invoice).filter(Invoice.id == inv_id).first()
    assert cancelled_inv.status == "cancelled"
    assert cancelled_inv.grand_total == orig_grand_total
    assert cancelled_inv.taxable_amount == orig_taxable_amount
    assert cancelled_inv.invoice_number == orig_invoice_number
    assert cancelled_inv.seller_gstin == orig_seller_gstin
    assert cancelled_inv.buyer_gstin == orig_buyer_gstin
    assert cancelled_inv.pdf_filename is not None
    assert cancelled_inv.sales_detail.pdf_storage_key is not None
    assert cancelled_inv.sales_detail.pdf_sha256 is not None

    # Cancelled invoice PDF reference and hash remain strictly immutable
    with pytest.raises(DBAPIError) as exc_canc_pdf:
        db.execute(text(f"UPDATE outbound_sales_invoices SET pdf_storage_key = 'post_cancel_tamper.pdf' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "PDF storage key, SHA-256 hash, and generation timestamp are immutable" in str(exc_canc_pdf.value)

    with pytest.raises(DBAPIError) as exc_canc_hash:
        db.execute(text(f"UPDATE outbound_sales_invoices SET pdf_sha256 = 'bad_hash_post_cancel' WHERE invoice_id = {inv_id}"))
    db.rollback()
    assert "PDF storage key, SHA-256 hash, and generation timestamp are immutable" in str(exc_canc_hash.value)

    with pytest.raises(DBAPIError) as exc_canc_hdr:
        db.execute(text(f"UPDATE invoices SET pdf_filename = 'post_cancel_hdr.pdf' WHERE id = {inv_id}"))
    db.rollback()
    assert "PDF filename and file size are immutable" in str(exc_canc_hdr.value)

    # Transitioning out of cancelled status fails at DB level
    with pytest.raises(DBAPIError) as exc_term:
        db.execute(text(f"UPDATE invoices SET status = 'approved' WHERE id = {inv_id}"))
    db.rollback()
    assert "Status is terminal" in str(exc_term.value)


def test_generated_invoice_mandatory_gst_registration(db, setup_test_data):
    """
    Verifies that generated invoices MUST have a non-null gst_registration_id,
    while supplier invoice copies (kind = 'copy') are allowed to have NULL gst_registration_id.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    comp_id = setup_test_data["company_id"]
    branch_id = setup_test_data["branch_id"]

    # 1. Attempt to insert generated invoice with NULL gst_registration_id -> MUST FAIL
    with pytest.raises(DBAPIError) as exc_chk:
        db.execute(text(f"""
            INSERT INTO invoices (
                company_id, branch_id, gst_registration_id, kind, status,
                invoice_date, currency
            ) VALUES (
                {comp_id}, {branch_id}, NULL, 'generated', 'draft',
                '2026-06-01', 'INR'
            );
        """))
    db.rollback()
    assert "chk_invoices_gst_registration_requirement" in str(exc_chk.value)

    # 2. Attempt to insert supplier invoice copy with NULL gst_registration_id -> MUST SUCCEED
    copy_id = db.execute(text(f"""
        INSERT INTO invoices (
            company_id, branch_id, gst_registration_id, kind, status,
            invoice_date, currency
        ) VALUES (
            {comp_id}, {branch_id}, NULL, 'copy', 'available',
            '2026-06-01', 'INR'
        ) RETURNING id;
    """)).scalar()
    db.commit()
    assert copy_id is not None

    # Clean up test row
    db.execute(text(f"DELETE FROM invoices WHERE id = {copy_id}"))
    db.commit()


def test_issuance_pdf_failure_and_retry_workflow(client, auth_headers, setup_test_data, db, monkeypatch):
    """
    Verifies the resilience of the two-phase issuance workflow:
    1. During approval, number is reserved and status set to pending_issuance.
    2. If PDF generation fails, invoice remains in pending_issuance with its reserved number.
    3. Retrying issuance reuses the exact same invoice number without burning sequences.
    4. Successful retry transitions to approved and stores immutable PDF metadata.
    5. Exactly 1 invoice exists with that number (no duplicate created).
    """
    import app.services.invoice_issuance as issuance_module
    from app.models import Invoice

    creator_headers = auth_headers(setup_test_data["creator_email"])
    approver_headers = auth_headers(setup_test_data["approver_email"])

    # 1. Create and submit draft
    draft_payload = {
        "branch_id": setup_test_data["branch_id"],
        "gst_registration_id": setup_test_data["gst_reg_id"],
        "customer_id": setup_test_data["customer_id"],
        "place_of_supply": "33",
        "invoice_date": "2026-08-01",
        "notes": "PDF generation retry resilience test",
        "apply_round_off": False,
        "items": [
            {
                "description": "Storage Area Network Appliance",
                "hsn_sac_code": "8471",
                "item_type": "goods",
                "quantity": 1,
                "unit": "nos",
                "unit_price": 75000.00,
                "discount_percent": 0.0,
                "gst_rate": 18.0,
                "gst_classification": "TAXABLE",
            }
        ],
    }
    resp = client.post("/api/sales-invoices/drafts", json=draft_payload, headers=creator_headers)
    assert resp.status_code == 201, resp.text
    inv_id = resp.json()["id"]

    sub_resp = client.post(f"/api/sales-invoices/{inv_id}/submit", headers=creator_headers)
    assert sub_resp.status_code == 200

    # 2. Simulate PDF generation failure during first approval attempt
    original_render_fn = issuance_module._render_and_save_sales_invoice_pdf
    call_count = {"count": 0}

    def failing_render(*args, **kwargs):
        call_count["count"] += 1
        raise RuntimeError("Simulated WeasyPrint crash / storage disk failure")

    monkeypatch.setattr(issuance_module, "_render_and_save_sales_invoice_pdf", failing_render)

    # First approval attempt fails with 500
    fail_appr = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=approver_headers)
    assert fail_appr.status_code == 500
    assert "PDF generation failed during issuance" in fail_appr.json()["detail"]
    assert call_count["count"] == 1

    # 3. Verify DB state: invoice is in pending_issuance with reserved number
    db.expire_all()
    inv_row = db.query(Invoice).filter(Invoice.id == inv_id).first()
    assert inv_row.status == "pending_issuance"
    assert inv_row.invoice_number is not None
    reserved_number = inv_row.invoice_number
    assert reserved_number.startswith("INV/2026-27/")
    assert inv_row.sales_detail.issuance_attempt_count >= 1
    assert "Simulated WeasyPrint crash" in (inv_row.sales_detail.issuance_error_details or "")
    assert inv_row.sales_detail.pdf_storage_key is None

    # 4. Restore original PDF renderer and retry issuance
    monkeypatch.setattr(issuance_module, "_render_and_save_sales_invoice_pdf", original_render_fn)

    retry_appr = client.post(f"/api/sales-invoices/{inv_id}/approve", headers=approver_headers)
    assert retry_appr.status_code == 200, retry_appr.text
    appr_data = retry_appr.json()

    # Must reuse the identical reserved invoice number!
    assert appr_data["status"] == "approved"
    assert appr_data["invoice_number"] == reserved_number
    assert appr_data["pdf_filename"] is not None
    assert appr_data["pdf_sha256"] is not None

    # 5. Verify no duplicate invoice was created
    db.expire_all()
    duplicate_count = db.query(Invoice).filter(Invoice.invoice_number == reserved_number).count()
    assert duplicate_count == 1

