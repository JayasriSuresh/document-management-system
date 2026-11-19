"""
Multi-Currency and Exchange Rate Service.

Supports conversion and tracking between AI provider billing currency (USD)
and operational/reporting currency (INR).
Preserves immutable historical exchange rates on usage records.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Union
from sqlalchemy.orm import Session
from app.models import PlatformSetting

DEFAULT_USD_TO_INR_RATE = 85.00


def get_usd_to_inr_rate(db: Session) -> float:
    """
    Returns the current platform USD-to-INR exchange rate.
    Defaults to 85.00 if not configured.
    """
    try:
        setting = db.query(PlatformSetting).filter(PlatformSetting.key == "usd_to_inr_exchange_rate").first()
        if setting and setting.value is not None:
            if isinstance(setting.value, (int, float)):
                return float(setting.value)
            if isinstance(setting.value, dict) and "rate" in setting.value:
                return float(setting.value["rate"])
            if isinstance(setting.value, str):
                return float(setting.value)
    except Exception:
        pass
    return DEFAULT_USD_TO_INR_RATE


def set_usd_to_inr_rate(db: Session, rate: float, updated_by: Optional[int] = None) -> float:
    """Updates the platform-wide USD-to-INR exchange rate in platform_settings."""
    rate_val = round(float(rate), 4)
    setting = db.query(PlatformSetting).filter(PlatformSetting.key == "usd_to_inr_exchange_rate").first()
    if not setting:
        setting = PlatformSetting(
            key="usd_to_inr_exchange_rate",
            value={"rate": rate_val, "updated_at": datetime.utcnow().isoformat()},
            updated_by=updated_by,
        )
        db.add(setting)
    else:
        setting.value = {"rate": rate_val, "updated_at": datetime.utcnow().isoformat()}
        setting.updated_at = datetime.utcnow()
        setting.updated_by = updated_by
    db.commit()
    return rate_val


def convert_usd_cents_to_inr(cost_cents: int, rate: float) -> float:
    """Converts USD cents to INR amount rounded to 4 decimal places."""
    if not cost_cents or cost_cents <= 0:
        return 0.0
    usd_dollars = cost_cents / 100.0
    return round(usd_dollars * rate, 4)


def convert_inr_to_usd_cents(inr_amount: float, rate: float) -> int:
    """Converts INR amount to USD cents rounded to nearest cent."""
    if not inr_amount or inr_amount <= 0 or rate <= 0:
        return 0
    usd_dollars = inr_amount / rate
    return int(round(usd_dollars * 100))


def format_inr(amount: Union[float, int, Decimal, None]) -> str:
    """Formats amount with Indian Rupee formatting (e.g. ₹4,250.00)."""
    if amount is None:
        return "₹0.00"
    try:
        v = float(amount)
        neg = v < 0
        v = abs(v)
        integer_part, decimal_part = f"{v:.2f}".split(".")
        if len(integer_part) > 3:
            last3 = integer_part[-3:]
            rest = integer_part[:-3]
            groups = []
            while len(rest) > 2:
                groups.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                groups.append(rest)
            groups.reverse()
            integer_part = ",".join(groups) + "," + last3
        result = f"₹{integer_part}.{decimal_part}"
        return ("-" + result) if neg else result
    except Exception:
        return f"₹{amount:.2f}"
