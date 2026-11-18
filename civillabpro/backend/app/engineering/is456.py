"""IS 456:2000 limit-state rules used by the structural engines.

Units: N, mm, N/mm2 throughout. Every function names the clause it implements.
Tables are transcribed from the code; tests/unit/test_is456.py cross-checks
Table 19 against the SP 16 closed form and the steel curve against SP 16 Table F.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

CODE = "IS 456:2000"
ES = 200_000.0  # Cl. 5.6.3, modulus of elasticity of steel

CONCRETE_GRADES = (20, 25, 30, 35, 40, 45, 50, 55)  # Table 2; design rules hold up to M55 (Cl. 6.1, note)
STEEL_GRADES = (250, 415, 500, 550)  # IS 432 mild steel; IS 1786 Fe 415/500/550 (D and S variants design alike)
EXPOSURES = ("mild", "moderate", "severe", "very_severe", "extreme")

# ----------------------------------------------------------------------------- materials


def xu_max_ratio(fy: float) -> float:
    """Cl. 38.1(f): limiting neutral-axis depth ratio xu,max/d.

    The clause requires the tension steel strain at failure to reach
    0.87 fy/Es + 0.002 while the concrete is at 0.0035, which gives
    xu,max/d = 0.0035 / (0.0055 + 0.87 fy/Es). The note to the clause prints this
    rounded (0.53, 0.48, 0.46 for Fe 250, 415, 500). The unrounded ratio is used
    here: it is the condition itself, it holds for every grade, and it
    reproduces the limiting-moment factors of SP 16, Table E (0.149, 0.138, 0.133).
    """
    return 0.0035 / (0.0055 + 0.87 * fy / ES)


# Fig. 23A (cold-worked deformed bars): design stress as a fraction of 0.87 fy
# against the inelastic strain at that stress. Total strain = stress/Es + inelastic.
_HYSD_CURVE = ((0.80, 0.0), (0.85, 0.0001), (0.90, 0.0003), (0.95, 0.0007), (0.975, 0.0010), (1.0, 0.0020))


def steel_design_stress(strain: float, fy: float) -> float:
    """Design stress in reinforcement at a given strain (Cl. 38.1(e), Fig. 23).

    Fe 250 follows Fig. 23B (elastic, then a plateau at 0.87 fy). Higher grades
    follow Fig. 23A, interpolating linearly between the plotted points.
    """
    strain = abs(strain)
    fyd = 0.87 * fy
    if fy <= 250:
        return min(ES * strain, fyd)
    pts = [(k * fyd / ES + inel, k * fyd) for k, inel in _HYSD_CURVE]
    if strain <= pts[0][0]:
        return ES * strain
    for (e0, s0), (e1, s1) in zip(pts, pts[1:], strict=False):
        if strain <= e1:
            return s0 + (s1 - s0) * (strain - e0) / (e1 - e0)
    return fyd


# ------------------------------------------------------------------------------- flexure


@dataclass(frozen=True)
class FlexureDesign:
    mu: float  # design moment, N mm
    mu_lim: float  # limiting moment of the singly reinforced section, N mm
    xu_max: float  # mm
    doubly: bool
    ast_req: float  # mm2
    asc_req: float  # mm2
    xu: float  # neutral-axis depth with the required steel, mm
    ast_lim: float = 0.0  # tension steel balancing the concrete at xu,max (doubly only)
    ast2: float = 0.0  # tension steel balancing the compression steel (doubly only)
    eps_sc: float = 0.0
    fsc: float = 0.0
    fcc: float = 0.0
    na_in_flange: bool | None = None  # flanged sections only: the neutral axis lies within the flange


def limiting_moment(fck: float, fy: float, b: float, d: float) -> float:
    """Annex G, G-1.1(c): Mu,lim = 0.36 fck b xu,max (d - 0.42 xu,max)."""
    xu_max = xu_max_ratio(fy) * d
    return 0.36 * fck * b * xu_max * (d - 0.42 * xu_max)


def design_rectangular(mu: float, fck: float, fy: float, b: float, d: float, d_c: float) -> FlexureDesign:
    """Required steel for a rectangular section under a factored moment (Annex G).

    Singly reinforced (G-1.1(b)): Mu = 0.87 fy Ast d (1 - Ast fy / (b d fck)),
    solved for Ast in the form printed in SP 16 (the factor 4.6 is 4/0.87 rounded
    up, which is on the safe side).
    Doubly reinforced (G-1.2): Mu - Mu,lim = Asc (fsc - fcc)(d - d'), with the
    concrete displaced by the compression bars deducted (fcc = 0.446 fck, the
    peak of the stress block in Fig. 21). The code's own expression leaves fcc
    out; deducting it follows SP 16, Cl. 2.3.2 and is on the safe side.
    """
    xu_max = xu_max_ratio(fy) * d
    mu_lim = limiting_moment(fck, fy, b, d)
    if mu <= mu_lim:
        r = 4.6 * mu / (fck * b * d * d)
        ast = 0.5 * fck / fy * (1.0 - math.sqrt(max(0.0, 1.0 - r))) * b * d
        xu = 0.87 * fy * ast / (0.36 * fck * b)
        return FlexureDesign(mu, mu_lim, xu_max, False, ast, 0.0, xu)
    ast_lim = 0.36 * fck * b * xu_max / (0.87 * fy)
    eps_sc = 0.0035 * (1.0 - d_c / xu_max)
    fsc = steel_design_stress(eps_sc, fy) if eps_sc > 0 else 0.0
    fcc = 0.446 * fck
    if fsc - fcc <= 0 or d - d_c <= 0:
        return FlexureDesign(mu, mu_lim, xu_max, True, math.inf, math.inf, xu_max, ast_lim, math.inf, eps_sc, fsc, fcc)
    asc = (mu - mu_lim) / ((fsc - fcc) * (d - d_c))
    ast2 = asc * (fsc - fcc) / (0.87 * fy)
    return FlexureDesign(mu, mu_lim, xu_max, True, ast_lim + ast2, asc, xu_max, ast_lim, ast2, eps_sc, fsc, fcc)


@dataclass(frozen=True)
class MomentCapacity:
    mu: float  # N mm
    xu: float  # mm
    limited: bool  # True when the steel provided would push xu beyond xu,max


def moment_capacity(
    fck: float, fy: float, b: float, d: float, ast: float, asc: float, d_c: float
) -> MomentCapacity:
    """Moment of resistance of the section as detailed (Cl. 38.1).

    Solves horizontal equilibrium for the neutral axis with the compression
    steel stress taken from its strain. Tension steel is at 0.87 fy, which the
    code guarantees while xu <= xu,max (Cl. 38.1(f)). If the steel provided needs
    a deeper neutral axis than xu,max, the capacity is taken at xu,max and the
    result is marked ``limited``.
    """
    return _capacity(lambda xu: (0.36 * fck * b * xu, 0.36 * fck * b * xu * (d - 0.42 * xu)), fck, fy, d, ast, asc, d_c)


def _capacity(concrete: Callable[[float], tuple[float, float]], fck: float, fy: float, d: float, ast: float, asc: float,
              d_c: float) -> MomentCapacity:
    """Equilibrium for any compression zone: ``concrete(xu)`` gives its force (N) and moment about the tension steel (N mm)."""
    xu_max = xu_max_ratio(fy) * d
    fcc = 0.446 * fck
    tension = 0.87 * fy * ast

    def comp_steel(xu: float) -> float:
        if asc <= 0 or xu <= d_c:
            return 0.0
        return asc * max(0.0, steel_design_stress(0.0035 * (xu - d_c) / xu, fy) - fcc)

    def unbalance(xu: float) -> float:
        return concrete(xu)[0] + comp_steel(xu) - tension

    if unbalance(xu_max) < -1e-9 * max(tension, 1.0):
        xu, limited = xu_max, True
    else:
        lo, hi = 0.0, xu_max
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if unbalance(mid) < 0:
                lo = mid
            else:
                hi = mid
        xu, limited = 0.5 * (lo + hi), False
    mu = concrete(xu)[1] + comp_steel(xu) * (d - d_c)
    return MomentCapacity(mu, xu, limited)


# ------------------------------------------------------------------------ flanged sections

FlangeKind = Literal["T", "L"]


def effective_flange_width(kind: FlangeKind, l0: float, bw: float, df: float, b_actual: float, isolated: bool) -> float:
    """Cl. 23.1.2: effective width of the flange, not more than the width actually available.

    (a) T-beams l0/6 + bw + 6 Df; (b) L-beams l0/12 + bw + 3 Df; (c) isolated T-beams l0/(l0/b + 4) + bw;
    (d) isolated L-beams 0.5 l0/(l0/b + 4) + bw. l0 is the distance between points of zero moment, b the
    actual width of the flange.
    """
    if isolated:
        over = l0 / (l0 / b_actual + 4.0)
        bf = (over if kind == "T" else 0.5 * over) + bw
    else:
        bf = (l0 / 6.0 + 6.0 * df if kind == "T" else l0 / 12.0 + 3.0 * df) + bw
    return min(bf, b_actual)


def flange_depth_yf(xu: float, df: float) -> float:
    """Annex G-2.2.2: depth of the flange taken at 0.45 fck, yf = 0.15 xu + 0.65 Df, not more than Df.

    It equals Df once Df <= 3/7 xu, that is when the whole flange lies in the uniform part of the stress
    block; the code's own condition Df/d <= 0.2 is that statement at xu = xu,max.
    """
    return min(0.15 * xu + 0.65 * df, df)


def flanged_concrete(fck: float, bf: float, bw: float, df: float, d: float, xu: float) -> tuple[float, float]:
    """Compression force (N) and its moment about the tension steel (N mm) for a flanged section (Annex G-2).

    Neutral axis within the flange: a rectangle of width bf (G-2.1). Below it: the web as a rectangle of
    width bw plus the outstands (bf - bw) at 0.45 fck over yf (G-2.2.1, G-2.2.2, with xu for xu,max as G-2.2
    allows).
    """
    if xu <= df:
        c = 0.36 * fck * bf * xu
        return c, c * (d - 0.42 * xu)
    yf = flange_depth_yf(xu, df)
    web, flange = 0.36 * fck * bw * xu, 0.45 * fck * (bf - bw) * yf
    return web + flange, web * (d - 0.42 * xu) + flange * (d - yf / 2.0)


def limiting_moment_flanged(fck: float, fy: float, bf: float, bw: float, df: float, d: float) -> float:
    """Annex G-2.2.1 and G-2.2.2: the moment of resistance at xu = xu,max."""
    return flanged_concrete(fck, bf, bw, df, d, xu_max_ratio(fy) * d)[1]


def design_flanged(mu: float, fck: float, fy: float, bf: float, bw: float, df: float, d: float, d_c: float) -> FlexureDesign:
    """Required steel for a flanged section with the flange in compression (Annex G-2).

    The neutral axis lies in the flange when Mu <= 0.36 fck bf Df (d - 0.42 Df) (or when Df >= xu,max):
    the section is then a rectangle bf x d (G-1.1(b)). Otherwise xu is found from Mu by bisection on the
    G-2.2 expressions (they rise with xu) and the steel balances the compression. Above the flanged limiting
    moment the excess is carried by compression steel as in G-1.2.
    """
    xu_max = xu_max_ratio(fy) * d
    mu_lim = limiting_moment_flanged(fck, fy, bf, bw, df, d)
    mu_f = 0.36 * fck * bf * df * (d - 0.42 * df)
    if df >= xu_max or mu <= mu_f:
        r = design_rectangular(mu, fck, fy, bf, d, d_c)
        if not r.doubly:
            return FlexureDesign(mu, mu_lim, xu_max, False, r.ast_req, 0.0, r.xu, na_in_flange=r.xu <= df + 1e-9)
        return FlexureDesign(**{**r.__dict__, "na_in_flange": r.xu <= df + 1e-9})  # Df >= xu,max: a rectangle bf wide
    if mu <= mu_lim:
        lo, hi = df, xu_max
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if flanged_concrete(fck, bf, bw, df, d, mid)[1] < mu:
                lo = mid
            else:
                hi = mid
        xu = hi
        ast = flanged_concrete(fck, bf, bw, df, d, xu)[0] / (0.87 * fy)
        return FlexureDesign(mu, mu_lim, xu_max, False, ast, 0.0, xu, na_in_flange=False)
    ast_lim = flanged_concrete(fck, bf, bw, df, d, xu_max)[0] / (0.87 * fy)
    eps_sc = 0.0035 * (1.0 - d_c / xu_max)
    fsc = steel_design_stress(eps_sc, fy) if eps_sc > 0 else 0.0
    fcc = 0.446 * fck
    if fsc - fcc <= 0 or d - d_c <= 0:
        return FlexureDesign(mu, mu_lim, xu_max, True, math.inf, math.inf, xu_max, ast_lim, math.inf, eps_sc, fsc, fcc, False)
    asc = (mu - mu_lim) / ((fsc - fcc) * (d - d_c))
    ast2 = asc * (fsc - fcc) / (0.87 * fy)
    return FlexureDesign(mu, mu_lim, xu_max, True, ast_lim + ast2, asc, xu_max, ast_lim, ast2, eps_sc, fsc, fcc, False)


def moment_capacity_flanged(fck: float, fy: float, bf: float, bw: float, df: float, d: float, ast: float, asc: float,
                            d_c: float) -> MomentCapacity:
    """Moment of resistance of a flanged section as detailed: equilibrium on the Annex G-2 compression zone."""
    return _capacity(lambda xu: flanged_concrete(fck, bf, bw, df, d, xu), fck, fy, d, ast, asc, d_c)


def min_tension_steel(b: float, d: float, fy: float) -> float:
    """Cl. 26.5.1.1(a): As / (b d) >= 0.85 / fy."""
    return 0.85 * b * d / fy


def max_steel(b: float, D: float) -> float:
    """Cl. 26.5.1.1(b) and 26.5.1.2: 0.04 b D on either face."""
    return 0.04 * b * D


# --------------------------------------------------------------------------------- shear

_PT = (0.15, 0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50, 2.75, 3.00)
# Table 19: design shear strength of concrete, N/mm2; columns M15 ... M40 and above.
_TAU_C = {
    15: (0.28, 0.35, 0.46, 0.54, 0.60, 0.64, 0.68, 0.71, 0.71, 0.71, 0.71, 0.71, 0.71),
    20: (0.28, 0.36, 0.48, 0.56, 0.62, 0.67, 0.72, 0.75, 0.79, 0.81, 0.82, 0.82, 0.82),
    25: (0.29, 0.36, 0.49, 0.57, 0.64, 0.70, 0.74, 0.78, 0.82, 0.85, 0.88, 0.90, 0.92),
    30: (0.29, 0.37, 0.50, 0.59, 0.66, 0.71, 0.76, 0.80, 0.84, 0.88, 0.91, 0.94, 0.96),
    35: (0.29, 0.37, 0.50, 0.59, 0.67, 0.73, 0.78, 0.82, 0.86, 0.90, 0.93, 0.96, 0.99),
    40: (0.30, 0.38, 0.51, 0.60, 0.68, 0.74, 0.79, 0.84, 0.88, 0.92, 0.95, 0.98, 1.01),
}
# Table 20: maximum shear stress, N/mm2.
_TAU_C_MAX = {15: 2.5, 20: 2.8, 25: 3.1, 30: 3.5, 35: 3.7, 40: 4.0}


def _grade_column(fck: float) -> int:
    """Tables 19 and 20 stop at 'M40 and above'; grades between columns take the lower column."""
    return max(g for g in _TAU_C if g <= min(fck, 40))


def tau_c(fck: float, pt: float) -> float:
    """Table 19: design shear strength for 100 As/(b d) = pt, interpolated linearly in pt.

    Below 0.15 % the first row applies and above 3.0 % the last (the table's own end rows).
    """
    col = _TAU_C[_grade_column(fck)]
    pt = min(max(pt, _PT[0]), _PT[-1])
    for i in range(len(_PT) - 1):
        if pt <= _PT[i + 1]:
            f = (pt - _PT[i]) / (_PT[i + 1] - _PT[i])
            return col[i] + f * (col[i + 1] - col[i])
    return col[-1]


def tau_c_formula(fck: float, pt: float) -> float:
    """SP 16, Cl. 4.1: the closed form Table 19 was generated from. Used for cross-checks only."""
    pt = min(max(pt, 0.15), 3.0)
    beta = max(0.8 * fck / (6.89 * pt), 1.0)
    return 0.85 * math.sqrt(0.8 * fck) * (math.sqrt(1.0 + 5.0 * beta) - 1.0) / (6.0 * beta)


def tau_c_max(fck: float) -> float:
    """Table 20."""
    return _TAU_C_MAX[_grade_column(fck)]


def stirrup_spacing_for_shear(vus: float, fy: float, asv: float, d: float) -> float:
    """Cl. 40.4(a): Vus = 0.87 fy Asv d / sv for vertical stirrups."""
    return 0.87 * fy * asv * d / vus


def stirrup_spacing_minimum_steel(fy: float, asv: float, b: float) -> float:
    """Cl. 26.5.1.6: Asv / (b sv) >= 0.4 / (0.87 fy)."""
    return 0.87 * fy * asv / (0.4 * b)


def shear_fy(fy: float) -> float:
    """Cl. 40.4: fy of shear reinforcement not taken above 415 N/mm2."""
    return min(fy, 415.0)


# ------------------------------------------------------------------------ serviceability

BASIC_SPAN_DEPTH = {"cantilever": 7.0, "simply_supported": 20.0, "continuous": 26.0}  # Cl. 23.2.1(a)


def service_steel_stress(fy: float, ast_req: float, ast_prov: float) -> float:
    """Fig. 4, note: fs = 0.58 fy (area required / area provided)."""
    return 0.58 * fy * ast_req / ast_prov


def tension_modification_factor(fs: float, pt: float) -> float:
    """Fig. 4 as the expression in SP 24: 1 / (0.225 + 0.00322 fs + 0.625 log10 pt), at most 2.0."""
    den = 0.225 + 0.00322 * fs + 0.625 * math.log10(pt)
    if den <= 0.5:
        return 2.0
    return min(2.0, 1.0 / den)


def compression_modification_factor(pc: float) -> float:
    """Fig. 5 as the expression in SP 24: 1 + pc / (3 + pc), at most 1.5."""
    return min(1.5, 1.0 + pc / (3.0 + pc))


def flanged_reduction_factor(bw_over_bf: float) -> float:
    """Fig. 6 (Cl. 23.2.1(e)): 0.8 for bw/bf up to 0.3, rising linearly to 1.0 at bw/bf = 1.0."""
    r = min(max(bw_over_bf, 0.0), 1.0)
    return 0.8 if r <= 0.3 else 0.8 + 0.2 * (r - 0.3) / 0.7


# ------------------------------------------------------------------------------ detailing

_BOND_PLAIN = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}  # Cl. 26.2.1.1, plain bars in tension
_NOMINAL_COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}  # Table 16
_MIN_GRADE_RC = {"mild": 20, "moderate": 25, "severe": 30, "very_severe": 35, "extreme": 40}  # Table 5


def bond_stress(fck: float, fy: float, compression: bool = False) -> float:
    """Cl. 26.2.1.1: design bond stress; +60 % for deformed bars, +25 % for bars in compression."""
    tbd = _BOND_PLAIN[max(g for g in _BOND_PLAIN if g <= min(fck, 40))]
    if fy >= 415:
        tbd *= 1.6
    if compression:
        tbd *= 1.25
    return tbd


def development_length(dia: float, fck: float, fy: float, compression: bool = False) -> float:
    """Cl. 26.2.1: Ld = dia * 0.87 fy / (4 tbd)."""
    return dia * 0.87 * fy / (4.0 * bond_stress(fck, fy, compression))


def nominal_cover(exposure: str) -> float:
    """Table 16: nominal cover to all reinforcement, mm (the table's reductions in its notes are not taken)."""
    return float(_NOMINAL_COVER[exposure])


def min_grade(exposure: str) -> int:
    """Table 5: minimum grade of reinforced concrete."""
    return _MIN_GRADE_RC[exposure]


def max_clear_bar_spacing(fy: float) -> float:
    """Table 15, no redistribution: 300, 180 and 150 mm for Fe 250, 415 and 500.

    The tabulated values equal 75 000 / fy; that relation is used for grades the
    table does not list (Fe 550).
    """
    table = {250: 300.0, 415: 180.0, 500: 150.0}
    return table.get(int(fy), math.floor(75_000.0 / fy))


def min_clear_bar_spacing_horizontal(dia: float, aggregate: float) -> float:
    """Cl. 26.3.2(a): the bar diameter, or 5 mm more than the aggregate size, whichever is greater."""
    return max(dia, aggregate + 5.0)


def min_clear_bar_spacing_vertical(dia: float, aggregate: float) -> float:
    """Cl. 26.3.2(c): 15 mm, two-thirds of the aggregate size or the bar diameter, whichever is greatest."""
    return max(15.0, 2.0 * aggregate / 3.0, dia)
