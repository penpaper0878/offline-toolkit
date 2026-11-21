"""Decimal arithmetic with the half-up rounding estimates use, so that totals are the same on every machine."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")
ONE = Decimal("1")


def dec(x: float | int | str | Decimal | None) -> Decimal:
    """A Decimal from a float the way it was written (its shortest repr), not from its binary value."""
    if x is None:
        return Decimal(0)
    if isinstance(x, Decimal):
        return x
    return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


def r2(x: Decimal) -> Decimal:
    """To two decimals, half up: rupees and paise, and quantities measured to 0.01."""
    return x.quantize(TWO, rounding=ROUND_HALF_UP)


def r0(x: Decimal) -> Decimal:
    """To the whole rupee, half up."""
    return x.quantize(ONE, rounding=ROUND_HALF_UP)
