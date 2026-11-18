"""Isolated rectangular footing of uniform depth under a rectangular column, to IS 456:2000.

Size from the service loads and the safe bearing pressure, with moments in both planes and no
loss of contact; depth from flexure without compression steel, one-way shear at d from the column
faces (Cl. 34.2.4.1(a)) and punching shear at d/2 (Cl. 31.6, 34.2.4.1(b)); steel both ways at
the column faces (Cl. 34.2.3), the short-direction steel split by the central band rule
(Cl. 34.3.1(b)); development length within the projection (Cl. 34.2.4.3); bearing at the base
of the column (Cl. 34.4); edge thickness (Cl. 34.1.2); cover for footings (Cl. 26.4.2.2).

Directions: L, the length, is in the plane of the column depth D_c; B, the width, in the plane of
the column width b_c. "Bars along L" span the length and are spread across the width.

Worked example (the defaults): column 300 x 450, service load 800 kN, no moment, safe bearing
pressure 200 kN/m2, 10 percent for the footing's own weight, M25 / Fe 415, cover 50.
tests/handcheck/check_footing.py reproduces the results independently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engineering import is456
from app.engineering import is456_slabs as sl
from app.engineering.rebar import bar_area
from app.engineering.trace import CalcSheet

ELEMENT_TYPE = "footing"
ENGINE_VERSION = "1.0.0"
CODE_BASIS = ("IS 456:2000", "IS 2502:1963")
REF = is456.CODE

FOOTING_BAR_DIAMETERS = (10, 12, 16, 20, 25)
FOOTING_MIN_COVER = 50.0  # Cl. 26.4.2.2
EDGE_MIN = 150.0  # Cl. 34.1.2, footings on soil
STEP = 50.0  # plan dimensions and depth are set out in 50 mm steps
MAX_PROJECTION = 3000.0  # mm, the largest projection tried when the plan grows to anchor the bars
PRACTICAL_MIN_SPACING = 100.0
BEND_90_VALUE = 8.0  # Cl. 26.2.2.1(b): anchorage value of a bend, 4 diameters per 45 degrees


def _f(default: Any, title: str, group: str, unit: str = "", show_if: dict[str, Any] | None = None, labels: dict[str, str] | None = None,
       **kw: Any) -> Any:
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if show_if:
        extra["show_if"] = show_if
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


class FootingInput(BaseModel):
    """Everything the footing engine reads. Lengths in mm, loads in kN, moments in kN m, pressures in kN/m2."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("F1", "Footing mark", "Member", min_length=1, max_length=40)
    column_width_mm: float = _f(300, "Column width b_c", "Column", "mm", ge=150, le=2000, description="In the plane of the footing width B")
    column_depth_mm: float = _f(450, "Column depth D_c", "Column", "mm", ge=150, le=3000, description="In the plane of the footing length L")

    p_service_kn: float = _f(800, "Service axial load", "Loading", "kN", gt=0, le=1e5, description="Dead + imposed, unfactored")
    m_l_service_knm: float = _f(0, "Service moment in the plane of L", "Loading", "kN m", ge=0, le=1e5)
    m_b_service_knm: float = _f(0, "Service moment in the plane of B", "Loading", "kN m", ge=0, le=1e5)
    load_factor: float = _f(1.5, "Load factor", "Loading", "", ge=1.0, le=2.0, description="For design of the concrete, Table 18")
    self_weight_pct: float = _f(10, "Allowance for own weight", "Loading", "%", ge=0, le=40, description="Footing and backfill, for sizing only")

    sbc_kn_m2: float = _f(200, "Safe bearing pressure", "Soil", "kN/m2", gt=0, le=5000, description="Net, from the soil investigation")

    length_mm: float | None = _f(None, "Length L", "Size", "mm", ge=500, le=20000, description="Blank: sized by the engine, equal projections")
    width_mm: float | None = _f(None, "Width B", "Size", "mm", ge=500, le=20000, description="Blank: sized by the engine, equal projections")
    depth_mm: float | None = _f(None, "Depth D", "Size", "mm", ge=200, le=3000, description="Blank: the least depth that passes")

    fck: Literal[20, 25, 30, 35, 40] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in (20, 25, 30, 35, 40)})
    fy: Literal[250, 415, 500, 550] = _f(415, "Steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Clear cover", "Materials", "mm", ge=40, le=100, description="Blank: 50 mm or Table 16, whichever is more")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)
    bar_dia_mm: Literal[10, 12, 16, 20, 25] | None = _f(None, "Bar size", "Reinforcement", "mm", description="Blank lets the engine choose")

    @model_validator(mode="after")
    def _consistent(self) -> FootingInput:
        if (self.length_mm is None) != (self.width_mm is None):
            raise ValueError("Enter both the length and the width, or leave both blank for the engine to size the footing.")
        if self.length_mm is not None and self.width_mm is not None:
            if self.length_mm <= self.column_depth_mm or self.width_mm <= self.column_width_mm:
                raise ValueError("The footing must be larger than the column in both directions.")
        return self


@dataclass(frozen=True)
class Pressures:
    q_max: float
    q_min: float


def service_pressures(inp: FootingInput, L: float, B: float) -> Pressures:
    """Gross service pressures with the own-weight allowance, kN/m2 (L, B in m)."""
    p = inp.p_service_kn * (1 + inp.self_weight_pct / 100.0)
    a = L * B
    var = 6 * inp.m_l_service_knm / (B * L * L) + 6 * inp.m_b_service_knm / (L * B * B)
    return Pressures(p / a + var, p / a - var)


def factored_pressure(inp: FootingInput, L: float, B: float) -> float:
    """Largest factored net upward pressure from the column load (own weight excluded), kN/m2. Used as uniform."""
    pu, ml, mb = inp.load_factor * inp.p_service_kn, inp.load_factor * inp.m_l_service_knm, inp.load_factor * inp.m_b_service_knm
    return pu / (L * B) + 6 * ml / (B * L * L) + 6 * mb / (L * B * B)


def size_plan(inp: FootingInput) -> tuple[float, float]:
    """Smallest L x B (mm) with equal projections, in 50 mm steps, that keeps the pressure within limits."""
    bc, dc = inp.column_width_mm, inp.column_depth_mm
    a = STEP
    while a < 20000:
        L, B = dc + 2 * a, bc + 2 * a
        L, B = math.ceil(L / STEP - 1e-9) * STEP, math.ceil(B / STEP - 1e-9) * STEP
        pr = service_pressures(inp, L / 1000, B / 1000)
        if pr.q_max <= inp.sbc_kn_m2 + 1e-9 and pr.q_min >= -1e-9:
            return L, B
        a += STEP / 2
    return math.inf, math.inf


@dataclass(frozen=True)
class Trial:
    """Everything that depends on the depth and the bar size."""

    D: float
    dia: int
    d_l: float  # bars along L, outer layer
    d_b: float  # bars along B, inner layer
    m_l: float  # kN m, at the face, over the width B
    m_b: float  # kN m, over the length L
    as_l: float  # mm2 required (flexure or minimum), over B
    as_b: float  # mm2 required, over L
    as_flex_l: float
    as_flex_b: float
    s_l: float  # spacing of bars along L
    n_l: int
    n_b_band: int
    n_b_outer: int  # in each outer portion
    s_b_band: float
    s_b_outer: float
    as_prov_l: float
    as_prov_b: float
    v1_l: float  # kN, one-way shear across the width at d from the face
    v1_b: float
    tau1_l: float
    tau1_b: float
    tc_l: float
    tc_b: float
    vp: float  # kN, punching
    b0: float
    tau_p: float
    tau_p_allow: float
    ks: float
    ok_flexure: bool
    ok_shear: bool
    ok_spacing: bool
    ok_anchorage: bool
    bent_ends: bool  # bars need a 90 degree bend at each end to develop their stress


def bars_across(as_req: float, width: float, dia: int, s_max: float, cover: float) -> tuple[float, int, float]:
    """(spacing, count, area provided) for an area spread over a width, spacing in 10 mm steps."""
    a1 = bar_area(dia)
    n = max(math.ceil(as_req / a1 - 1e-9), 2)
    usable = width - 2 * cover - dia
    s = usable / (n - 1)
    if s > s_max:
        n = math.ceil(usable / s_max - 1e-9) + 1
    s = math.floor(usable / (n - 1) / 10.0 + 1e-9) * 10.0
    return s, n, n * a1


def bars_short_direction(as_b: float, L: float, B: float, dia: int, s_max: float, cover: float) -> tuple[int, float, int, float, float]:
    """Bars along B (spanning the width, spread along the length): (n in band, band spacing, n in each outer part, outer spacing, area).

    Cl. 34.3.1(b): the central band of width B takes 2/(beta + 1) of the steel, the rest is spread in
    the outer parts. Where the outer parts are too narrow for bars of their own, the bars are spread
    uniformly over the length, with enough of them inside the band to carry its share.
    """
    a1 = bar_area(dia)
    beta = L / B
    band_req = as_b * 2.0 / (beta + 1.0)
    rest = (as_b - band_req) / 2.0
    outer_usable = (L - B) / 2.0 - cover
    if outer_usable < PRACTICAL_MIN_SPACING:
        usable = L - 2.0 * cover - dia
        n = max(math.ceil(as_b / a1 - 1e-9), 2, math.ceil(usable / s_max - 1e-9) + 1)
        while True:
            s = math.floor(usable / (n - 1) / 10.0 + 1e-9) * 10.0
            start = (L - (n - 1) * s) / 2.0  # the bars are centred on the footing
            in_band = sum(1 for i in range(n) if (L - B) / 2.0 - 1e-6 <= start + i * s <= (L + B) / 2.0 + 1e-6)
            if in_band * a1 >= band_req - 1e-9 and s <= s_max + 1e-9:
                return in_band, s, (n - in_band) // 2, s, n * a1
            n += 1
    n_band = max(math.ceil(band_req / a1 - 1e-9), 2)
    s_band = math.floor((B - dia) / (n_band - 1) / 10.0 + 1e-9) * 10.0
    if s_band > s_max:
        s_band = math.floor(s_max / 10.0) * 10.0
        n_band = math.ceil((B - dia) / s_band - 1e-9) + 1
    n_out = max(math.ceil(rest / a1 - 1e-9), math.ceil(outer_usable / s_max - 1e-9), 1)
    s_out = math.floor(outer_usable / n_out / 10.0 + 1e-9) * 10.0
    return n_band, s_band, n_out, s_out, (n_band + 2 * n_out) * a1


def trial(inp: FootingInput, L: float, B: float, D: float, dia: int, cover: float, qu: float) -> Trial:
    fck, fy = float(inp.fck), float(inp.fy)
    bc, dc = inp.column_width_mm, inp.column_depth_mm
    d_l = D - cover - dia / 2.0
    d_b = D - cover - 1.5 * dia
    a_l, a_b = (L - dc) / 2.0, (B - bc) / 2.0  # projections, mm
    q = qu / 1000.0  # kN/m2 to N/mm2
    m_l = q * B * a_l * a_l / 2.0  # N mm, Cl. 34.2.3.2: at the face of the column
    m_b = q * L * a_b * a_b / 2.0
    ok_flexure = m_l <= is456.limiting_moment(fck, fy, B, d_l) and m_b <= is456.limiting_moment(fck, fy, L, d_b)
    as_flex_l = is456.design_rectangular(m_l, fck, fy, B, d_l, 0).ast_req if ok_flexure else math.inf
    as_flex_b = is456.design_rectangular(m_b, fck, fy, L, d_b, 0).ast_req if ok_flexure else math.inf
    as_l = max(as_flex_l, sl.min_steel(B, D, fy))
    as_b = max(as_flex_b, sl.min_steel(L, D, fy))
    s_max_l, s_max_b = sl.max_spacing_main(d_l), sl.max_spacing_main(d_b)
    if not ok_flexure:
        nan = math.nan
        return Trial(D, dia, d_l, d_b, m_l / 1e6, m_b / 1e6, as_l, as_b, as_flex_l, as_flex_b, nan, 0, 0, 0, nan, nan, 0, 0, nan, nan, nan, nan,
                     nan, nan, nan, nan, nan, nan, nan, False, False, False, False, False)
    s_l, n_l, ap_l = bars_across(as_l, B, dia, s_max_l, cover)
    # Cl. 34.3.1(b): in the short direction, 2/(beta + 1) of the steel in a central band of width B
    n_band, s_band, n_out, s_out, ap_b = bars_short_direction(as_b, L, B, dia, s_max_b, cover)
    ok_spacing = min(s_l, s_band, s_out if n_out else s_band) >= PRACTICAL_MIN_SPACING - 1e-9 and min(s_l, s_band, s_out if n_out else s_band) - dia >= \
        is456.min_clear_bar_spacing_horizontal(dia, inp.max_aggregate_mm) - 1e-9
    # one-way shear at d from the column faces, Cl. 34.2.4.1(a)
    v1_l = q * B * max(a_l - d_l, 0.0)
    v1_b = q * L * max(a_b - d_b, 0.0)
    tau1_l, tau1_b = v1_l / (B * d_l), v1_b / (L * d_b)
    tc_l = is456.tau_c(fck, 100.0 * ap_l / (B * d_l))
    tc_b = is456.tau_c(fck, 100.0 * ap_b / (L * d_b))
    # punching at d/2 from the faces, Cl. 31.6.1 with the average effective depth
    d_avg = (d_l + d_b) / 2.0
    b0 = 2.0 * ((bc + d_avg) + (dc + d_avg))
    vp = q * (L * B - (bc + d_avg) * (dc + d_avg))
    tau_p = vp / (b0 * d_avg)
    ks = min(0.5 + min(bc, dc) / max(bc, dc), 1.0)
    tau_p_allow = ks * 0.25 * math.sqrt(fck)
    ok_shear = tau1_l <= tc_l + 1e-12 and tau1_b <= tc_b + 1e-12 and tau_p <= tau_p_allow + 1e-12
    # Cl. 34.2.4.3: the bars develop their stress within the shorter projection beyond the column face,
    # straight or, where that is too short, with a 90 degree bend at the end worth 8 diameters (Cl. 26.2.2.1(b))
    ld = is456.development_length(dia, fck, fy)
    straight = min(a_l, a_b) - cover
    ok_anchorage = ld <= straight + BEND_90_VALUE * dia + 1e-9
    bent_ends = ld > straight + 1e-9
    return Trial(D, dia, d_l, d_b, m_l / 1e6, m_b / 1e6, as_l, as_b, as_flex_l, as_flex_b, s_l, n_l, n_band, n_out, s_band, s_out, ap_l, ap_b,
                 v1_l / 1e3, v1_b / 1e3, tau1_l, tau1_b, tc_l, tc_b, vp / 1e3, b0, tau_p, tau_p_allow, ks, ok_flexure, ok_shear, ok_spacing, ok_anchorage,
                 bent_ends)


def select_section(inp: FootingInput, L: float, B: float, cover: float, qu: float) -> tuple[Trial | None, bool]:
    """The least depth, then the smallest bar, that passes; and whether development length alone blocked a design.

    Straight bars at any depth come first; bent ends only where no straight bar can develop within the projection.
    An entered depth is checked as it is: the trial with the largest bar is returned whatever its result, unless
    the section needs compression steel.
    """
    dias = [inp.bar_dia_mm] if inp.bar_dia_mm else list(FOOTING_BAR_DIAMETERS)
    depths = [float(inp.depth_mm)] if inp.depth_mm else [float(d) for d in range(300, 3001, int(STEP))]
    anchorage_blocked = False
    for allow_bent in (False, True):
        for D in depths:
            for dia in dias:
                t = trial(inp, L, B, D, dia, cover, qu)
                anchored = t.ok_anchorage and (allow_bent or not t.bent_ends)
                if t.ok_flexure and t.ok_spacing and anchored and (t.ok_shear or inp.depth_mm):
                    return t, anchorage_blocked
                if t.ok_flexure and t.ok_spacing and t.ok_shear and not t.ok_anchorage:
                    anchorage_blocked = True
                if inp.depth_mm and allow_bent and t.ok_flexure and dia == dias[-1]:
                    return t, anchorage_blocked
    return None, anchorage_blocked


def enlarge_plan(L: float, B: float, bc: float, dc: float) -> tuple[float, float]:
    """The next plan with equal projections, 25 mm more than the shorter one, rounded up to 50 mm and never smaller."""
    a = min((L - dc) / 2.0, (B - bc) / 2.0) + STEP / 2
    return max(L, math.ceil((dc + 2 * a) / STEP - 1e-9) * STEP), max(B, math.ceil((bc + 2 * a) / STEP - 1e-9) * STEP)


def effective_cover(inp: FootingInput) -> float:
    if inp.clear_cover_mm is not None:
        return inp.clear_cover_mm
    return max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure))


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def design_footing(inp: FootingInput) -> dict[str, Any]:
    from app.modules.structural.domain import footing_detailing

    sheet = CalcSheet()
    fck, fy = float(inp.fck), float(inp.fy)
    bc, dc = inp.column_width_mm, inp.column_depth_mm
    cover = effective_cover(inp)

    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.step(f"{REF}, Cl. 26.4.2.2 and Table 16" if inp.clear_cover_mm is None else "Input",
               "Clear cover: 50 mm for footings, and not less than Table 16", "c", "", cover, "mm", 0)
    sheet.check("cover", f"{REF}, Cl. 26.4.2.2", "Cover in a footing", "c", cover, ">=", "c_min",
                max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure)), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ plan size
    sheet.section("2. Plan size")
    p_gross = inp.p_service_kn * (1 + inp.self_weight_pct / 100.0)
    sheet.step("Input", "Service load and own-weight allowance", "P (1 + alpha)", f"{_n(inp.p_service_kn, 1)} x (1 + {_n(inp.self_weight_pct, 0)}/100)",
               p_gross, "kN", 1)
    sheet.step("Statics", "Area needed for the axial load alone", "A_req = P (1 + alpha) / q_safe", f"{_n(p_gross, 1)} / {_n(inp.sbc_kn_m2, 0)}",
               p_gross / inp.sbc_kn_m2, "m2", 3)
    if inp.length_mm is None:
        L, B = size_plan(inp)
        if math.isinf(L):
            return _stopped(sheet, "No footing up to 20 m keeps the pressure within the safe bearing pressure without losing contact: "
                                   "check the loads, the moments and the bearing pressure.")
        sheet.step("Selected", "Equal projections from the column faces, in 50 mm steps, smallest that keeps the pressure within limits",
                   "L x B", "", f"{_n(L, 0)} x {_n(B, 0)}", "mm")
    else:
        L, B = float(inp.length_mm), float(inp.width_mm or 0)
        sheet.step("Input", "Plan size", "L x B", "", f"{_n(L, 0)} x {_n(B, 0)}", "mm")
    chosen, anchorage_blocked = select_section(inp, L, B, cover, factored_pressure(inp, L / 1000, B / 1000))
    if chosen is None and anchorage_blocked and inp.length_mm is None:
        # A small footing on strong soil: the bars cannot develop their stress within the projections even with
        # end bends, so the plan grows beyond what the bearing pressure needs (the pressure only falls).
        L0, B0 = L, B
        while chosen is None and anchorage_blocked and min(L - dc, B - bc) / 2 < MAX_PROJECTION:
            L, B = enlarge_plan(L, B, bc, dc)
            chosen, anchorage_blocked = select_section(inp, L, B, cover, factored_pressure(inp, L / 1000, B / 1000))
        if chosen is not None:
            sheet.step(f"{REF}, Cl. 34.2.4.3 and 26.2.1", "Enlarged, equal projections in 50 mm steps, until the bars can develop "
                       "their stress within the projections (with end bends where needed)", "L x B",
                       f"from {_n(L0, 0)} x {_n(B0, 0)}", f"{_n(L, 0)} x {_n(B, 0)}", "mm")
            sheet.flag("info", f"The plan is {_n(L, 0)} x {_n(B, 0)} mm, larger than the {_n(L0, 0)} x {_n(B0, 0)} mm the bearing pressure "
                               "needs, so that the bars can be anchored within the projections.")
    pr = service_pressures(inp, L / 1000, B / 1000)
    sheet.step("Statics", "Service pressures with the moments", "q = P (1 + alpha)/A +/- 6 M_L/(B L^2) +/- 6 M_B/(L B^2)",
               f"A = {_n(L * B / 1e6, 3)} m2", f"{_n(pr.q_max, 1)}, {_n(pr.q_min, 1)}", "kN/m2")
    sheet.check("bearing_soil", "Soil", "Largest pressure within the safe bearing pressure", "q_max", pr.q_max, "<=", "q_safe", inp.sbc_kn_m2, "kN/m2", 1)
    sheet.check("contact", "Soil", "No loss of contact (smallest pressure not negative)", "q_min", pr.q_min, ">=", "0", 0.0, "kN/m2", 1, ratio=False)
    qu = factored_pressure(inp, L / 1000, B / 1000)
    sheet.step(f"{REF}, Table 18", "Largest factored net upward pressure, from the column load only, taken as uniform",
               "q_u = gamma_f (P/A + 6 M_L/(B L^2) + 6 M_B/(L B^2))", f"gamma_f = {_n(inp.load_factor)}", qu, "kN/m2", 1)

    # ------------------------------------------------------------------ depth and bars
    if chosen is None:
        if inp.depth_mm:
            message = "The depth entered needs compression steel at the column face: increase it or leave it blank."
        elif anchorage_blocked:
            message = ("The projections beyond the column are too short to develop even 10 mm bars with end bends (Cl. 34.2.4.3): "
                       "enter a larger length and width, or leave them blank.")
        else:
            message = "No depth up to 3 m with bars of 10 to 25 mm carries the moments and shears: check the loads and the plan size."
        return _stopped(sheet, message)
    t = chosen
    D = t.D
    a_l, a_b = (L - dc) / 2.0, (B - bc) / 2.0

    sheet.section("3. Bending at the column faces")
    sheet.step("Selected" if not inp.depth_mm else "Input",
               "Depth: the least in 50 mm steps that needs no compression steel and no shear steel" if not inp.depth_mm else "Depth", "D", "", D, "mm", 0)
    sheet.check("edge", f"{REF}, Cl. 34.1.2", "Thickness at the edge of a footing on soil", "D", D, ">=", "D_edge,min", EDGE_MIN, "mm", 0, ratio=False)
    sheet.step("Geometry", f"Effective depths with T{t.dia}: bars along L (outer), bars along B (inner)", "d_L, d_B",
               f"{_n(D, 0)} - {_n(cover, 0)} - {t.dia}/2; d_L - {t.dia}", f"{_n(t.d_l, 1)}, {_n(t.d_b, 1)}", "mm")
    sheet.step(f"{REF}, Cl. 34.2.3.2", "Moment at the face of the column, bars along L (projection a_L, over width B)", "M_L = q_u B a_L^2 / 2",
               f"{_n(qu, 1)} x {_n(B / 1000, 3)} x {_n(a_l / 1000, 3)}^2 / 2", t.m_l, "kN m", 2)
    sheet.step(f"{REF}, Cl. 34.2.3.2", "Moment at the face of the column, bars along B (projection a_B, over length L)", "M_B = q_u L a_B^2 / 2",
               f"{_n(qu, 1)} x {_n(L / 1000, 3)} x {_n(a_b / 1000, 3)}^2 / 2", t.m_b, "kN m", 2)
    for name, m, b_w, d, asf, asr in (("L", t.m_l, B, t.d_l, t.as_flex_l, t.as_l), ("B", t.m_b, L, t.d_b, t.as_flex_b, t.as_b)):
        mu_lim = is456.limiting_moment(fck, fy, b_w, d) / 1e6
        sheet.check(f"mulim_{name}", f"{REF}, Annex G-1.1(c)", f"Bars along {name}: no compression steel needed", "M", m, "<=", "M_u,lim", mu_lim, "kN m", 2)
        sheet.step(f"{REF}, Annex G-1.1(b)", f"Bars along {name}: steel for the moment, width {_n(b_w, 0)}", "A_s", f"d = {_n(d, 1)}", asf, "mm2", 0)
        sheet.step(f"{REF}, Cl. 26.5.2.1", f"Bars along {name}: steel required, not less than {'0.15' if fy <= 250 else '0.12'} percent", "A_s,req", "",
                   asr, "mm2", 0)
    sheet.section("4. Reinforcement")
    beta = L / B
    sheet.step("Selected", f"Bars along L, spread uniformly across the width: {t.n_l} T{t.dia} at {t.s_l:.0f}", "A_s,prov", "", t.as_prov_l, "mm2", 0)
    sheet.check("as_l", f"{REF}, Cl. 34.3.1(a)", "Bars along L: steel provided", "A_s,req", t.as_l, "<=", "A_s,prov", t.as_prov_l, "mm2", 0)
    sheet.step(f"{REF}, Cl. 34.3.1(b)", "Bars along B: share in the central band of width B", "2 / (beta + 1)", f"beta = L/B = {_n(beta, 3)}",
               2 / (beta + 1), "", 3)
    sheet.step("Selected", f"Bars along B: {t.n_b_band} T{t.dia} at {t.s_b_band:.0f} in the central band"
               + (f", {t.n_b_outer} T{t.dia} at {t.s_b_outer:.0f} in each outer part" if t.n_b_outer else ""), "A_s,prov", "", t.as_prov_b, "mm2", 0)
    sheet.check("as_b", f"{REF}, Cl. 34.3.1(b)", "Bars along B: steel provided", "A_s,req", t.as_b, "<=", "A_s,prov", t.as_prov_b, "mm2", 0)
    band_req = t.as_b * 2 / (beta + 1)
    sheet.check("band", f"{REF}, Cl. 34.3.1(b)", "Bars along B: steel in the central band", "A_s,band,req", band_req, "<=", "A_s,band",
                t.n_b_band * bar_area(t.dia), "mm2", 0)
    s_max = sl.max_spacing_main(t.d_b)
    sheet.check("spacing", f"{REF}, Cl. 26.3.3(b)", "Spacing of bars", "s", max(t.s_l, t.s_b_band, t.s_b_outer), "<=", "s_max", s_max, "mm", 0)
    ld = is456.development_length(t.dia, fck, fy)
    avail = min(a_l, a_b) - cover
    sheet.step(f"{REF}, Cl. 26.2.1", f"Development length of T{t.dia}", "L_d", "", ld, "mm", 0)
    if t.bent_ends:
        sheet.step(f"{REF}, Cl. 26.2.2.1(b)", "Straight length too short: bars bent up 90 degrees at the ends, the bend worth 8 diameters",
                   "a - c + 8 d_b", f"{_n(avail, 0)} + 8 x {t.dia}", avail + BEND_90_VALUE * t.dia, "mm", 0)
        sheet.check("anchorage", f"{REF}, Cl. 34.2.4.3, 26.2.2.1(b)", "Bars developed beyond the face of the column, with end bends",
                    "L_d", ld, "<=", "a - c + 8 d_b", avail + BEND_90_VALUE * t.dia, "mm", 0)
    else:
        sheet.check("anchorage", f"{REF}, Cl. 34.2.4.3", "Bars developed beyond the face of the column (shorter projection, less cover)",
                    "L_d", ld, "<=", "a - c", avail, "mm", 0)

    sheet.section("5. Shear")
    for name, v, tau, tc, d in (("L", t.v1_l, t.tau1_l, t.tc_l, t.d_l), ("B", t.v1_b, t.tau1_b, t.tc_b, t.d_b)):
        a = a_l if name == "L" else a_b
        width = B if name == "L" else L
        sheet.step(f"{REF}, Cl. 34.2.4.1(a)", f"One-way shear for bars along {name}, at d from the face", f"V_{name} = q_u x {_n(width / 1000, 3)} x (a - d)",
                   f"{_n(qu, 1)} x {_n(width / 1000, 3)} x ({_n(a / 1000, 3)} - {_n(d / 1000, 3)})", v, "kN", 1)
        sheet.check(f"shear_{name}", f"{REF}, Cl. 34.2.4.1(a), Table 19", f"One-way shear, bars along {name}", "tau_v", tau, "<=", "tau_c", tc, "N/mm2", 3)
    sheet.step(f"{REF}, Cl. 31.6.1", "Punching: perimeter at d/2 from the column faces", "b_0 = 2 [(b_c + d) + (D_c + d)]",
               f"d = {_n((t.d_l + t.d_b) / 2, 1)}", t.b0, "mm", 0)
    sheet.step(f"{REF}, Cl. 31.6.1", "Punching shear: the load outside the perimeter", "V_p = q_u [L B - (b_c + d)(D_c + d)]", "", t.vp, "kN", 1)
    sheet.step(f"{REF}, Cl. 31.6.3.1", "Allowable punching stress", "k_s 0.25 sqrt(f_ck), k_s = 0.5 + beta_c <= 1",
               f"beta_c = {_n(min(bc, dc) / max(bc, dc), 3)}", t.tau_p_allow, "N/mm2", 3)
    sheet.check("punching", f"{REF}, Cl. 31.6.3", "Punching shear", "tau_v", t.tau_p, "<=", "k_s tau_c", t.tau_p_allow, "N/mm2", 3)

    sheet.section("6. Transfer of load at the base of the column")
    pu = inp.load_factor * inp.p_service_kn
    # A_1: the lower base of the largest frustum, similar to the column and wholly within the footing, sides 1 vertical
    # to 2 horizontal, so each side grows by at most 2 D; sqrt(A_1/A_2) is then the scale factor of that base.
    ratio = min(L / dc, B / bc, 1.0 + 4.0 * D / max(bc, dc), 2.0)
    bearing_allow = 0.45 * fck * ratio
    sigma = pu * 1e3 / (bc * dc)
    sheet.step(f"{REF}, Cl. 34.4", "Bearing stress on the footing under the column", "sigma = P_u / (b_c D_c)",
               f"{_n(pu, 1)} x 10^3 / ({_n(bc, 0)} x {_n(dc, 0)})", sigma, "N/mm2", 2)
    sheet.step(f"{REF}, Cl. 34.4", "Allowable bearing stress; A_1 within the footing at a slope of 1 in 2, sqrt(A_1/A_2) not more than 2",
               "0.45 f_ck sqrt(A_1/A_2)", f"sqrt(A_1/A_2) = min(L/D_c, B/b_c, 1 + 4 D/max(b_c, D_c), 2) = {_n(ratio, 3)}",
               bearing_allow, "N/mm2", 2)
    sheet.check("bearing", f"{REF}, Cl. 34.4", "Bearing at the base of the column", "sigma", sigma, "<=", "sigma_allow", bearing_allow, "N/mm2", 2)
    if sigma > bearing_allow:
        excess = (sigma - bearing_allow) * bc * dc / 1e3
        sheet.flag("warning", f"Bearing under the column exceeds the allowable by {excess:.0f} kN: carry the excess on column bars or dowels "
                              "continued into the footing, or raise the concrete grade.", f"{REF}, Cl. 34.4")
    dowels = 0.005 * bc * dc
    sheet.step(f"{REF}, Cl. 34.4.3", "Column bars or dowels continued into the footing, at least 0.5 percent of the column", "A_s,dowel,min", "",
               dowels, "mm2", 0)

    # ------------------------------------------------------------------ flags and outputs
    if inp.m_l_service_knm or inp.m_b_service_knm:
        sheet.flag("info", "The largest factored pressure is applied over the whole footing for bending and shear, which is on the safe side with moments.")
    sheet.flag("info", "One-way shear uses tau_c of Table 19 without the enhancement for slabs, which is on the safe side.")
    if inp.depth_mm and not t.ok_shear:
        sheet.flag("warning", "The depth entered fails a shear check: increase it, or leave it blank for the engine to choose.")
    reinforcement = {
        "dia": t.dia, "cover": cover, "L": L, "B": B, "D": D, "bent_ends": t.bent_ends,
        "along_l": {"count": t.n_l, "spacing": t.s_l, "area": round(t.as_prov_l, 1), "label": f"{t.n_l}-T{t.dia} @ {t.s_l:.0f}"},
        "along_b": {"band_count": t.n_b_band, "band_spacing": t.s_b_band, "outer_count": t.n_b_outer, "outer_spacing": t.s_b_outer,
                    "area": round(t.as_prov_b, 1), "label": f"{t.n_b_band + 2 * t.n_b_outer}-T{t.dia}" + ("" if t.n_b_outer else f" @ {t.s_b_band:.0f}")},
    }
    bbs = footing_detailing.bar_schedule(inp, reinforcement)
    quantities = footing_detailing.quantities(inp, reinforcement, bbs)
    drawing = footing_detailing.drawing(inp, reinforcement)

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    key_results = [
        {"label": "Size L x B x D", "sym": "", "value": f"{L:.0f} x {B:.0f} x {D:.0f}", "unit": "mm", "dp": 0},
        {"label": "Largest pressure", "sym": "q_max", "value": round(pr.q_max, 1), "unit": "kN/m2", "dp": 1},
        {"label": "Bars along L", "sym": "", "value": reinforcement["along_l"]["label"], "unit": "", "dp": 0},
        {"label": "Bars along B", "sym": "", "value": (f"{t.n_b_band} @ {t.s_b_band:.0f} in band + {2 * t.n_b_outer} @ {t.s_b_outer:.0f} outside"
                                                     if t.n_b_outer else f"{t.n_b_band}-T{t.dia} @ {t.s_b_band:.0f}"),
         "unit": "", "dp": 0},
        {"label": "Punching ratio", "sym": "", "value": round(t.tau_p / t.tau_p_allow, 3), "unit": "", "dp": 3},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
        {"label": "Concrete", "sym": "", "value": quantities["concrete_m3"], "unit": "m3", "dp": 3},
    ]
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok", "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok), "checks_total": len(checks), "max_utilisation": max(utils) if utils else None,
        "key_results": key_results,
        "data": {
            "cover": cover, "L": L, "B": B, "D": D, "dia": t.dia, "d_l": round(t.d_l, 3), "d_b": round(t.d_b, 3),
            "q_max": round(pr.q_max, 6), "q_min": round(pr.q_min, 6), "qu": round(qu, 6),
            "m_l": round(t.m_l, 6), "m_b": round(t.m_b, 6), "as_flex_l": round(t.as_flex_l, 4), "as_flex_b": round(t.as_flex_b, 4),
            "as_l": round(t.as_l, 4), "as_b": round(t.as_b, 4), "as_prov_l": round(t.as_prov_l, 4), "as_prov_b": round(t.as_prov_b, 4),
            "n_l": t.n_l, "s_l": t.s_l, "n_b_band": t.n_b_band, "s_b_band": t.s_b_band, "n_b_outer": t.n_b_outer, "s_b_outer": t.s_b_outer,
            "v1_l": round(t.v1_l, 6), "v1_b": round(t.v1_b, 6), "tau1_l": round(t.tau1_l, 6), "tau1_b": round(t.tau1_b, 6),
            "tc_l": round(t.tc_l, 6), "tc_b": round(t.tc_b, 6), "vp": round(t.vp, 6), "b0": round(t.b0, 4), "tau_p": round(t.tau_p, 6),
            "tau_p_allow": round(t.tau_p_allow, 6), "ks": round(t.ks, 6), "ld": round(ld, 3), "bearing": round(sigma, 6),
            "bearing_allow": round(bearing_allow, 6), "dowels_min": round(dowels, 3), "bent_ends": t.bent_ends,
        },
        "reinforcement": reinforcement, "sheet": sheet.to_dict(), "bbs": bbs, "quantities": quantities, "drawing": drawing, "charts": [],
    }


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS), "status": "stopped", "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok), "checks_total": len(sheet.checks()), "max_utilisation": None, "key_results": [],
        "data": {}, "reinforcement": None, "sheet": sheet.to_dict(), "bbs": None, "quantities": None, "drawing": None, "charts": [],
    }
