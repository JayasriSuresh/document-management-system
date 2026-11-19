"""
Tests for Module 13 Phase 3:
- Pure Decimal Tax Engine (intra-state, inter-state, paise retention, round-off, discounts, classifications).
- GSTIN validation (regex, state catalogue, Modulo-36 Luhn checksum).
- Indian Financial Year calculation (IST boundary conditions).
- Transaction-safe number sequence reservation.
"""

import pytest
from decimal import Decimal
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor

from app.services.tax_engine import (
    calculate_taxes,
    TaxLineInput,
    GstClassification,
)
from app.services.gstin_validator import (
    validate_gstin,
    get_gstin_state,
    compute_gstin_checksum,
)
from app.services.invoice_numbering import (
    get_current_financial_year,
    format_invoice_number,
    reserve_invoice_number,
)
from app.database import SessionLocal
from app.models import (
    Company,
    Branch,
    GstRegistration,
    NumberSequence,
)


def test_tax_engine_intra_state_single_item():
    """Intra-state transaction splits GST equally between CGST and SGST."""
    items = [
        TaxLineInput(
            description="Office Chair",
            quantity=Decimal("2"),
            unit_price=Decimal("5000.00"),
            gst_rate=Decimal("18.00"),
        )
    ]
    result = calculate_taxes(
        supplier_state_code="33",
        place_of_supply="33",
        items=items,
        apply_round_off=False,
    )

    assert result.is_intra_state is True
    assert result.taxable_amount == Decimal("10000.00")
    assert result.cgst_amount == Decimal("900.00")
    assert result.sgst_amount == Decimal("900.00")
    assert result.igst_amount == Decimal("0.00")
    assert result.total_tax_amount == Decimal("1800.00")
    assert result.round_off == Decimal("0.00")
    assert result.grand_total == Decimal("11800.00")


def test_tax_engine_inter_state_single_item():
    """Inter-state transaction applies full GST rate to IGST with zero CGST/SGST."""
    items = [
        TaxLineInput(
            description="Consulting Service",
            quantity=Decimal("1"),
            unit_price=Decimal("50000.00"),
            item_type="services",
            gst_rate=Decimal("18.00"),
        )
    ]
    result = calculate_taxes(
        supplier_state_code="33",  # Tamil Nadu
        place_of_supply="29",      # Karnataka
        items=items,
        apply_round_off=False,
    )

    assert result.is_intra_state is False
    assert result.taxable_amount == Decimal("50000.00")
    assert result.cgst_amount == Decimal("0.00")
    assert result.sgst_amount == Decimal("0.00")
    assert result.igst_amount == Decimal("9000.00")
    assert result.total_tax_amount == Decimal("9000.00")
    assert result.grand_total == Decimal("59000.00")


def test_tax_engine_paise_retention_and_round_off():
    """
    Verifies exact paise precision (no premature whole-rupee rounding).
    Simulates Document 492:
    Taxable 81355.95, CGST 7322.04, SGST 7322.04.
    Raw total is 96000.03.
    Without round-off: 96000.03.
    With round-off: 96000.00 (round_off = -0.03).
    """
    items = [
        TaxLineInput(
            description="ZEBRONICS A25FHD 25\" MONITOR WHITE",
            quantity=Decimal("15"),
            unit_price=Decimal("5423.73"),  # 15 * 5423.73 = 81355.95
            gst_rate=Decimal("18.00"),
        )
    ]

    # 1. Without round-off (retains paise)
    res_no_round = calculate_taxes("33", "33", items, apply_round_off=False)
    assert res_no_round.taxable_amount == Decimal("81355.95")
    assert res_no_round.cgst_amount == Decimal("7322.04")
    assert res_no_round.sgst_amount == Decimal("7322.04")
    assert res_no_round.round_off == Decimal("0.00")
    assert res_no_round.grand_total == Decimal("96000.03")

    # 2. With round-off
    res_round = calculate_taxes("33", "33", items, apply_round_off=True)
    assert res_round.taxable_amount == Decimal("81355.95")
    assert res_round.round_off == Decimal("-0.03")
    assert res_round.grand_total == Decimal("96000.00")


def test_tax_engine_discount_calculations():
    """Tests percentage and fixed amount discounts."""
    # Percentage discount: 10% of 10000 = 1000 -> Taxable 9000
    items_pct = [
        TaxLineInput(
            description="Item with 10% discount",
            quantity=Decimal("10"),
            unit_price=Decimal("1000.00"),
            discount_percent=Decimal("10.00"),
            gst_rate=Decimal("18.00"),
        )
    ]
    res_pct = calculate_taxes("33", "33", items_pct)
    assert res_pct.total_gross_amount == Decimal("10000.00")
    assert res_pct.total_discount_amount == Decimal("1000.00")
    assert res_pct.taxable_amount == Decimal("9000.00")
    assert res_pct.cgst_amount == Decimal("810.00")
    assert res_pct.sgst_amount == Decimal("810.00")
    assert res_pct.grand_total == Decimal("10620.00")

    # Fixed discount: 500 off 5000 -> Taxable 4500
    items_fixed = [
        TaxLineInput(
            description="Item with fixed discount",
            quantity=Decimal("5"),
            unit_price=Decimal("1000.00"),
            discount_amount=Decimal("500.00"),
            gst_rate=Decimal("12.00"),
        )
    ]
    res_fixed = calculate_taxes("33", "33", items_fixed)
    assert res_fixed.total_gross_amount == Decimal("5000.00")
    assert res_fixed.total_discount_amount == Decimal("500.00")
    assert res_fixed.taxable_amount == Decimal("4500.00")


def test_tax_engine_discounts_exceeding_gross_rejected():
    """A discount larger than the line amount must raise a ValueError."""
    items = [
        TaxLineInput(
            description="Discount error",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00"),
            discount_amount=Decimal("150.00"),
        )
    ]
    with pytest.raises(ValueError, match="cannot exceed gross amount"):
        calculate_taxes("33", "33", items)


def test_tax_engine_classifications():
    """Zero-rated, exempt, nil-rated, and non-GST items have 0 tax regardless of gst_rate."""
    items = [
        TaxLineInput(
            description="Export item",
            quantity=Decimal("1"),
            unit_price=Decimal("2000.00"),
            gst_rate=Decimal("18.00"),
            gst_classification=GstClassification.ZERO_RATED,
        ),
        TaxLineInput(
            description="Agricultural produce",
            quantity=Decimal("1"),
            unit_price=Decimal("3000.00"),
            gst_rate=Decimal("5.00"),
            gst_classification=GstClassification.EXEMPT,
        ),
    ]
    res = calculate_taxes("33", "29", items)
    assert res.taxable_amount == Decimal("5000.00")
    assert res.cgst_amount == Decimal("0.00")
    assert res.sgst_amount == Decimal("0.00")
    assert res.igst_amount == Decimal("0.00")
    assert res.grand_total == Decimal("5000.00")


def test_gstin_validator_known_valid():
    """Validates real and synthetic valid GSTINs."""
    # Real live GSTINs from document 492
    assert validate_gstin("33BLAPS0819R1ZQ")[0] is True
    assert validate_gstin("33ALJPP7733P1ZE")[0] is True

    state_code, state_name = get_gstin_state("33BLAPS0819R1ZQ")
    assert state_code == "33"
    assert state_name == "Tamil Nadu"


def test_gstin_validator_invalid_checksum():
    """GSTIN with tampered 15th character is rejected."""
    # Correct is 'Q', replace with 'A'
    is_valid, msg = validate_gstin("33BLAPS0819R1ZA")
    assert is_valid is False
    assert "Invalid GSTIN checksum" in msg


def test_gstin_validator_invalid_state_code():
    """State code not in Indian GST catalogue is rejected."""
    # State code '00' is invalid
    is_valid, msg = validate_gstin("00BLAPS0819R1ZQ")
    assert is_valid is False
    assert "Invalid state code" in msg


def test_financial_year_boundaries():
    """Tests Indian Financial Year logic across calendar year and FY transitions."""
    assert get_current_financial_year(date(2026, 3, 31)) == "2025-26"
    assert get_current_financial_year(date(2026, 4, 1)) == "2026-27"
    assert get_current_financial_year(date(2026, 11, 12)) == "2026-27"
    assert get_current_financial_year(date(2027, 1, 15)) == "2026-27"
    assert get_current_financial_year(date(2027, 3, 31)) == "2026-27"
    assert get_current_financial_year(date(2027, 4, 1)) == "2027-28"


def test_invoice_number_format_and_length():
    """Ensures formatted invoice number adheres to max 16 chars per GST Rule 46(b)."""
    inv_no = format_invoice_number("INV", "2026-27", 1)
    assert inv_no == "INV/2026-27/0001"
    assert len(inv_no) <= 16

    # Test error when prefix + FY + seq exceeds 16 chars
    with pytest.raises(ValueError, match="exceeds the statutory maximum length"):
        format_invoice_number("VERYLONGPREFIX", "2026-27", 1)


def test_number_sequence_reservation_in_db():
    """Tests atomic number reservation against the database."""
    db = SessionLocal()
    try:
        # Create a test company & registration if not existing
        company = db.query(Company).filter(Company.name == "Numbering Test Company").first()
        if not company:
            company = Company(name="Numbering Test Company", code="TESTNUM", status="active")
            db.add(company)
            db.flush()

        gst_reg = db.query(GstRegistration).filter(
            GstRegistration.company_id == company.id,
            GstRegistration.gstin == "33ALJPP7733P1ZE",
        ).first()
        if not gst_reg:
            # Check if gstin is registered elsewhere, or use a new clean one
            existing = db.query(GstRegistration).filter(GstRegistration.gstin == "33ALJPP7733P1ZE").first()
            if existing:
                gst_reg = existing
                company = db.query(Company).filter(Company.id == gst_reg.company_id).first()
            else:
                gst_reg = GstRegistration(
                    company_id=company.id,
                    gstin="33ALJPP7733P1ZE",
                    legal_name="Test Legal Name",
                    state_code="33",
                    state_name="Tamil Nadu",
                    registered_address="123 Test St",
                    is_active=True,
                )
                db.add(gst_reg)
                db.flush()

        # Reserve number 1
        num1, fy1 = reserve_invoice_number(
            db, company.id, gst_reg.id, series_code="INV", invoice_date=date(2026, 5, 10)
        )
        assert num1 == "INV/2026-27/0001"
        assert fy1 == "2026-27"

        # Reserve number 2
        num2, fy2 = reserve_invoice_number(
            db, company.id, gst_reg.id, series_code="INV", invoice_date=date(2026, 5, 10)
        )
        assert num2 == "INV/2026-27/0002"
        assert fy2 == "2026-27"

        db.commit()

        # Test concurrency with 10 concurrent threads reserving numbers
        def reserve_task(_):
            worker_db = SessionLocal()
            try:
                num, _ = reserve_invoice_number(
                    worker_db, company.id, gst_reg.id, series_code="INV", invoice_date=date(2026, 5, 10)
                )
                worker_db.commit()
                return num
            finally:
                worker_db.close()

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(reserve_task, range(10)))

        # All 10 numbers must be unique
        assert len(results) == 10
        assert len(set(results)) == 10
        # Expected sequence numbers 0003 through 0012
        seq_nums = sorted([int(r.split("/")[-1]) for r in results])
        assert seq_nums == list(range(3, 13))

        # Cleanup test company
        db.query(NumberSequence).filter(NumberSequence.company_id == company.id).delete()
        db.query(GstRegistration).filter(GstRegistration.company_id == company.id).delete()
        db.query(Company).filter(Company.id == company.id).delete()
        db.commit()
    finally:
        db.close()
