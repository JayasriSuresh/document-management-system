"""
Module 11 – Centralized Deterministic Validation Engine.

Deterministic validation service that validates extracted document data against
a pinned template version and its allowlisted business rules:
- GSTIN format & state code consistency
- Invoice date parsing and normalization
- Line-item arithmetic (qty * rate - discount == amount)
- Taxable value and tax totals consistency against grand total
- CGST/SGST vs IGST consistency (intra-state vs inter-state)
- Required field and schema constraint enforcement

Crucial:
- Zero AI hallucination: all checks are pure deterministic arithmetic and format rules.
- Severity levels: 'error' (prevents approval) and 'warning' (review required, approvable).
"""

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Union

# ── Indian GSTIN Regex ────────────────────────────────────────────────────────
# 2 digits (state code) + 5 letters (PAN) + 4 digits + 1 letter + 1 entity char + 'Z' + 1 checksum char
GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')

# Valid Indian GST State Codes (01 to 38, plus special codes 97, 99)
VALID_GST_STATE_CODES = frozenset({
    f"{i:02d}" for i in range(1, 39)
} | {"97", "99"})


@dataclass
class ValidationFlag:
    field_path: str
    rule_id: str
    severity: str  # "error" | "warning"
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_path": self.field_path,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class ValidationResult:
    is_valid: bool
    flags: List[ValidationFlag] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.flags)

    @property
    def has_warnings(self) -> bool:
        return any(f.severity == "warning" for f in self.flags)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "flags": [f.to_dict() for f in self.flags],
        }


def _get_nested(data: Dict[str, Any], path: str) -> Any:
    """Safely traverse dot-separated paths (e.g. 'seller.gstin' or 'totals.grand_total')."""
    if not data or not path:
        return None
    parts = path.split(".")
    curr = data
    for p in parts:
        if isinstance(curr, dict):
            curr = curr.get(p)
        else:
            return None
    return curr


def _to_float(val: Any) -> Optional[float]:
    """Safely parse a numeric float value from int, float, or string."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Clean currency signs, commas, and trailing text
        cleaned = re.sub(r'[^\d.-]', '', val.strip())
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    return None


def _parse_date(date_str: Any) -> Optional[datetime]:
    """Parse common invoice date formats into a normalized datetime object."""
    if not date_str or not isinstance(date_str, str):
        return None
    clean_str = date_str.strip()
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
        "%Y/%m/%d", "%Y.%m.%d",
        "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y",
        "%d-%B-%Y", "%d-%B-%y", "%d %B %Y", "%d %B %y",
        "%d/%b/%Y", "%d/%b/%y", "%b %d, %Y", "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            pass
        try:
            return datetime.strptime(clean_str.title(), fmt)
        except ValueError:
            continue
    return None


class DeterministicValidationEngine:
    @staticmethod
    def validate_gstin(gstin_val: Any, field_path: str, flags: List[ValidationFlag], state_code: Optional[str] = None) -> None:
        """Validate Indian GSTIN format and structure."""
        if not gstin_val or not isinstance(gstin_val, str) or not gstin_val.strip():
            # If not provided, required-field checks handle if it was mandatory
            return

        g = gstin_val.strip().upper()
        if len(g) != 15:
            flags.append(ValidationFlag(
                field_path=field_path,
                rule_id="gstin_format",
                severity="error",
                message=f"GSTIN '{g}' must be exactly 15 characters (got {len(g)})",
                expected="15-character alphanumeric GSTIN",
                actual=g,
            ))
            return

        if not GSTIN_REGEX.match(g):
            flags.append(ValidationFlag(
                field_path=field_path,
                rule_id="gstin_format",
                severity="error",
                message=f"Invalid GSTIN format '{g}'. Must match pattern 2-digit state + 10-char PAN + entity code + Z + checksum",
                expected="2-digit state code + 10-char PAN + entity code + Z + checksum",
                actual=g,
            ))
            return

        st_code = g[:2]
        if st_code not in VALID_GST_STATE_CODES:
            flags.append(ValidationFlag(
                field_path=field_path,
                rule_id="gstin_state_code",
                severity="warning",
                message=f"GSTIN state code '{st_code}' is not a recognized Indian state code",
                expected="Valid GST state code (01-38, 97, 99)",
                actual=st_code,
            ))

        if state_code and str(state_code).strip():
            sc = str(state_code).strip().zfill(2)
            if sc != st_code:
                flags.append(ValidationFlag(
                    field_path=field_path,
                    rule_id="gstin_state_code_mismatch",
                    severity="warning",
                    message=f"GSTIN state code '{st_code}' does not match declared state code '{sc}'",
                    expected=sc,
                    actual=st_code,
                ))

    @staticmethod
    def validate_date(date_val: Any, field_path: str, flags: List[ValidationFlag]) -> None:
        """Validate invoice date format and bounds."""
        if not date_val:
            return
        dt = _parse_date(str(date_val))
        if not dt:
            flags.append(ValidationFlag(
                field_path=field_path,
                rule_id="invoice_date_format",
                severity="error",
                message=f"Unrecognized invoice date format: '{date_val}'",
                expected="YYYY-MM-DD or DD/MM/YYYY",
                actual=date_val,
            ))
            return

        # Sanity check on year
        if dt.year < 2000 or dt.year > 2050:
            flags.append(ValidationFlag(
                field_path=field_path,
                rule_id="invoice_date_range",
                severity="warning",
                message=f"Invoice date '{date_val}' is outside typical range (2000-2050)",
                expected="Year between 2000 and 2050",
                actual=dt.year,
            ))

    @staticmethod
    def validate_line_items(items: Any, items_path: str, tolerance: float, flags: List[ValidationFlag]) -> None:
        """Validate arithmetic consistency within line items: qty * rate - discount == amount."""
        if not items or not isinstance(items, list):
            return

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_path = f"{items_path}[{idx}]"
            desc = item.get("description") or f"Item #{idx+1}"

            qty_val = item.get("qty")
            qty_num = _to_float(qty_val)
            rate_num = _to_float(item.get("rate"))
            disc_num = _to_float(item.get("discount")) or 0.0
            amount_num = _to_float(item.get("amount"))

            if qty_num is not None and rate_num is not None:
                calc_amount = (qty_num * rate_num) - disc_num
                if amount_num is not None:
                    diff = abs(calc_amount - amount_num)
                    if diff > tolerance:
                        flags.append(ValidationFlag(
                            field_path=f"{item_path}.amount",
                            rule_id="line_item_math",
                            severity="error",
                            message=f"{desc}: calculated qty ({qty_num}) × rate ({rate_num}) - discount ({disc_num}) = {calc_amount:.2f} does not match line amount {amount_num:.2f}",
                            expected=round(calc_amount, 2),
                            actual=round(amount_num, 2),
                        ))

    @staticmethod
    def validate_totals(totals: Any, totals_path: str, tolerance: float, flags: List[ValidationFlag]) -> None:
        """Validate taxable value + taxes == grand total."""
        if not totals or not isinstance(totals, dict):
            return

        tv = _to_float(totals.get("taxable_value")) or 0.0
        cg = _to_float(totals.get("cgst")) or 0.0
        sg = _to_float(totals.get("sgst")) or 0.0
        ig = _to_float(totals.get("igst")) or 0.0
        ro = _to_float(totals.get("round_off")) or 0.0
        gt = _to_float(totals.get("grand_total"))

        if gt is not None and gt > 0:
            calc_total = tv + cg + sg + ig + ro
            diff = abs(calc_total - gt)
            if diff > tolerance:
                flags.append(ValidationFlag(
                    field_path=f"{totals_path}.grand_total",
                    rule_id="totals_consistency",
                    severity="error",
                    message=f"Taxable value ({tv:.2f}) + CGST ({cg:.2f}) + SGST ({sg:.2f}) + IGST ({ig:.2f}) + RoundOff ({ro:.2f}) = {calc_total:.2f} does not match Grand Total {gt:.2f}",
                    expected=round(calc_total, 2),
                    actual=round(gt, 2),
                ))

    @staticmethod
    def validate_gst_consistency(seller: Any, buyer: Any, totals: Any, flags: List[ValidationFlag]) -> None:
        """Validate CGST/SGST vs IGST consistency against seller/buyer state codes."""
        if not totals or not isinstance(totals, dict):
            return

        cg = _to_float(totals.get("cgst")) or 0.0
        sg = _to_float(totals.get("sgst")) or 0.0
        ig = _to_float(totals.get("igst")) or 0.0

        # CGST and SGST must generally be equal in Indian GST intra-state supplies
        if (cg > 0 or sg > 0) and not (ig > 0):
            if abs(cg - sg) > 0.05:
                flags.append(ValidationFlag(
                    field_path="totals.cgst",
                    rule_id="gst_tax_consistency",
                    severity="warning",
                    message=f"CGST ({cg:.2f}) and SGST ({sg:.2f}) amounts should be equal for intra-state supply",
                    expected=cg,
                    actual=sg,
                ))

        # Check state codes if available
        seller_dict = seller if isinstance(seller, dict) else {}
        buyer_dict = buyer if isinstance(buyer, dict) else {}
        seller_sc = str(seller_dict.get("state_code") or "").strip().zfill(2) if seller_dict.get("state_code") else ""
        buyer_sc = str(buyer_dict.get("state_code") or "").strip().zfill(2) if buyer_dict.get("state_code") else ""

        if seller_sc and buyer_sc:
            if seller_sc == buyer_sc and ig > 0 and not (cg > 0 or sg > 0):
                flags.append(ValidationFlag(
                    field_path="totals.igst",
                    rule_id="gst_tax_consistency",
                    severity="warning",
                    message=f"Intra-state supply (seller and buyer state code {seller_sc}) has IGST ({ig:.2f}) instead of CGST/SGST",
                    expected="CGST + SGST",
                    actual="IGST",
                ))
            elif seller_sc != buyer_sc and (cg > 0 or sg > 0) and not (ig > 0):
                flags.append(ValidationFlag(
                    field_path="totals.cgst",
                    rule_id="gst_tax_consistency",
                    severity="warning",
                    message=f"Inter-state supply (seller state {seller_sc} ≠ buyer state {buyer_sc}) has CGST/SGST instead of IGST",
                    expected="IGST",
                    actual="CGST + SGST",
                ))

    @staticmethod
    def validate_schema_fields(data: Dict[str, Any], schema_fields: List[Dict[str, Any]], prefix: str, flags: List[ValidationFlag]) -> None:
        """Validate required fields and basic constraints declared in schema."""
        for f in schema_fields:
            key = f.get("key", "")
            f_path = f"{prefix}.{key}" if prefix else key
            label = f.get("label", key)
            is_req = f.get("required", False)
            val = _get_nested(data, f_path)

            if is_req:
                if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, (list, dict)) and len(val) == 0):
                    flags.append(ValidationFlag(
                        field_path=f_path,
                        rule_id="required_field",
                        severity="error",
                        message=f"Required field '{label}' is missing or empty",
                        expected="Non-empty value",
                        actual=None,
                    ))

            # Recurse into nested object fields
            if f.get("type") == "object" and "fields" in f:
                DeterministicValidationEngine.validate_schema_fields(data, f["fields"], f_path, flags)


def validate_extraction(data: Dict[str, Any], template_version: Any) -> ValidationResult:
    """
    Central validation function:
    Executes schema checks, configured rules, and deterministic validators.
    """
    flags: List[ValidationFlag] = []
    if not isinstance(data, dict):
        flags.append(ValidationFlag(
            field_path="",
            rule_id="extraction_data_invalid",
            severity="error",
            message="Extracted data is not a valid JSON object",
        ))
        return ValidationResult(is_valid=False, flags=flags)

    schema_json = getattr(template_version, "schema_json", {}) or {}
    validation_rules = getattr(template_version, "validation_rules", []) or []

    # 1. Schema-level required fields
    fields = schema_json.get("fields", [])
    if fields:
        DeterministicValidationEngine.validate_schema_fields(data, fields, "", flags)

    # 2. Configured validation rules
    for rule in validation_rules:
        r_type = rule.get("type", "").lower()
        r_severity = rule.get("severity", "error")

        if r_type == "gstin":
            target_fields = rule.get("fields", ["seller.gstin", "buyer.gstin"])
            for fp in target_fields:
                state_code_path = fp.replace(".gstin", ".state_code")
                sc = _get_nested(data, state_code_path)
                val = _get_nested(data, fp)
                DeterministicValidationEngine.validate_gstin(val, fp, flags, state_code=sc)

        elif r_type == "date":
            target_fields = rule.get("fields", ["invoice.date"])
            for fp in target_fields:
                val = _get_nested(data, fp)
                DeterministicValidationEngine.validate_date(val, fp, flags)

        elif r_type == "line_item_arithmetic":
            items_path = rule.get("items_path", "items")
            tol = float(rule.get("tolerance", 0.5))
            items = _get_nested(data, items_path)
            DeterministicValidationEngine.validate_line_items(items, items_path, tol, flags)

        elif r_type == "totals_sum":
            totals_path = rule.get("totals_path", "totals")
            tol = float(rule.get("tolerance", 0.5))
            totals = _get_nested(data, totals_path)
            DeterministicValidationEngine.validate_totals(totals, totals_path, tol, flags)

        elif r_type == "gst_consistency":
            seller_path = rule.get("seller_path", "seller")
            buyer_path = rule.get("buyer_path", "buyer")
            totals_path = rule.get("totals_path", "totals")
            seller = _get_nested(data, seller_path)
            buyer = _get_nested(data, buyer_path)
            totals = _get_nested(data, totals_path)
            DeterministicValidationEngine.validate_gst_consistency(seller, buyer, totals, flags)

        elif r_type == "required":
            for fp in rule.get("fields", []):
                val = _get_nested(data, fp)
                if val is None or (isinstance(val, str) and not val.strip()):
                    flags.append(ValidationFlag(
                        field_path=fp,
                        rule_id=rule.get("rule_id", "required"),
                        severity=r_severity,
                        message=rule.get("message", f"Field '{fp}' is required"),
                    ))

        elif r_type == "numeric_range":
            fp = rule.get("field", "")
            val = _to_float(_get_nested(data, fp))
            min_v = rule.get("min")
            max_v = rule.get("max")
            if val is not None:
                if min_v is not None and val < float(min_v):
                    flags.append(ValidationFlag(
                        field_path=fp,
                        rule_id="numeric_range",
                        severity=r_severity,
                        message=f"Field '{fp}' value {val} is below minimum {min_v}",
                        expected=min_v,
                        actual=val,
                    ))
                if max_v is not None and val > float(max_v):
                    flags.append(ValidationFlag(
                        field_path=fp,
                        rule_id="numeric_range",
                        severity=r_severity,
                        message=f"Field '{fp}' value {val} exceeds maximum {max_v}",
                        expected=max_v,
                        actual=val,
                    ))

    is_valid = not any(f.severity == "error" for f in flags)
    return ValidationResult(is_valid=is_valid, flags=flags)
