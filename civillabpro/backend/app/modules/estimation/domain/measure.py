"""Measurement of quantities for a detailed estimate.

Each line is a count and up to three dimensions in metres: the quantity is their product, a dimension left blank not
entering it (a length alone for running metres, two for areas, three for volumes). Deductions (openings, overlaps) are
lines marked to deduct. IS 1200's general rules measure dimensions to 0.01 m, areas to 0.01 m2 and volumes to 0.01 m3:
each line is worked to 0.01 and the item is the sum of its lines (interpretation 111).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.modules.estimation.domain.money import dec, r2


@dataclass(frozen=True)
class MeasureLine:
    description: str = ""
    nos: float = 1.0
    length: float | None = None
    breadth: float | None = None
    depth: float | None = None
    deduct: bool = False


def line_quantity(line: MeasureLine) -> Decimal:
    """nos x length x breadth x depth, the blank dimensions left out, to 0.01; negative for a deduction."""
    q = dec(line.nos)
    for dim in (line.length, line.breadth, line.depth):
        if dim is not None:
            q *= dec(dim)
    q = r2(q)
    return -q if line.deduct else q


def item_quantity(lines: list[MeasureLine]) -> Decimal:
    """The sum of the lines' quantities."""
    return sum((line_quantity(ln) for ln in lines), Decimal(0))
