"""The abstract of cost of an estimate: each item's amount, the sub-total, the additions on it, and the total.

An item's amount is its quantity times its rate, to the paisa. The additions (a cost index over the schedule's base year,
contingencies, work-charged establishment, and so on) are percentages of the sub-total, each worked to the paisa; the total
is rounded to the whole rupee (interpretation 113).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.estimation.domain.money import dec, r0, r2


def amount(quantity: Decimal | float, rate: Decimal | float) -> Decimal:
    return r2(dec(quantity) * dec(rate))


@dataclass(frozen=True)
class Addition:
    label: str
    pct: float


@dataclass(frozen=True)
class Abstract:
    subtotal: Decimal
    additions: list[tuple[str, float, Decimal]]
    total: Decimal
    rounded: Decimal


def abstract(amounts: list[Decimal], additions: list[Addition]) -> Abstract:
    subtotal = sum(amounts, Decimal(0))
    adds = [(a.label, a.pct, r2(subtotal * dec(a.pct) / 100)) for a in additions]
    total = subtotal + sum((x for _, _, x in adds), Decimal(0))
    return Abstract(subtotal, adds, total, r0(total))


# a design's quantities (as its result reports them) and the units an item may take them in
DESIGN_QUANTITIES: dict[str, tuple[str, str]] = {
    "concrete_m3": ("Concrete", "m3"),
    "formwork_m2": ("Formwork", "m2"),
    "steel_kg": ("Reinforcement steel", "kg"),
}
UNIT_FACTORS: dict[tuple[str, str], Decimal] = {
    ("m3", "m3"): Decimal(1), ("m2", "m2"): Decimal(1), ("kg", "kg"): Decimal(1),
    ("kg", "t"): Decimal("0.001"), ("kg", "q"): Decimal("0.01"),
}
# the spellings schedules of rates use, to the units above
UNIT_NAMES: dict[str, str] = {
    "m3": "m3", "cum": "m3", "cumt": "m3", "cubm": "m3", "m³": "m3", "cubicmetre": "m3", "cubicmeter": "m3",
    "m2": "m2", "sqm": "m2", "sqmt": "m2", "m²": "m2", "squaremetre": "m2", "squaremeter": "m2",
    "kg": "kg", "kgs": "kg", "kilogram": "kg",
    "t": "t", "mt": "t", "tonne": "t", "tonnes": "t", "ton": "t", "tons": "t",
    "q": "q", "qtl": "q", "quintal": "q", "quintals": "q",
}


def canonical_unit(unit: str) -> str:
    """A unit as the factors know it: lower case, without spaces, dots or hyphens ('cu. m', 'Cum', 'm3' all to m3)."""
    key = "".join(ch for ch in unit.strip().lower() if ch not in " .-_")
    return UNIT_NAMES.get(key, key)


def unit_factor(design_unit: str, item_unit: str) -> Decimal | None:
    """The factor from a design's unit to an item's, or None where they do not convert."""
    return UNIT_FACTORS.get((canonical_unit(design_unit), canonical_unit(item_unit)))
