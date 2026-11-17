"""Rectangular reinforced concrete section under axial load and uniaxial bending (IS 456:2000, Cl. 39.1).

Strain compatibility with the assumptions of Cl. 38.1 (a) to (e) and Cl. 39.1:

* plane sections remain plane;
* with the neutral axis within the section, the strain at the highly compressed edge is 0.0035;
* with the neutral axis outside the section (whole section in compression), the strain at the
  highly compressed edge is 0.0035 minus 0.75 times the strain at the least compressed edge.
  This is the same as a strain profile that pivots about the point 3D/7 from the highly
  compressed edge, where the strain is 0.002;
* concrete follows the design curve of Fig. 21 (parabola to 0.002, then constant to 0.0035,
  at 0.67 fck / 1.5) and carries no tension;
* steel follows Fig. 23 (``is456.steel_design_stress``), in tension and in compression.

The concrete block is integrated in closed form. A bar in the compressed zone displaces the
concrete it occupies, so the concrete stress at its strain is deducted from the steel stress.

Units: N, mm. Distances are measured from the compression edge for the direction of bending.
Pure Python, no framework imports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.engineering import is456

FCD_FACTOR = 0.67 / 1.5  # Fig. 21: design strength 0.67 fck / gamma_m with gamma_m = 1.5
EPS_0 = 0.002  # end of the parabola, and the strain at the pivot when the whole section is in compression
EPS_CU = 0.0035  # ultimate compressive strain


@dataclass(frozen=True)
class Layer:
    """A row of bars parallel to the axis of bending."""

    y: float  # distance of the row from the compression edge, mm
    area: float  # total bar area in the row, mm2


@dataclass(frozen=True)
class SectionState:
    xu: float  # neutral-axis depth, mm (math.inf: uniform strain 0.002)
    p: float  # axial force, N, compression positive
    m: float  # moment about the mid-depth, N mm


def concrete_stress(strain: float, fck: float) -> float:
    """Fig. 21 design curve, N/mm2. No tension."""
    if strain <= 0.0:
        return 0.0
    fcd = FCD_FACTOR * fck
    if strain >= EPS_0:
        return fcd
    r = strain / EPS_0
    return fcd * (2.0 * r - r * r)


def _f0(e: float, fcd: float) -> float:
    """Integral of the stress from 0 to strain e (per unit strain)."""
    if e <= 0.0:
        return 0.0
    if e <= EPS_0:
        return fcd * (e * e / EPS_0 - e**3 / (3.0 * EPS_0**2))
    return fcd * (2.0 * EPS_0 / 3.0 + (e - EPS_0))


def _f1(e: float, fcd: float) -> float:
    """Integral of stress times strain from 0 to strain e."""
    if e <= 0.0:
        return 0.0
    if e <= EPS_0:
        return fcd * (2.0 * e**3 / (3.0 * EPS_0) - e**4 / (4.0 * EPS_0**2))
    return fcd * (5.0 * EPS_0**2 / 12.0 + (e * e - EPS_0 * EPS_0) / 2.0)


def strain_profile(xu: float, depth: float) -> tuple[float, float]:
    """(strain at the compression edge, curvature) for a neutral-axis depth ``xu``. Cl. 39.1."""
    if math.isinf(xu):
        return EPS_0, 0.0
    if xu <= depth:
        return EPS_CU, EPS_CU / xu
    kappa = EPS_0 / (xu - 3.0 * depth / 7.0)
    return EPS_0 * xu / (xu - 3.0 * depth / 7.0), kappa


def strain_at(y: float, xu: float, depth: float) -> float:
    top, kappa = strain_profile(xu, depth)
    return top - kappa * y


def concrete_resultant(width: float, depth: float, xu: float, fck: float) -> tuple[float, float]:
    """Compressive force in the concrete (N) and its distance from the compression edge (mm)."""
    fcd = FCD_FACTOR * fck
    top, kappa = strain_profile(xu, depth)
    if kappa == 0.0:
        return fcd * width * depth, depth / 2.0
    low = max(top - kappa * depth, 0.0)  # strain at the lower end of the compressed zone
    df0 = _f0(top, fcd) - _f0(low, fcd)
    force = width / kappa * df0
    if force <= 0.0:
        return 0.0, 0.0
    moment_about_edge = width / (kappa * kappa) * (top * df0 - (_f1(top, fcd) - _f1(low, fcd)))
    return force, moment_about_edge / force


def bar_stress(strain: float, fck: float, fy: float) -> float:
    """Net stress in a bar, N/mm2, compression positive: steel stress less the concrete it displaces."""
    steel = math.copysign(is456.steel_design_stress(strain, fy), strain)
    return steel - concrete_stress(strain, fck) if strain > 0.0 else steel


def state(width: float, depth: float, layers: list[Layer], fck: float, fy: float, xu: float) -> SectionState:
    """Axial force and moment about mid-depth for a neutral-axis depth."""
    force, yc = concrete_resultant(width, depth, xu, fck)
    p = force
    m = force * (depth / 2.0 - yc)
    for layer in layers:
        f = layer.area * bar_stress(strain_at(layer.y, xu, depth), fck, fy)
        p += f
        m += f * (depth / 2.0 - layer.y)
    return SectionState(xu, p, m)


def squash_load(width: float, depth: float, layers: list[Layer], fck: float, fy: float) -> float:
    """Axial capacity by strain compatibility at uniform strain 0.002 (no bending), N."""
    return state(width, depth, layers, fck, fy, math.inf).p


_XU_MIN_RATIO = 1e-6
_XU_MAX_RATIO = 1e4  # beyond this the strain is uniform to within the precision that matters


def at_axial_load(width: float, depth: float, layers: list[Layer], fck: float, fy: float, p: float) -> SectionState | None:
    """Moment of resistance at a given axial load (N), found by bisection on the neutral-axis depth.

    Returns None when the load exceeds the squash load or lies below the tension capacity.
    """
    lo, hi = _XU_MIN_RATIO * depth, depth
    s_lo = state(width, depth, layers, fck, fy, lo)
    if p < s_lo.p:
        return None
    s_hi = state(width, depth, layers, fck, fy, hi)
    while s_hi.p < p:
        if hi >= _XU_MAX_RATIO * depth:
            p0 = squash_load(width, depth, layers, fck, fy)
            if p > p0 * (1.0 + 1e-12):
                return None
            return state(width, depth, layers, fck, fy, math.inf)
        lo, hi = hi, min(hi * 2.0, _XU_MAX_RATIO * depth)
        s_hi = state(width, depth, layers, fck, fy, hi)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        s_mid = state(width, depth, layers, fck, fy, mid)
        if s_mid.p < p:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-10 * depth:
            break
    return state(width, depth, layers, fck, fy, 0.5 * (lo + hi))


def balanced(width: float, depth: float, layers: list[Layer], fck: float, fy: float) -> SectionState:
    """Balanced failure: concrete at 0.0035 as the extreme tension row reaches the strain of Cl. 38.1(f).

    The neutral-axis depth is the limiting value xu,max of Cl. 38.1(f), measured to the extreme
    tension row. Its axial force is Pb of Cl. 39.7.1.1.
    """
    d = max(layer.y for layer in layers)
    return state(width, depth, layers, fck, fy, is456.xu_max_ratio(fy) * d)


def interaction_curve(width: float, depth: float, layers: list[Layer], fck: float, fy: float, points: int = 36) -> list[tuple[float, float]]:
    """(M, P) pairs from pure bending to the squash load, compression only, sorted by P. N mm and N."""
    out: list[tuple[float, float]] = []
    pure = at_axial_load(width, depth, layers, fck, fy, 0.0)
    if pure is not None:
        out.append((pure.m, 0.0))
    for i in range(points):
        # neutral-axis depths spread from shallow to deep, then the uniform-strain end
        xu = depth * 0.04 * (400.0 ** (i / (points - 1)))
        s = state(width, depth, layers, fck, fy, xu)
        if s.p > 0.0:
            out.append((s.m, s.p))
    end = state(width, depth, layers, fck, fy, math.inf)  # zero moment only when the bars are symmetric
    out.append((end.m, end.p))
    out.sort(key=lambda mp: mp[1])
    return out
