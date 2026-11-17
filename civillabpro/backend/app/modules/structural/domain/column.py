"""Rectangular reinforced concrete column to IS 456:2000 (limit state method).

Scope of version 1.0: rectangular tied columns under a factored axial load with end moments
about both axes from an external analysis. Covers effective length (Cl. 25.2, Table 28),
slenderness and its limits (Cl. 25.1.2, 25.3), minimum eccentricity applied about one axis
at a time (Cl. 25.4), additional moments of slender columns with the reduction factor k
(Cl. 39.7.1, 39.7.1.1), short columns with only minimum eccentricity (Cl. 39.3), and axial
load with biaxial bending (Cl. 39.6) with uniaxial capacities by strain compatibility
(Cl. 39.1). Selects the bars and ties and details them to Cl. 26.4.2.1 and 26.5.3.

Axes: x and y are the principal axes of the section. M_ux bends about the x axis and acts in
the plane of the depth D; M_uy bends about the y axis, in the plane of the width b.

Worked example (the defaults): 300 x 450, unsupported length 3.6 m, held in position at both
ends and not restrained against rotation (Table 28, 1.00 l) about both axes, M25 / Fe 500,
moderate exposure, Pu = 1200 kN, Mux = 90 kN m (other end -45, double curvature),
Muy = 30 kN m (other end 10). Expected: short about x (8.0), slender about y (12.0),
e_x,min = 22.2 mm, e_y,min = 20.0 mm, M_iy = 22.0 kN m, May = 25.92 kN m before reduction;
case 2 (minimum eccentricity about y) raises the initial moment about y to Pu e_y,min = 24.0.
tests/handcheck/check_column.py reproduces the results independently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engineering import is456
from app.engineering import rc_section as rc
from app.engineering.rebar import bar_area
from app.engineering.trace import CalcSheet

ELEMENT_TYPE = "column"
ENGINE_VERSION = "1.0.0"
CODE_BASIS = ("IS 456:2000", "SP 16:1980", "IS 2502:1963")
REF = is456.CODE

COLUMN_BAR_DIAMETERS = (12, 16, 20, 25, 28, 32)

# Table 28: recommended effective length factor, whether the end is free to sway, description.
TABLE_28: dict[str, tuple[float, bool, str]] = {
    "a": (0.65, False, "held in position and restrained against rotation at both ends"),
    "b": (0.80, False, "held in position at both ends, restrained against rotation at one end"),
    "c": (1.00, False, "held in position at both ends, not restrained against rotation"),
    "d": (1.20, True, "held in position and restrained against rotation at one end; at the other restrained against rotation but not held in position"),
    "e": (1.50, True, "held in position and restrained against rotation at one end; at the other partially restrained against rotation but not held in position"),
    "f": (2.00, True, "held in position at one end but not restrained against rotation; at the other restrained against rotation but not held in position"),
    "g": (2.00, True, "held in position and restrained against rotation at one end; neither held in position nor restrained at the other"),
}
FREE_END = frozenset({"g"})  # one end unrestrained: Cl. 25.3.2 applies

_END_LABELS = {
    "a": "0.65 l: both ends fixed, no sway",
    "b": "0.80 l: fixed and pinned, no sway",
    "c": "1.00 l: both ends pinned, no sway",
    "d": "1.20 l: both ends fixed, sway",
    "e": "1.50 l: fixed and partly fixed, sway",
    "f": "2.00 l: pinned and fixed, sway",
    "g": "2.00 l: fixed and free (cantilever)",
    "custom": "Factor entered below",
}

EndCondition = Literal["a", "b", "c", "d", "e", "f", "g", "custom"]


def _f(default: Any, title: str, group: str, unit: str = "", show_if: dict[str, Any] | None = None, labels: dict[str, str] | None = None,
       **kw: Any) -> Any:
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if show_if:
        extra["show_if"] = show_if
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


class ColumnInput(BaseModel):
    """Everything the column engine reads. Lengths in mm, forces in kN, moments in kN m."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("C1", "Member mark", "Member", min_length=1, max_length=40)
    width_mm: float = _f(300, "Width b", "Geometry", "mm", ge=200, le=2000, description="Dimension in the plane of M_uy")
    depth_mm: float = _f(450, "Depth D", "Geometry", "mm", ge=200, le=3000, description="Dimension in the plane of M_ux")
    unsupported_length_mm: float = _f(3600, "Unsupported length", "Geometry", "mm", ge=500, le=30000,
                                      description="Clear height between restraints (Cl. 25.1.3), for bending about x")
    unsupported_length_y_mm: float | None = _f(None, "Unsupported length about y", "Geometry", "mm", ge=500, le=30000,
                                               description="Blank: same as about x")

    end_x: EndCondition = _f("c", "End restraint about x", "Effective length", labels=_END_LABELS, description="IS 456 Table 28")
    k_x: float = _f(1.0, "Factor about x", "Effective length", "", {"end_x": "custom"}, ge=0.5, le=3.0)
    sway_x: bool = _f(False, "Sway about x", "Effective length", "", {"end_x": "custom"})
    end_y: EndCondition = _f("c", "End restraint about y", "Effective length", labels=_END_LABELS, description="IS 456 Table 28")
    k_y: float = _f(1.0, "Factor about y", "Effective length", "", {"end_y": "custom"}, ge=0.5, le=3.0)
    sway_y: bool = _f(False, "Sway about y", "Effective length", "", {"end_y": "custom"})

    fck: Literal[20, 25, 30, 35, 40, 45, 50, 55] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in is456.CONCRETE_GRADES})
    fy: Literal[250, 415, 500, 550] = _f(500, "Main steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Cover to ties", "Materials", "mm", ge=15, le=100,
                                      description="Blank: Table 16 and Cl. 26.4.2.1")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)

    pu_kn: float = _f(1200, "Axial load Pu", "Loading", "kN", gt=0, le=1e5, description="Factored, compression")
    mux_knm: float = _f(90, "Larger end moment M_ux", "Loading", "kN m", ge=0, le=1e5, description="Factored, about x")
    mux_other_knm: float = _f(-45, "Other end moment about x", "Loading", "kN m", ge=-1e5, le=1e5,
                              description="Same sign: single curvature; opposite sign: double curvature")
    muy_knm: float = _f(30, "Larger end moment M_uy", "Loading", "kN m", ge=0, le=1e5, description="Factored, about y")
    muy_other_knm: float = _f(10, "Other end moment about y", "Loading", "kN m", ge=-1e5, le=1e5,
                              description="Same sign: single curvature; opposite sign: double curvature")

    main_bar_dia_mm: Literal[12, 16, 20, 25, 28, 32] | None = _f(None, "Main bar size", "Reinforcement", "mm", description="Blank lets the engine choose")
    tie_dia_mm: Literal[8, 10, 12] = _f(8, "Tie size", "Reinforcement", "mm")
    max_steel_pct: float = _f(4.0, "Maximum steel", "Reinforcement", "%", ge=0.8, le=6.0,
                              description="Cl. 26.5.3.1 allows 6 %; 4 % leaves room for laps")
    beam_depth_mm: float = _f(450, "Floor beam depth", "Reinforcement", "mm", ge=0, le=3000,
                              description="At the top of the lift: main bars run through it to the lap above")

    @model_validator(mode="after")
    def _consistent(self) -> ColumnInput:
        long_side, short_side = max(self.width_mm, self.depth_mm), min(self.width_mm, self.depth_mm)
        if long_side > 4.0 * short_side:
            raise ValueError("The longer side is more than four times the shorter: design this member as a wall (IS 456:2000, Cl. 32.1).")
        if abs(self.mux_other_knm) > self.mux_knm + 1e-9:
            raise ValueError("Enter the larger end moment about x as M_ux; the other end moment must not exceed it in size.")
        if abs(self.muy_other_knm) > self.muy_knm + 1e-9:
            raise ValueError("Enter the larger end moment about y as M_uy; the other end moment must not exceed it in size.")
        return self


@dataclass(frozen=True)
class AxisGeometry:
    """Everything about one axis that does not depend on the bars."""

    name: str  # "x" or "y"
    dim: float  # section dimension in the plane of bending, mm (D for x, b for y)
    other: float  # the other dimension, mm
    length: float  # unsupported length, mm
    k: float  # effective length factor
    sway: bool
    free_end: bool
    end: str
    le: float  # effective length, mm
    ratio: float  # le / dim
    slender: bool
    e_min: float  # mm
    m2: float  # larger end moment, kN m
    m1: float  # other end moment, signed, kN m
    m_initial: float  # kN m
    ma: float  # additional moment before the reduction factor, kN m


@dataclass(frozen=True)
class Arrangement:
    dia: int
    n_b: int  # bars on each face of width b, corners included
    n_d: int  # bars on each face of depth D, corners included
    edge: float  # distance from a face to the bar centres, mm

    @property
    def count(self) -> int:
        return 2 * self.n_b + 2 * (self.n_d - 2)

    @property
    def area(self) -> float:
        return self.count * bar_area(self.dia)

    def label(self) -> str:
        return f"{self.count}-T{self.dia}"

    def layers(self, axis: str, b: float, D: float) -> list[rc.Layer]:
        """Rows of bars parallel to the bending axis, measured from the compression face."""
        a1 = bar_area(self.dia)
        if axis == "x":  # depth D; the faces of width b hold n_b bars
            outer, inner, depth = self.n_b, self.n_d - 2, D
        else:  # depth b; the faces of depth D hold n_d bars
            outer, inner, depth = self.n_d, self.n_b - 2, b
        e = self.edge
        rows = [rc.Layer(e, outer * a1), rc.Layer(depth - e, outer * a1)]
        for i in range(1, inner + 1):
            rows.append(rc.Layer(e + i * (depth - 2 * e) / (inner + 1), 2 * a1))
        return sorted(rows, key=lambda r: r.y)

    def spacing(self, b: float, D: float) -> tuple[float, float]:
        """Centre-to-centre spacing along the faces of width b and of depth D, mm."""
        return (b - 2 * self.edge) / (self.n_b - 1), (D - 2 * self.edge) / (self.n_d - 1)


@dataclass(frozen=True)
class LoadCase:
    name: str
    mx: float  # kN m
    my: float  # kN m


@dataclass(frozen=True)
class Capacity:
    """The checks of one bar arrangement."""

    arr: Arrangement
    puz: float  # kN
    pb_x: float  # kN
    pb_y: float  # kN
    k_x: float
    k_y: float
    cases: tuple[LoadCase, LoadCase]
    axial_only: bool  # Cl. 39.3 applies
    pu_cap_393: float  # kN
    mux1: float  # kN m
    muy1: float  # kN m
    xu_x: float
    xu_y: float
    alpha_n: float
    ratios: tuple[float, float]
    ok: bool


def effective_cover(inp: ColumnInput) -> float:
    """Cover to the ties: Table 16, and enough for 40 mm to the main bars (Cl. 26.4.2.1)."""
    if inp.clear_cover_mm is not None:
        return inp.clear_cover_mm
    return max(is456.nominal_cover(inp.exposure), 40.0 - inp.tie_dia_mm)


def min_longitudinal_cover(inp: ColumnInput, dia: float) -> float:
    """Cl. 26.4.2.1: 40 mm and not less than the bar diameter; 25 mm for columns of 200 mm or less with bars of 12 mm or less."""
    if min(inp.width_mm, inp.depth_mm) <= 200.0 and dia <= 12.0:
        return 25.0
    return max(40.0, dia)


def axis_geometry(inp: ColumnInput, axis: str) -> AxisGeometry:
    b, D = inp.width_mm, inp.depth_mm
    lx = inp.unsupported_length_mm
    ly = inp.unsupported_length_y_mm if inp.unsupported_length_y_mm is not None else lx
    if axis == "x":
        dim, other, length, end, kc, swc, m2, m1 = D, b, lx, inp.end_x, inp.k_x, inp.sway_x, inp.mux_knm, inp.mux_other_knm
    else:
        dim, other, length, end, kc, swc, m2, m1 = b, D, ly, inp.end_y, inp.k_y, inp.sway_y, inp.muy_knm, inp.muy_other_knm
    k, sway = (kc, swc) if end == "custom" else TABLE_28[end][:2]
    le = k * length
    ratio = le / dim
    slender = ratio >= 12.0  # Cl. 25.1.2: short only when the ratio is less than 12
    e_min = max(length / 500.0 + dim / 30.0, 20.0)  # Cl. 25.4
    if slender and not sway:
        m_initial = max(0.4 * m1 + 0.6 * m2, 0.4 * m2)  # Cl. 39.7.1, note 1
    else:
        m_initial = m2
    ma = inp.pu_kn * (dim / 1000.0) / 2000.0 * ratio * ratio if slender else 0.0  # Cl. 39.7.1
    return AxisGeometry(axis, dim, other, length, k, sway, end in FREE_END, end, le, ratio, slender, e_min, m2, m1, m_initial, ma)


def design_moments(inp: ColumnInput, gx: AxisGeometry, gy: AxisGeometry, k_x: float, k_y: float) -> tuple[LoadCase, LoadCase]:
    """Two load cases: minimum eccentricity about x, then about y (Cl. 25.4, note).

    Per axis: the initial moment, raised to Pu e_min on the axis that takes the minimum
    eccentricity, plus the reduced additional moment, and never less than the larger end moment.
    """
    pu = inp.pu_kn

    def total(g: AxisGeometry, k: float, with_emin: bool) -> float:
        initial = max(g.m_initial, pu * g.e_min / 1000.0) if with_emin else g.m_initial
        return max(initial + k * g.ma, g.m2)

    return (LoadCase("Minimum eccentricity about x", total(gx, k_x, True), total(gy, k_y, False)),
            LoadCase("Minimum eccentricity about y", total(gx, k_x, False), total(gy, k_y, True)))


def alpha_n(ratio: float) -> float:
    """Cl. 39.6: 1.0 for Pu/Puz up to 0.2, 2.0 from 0.8, linear between."""
    return 1.0 + (min(max(ratio, 0.2), 0.8) - 0.2) / 0.6


def evaluate(inp: ColumnInput, arr: Arrangement, gx: AxisGeometry, gy: AxisGeometry) -> Capacity:
    """Capacity checks of one bar arrangement, each factor computed for these bars."""
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    asc = arr.area
    ac = b * D - asc
    pu = inp.pu_kn
    puz = (0.45 * fck * ac + 0.75 * fy * asc) / 1000.0  # Cl. 39.6
    lx, ly = arr.layers("x", b, D), arr.layers("y", b, D)
    pb_x = rc.balanced(b, D, lx, fck, fy).p / 1000.0
    pb_y = rc.balanced(D, b, ly, fck, fy).p / 1000.0

    def k_factor(g: AxisGeometry, pb: float) -> float:
        if not g.slender:
            return 1.0
        if puz <= pb:
            return 1.0
        return min(max((puz - pu) / (puz - pb), 0.0), 1.0)  # Cl. 39.7.1.1

    kx, ky = k_factor(gx, pb_x), k_factor(gy, pb_y)
    cases = design_moments(inp, gx, gy, kx, ky)
    pu_393 = (0.4 * fck * ac + 0.67 * fy * asc) / 1000.0  # Cl. 39.3
    axial_only = (not gx.slender and not gy.slender and inp.mux_knm == 0 and inp.muy_knm == 0
                  and gx.e_min <= 0.05 * D and gy.e_min <= 0.05 * b)
    if axial_only:
        ok = pu <= pu_393 + 1e-9
        return Capacity(arr, puz, pb_x, pb_y, kx, ky, cases, True, pu_393, math.nan, math.nan, math.nan, math.nan, math.nan,
                        (math.nan, math.nan), ok)
    sx = rc.at_axial_load(b, D, lx, fck, fy, pu * 1000.0)
    sy = rc.at_axial_load(D, b, ly, fck, fy, pu * 1000.0)
    mux1 = sx.m / 1e6 if sx is not None else 0.0
    muy1 = sy.m / 1e6 if sy is not None else 0.0
    an = alpha_n(pu / puz) if puz > 0 else 2.0

    def ratio(c: LoadCase) -> float:
        if mux1 <= 0 or muy1 <= 0:
            return math.inf
        return (c.mx / mux1) ** an + (c.my / muy1) ** an

    ratios = (ratio(cases[0]), ratio(cases[1]))
    ok = pu < puz and max(ratios) <= 1.0 + 1e-9
    return Capacity(arr, puz, pb_x, pb_y, kx, ky, cases, False, pu_393, mux1, muy1,
                    sx.xu if sx else math.nan, sy.xu if sy else math.nan, an, ratios, ok)


def steel_per_metre(inp: ColumnInput, arr: Arrangement, cover: float) -> float:
    """Mass of main bars, ties and cross-ties per metre of height, kg/m: the cost the selection minimises.

    Main steel alone favours many small bars, which tighten the tie pitch (16 diameters) and
    need more cross-ties; counting the ties lets the selection see that.
    """
    b, D, dt = inp.width_mm, inp.depth_mm, inp.tie_dia_mm
    pitch = tie_pitch_provided(tie_spacing(inp, arr.dia)[0])
    s_b, s_d = arr.spacing(b, D)
    a, bb = b - 2.0 * cover, D - 2.0 * cover
    tie_len = 2.0 * (a + bb) + len(restrained_bars(arr.n_b, s_b)) * bb + len(restrained_bars(arr.n_d, s_d)) * a  # mm per set
    main = arr.area * 1e-6 * 7850.0
    ties = tie_len / pitch * bar_area(dt) * 1e-6 * 7850.0
    return main + ties


def tie_pitch_provided(allowed: float) -> float:
    """Round the allowed pitch down to a site-friendly value: 25 mm steps from 100 mm, 5 mm below."""
    return math.floor(allowed / 25.0 + 1e-9) * 25.0 if allowed >= 100 else math.floor(allowed / 5.0 + 1e-9) * 5.0


def candidates(inp: ColumnInput, cover: float) -> list[Arrangement]:
    """Symmetric arrangements that meet the detailing rules of Cl. 26.3.2 and 26.5.3.1, lightest first (ties counted)."""
    b, D = inp.width_mm, inp.depth_mm
    ag = b * D
    as_min, as_max = 0.008 * ag, inp.max_steel_pct / 100.0 * ag
    dias = (inp.main_bar_dia_mm,) if inp.main_bar_dia_mm else COLUMN_BAR_DIAMETERS
    out: list[Arrangement] = []
    for dia in dias:
        edge = cover + inp.tie_dia_mm + dia / 2.0
        s_clear_min = is456.min_clear_bar_spacing_horizontal(dia, inp.max_aggregate_mm)
        for n_b in range(2, 40):
            s_b = (b - 2 * edge) / (n_b - 1)
            if s_b - dia < s_clear_min - 1e-9:
                break
            if s_b > 300.0 + 1e-9:  # Cl. 26.5.3.1(g)
                continue
            for n_d in range(2, 40):
                s_d = (D - 2 * edge) / (n_d - 1)
                if s_d - dia < s_clear_min - 1e-9:
                    break
                if s_d > 300.0 + 1e-9:
                    continue
                arr = Arrangement(dia, n_b, n_d, edge)
                if as_min - 1e-9 <= arr.area <= as_max + 1e-9:
                    out.append(arr)
    out.sort(key=lambda a: (round(steel_per_metre(inp, a, cover), 6), a.count, a.dia))
    return out


def tie_spacing(inp: ColumnInput, dia: float) -> tuple[float, dict[str, float]]:
    """Cl. 26.5.3.2(c)(1): least lateral dimension, 16 times the smallest main bar, 300 mm."""
    limits = {"least lateral dimension": min(inp.width_mm, inp.depth_mm), "16 times the main bar diameter": 16.0 * dia, "300 mm": 300.0}
    return min(limits.values()), limits


def restrained_bars(n_face: int, spacing: float) -> list[int]:
    """Indices (1 .. n_face-2) of intermediate bars on a face that need a cross-tie.

    Cl. 26.5.3.2(b): corner bars are always held by the perimeter tie. Where the bars are not
    more than 75 mm apart, ties need only go round the corner and alternate bars; otherwise
    every intermediate bar is tied. The 75 mm is taken centre to centre (the smaller reading
    of "spaced", so the rule is used less often).
    """
    inner = list(range(1, n_face - 1))
    if spacing <= 75.0:
        return [i for i in inner if i % 2 == 0]
    return inner


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def design_column(inp: ColumnInput) -> dict[str, Any]:
    from app.modules.structural.domain import column_detailing

    sheet = CalcSheet()
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    pu = inp.pu_kn
    cover = effective_cover(inp)
    gx, gy = axis_geometry(inp, "x"), axis_geometry(inp, "y")

    # ------------------------------------------------------------------ durability
    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade", "f_ck", "", fck, "N/mm2", 0)
    sheet.step("Input", "Steel grade of main bars", "f_y", "", fy, "N/mm2", 0)
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    if inp.clear_cover_mm is None:
        sheet.step(f"{REF}, Table 16 and Cl. 26.4.2.1", "Cover to ties: Table 16, and 40 mm to the main bars",
                   "c = max(c_nom, 40 - d_t)", f"max({_n(is456.nominal_cover(inp.exposure), 0)}, 40 - {inp.tie_dia_mm})", cover, "mm", 0)
    else:
        sheet.step("Input", "Cover to ties", "c", "", cover, "mm", 0)
    sheet.check("cover", f"{REF}, Table 16", "Nominal cover to all reinforcement",
                "c", cover, ">=", "c_nom", is456.nominal_cover(inp.exposure), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ slenderness
    sheet.section("2. Effective length and slenderness")
    for g in (gx, gy):
        dsym = "D" if g.name == "x" else "b"
        if g.end == "custom":
            sheet.step("Input", f"Effective length factor about {g.name} ({'sway' if g.sway else 'no sway'})", f"k_{g.name}", "", g.k, "", 2)
        else:
            sheet.step(f"{REF}, Cl. 25.2, Table 28", f"End restraint about {g.name}: {TABLE_28[g.end][2]}", f"k_{g.name}", "", g.k, "", 2)
        sheet.step(f"{REF}, Cl. 25.2", f"Effective length about {g.name}", f"l_e{g.name} = k_{g.name} l",
                   f"{_n(g.k)} x {_n(g.length, 0)}", g.le, "mm", 0)
        sheet.step(f"{REF}, Cl. 25.1.2", f"Slenderness about {g.name}: {'slender' if g.slender else 'short'} (short below 12)",
                   f"l_e{g.name} / {dsym}", f"{_n(g.le, 0)} / {_n(g.dim, 0)}", g.ratio, "", 2)
    least = min(b, D)
    sheet.check("l_max", f"{REF}, Cl. 25.3.1", "Unsupported length not more than 60 times the least lateral dimension",
                "l", max(gx.length, gy.length), "<=", "60 b_min", 60.0 * least, "mm", 0)
    for g in (gx, gy):
        if g.free_end:
            lim = 100.0 * g.other**2 / g.dim
            sheet.check(f"l_cantilever_{g.name}", f"{REF}, Cl. 25.3.2", f"Column free at one end, bending about {g.name}: l not more than 100 b^2 / D",
                        "l", g.length, "<=", "100 b^2/D", lim, "mm", 0)

    # ------------------------------------------------------------------ forces before the bars
    sheet.section("3. Design forces")
    sheet.step("Input", "Factored axial load", "P_u", "", pu, "kN", 1)
    for g in (gx, gy):
        dsym = "D" if g.name == "x" else "b"
        sheet.step(f"{REF}, Cl. 25.4", f"Minimum eccentricity about {g.name}", f"e_{g.name},min = l/500 + {dsym}/30 >= 20",
                   f"{_n(g.length, 0)}/500 + {_n(g.dim, 0)}/30", g.e_min, "mm", 1)
        sheet.step("Input", f"End moments about {g.name}: larger, other (signed)", f"M_u{g.name}2, M_u{g.name}1", "", f"{_n(g.m2)}, {_n(g.m1)}", "kN m")
        if g.slender and not g.sway:
            sheet.step(f"{REF}, Cl. 39.7.1, Note 1", f"Initial moment of a braced slender column about {g.name}",
                       f"M_i{g.name} = max(0.4 M_u{g.name}1 + 0.6 M_u{g.name}2, 0.4 M_u{g.name}2)",
                       f"max(0.4 x {_n(g.m1)} + 0.6 x {_n(g.m2)}, 0.4 x {_n(g.m2)})", g.m_initial, "kN m")
        if g.slender:
            sheet.step(f"{REF}, Cl. 39.7.1", f"Additional moment about {g.name}, before reduction",
                       f"M_a{g.name} = P_u {dsym} / 2000 (l_e{g.name} / {dsym})^2",
                       f"{_n(pu, 1)} x {_n(g.dim / 1000, 3)} / 2000 x {_n(g.ratio)}^2", g.ma, "kN m")

    # ------------------------------------------------------------------ bar selection
    selected: Capacity | None = None
    for arr in candidates(inp, cover):
        cap = evaluate(inp, arr, gx, gy)
        if cap.ok:
            selected = cap
            break
    if selected is None:
        return _stopped(sheet, "No arrangement of bars within the maximum steel percentage carries the design forces: increase the "
                               "section, the concrete grade or the maximum steel, or check the loads.")
    cap = selected
    arr = cap.arr
    asc, ag = arr.area, b * D
    s_b, s_d = arr.spacing(b, D)
    p_pct = 100.0 * asc / ag

    sheet.section("4. Longitudinal reinforcement")
    sheet.step("Selected", f"Bars: {arr.n_b} on each face of width b, {arr.n_d} on each face of depth D (corners counted once)",
               "", arr.label(), asc, "mm2", 0)
    sheet.step(f"{REF}, Cl. 26.5.3.1(a)", "Steel percentage of the gross section", "p = 100 A_sc / (b D)",
               f"100 x {_n(asc, 0)} / ({_n(b, 0)} x {_n(D, 0)})", p_pct, "%", 2)
    sheet.check("p_min", f"{REF}, Cl. 26.5.3.1(a)", "Minimum longitudinal steel (0.8 %)", "p", p_pct, ">=", "p_min", 0.8, "%", 2, ratio=False)
    sheet.check("p_max", f"{REF}, Cl. 26.5.3.1(a)", f"Maximum longitudinal steel ({_n(inp.max_steel_pct, 1)} % as entered; the code allows 6 %)",
                "p", p_pct, "<=", "p_max", inp.max_steel_pct, "%", 2)
    sheet.check("n_bars", f"{REF}, Cl. 26.5.3.1(c)", "Number of bars in a rectangular column", "n", arr.count, ">=", "n_min", 4, "", 0, ratio=False)
    sheet.check("dia_min", f"{REF}, Cl. 26.5.3.1(d)", "Main bar diameter", "d_b", arr.dia, ">=", "d_b,min", 12, "mm", 0, ratio=False)
    sheet.check("s_max", f"{REF}, Cl. 26.5.3.1(g)", "Spacing of bars along the periphery", "s", max(s_b, s_d), "<=", "s_max", 300, "mm", 0)
    s_min = is456.min_clear_bar_spacing_horizontal(arr.dia, inp.max_aggregate_mm)
    sheet.check("s_min", f"{REF}, Cl. 26.3.2(a)", "Clear distance between bars", "s_clear", min(s_b, s_d) - arr.dia, ">=", "s_min", s_min, "mm", 0, ratio=False)
    sheet.check("cover_bar", f"{REF}, Cl. 26.4.2.1", "Cover to the main bars", "c + d_t", cover + inp.tie_dia_mm, ">=", "c_min",
                min_longitudinal_cover(inp, arr.dia), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ capacity
    sheet.section("5. Strength")
    ac = ag - asc
    sheet.step(f"{REF}, Cl. 39.6", "Axial capacity without bending", "P_uz = 0.45 f_ck A_c + 0.75 f_y A_sc",
               f"(0.45 x {_n(fck, 0)} x {_n(ac, 0)} + 0.75 x {_n(fy, 0)} x {_n(asc, 0)}) / 10^3", cap.puz, "kN", 1)
    if cap.axial_only:
        sheet.step(f"{REF}, Cl. 39.3", "Short column, no end moments, minimum eccentricity not more than 0.05 times each dimension: "
                   "axial design formula", "P_u,R = 0.4 f_ck A_c + 0.67 f_y A_sc",
                   f"(0.4 x {_n(fck, 0)} x {_n(ac, 0)} + 0.67 x {_n(fy, 0)} x {_n(asc, 0)}) / 10^3", cap.pu_cap_393, "kN", 1)
        sheet.check("axial", f"{REF}, Cl. 39.3", "Axial load", "P_u", pu, "<=", "P_u,R", cap.pu_cap_393, "kN", 1)
        governing_ratio = pu / cap.pu_cap_393
    else:
        for g, pb, k in ((gx, cap.pb_x, cap.k_x), (gy, cap.pb_y, cap.k_y)):
            if g.slender:
                sheet.step(f"{REF}, Cl. 39.7.1.1", f"Axial load at balanced failure, bending about {g.name} (strain compatibility, x_u = x_u,max)",
                           f"P_b{g.name}", "", pb, "kN", 1)
                sheet.step(f"{REF}, Cl. 39.7.1.1", f"Reduction factor for the additional moment about {g.name}",
                           f"k_{g.name} = (P_uz - P_u) / (P_uz - P_b{g.name}) <= 1",
                           f"({_n(cap.puz, 1)} - {_n(pu, 1)}) / ({_n(cap.puz, 1)} - {_n(pb, 1)})", k, "", 3)
        for i, c in enumerate(cap.cases):
            sheet.step(f"{REF}, Cl. 25.4 and 39.7.1", f"Case {i + 1}, {c.name.lower()}: design moments", "M_ux, M_uy", "",
                       f"{_n(c.mx)}, {_n(c.my)}", "kN m")
        sheet.step(f"{REF}, Cl. 39.1", f"Moment capacity about x at P_u (strain compatibility, x_u = {_n(cap.xu_x, 1)} mm)", "M_ux1", "", cap.mux1, "kN m", 2)
        sheet.step(f"{REF}, Cl. 39.1", f"Moment capacity about y at P_u (strain compatibility, x_u = {_n(cap.xu_y, 1)} mm)", "M_uy1", "", cap.muy1, "kN m", 2)
        sheet.check("puz", f"{REF}, Cl. 39.6", "Axial load below the axial capacity", "P_u", pu, "<=", "P_uz", cap.puz, "kN", 1)
        sheet.step(f"{REF}, Cl. 39.6", "Exponent of the interaction formula", "alpha_n (1.0 at P_u/P_uz <= 0.2, 2.0 at >= 0.8)",
                   f"P_u/P_uz = {_n(pu / cap.puz, 3)}", cap.alpha_n, "", 3)
        sheet.step(f"{REF}, Cl. 39.6", "Interaction formula for biaxial bending", "(M_ux/M_ux1)^alpha_n + (M_uy/M_uy1)^alpha_n <= 1.0", "", "", "")
        for i, (c, r) in enumerate(zip(cap.cases, cap.ratios, strict=True)):
            sub = f"({_n(c.mx)}/{_n(cap.mux1)})^{_n(cap.alpha_n, 3)} + ({_n(c.my)}/{_n(cap.muy1)})^{_n(cap.alpha_n, 3)}"
            sheet.step(f"{REF}, Cl. 39.6", f"Case {i + 1}, {c.name.lower()}", "", sub, r, "", 3)
            sheet.check(f"biaxial_{i + 1}", f"{REF}, Cl. 39.6", f"Biaxial bending, case {i + 1} ({c.name.lower()})",
                        "interaction ratio", r, "<=", "limit", 1.0, "", 3)
        governing_ratio = max(cap.ratios)

    # ------------------------------------------------------------------ ties
    sheet.section("6. Transverse reinforcement")
    dt = inp.tie_dia_mm
    dt_min = max(arr.dia / 4.0, 6.0)
    sheet.check("tie_dia", f"{REF}, Cl. 26.5.3.2(c)(2)", "Tie diameter: a quarter of the largest main bar, and 6 mm",
                "d_t", dt, ">=", "d_t,min", dt_min, "mm", 0, ratio=False)
    pitch_allow, limits = tie_spacing(inp, arr.dia)
    governing = min(limits, key=lambda k: limits[k])
    pitch = tie_pitch_provided(pitch_allow)
    sheet.step(f"{REF}, Cl. 26.5.3.2(c)(1)", "Tie pitch: least of the least lateral dimension, 16 times the main bar, 300 mm",
               "min(b_min, 16 d_b, 300)", f"min({_n(limits['least lateral dimension'], 0)}, {_n(16.0 * arr.dia, 0)}, 300)", pitch_allow, "mm", 0)
    sheet.step("Selected", f"Ties provided (governed by {governing})", "s_t", "", pitch, "mm", 0)
    sheet.check("pitch", f"{REF}, Cl. 26.5.3.2(c)(1)", "Tie pitch provided", "s_t", pitch, "<=", "s_t,max", pitch_allow, "mm", 0, ratio=False)
    tied_b = restrained_bars(arr.n_b, s_b)
    tied_d = restrained_bars(arr.n_d, s_d)
    if tied_b or tied_d:
        sheet.step(f"{REF}, Cl. 26.5.3.2(b)", "Cross-ties so that every corner bar and every intermediate bar more than 75 mm "
                   "from a tied bar is held by a tie corner", "cross-ties", "",
                   f"{len(tied_b)} across D, {len(tied_d)} across b", "", 0)
    ld_c = is456.development_length(arr.dia, fck, fy, compression=True)
    lap = max(ld_c, 24.0 * arr.dia)
    sheet.step(f"{REF}, Cl. 26.2.5.1(d)", "Lap length in compression: development length in compression, not less than 24 d_b",
               "L_lap = max(L_d,c, 24 d_b)", f"max({_n(ld_c, 0)}, {24 * arr.dia})", lap, "mm", 0)

    # ------------------------------------------------------------------ outputs
    sheet.flag("info", "Moments are taken from the analysis as entered; the engine adds minimum eccentricity and, for slender "
                       "columns, the additional moments of Cl. 39.7.1. Ductile detailing to IS 13920 is not applied.")
    if not gx.slender and not gy.slender and not cap.axial_only and inp.mux_knm == 0 and inp.muy_knm == 0:
        sheet.flag("info", "Minimum eccentricity exceeds 0.05 times a dimension, so the column is checked for bending "
                           "rather than by the axial formula of Cl. 39.3.", f"{REF}, Cl. 39.3")
    for g in (gx, gy):
        if g.end == "custom" and not g.sway and g.k > 1.0:
            sheet.flag("warning", f"A braced column about {g.name} normally has an effective length factor of 1.0 or less (Table 28).")
        if g.end == "custom" and g.sway and g.k < 1.2:
            sheet.flag("warning", f"A sway column about {g.name} normally has an effective length factor of 1.2 or more (Table 28).")
    if p_pct > 4.0:
        sheet.flag("warning", f"Steel is {p_pct:.1f} % of the section: at laps it doubles. Stagger the laps or use couplers.", f"{REF}, Cl. 26.5.3.1(a)")

    reinforcement = {
        "main": {"count": arr.count, "dia": arr.dia, "n_b": arr.n_b, "n_d": arr.n_d, "area": round(asc, 1), "label": arr.label(), "edge": arr.edge},
        "ties": {"dia": dt, "spacing": pitch, "label": f"T{dt} ties @ {pitch:.0f} c/c"},
        "cross_ties": {"across_D": tied_b, "across_b": tied_d},
        "cover": cover,
        "lap": round(lap, 0),
    }
    bbs = column_detailing.bar_schedule(inp, cover, reinforcement)
    quantities = column_detailing.quantities(inp, bbs)
    drawing = column_detailing.drawing(inp, cover, reinforcement)
    charts = [] if cap.axial_only else _charts(inp, arr, cap)

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    case_i = 0 if cap.axial_only or cap.ratios[0] >= cap.ratios[1] else 1
    key_results = [
        {"label": "Axial load", "sym": "P_u", "value": round(pu, 1), "unit": "kN", "dp": 1},
        {"label": "Design moment about x", "sym": "M_ux", "value": round(cap.cases[case_i].mx, 2), "unit": "kN m", "dp": 2},
        {"label": "Design moment about y", "sym": "M_uy", "value": round(cap.cases[case_i].my, 2), "unit": "kN m", "dp": 2},
        {"label": "Interaction ratio" if not cap.axial_only else "Axial ratio", "sym": "", "value": round(governing_ratio, 3), "unit": "", "dp": 3},
        {"label": "Main bars", "sym": "", "value": arr.label(), "unit": "", "dp": 0},
        {"label": "Steel ratio", "sym": "p", "value": round(p_pct, 2), "unit": "%", "dp": 2},
        {"label": "Ties", "sym": "", "value": reinforcement["ties"]["label"], "unit": "", "dp": 0},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
    ]
    return {
        "element_type": ELEMENT_TYPE,
        "engine_version": ENGINE_VERSION,
        "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok",
        "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok),
        "checks_total": len(checks),
        "max_utilisation": max(utils) if utils else None,
        "key_results": key_results,
        "data": {
            "cover": cover, "edge": round(arr.edge, 2), "asc": round(asc, 3), "p_pct": round(p_pct, 4),
            "lex": round(gx.le, 3), "ley": round(gy.le, 3), "ratio_x": round(gx.ratio, 5), "ratio_y": round(gy.ratio, 5),
            "slender_x": gx.slender, "slender_y": gy.slender, "ex_min": round(gx.e_min, 4), "ey_min": round(gy.e_min, 4),
            "mix": round(gx.m_initial, 5), "miy": round(gy.m_initial, 5), "max": round(gx.ma, 5), "may": round(gy.ma, 5),
            "puz": round(cap.puz, 4), "pb_x": round(cap.pb_x, 4), "pb_y": round(cap.pb_y, 4), "k_x": round(cap.k_x, 6), "k_y": round(cap.k_y, 6),
            "case1_mx": round(cap.cases[0].mx, 5), "case1_my": round(cap.cases[0].my, 5),
            "case2_mx": round(cap.cases[1].mx, 5), "case2_my": round(cap.cases[1].my, 5),
            "axial_only": cap.axial_only, "pu_cap_393": round(cap.pu_cap_393, 4),
            "mux1": None if cap.axial_only else round(cap.mux1, 5), "muy1": None if cap.axial_only else round(cap.muy1, 5),
            "alpha_n": None if cap.axial_only else round(cap.alpha_n, 6),
            "ratio_case1": None if cap.axial_only else round(cap.ratios[0], 6),
            "ratio_case2": None if cap.axial_only else round(cap.ratios[1], 6),
            "tie_pitch": pitch, "tie_pitch_allow": pitch_allow, "lap": round(lap, 1),
        },
        "reinforcement": reinforcement,
        "sheet": sheet.to_dict(),
        "bbs": bbs,
        "quantities": quantities,
        "drawing": drawing,
        "charts": charts,
    }


def _charts(inp: ColumnInput, arr: Arrangement, cap: Capacity) -> list[dict[str, Any]]:
    """Interaction diagrams for the bars provided, with the design forces of both cases."""
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    out = []
    for axis, width, depth, sym, idx in (("x", b, D, "M_ux", 0), ("y", D, b, "M_uy", 1)):
        curve = rc.interaction_curve(width, depth, arr.layers(axis, b, D), fck, fy)
        design = [[round(c.mx if idx == 0 else c.my, 2), round(inp.pu_kn, 1)] for c in cap.cases]
        labels = ["Case 1", "Case 2"]
        if design[0] == design[1]:  # both cases give the same moment about this axis: one point, one label
            design, labels = design[:1], ["Cases 1 and 2"]
        out.append({
            "id": f"interaction_{axis}",
            "title": f"Interaction about the {axis} axis, {arr.label()}",
            "x": {"label": sym, "unit": "kN m"},
            "y": {"label": "P_u", "unit": "kN"},
            "series": [
                {"name": "Capacity", "kind": "line", "points": [[round(m / 1e6, 2), round(p / 1e3, 1)] for m, p in curve]},
                {"name": "Design forces", "kind": "point", "points": design, "labels": labels},
            ],
            "note": "Uniaxial capacity by strain compatibility (Cl. 39.1). Biaxial bending is checked by Cl. 39.6, not by this curve alone.",
        })
    return out


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE,
        "engine_version": ENGINE_VERSION,
        "code_basis": list(CODE_BASIS),
        "status": "stopped",
        "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok),
        "checks_total": len(sheet.checks()),
        "max_utilisation": None,
        "key_results": [],
        "data": {},
        "reinforcement": None,
        "sheet": sheet.to_dict(),
        "bbs": None,
        "quantities": None,
        "drawing": None,
        "charts": [],
    }

