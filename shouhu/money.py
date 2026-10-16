"""Token amounts are integers in base units. Never floats."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN

from .config import TOKEN_DECIMALS, TOKEN_SYMBOL, UNIT


class AmountError(ValueError):
    pass


def to_units(amount) -> int:
    """Parse a human amount ('19.5', 20, '1,000') into base units. Rejects negatives, zero and junk."""
    if isinstance(amount, bool):
        raise AmountError("amount must be a number")
    text = str(amount).strip().replace(",", "").replace(TOKEN_SYMBOL, "").replace("USDC", "").strip()
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        raise AmountError(f"could not read amount '{amount}'")
    if d <= 0:
        raise AmountError("amount must be greater than zero")
    units = int((d * UNIT).to_integral_value(rounding=ROUND_DOWN))
    if units <= 0:
        raise AmountError(f"amount is below the smallest unit (1e-{TOKEN_DECIMALS})")
    return units


def fmt(units: int) -> str:
    d = Decimal(units) / UNIT
    return f"{d.quantize(Decimal(1) if d == d.to_integral() else Decimal('0.01'))} {TOKEN_SYMBOL}"
