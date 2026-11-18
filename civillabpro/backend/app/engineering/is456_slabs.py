"""IS 456:2000 rules for solid slabs: Tables 12, 13, 26 and 27, Annex D, Cl. 24, 26.3.3, 26.5.2, 40.2.

Sources and status (see docs/CODE_REGISTER.md):

* Table 27 is generated from the Rankine-Grashoff expressions it is based on,
  alpha_x = r^4 / (8 (1 + r^4)) and alpha_y = r^2 / (8 (1 + r^4)), rounded to three decimals at the
  tabulated ratios; a test checks the generated values against the printed ones for r up to 2.
* Table 26 is transcribed. Rows confirmed against published reproductions: case 1 (both rows),
  case 2 (negative), cases 5 and 6 (positive, in part), case 7 (positive), case 9. The rest are
  listed to cross-check against the printed code.
* Tables 12 and 13, the slab shear factor k and the Annex D detailing rules are the values of the
  2000 text as commonly published; the code register records which were corroborated.

Pure Python, no framework imports.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass

# ----------------------------------------------------------------------------------- Tables 12 and 13

# Table 12: bending moment coefficient (dead load, imposed load) for continuous beams and slabs.
# Multiplied by the design load per unit length and the square of the effective span. Cl. 22.5.1:
# three or more spans differing by not more than 15 percent of the longest, uniform loads.
TABLE_12 = {
    "end_span_middle": (1 / 12, 1 / 10),
    "support_next_to_end": (1 / 10, 1 / 9),  # hogging
    "interior_span_middle": (1 / 16, 1 / 12),
    "interior_support": (1 / 12, 1 / 9),  # hogging
}
# Table 13: shear force coefficient (dead load, imposed load), multiplied by the design load per unit
# length and the effective span.
TABLE_13 = {
    "end_support": (0.40, 0.45),
    "next_to_end_outer": (0.60, 0.60),
    "next_to_end_inner": (0.55, 0.60),
    "interior_support": (0.50, 0.60),
}

# -------------------------------------------------------------------------------------- Table 26

RATIOS_26 = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0)


@dataclass(frozen=True)
class Case26:
    number: int
    name: str
    neg_x: tuple[float, ...] | None  # short span, negative moment at continuous (long) edges
    pos_x: tuple[float, ...]  # short span, positive moment at mid-span
    neg_y: float | None  # long span, negative moment at continuous (short) edges
    pos_y: float  # long span, positive moment at mid-span


TABLE_26: dict[int, Case26] = {
    1: Case26(1, "Interior panel", (0.032, 0.037, 0.043, 0.047, 0.051, 0.053, 0.060, 0.065),
              (0.024, 0.028, 0.032, 0.036, 0.039, 0.041, 0.045, 0.049), 0.032, 0.024),
    2: Case26(2, "One short edge discontinuous", (0.037, 0.043, 0.048, 0.051, 0.055, 0.057, 0.064, 0.068),
              (0.028, 0.032, 0.036, 0.039, 0.041, 0.044, 0.048, 0.052), 0.037, 0.028),
    3: Case26(3, "One long edge discontinuous", (0.037, 0.044, 0.052, 0.057, 0.063, 0.067, 0.077, 0.085),
              (0.028, 0.033, 0.039, 0.044, 0.047, 0.051, 0.059, 0.065), 0.037, 0.028),
    4: Case26(4, "Two adjacent edges discontinuous", (0.047, 0.053, 0.060, 0.065, 0.071, 0.075, 0.084, 0.091),
              (0.035, 0.040, 0.045, 0.049, 0.053, 0.056, 0.063, 0.069), 0.047, 0.035),
    5: Case26(5, "Two short edges discontinuous", (0.045, 0.049, 0.052, 0.056, 0.059, 0.060, 0.065, 0.069),
              (0.035, 0.037, 0.040, 0.043, 0.044, 0.045, 0.049, 0.052), None, 0.035),
    6: Case26(6, "Two long edges discontinuous", None,
              (0.035, 0.043, 0.051, 0.057, 0.063, 0.068, 0.080, 0.088), 0.045, 0.035),
    7: Case26(7, "Three edges discontinuous (one long edge continuous)", (0.057, 0.064, 0.071, 0.076, 0.080, 0.084, 0.091, 0.097),
              (0.043, 0.048, 0.053, 0.057, 0.060, 0.064, 0.069, 0.073), None, 0.043),
    8: Case26(8, "Three edges discontinuous (one short edge continuous)", None,
              (0.043, 0.051, 0.059, 0.065, 0.071, 0.076, 0.087, 0.096), 0.057, 0.043),
    9: Case26(9, "Four edges discontinuous", None,
              (0.056, 0.064, 0.072, 0.079, 0.085, 0.089, 0.100, 0.107), None, 0.056),
}


def case_26(long_discontinuous: int, short_discontinuous: int) -> int:
    """Table 26 case from the number of discontinuous long edges and short edges (0, 1 or 2 each).

    Long edges have the length of the long span; they support the short span.
    """
    table = {
        (0, 0): 1, (0, 1): 2, (1, 0): 3, (1, 1): 4, (0, 2): 5, (2, 0): 6,
        (1, 2): 7,  # three discontinuous; the continuous one is a long edge
        (2, 1): 8,  # three discontinuous; the continuous one is a short edge
        (2, 2): 9,
    }
    return table[(long_discontinuous, short_discontinuous)]


def interpolate(xs: tuple[float, ...], ys: tuple[float, ...], x: float) -> float:
    """Linear interpolation inside the table; the end values outside it."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x) - 1
    f = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + f * (ys[i + 1] - ys[i])


@dataclass(frozen=True)
class Coefficients:
    neg_x: float | None
    pos_x: float
    neg_y: float | None
    pos_y: float


def coefficients_26(case: int, ratio: float) -> Coefficients:
    c = TABLE_26[case]
    return Coefficients(
        interpolate(RATIOS_26, c.neg_x, ratio) if c.neg_x else None,
        interpolate(RATIOS_26, c.pos_x, ratio),
        c.neg_y,
        c.pos_y,
    )


# -------------------------------------------------------------------------------------- Table 27

RATIOS_27 = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0)


def rankine_grashoff(ratio: float) -> tuple[float, float]:
    """(alpha_x, alpha_y) of a simply supported panel whose corners may lift, unrounded."""
    r4 = ratio**4
    return r4 / (8.0 * (1.0 + r4)), ratio * ratio / (8.0 * (1.0 + r4))


TABLE_27_X = tuple(round(rankine_grashoff(r)[0], 3) for r in RATIOS_27)
TABLE_27_Y = tuple(round(rankine_grashoff(r)[1], 3) for r in RATIOS_27)


def coefficients_27(ratio: float) -> Coefficients:
    return Coefficients(None, interpolate(RATIOS_27, TABLE_27_X, ratio), None, interpolate(RATIOS_27, TABLE_27_Y, ratio))


# --------------------------------------------------------------------------------- slab rules

_K_DEPTHS = (150.0, 175.0, 200.0, 225.0, 250.0, 275.0, 300.0)
_K_VALUES = (1.30, 1.25, 1.20, 1.15, 1.10, 1.05, 1.00)


def shear_factor_k(overall_depth: float) -> float:
    """Cl. 40.2.1.1: enhancement of tau_c for solid slabs, by overall depth; linear between the tabulated depths."""
    return interpolate(_K_DEPTHS, _K_VALUES, overall_depth)


def min_steel(b: float, D: float, fy: float) -> float:
    """Cl. 26.5.2.1: 0.15 percent of the gross section for mild steel, 0.12 percent for high strength deformed bars."""
    return (0.0015 if fy <= 250 else 0.0012) * b * D


def max_bar_diameter(D: float) -> float:
    """Cl. 26.5.2.2: not more than one-eighth of the slab thickness."""
    return D / 8.0


def max_spacing_main(d: float) -> float:
    """Cl. 26.3.3(b)(1): three times the effective depth or 300 mm, whichever is smaller."""
    return min(3.0 * d, 300.0)


def max_spacing_distribution(d: float) -> float:
    """Cl. 26.3.3(b)(2): five times the effective depth or 450 mm, whichever is smaller."""
    return min(5.0 * d, 450.0)


def two_way_span_depth_note2(fy: float, simply_supported: bool) -> float:
    """Cl. 24.1, note 2: span to overall depth for two-way slabs of short span up to 3.5 m, imposed load up to 3 kN/m2.

    35 simply supported, 40 continuous, for mild steel; times 0.8 for Fe 415. Not given for higher grades.
    """
    base = 35.0 if simply_supported else 40.0
    return base * (0.8 if fy > 250 else 1.0)


# Annex D detailing
MIDDLE_STRIP = 0.75  # D-1.2: middle strip three-quarters of the width
EDGE_STRIP = 0.125  # each edge strip one-eighth
TORSION_EXTENT = 0.2  # D-1.8: torsion steel extends one-fifth of the shorter span from the edges
TORSION_FRACTION = 0.75  # D-1.8: each of four layers, three-quarters of the steel for the maximum mid-span moment
TOP_EXTENT_FULL = 0.3  # D-1.5: at least half the top steel extends 0.3 l (all of it here)
DISCONTINUOUS_TOP_FRACTION = 0.5  # D-1.6: half the mid-span steel at a discontinuous edge ...
DISCONTINUOUS_TOP_EXTENT = 0.1  # ... extending 0.1 l into the span
