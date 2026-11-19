"""
GSTIN validation service.
Validates structure, state code, PAN component, and Modulo-36 checksum.
"""

import re
from typing import Dict, Optional, Tuple

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Official Indian State & Union Territory GST Codes
INDIAN_GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh (Old)",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh (New)",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def compute_gstin_checksum(gstin_14: str) -> Optional[str]:
    """
    Computes the 15th character checksum for a 14-character GSTIN prefix using Modulo-36 Luhn-like algorithm.
    """
    if len(gstin_14) != 14:
        return None
    gstin_14 = gstin_14.upper()
    total = 0
    for i, c in enumerate(gstin_14):
        if c not in GSTIN_CHARS:
            return None
        val = GSTIN_CHARS.index(c)
        factor = 1 if (i % 2 == 0) else 2
        prod = val * factor
        total += (prod // 36) + (prod % 36)

    check_val = (36 - (total % 36)) % 36
    return GSTIN_CHARS[check_val]


def validate_gstin(gstin: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Validates GSTIN:
    - Non-empty, 15 chars, uppercase alphanumeric
    - Regex pattern matching
    - Valid state code
    - Valid PAN structure
    - Valid Modulo-36 checksum
    
    Returns:
        (is_valid: bool, error_message: Optional[str])
    """
    if not gstin:
        return False, "GSTIN cannot be empty"

    cleaned = gstin.strip().upper()
    if len(cleaned) != 15:
        return False, f"GSTIN must be exactly 15 characters, got {len(cleaned)}"

    if not GSTIN_REGEX.match(cleaned):
        return False, "Invalid GSTIN format pattern"

    state_code = cleaned[:2]
    if state_code not in INDIAN_GST_STATE_CODES:
        return False, f"Invalid state code '{state_code}' in GSTIN"

    expected_checksum = compute_gstin_checksum(cleaned[:14])
    if cleaned[14] != expected_checksum:
        return False, f"Invalid GSTIN checksum: expected '{expected_checksum}', got '{cleaned[14]}'"

    return True, None


def get_gstin_state(gstin: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (state_code, state_name) from GSTIN if valid, else (None, None).
    """
    is_valid, _ = validate_gstin(gstin)
    if not is_valid:
        return None, None
    code = gstin.strip().upper()[:2]
    return code, INDIAN_GST_STATE_CODES.get(code)
