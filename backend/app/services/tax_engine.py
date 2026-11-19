"""
Authoritative pure-Decimal tax calculation engine for Indian GST compliance.
Enforces 2-decimal-place precision (paise retention), standard ROUND_HALF_UP,
explicit intra-state vs inter-state tax routing, and configurable round-off.
"""

from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Union, Dict, Any


class GstClassification(str, Enum):
    TAXABLE = "TAXABLE"
    ZERO_RATED = "ZERO_RATED"
    EXEMPT = "EXEMPT"
    NIL_RATED = "NIL_RATED"
    NON_GST = "NON_GST"


CENT = Decimal("0.01")
ZERO_2DP = Decimal("0.00")
ZERO_4DP = Decimal("0.0000")
HUNDRED = Decimal("100")


def to_decimal(val: Union[Decimal, int, float, str, None], default: str = "0.00") -> Decimal:
    """Safely converts an input to Decimal, avoiding floating point inaccuracy."""
    if val is None:
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


@dataclass(frozen=True)
class TaxLineInput:
    description: str
    quantity: Decimal
    unit_price: Decimal
    hsn_sac_code: Optional[str] = None
    item_type: str = "goods"  # "goods" or "services"
    unit: str = "nos"
    discount_amount: Decimal = ZERO_2DP
    discount_percent: Decimal = ZERO_2DP
    gst_rate: Decimal = ZERO_2DP  # Combined GST percentage, e.g. Decimal("18.00")
    gst_classification: GstClassification = GstClassification.TAXABLE


@dataclass(frozen=True)
class CalculatedLineItem:
    item_order: int
    description: str
    hsn_sac_code: Optional[str]
    item_type: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    gross_amount: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    gst_classification: str
    gst_rate: Decimal
    cgst_rate: Decimal
    cgst_amount: Decimal
    sgst_rate: Decimal
    sgst_amount: Decimal
    igst_rate: Decimal
    igst_amount: Decimal
    total_tax_amount: Decimal
    line_total: Decimal

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d


@dataclass(frozen=True)
class TaxEngineResult:
    supplier_state_code: str
    place_of_supply: str
    is_intra_state: bool
    apply_round_off: bool
    lines: List[CalculatedLineItem]
    total_gross_amount: Decimal
    total_discount_amount: Decimal
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax_amount: Decimal
    round_off: Decimal
    grand_total: Decimal

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_state_code": self.supplier_state_code,
            "place_of_supply": self.place_of_supply,
            "is_intra_state": self.is_intra_state,
            "apply_round_off": self.apply_round_off,
            "lines": [line.to_dict() for line in self.lines],
            "total_gross_amount": str(self.total_gross_amount),
            "total_discount_amount": str(self.total_discount_amount),
            "taxable_amount": str(self.taxable_amount),
            "cgst_amount": str(self.cgst_amount),
            "sgst_amount": str(self.sgst_amount),
            "igst_amount": str(self.igst_amount),
            "total_tax_amount": str(self.total_tax_amount),
            "round_off": str(self.round_off),
            "grand_total": str(self.grand_total),
        }


def calculate_taxes(
    supplier_state_code: str,
    place_of_supply: str,
    items: List[TaxLineInput],
    apply_round_off: bool = False,
) -> TaxEngineResult:
    """
    Pure Decimal tax calculation engine.
    
    Rules:
    - Never uses python float.
    - Each line item calculates gross = qty * rate.
    - Line discount is subtracted to arrive at taxable value.
    - Tax is determined:
        Intra-state (supplier_state == place_of_supply): CGST (gst_rate / 2) + SGST (gst_rate / 2)
        Inter-state (supplier_state != place_of_supply): IGST (gst_rate)
    - Taxes are quantized to 2 decimal places per line item (paise precision) using ROUND_HALF_UP.
    - Header totals are the exact sum of line items.
    - If apply_round_off is False (default), grand_total retains paise, round_off is 0.00.
    - If apply_round_off is True, grand_total is rounded to whole rupee, round_off captures the difference.
    """
    supp_state = str(supplier_state_code or "").strip().zfill(2)
    pos_state = str(place_of_supply or "").strip().zfill(2)
    is_intra = (supp_state == pos_state)

    calculated_lines: List[CalculatedLineItem] = []

    sum_gross = ZERO_2DP
    sum_discount = ZERO_2DP
    sum_taxable = ZERO_2DP
    sum_cgst = ZERO_2DP
    sum_sgst = ZERO_2DP
    sum_igst = ZERO_2DP

    for idx, item in enumerate(items, start=1):
        qty = to_decimal(item.quantity)
        rate = to_decimal(item.unit_price)

        if qty <= Decimal("0"):
            raise ValueError(f"Line {idx} quantity must be greater than zero, got {qty}")
        if rate < Decimal("0"):
            raise ValueError(f"Line {idx} unit price cannot be negative, got {rate}")

        # Gross calculation
        gross = (qty * rate).quantize(CENT, rounding=ROUND_HALF_UP)

        # Discount calculation
        disc_amt = to_decimal(item.discount_amount).quantize(CENT, rounding=ROUND_HALF_UP)
        disc_pct = to_decimal(item.discount_percent).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if disc_amt > ZERO_2DP:
            line_discount = disc_amt
        elif disc_pct > ZERO_2DP:
            line_discount = (gross * disc_pct / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
        else:
            line_discount = ZERO_2DP

        if line_discount > gross:
            raise ValueError(f"Line {idx} discount ({line_discount}) cannot exceed gross amount ({gross})")

        taxable = (gross - line_discount).quantize(CENT, rounding=ROUND_HALF_UP)

        raw_classification = item.gst_classification
        if hasattr(raw_classification, "value"):
            classification = str(raw_classification.value).upper()
        else:
            classification = str(raw_classification or "TAXABLE").upper()
        raw_gst_rate = to_decimal(item.gst_rate)
        if raw_gst_rate < ZERO_2DP:
            raise ValueError(f"Line {idx} GST rate cannot be negative, got {raw_gst_rate}")
        if raw_gst_rate > Decimal("100.00"):
            raise ValueError(f"Line {idx} GST rate cannot exceed 100%, got {raw_gst_rate}")

        if classification != GstClassification.TAXABLE.value or raw_gst_rate <= ZERO_2DP:
            gst_rate = ZERO_2DP
            cgst_rate = ZERO_2DP
            sgst_rate = ZERO_2DP
            igst_rate = ZERO_2DP
            cgst_amt = ZERO_2DP
            sgst_amt = ZERO_2DP
            igst_amt = ZERO_2DP
        else:
            gst_rate = raw_gst_rate
            if is_intra:
                cgst_rate = (gst_rate / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sgst_rate = (gst_rate / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                igst_rate = ZERO_2DP
                cgst_amt = (taxable * cgst_rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
                sgst_amt = (taxable * sgst_rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
                igst_amt = ZERO_2DP
            else:
                cgst_rate = ZERO_2DP
                sgst_rate = ZERO_2DP
                igst_rate = gst_rate.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                cgst_amt = ZERO_2DP
                sgst_amt = ZERO_2DP
                igst_amt = (taxable * igst_rate / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)

        line_tax_total = (cgst_amt + sgst_amt + igst_amt).quantize(CENT, rounding=ROUND_HALF_UP)
        line_total = (taxable + line_tax_total).quantize(CENT, rounding=ROUND_HALF_UP)

        calculated_line = CalculatedLineItem(
            item_order=idx,
            description=item.description,
            hsn_sac_code=item.hsn_sac_code,
            item_type=item.item_type or "goods",
            quantity=qty,
            unit=item.unit or "nos",
            unit_price=rate,
            gross_amount=gross,
            discount_percent=disc_pct,
            discount_amount=line_discount,
            taxable_amount=taxable,
            gst_classification=classification,
            gst_rate=gst_rate,
            cgst_rate=cgst_rate,
            cgst_amount=cgst_amt,
            sgst_rate=sgst_rate,
            sgst_amount=sgst_amt,
            igst_rate=igst_rate,
            igst_amount=igst_amt,
            total_tax_amount=line_tax_total,
            line_total=line_total,
        )
        calculated_lines.append(calculated_line)

        sum_gross += gross
        sum_discount += line_discount
        sum_taxable += taxable
        sum_cgst += cgst_amt
        sum_sgst += sgst_amt
        sum_igst += igst_amt

    sum_tax_total = (sum_cgst + sum_sgst + sum_igst).quantize(CENT, rounding=ROUND_HALF_UP)
    raw_total = (sum_taxable + sum_tax_total).quantize(CENT, rounding=ROUND_HALF_UP)

    if apply_round_off:
        grand_total = raw_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(CENT)
        round_off = (grand_total - raw_total).quantize(CENT)
    else:
        grand_total = raw_total
        round_off = ZERO_2DP

    return TaxEngineResult(
        supplier_state_code=supp_state,
        place_of_supply=pos_state,
        is_intra_state=is_intra,
        apply_round_off=apply_round_off,
        lines=calculated_lines,
        total_gross_amount=sum_gross.quantize(CENT),
        total_discount_amount=sum_discount.quantize(CENT),
        taxable_amount=sum_taxable.quantize(CENT),
        cgst_amount=sum_cgst.quantize(CENT),
        sgst_amount=sum_sgst.quantize(CENT),
        igst_amount=sum_igst.quantize(CENT),
        total_tax_amount=sum_tax_total.quantize(CENT),
        round_off=round_off,
        grand_total=grand_total.quantize(CENT),
    )
