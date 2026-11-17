"""Reinforcing bar properties (IS 1786:2008 nominal sizes) and bar-group helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

STEEL_DENSITY_KG_M3 = 7850.0  # IS 1786:2008, Cl. 6.2 (mass per metre based on 0.00785 kg/mm2 per metre)

# Nominal sizes commonly rolled and stocked in India (mm).
STANDARD_DIAMETERS = (8, 10, 12, 16, 20, 25, 28, 32, 36, 40)
MAIN_BAR_DIAMETERS = (12, 16, 20, 25, 32)
STIRRUP_DIAMETERS = (8, 10, 12)


def bar_area(dia_mm: float) -> float:
    """Cross-sectional area of one bar, mm2."""
    return math.pi * dia_mm**2 / 4.0


def bar_unit_weight(dia_mm: float) -> float:
    """Mass per metre of one bar, kg/m (= d^2 / 162.2)."""
    return bar_area(dia_mm) * 1e-6 * STEEL_DENSITY_KG_M3


@dataclass(frozen=True)
class BarGroup:
    """``count`` bars of one diameter on one face, split into layers.

    ``layers`` lists the number of bars per layer, starting with the layer
    nearest the face.
    """

    dia: int
    layers: tuple[int, ...]

    @property
    def count(self) -> int:
        return sum(self.layers)

    @property
    def area(self) -> float:
        return self.count * bar_area(self.dia)

    def label(self) -> str:
        if len(self.layers) == 1:
            return f"{self.count}-T{self.dia}"
        return f"{self.count}-T{self.dia} ({'+'.join(str(n) for n in self.layers)})"
