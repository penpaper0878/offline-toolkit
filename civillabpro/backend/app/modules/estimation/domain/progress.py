"""Progress of the work against an estimate, from the measurement book.

Each entry of the book measures work done on one item of the estimate, by the lines of `measure` (interpretation 111). For an
item, the quantity measured to date is the sum of its entries; the quantity checked, the sum of the entries checked by a
second person. Against the estimated quantity that gives the balance still to do and, where the work has gone past the
estimate, the excess, valued at the estimate's rate (interpretation 117). Nothing here judges whether an excess is allowed:
departments set their own deviation limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.modules.estimation.domain.abstract import amount
from app.modules.estimation.domain.money import dec

ZERO = Decimal(0)


@dataclass(frozen=True)
class ItemProgress:
    estimated: Decimal
    measured: Decimal  # to date, all entries
    checked: Decimal  # to date, the entries checked
    balance: Decimal  # estimated - measured, not below zero
    excess: Decimal  # measured - estimated, not below zero
    percent: Decimal | None  # measured / estimated x 100 to 0.1; None for an item estimated at nothing
    value_measured: Decimal  # measured x rate, to the paisa
    value_checked: Decimal
    value_excess: Decimal


def item_progress(estimated: Decimal | float, entries: list[tuple[Decimal, bool]], rate: Decimal | float) -> ItemProgress:
    """An item's progress from its entries, each (quantity, checked)."""
    est = dec(estimated)
    measured = sum((q for q, _ in entries), ZERO)
    checked = sum((q for q, ok in entries if ok), ZERO)
    balance = max(est - measured, ZERO)
    excess = max(measured - est, ZERO)
    percent = (measured * 100 / est).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if est > 0 else None
    return ItemProgress(est, measured, checked, balance, excess, percent,
                        amount(measured, rate), amount(checked, rate), amount(excess, rate))
