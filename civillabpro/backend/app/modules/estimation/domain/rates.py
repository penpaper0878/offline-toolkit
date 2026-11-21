"""Analysis of rates, in the form the CPWD analysis of rates uses.

The cost of materials, labour, plant (tools and plant, carriage) and sundries for an output quantity of the item; water
charges as a percentage of that cost; then the contractor's overheads and profit as a percentage of the cost with water;
the rate is the total over the output quantity, to the paisa (interpretation 112). The percentages are entered: CPWD's
analysis takes 1 percent for water and 15 percent for overheads and profit, which are the defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.modules.estimation.domain.money import dec, r2

Kind = Literal["material", "labour", "plant", "sundries"]
KINDS: tuple[Kind, ...] = ("material", "labour", "plant", "sundries")


@dataclass(frozen=True)
class AnalysisLine:
    kind: Kind
    description: str
    unit: str
    quantity: float
    rate: float

    @property
    def amount(self) -> Decimal:
        return r2(dec(self.quantity) * dec(self.rate))


@dataclass(frozen=True)
class Analysis:
    by_kind: dict[str, Decimal]
    cost: Decimal
    water: Decimal
    overheads_profit: Decimal
    total: Decimal
    output_qty: Decimal
    rate: Decimal
    lines: list[Decimal] = field(default_factory=list)  # each line's amount


def analyse(lines: list[AnalysisLine], output_qty: float, water_pct: float = 1.0, overheads_profit_pct: float = 15.0) -> Analysis:
    """The rate per unit of an item from its constituents (see the module docstring)."""
    if output_qty <= 0:
        raise ValueError("The output quantity must be more than nil.")
    amounts = [ln.amount for ln in lines]
    by_kind = {k: sum((a for ln, a in zip(lines, amounts, strict=True) if ln.kind == k), Decimal(0)) for k in KINDS}
    cost = sum(amounts, Decimal(0))
    water = r2(cost * dec(water_pct) / 100)
    op = r2((cost + water) * dec(overheads_profit_pct) / 100)
    total = cost + water + op
    out = dec(output_qty)
    return Analysis(by_kind, cost, water, op, total, out, r2(total / out), amounts)
