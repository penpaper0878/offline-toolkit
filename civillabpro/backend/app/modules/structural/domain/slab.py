"""Solid slab panel to IS 456:2000 (limit state method).

One panel, defined by its two clear spans and the condition of its four edges (continuous over a
support, or discontinuous). When the long span is more than twice the short one the panel spans
one way (Annex D-1.11) and is designed as a strip of the short span: simply supported, or with the
coefficients of Tables 12 and 13 at an end or interior span. Otherwise it spans two ways and the
moments come from Table 26 (corners held down) or Table 27 (simply supported, corners free to lift).

Checks: flexure per metre width (Annex G), minimum steel, bar size and spacing, shear without
shear reinforcement (Cl. 40.2.1.1, k tau_c, and half of Table 20), deflection (Cl. 24.1 note 2
where it applies, otherwise Cl. 23.2.1), torsion steel at corners and edge strips (Annex D).

Worked example (the defaults): corner panel, clear spans 3.3 x 4.5 m on 230 mm beams, D = 150,
M25 / Fe 415, moderate exposure, finishes 1.5 + imposed 3.0 kN/m2. Two-way, Table 26 case 4.
tests/handcheck/check_slab.py reproduces the results independently.
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

ELEMENT_TYPE = "slab"
ENGINE_VERSION = "1.0.0"
CODE_BASIS = ("IS 456:2000", "IS 2502:1963")
REF = is456.CODE

SLAB_BAR_DIAMETERS = (8, 10, 12, 16)
PRACTICAL_MIN_SPACING = 100.0  # mm: closer bars are hard to place and compact around
ABSOLUTE_MIN_SPACING = 75.0

Edge = Literal["continuous", "discontinuous"]
_EDGE_LABELS = {"continuous": "Continuous", "discontinuous": "Discontinuous"}


def _f(default: Any, title: str, group: str, unit: str = "", show_if: dict[str, Any] | None = None, labels: dict[str, str] | None = None,
       **kw: Any) -> Any:
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if show_if:
        extra["show_if"] = show_if
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


class SlabInput(BaseModel):
    """Everything the slab engine reads. Lengths in mm, loads in kN/m2."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("S1", "Panel mark", "Member", min_length=1, max_length=40)
    span_x_mm: float = _f(3300, "Shorter clear span lx", "Geometry", "mm", ge=500, le=12000)
    span_y_mm: float = _f(4500, "Longer clear span ly", "Geometry", "mm", ge=500, le=30000)
    support_width_mm: float = _f(230, "Support width", "Geometry", "mm", ge=100, le=1000, description="Width of the beams or walls at the edges")
    thickness_mm: float = _f(150, "Thickness D", "Geometry", "mm", ge=75, le=500)

    long_edge_1: Edge = _f("discontinuous", "Long edge 1", "Edges", labels=_EDGE_LABELS, description="Edges of length ly carry the short span")
    long_edge_2: Edge = _f("continuous", "Long edge 2", "Edges", labels=_EDGE_LABELS)
    short_edge_1: Edge = _f("discontinuous", "Short edge 1", "Edges", labels=_EDGE_LABELS, description="Edges of length lx carry the long span")
    short_edge_2: Edge = _f("continuous", "Short edge 2", "Edges", labels=_EDGE_LABELS)
    corners_held_down: bool = _f(True, "Corners held down", "Edges",
                                 description="For a panel discontinuous on all four edges: Table 26 if held down, Table 27 if free to lift")

    fck: Literal[20, 25, 30, 35, 40, 45, 50, 55] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in is456.CONCRETE_GRADES})
    fy: Literal[250, 415, 500, 550] = _f(415, "Steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Clear cover", "Materials", "mm", ge=15, le=75, description="Blank: Table 16")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)

    finishes_kn_m2: float = _f(1.5, "Finishes and partitions", "Loading", "kN/m2", ge=0, le=50, description="Characteristic, excluding self-weight")
    live_load_kn_m2: float = _f(3.0, "Imposed load", "Loading", "kN/m2", ge=0, le=50, description="Characteristic, IS 875 (Part 2)")
    include_self_weight: bool = _f(True, "Add self-weight", "Loading")
    unit_weight_kn_m3: float = _f(25, "Unit weight of concrete", "Loading", "kN/m3", ge=20, le=30)
    load_factor: float = _f(1.5, "Load factor", "Loading", "", ge=1.0, le=2.0, description="On dead and imposed load, Table 18")

    bar_dia_mm: Literal[8, 10, 12, 16] | None = _f(None, "Bar size", "Reinforcement", "mm", description="Blank lets the engine choose one size for the panel")

    @model_validator(mode="after")
    def _consistent(self) -> SlabInput:
        if self.span_y_mm < self.span_x_mm:
            raise ValueError("Enter the shorter clear span as lx and the longer as ly.")
        if self.finishes_kn_m2 + self.live_load_kn_m2 <= 0 and not self.include_self_weight:
            raise ValueError("Enter a load, or include the self-weight.")
        return self


@dataclass(frozen=True)
class Location:
    """One reinforcement location: a moment (or a rule) and the bars that resist it."""

    id: str
    label: str
    direction: Literal["x", "y"]  # bars parallel to the short span (x) or to the long span (y)
    layer: Literal["bottom", "top"]
    moment: float | None  # kN m per metre, None for rule-based steel
    d: float  # mm
    as_flex: float  # mm2/m for the moment
    as_min: float  # mm2/m (0 for top steel)
    s_max: float  # mm
    ref: str

    @property
    def as_req(self) -> float:
        return max(self.as_flex, self.as_min)


@dataclass(frozen=True)
class Bars:
    dia: int
    spacing: float
    area: float  # mm2/m


def spacing_for(as_req: float, dia: int, s_max: float) -> Bars:
    """Bars of one size at a spacing in 10 mm steps that provides the area and keeps within the maximum."""
    a = bar_area(dia)
    s_cap = math.floor(s_max / 10.0 + 1e-9) * 10.0
    s_area = math.floor(1000.0 * a / as_req / 10.0 + 1e-9) * 10.0 if as_req > 0 else s_cap
    s = min(s_area, s_cap)
    return Bars(dia, s, 1000.0 * a / s if s > 0 else 0.0)


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def effective_cover(inp: SlabInput) -> float:
    return inp.clear_cover_mm if inp.clear_cover_mm is not None else is456.nominal_cover(inp.exposure)


def design_slab(inp: SlabInput) -> dict[str, Any]:
    from app.modules.structural.domain import slab_detailing

    sheet = CalcSheet()
    D, fck, fy = inp.thickness_mm, float(inp.fck), float(inp.fy)
    lxc, lyc = inp.span_x_mm, inp.span_y_mm
    cover = effective_cover(inp)
    long_disc = [inp.long_edge_1, inp.long_edge_2].count("discontinuous")
    short_disc = [inp.short_edge_1, inp.short_edge_2].count("discontinuous")

    # ------------------------------------------------------------------ materials
    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.step(f"{REF}, Table 16" if inp.clear_cover_mm is None else "Input", "Clear cover", "c", "", cover, "mm", 0)
    sheet.check("cover", f"{REF}, Table 16", "Nominal cover", "c", cover, ">=", "c_nom", is456.nominal_cover(inp.exposure), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ loads (do not depend on the bars)
    w_self = inp.unit_weight_kn_m3 * D / 1000.0 if inp.include_self_weight else 0.0
    gk, qk = inp.finishes_kn_m2 + w_self, inp.live_load_kn_m2
    wd, wl = inp.load_factor * gk, inp.load_factor * qk
    wu = wd + wl

    # ------------------------------------------------------------------ one bar size for the panel
    dias = [inp.bar_dia_mm] if inp.bar_dia_mm else [d for d in SLAB_BAR_DIAMETERS if d <= sl.max_bar_diameter(D)]
    if not dias:
        return _stopped(sheet, "The slab is too thin for 8 mm bars (one-eighth of the thickness, Cl. 26.5.2.2): increase the thickness.")
    chosen: tuple[Any, ...] | None = None
    fallback: tuple[Any, ...] | None = None
    for dia in dias:
        plan = _plan(inp, dia, cover, long_disc, short_disc, wd, wl, wu)
        if plan is None:
            continue
        locs, geo = plan
        bars = {loc.id: spacing_for(loc.as_req, dia, loc.s_max) for loc in locs}
        tightest = min(b.spacing for b in bars.values())
        if tightest >= PRACTICAL_MIN_SPACING:
            chosen = (dia, locs, geo, bars)
            break
        if tightest >= ABSOLUTE_MIN_SPACING:
            fallback = (dia, locs, geo, bars)
    if chosen is None:
        chosen = fallback
    if chosen is None:
        # The moment exceeds the limiting moment, or the bars would be closer than 75 mm.
        _spans_section(sheet, inp, None, long_disc, short_disc)
        return _stopped(sheet, "No bar size up to one-eighth of the thickness carries the moments at 75 mm or more without "
                               "compression steel: increase the thickness or the concrete grade.")
    dia, locs, geo, bars = chosen
    if min(b.spacing for b in bars.values()) < PRACTICAL_MIN_SPACING:
        sheet.flag("warning", "Bars are closer than 100 mm somewhere in the panel: consider a thicker slab.")

    # ------------------------------------------------------------------ spans and coefficients
    _spans_section(sheet, inp, geo, long_disc, short_disc)

    # ------------------------------------------------------------------ loads
    sheet.section("3. Loads")
    if inp.include_self_weight:
        sheet.step("IS 875 (Part 1):1987", "Self-weight", "g_sw = gamma D", f"{_n(inp.unit_weight_kn_m3, 0)} x {_n(D / 1000, 3)}", w_self, "kN/m2", 3)
    sheet.step("Input", "Characteristic dead and imposed load", "g_k, q_k", "", f"{_n(gk, 3)}, {_n(qk, 3)}", "kN/m2")
    sheet.step(f"{REF}, Table 18", "Design load", "w_u = gamma_f (g_k + q_k)", f"{_n(inp.load_factor)} x ({_n(gk, 3)} + {_n(qk, 3)})", wu, "kN/m2", 3)

    # ------------------------------------------------------------------ moments and flexure
    sheet.section("4. Design moments")
    for line in geo["moment_lines"]:
        sheet.step(*line)
    sheet.section("5. Flexure (per metre width)")
    sheet.step("Selected", "Bar size for the panel: the smallest that keeps every spacing at 100 mm or more", "d_b", "", dia, "mm", 0)
    sheet.check("dia_max", f"{REF}, Cl. 26.5.2.2", "Bar diameter not more than one-eighth of the thickness", "d_b", dia, "<=", "D/8", D / 8, "mm", 1)
    sheet.step("Geometry", "Effective depths: short span bottom (outer layer), long span bottom (inner layer), top",
               "d_x, d_y, d_t", f"{_n(D, 0)} - {_n(cover, 0)} - {dia}/2; d_x - {dia}; d_x", f"{_n(geo['d_x'], 1)}, {_n(geo['d_y'], 1)}, {_n(geo['d_x'], 1)}", "mm")
    as_min = sl.min_steel(1000.0, D, fy)
    sheet.step(f"{REF}, Cl. 26.5.2.1", f"Minimum steel ({'0.15' if fy <= 250 else '0.12'} percent of b D)", "A_s,min", "", as_min, "mm2/m", 0)
    for loc in locs:
        b = bars[loc.id]
        if loc.moment is not None:
            mu_lim = is456.limiting_moment(fck, fy, 1000.0, loc.d) / 1e6
            sheet.step(f"{REF}, Annex G-1.1(b)", f"{loc.label}: steel for M = {_n(loc.moment)} kN m/m (M_u,lim = {_n(mu_lim)})",
                       "A_s = 0.5 (f_ck/f_y) [1 - sqrt(1 - 4.6 M / (f_ck b d^2))] b d", f"d = {_n(loc.d, 1)}", loc.as_flex, "mm2/m", 0)
        else:
            rule = "minimum steel" if loc.as_flex == 0 else "rule"
            sheet.step(loc.ref, f"{loc.label}: steel by {rule}", "A_s", "", loc.as_req, "mm2/m", 0)
        sheet.step("Selected", f"{loc.label}: T{dia} at {b.spacing:.0f} mm", "A_s,prov", "", b.area, "mm2/m", 0)
        sheet.check(f"as_{loc.id}", loc.ref, f"{loc.label}: steel provided", "A_s,req", loc.as_req, "<=", "A_s,prov", b.area, "mm2/m", 0)
        sheet.check(f"s_{loc.id}", f"{REF}, Cl. 26.3.3(b)", f"{loc.label}: spacing", "s", b.spacing, "<=", "s_max", loc.s_max, "mm", 0)
    s_tight = min(b.spacing for b in bars.values())
    sheet.check("s_min", f"{REF}, Cl. 26.3.2(a)", "Clear distance between bars", "s - d_b", s_tight - dia, ">=", "s_min",
                is456.min_clear_bar_spacing_horizontal(dia, inp.max_aggregate_mm), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ shear
    sheet.section("6. Shear")
    bottom_x = bars["bottom_x"]
    d_x = geo["d_x"]
    vu = geo["vu"]
    tau_v = vu * 1e3 / (1000.0 * d_x)
    pt = 100.0 * bottom_x.area / (1000.0 * d_x)
    tc = is456.tau_c(fck, pt)
    k = sl.shear_factor_k(D)
    sheet.step(geo["shear_ref"], geo["shear_text"], geo["shear_eq"], geo["shear_sub"], vu, "kN/m", 2)
    sheet.step(f"{REF}, Cl. 40.1", "Nominal shear stress", "tau_v = V_u / (b d)", f"{_n(vu)} x 10^3 / (1000 x {_n(d_x, 1)})", tau_v, "N/mm2", 3)
    sheet.step(f"{REF}, Table 19", "Shear strength of concrete with the bottom steel that runs into the support", "tau_c",
               f"p_t = {_n(pt, 3)} %", tc, "N/mm2", 3)
    sheet.step(f"{REF}, Cl. 40.2.1.1", "Factor for solid slabs by overall depth", "k", f"D = {_n(D, 0)} mm", k, "", 2)
    sheet.check("shear", f"{REF}, Cl. 40.2.1.1", "Shear without shear reinforcement", "tau_v", tau_v, "<=", "k tau_c", k * tc, "N/mm2", 3)
    sheet.check("shear_max", f"{REF}, Cl. 40.2.3.1", "Nominal shear stress in a slab not more than half of Table 20",
                "tau_v", tau_v, "<=", "tau_c,max / 2", is456.tau_c_max(fck) / 2.0, "N/mm2", 3)

    # ------------------------------------------------------------------ deflection
    sheet.section("7. Deflection")
    lx = geo["lx"]
    note2 = (not geo["one_way"]) and lx <= 3500.0 + 1e-9 and inp.live_load_kn_m2 <= 3.0 + 1e-9 and fy <= 415
    all_disc = long_disc == 2 and short_disc == 2
    if note2:
        allow = sl.two_way_span_depth_note2(fy, simply_supported=all_disc)
        sheet.step(f"{REF}, Cl. 24.1, note 2", f"Two-way slab, short span up to 3.5 m, imposed load up to 3 kN/m2: span to overall depth "
                   f"{'35' if all_disc else '40'}{' x 0.8 for Fe 415' if fy > 250 else ''}", "(l_x/D)_allow", "", allow, "", 1)
        sheet.check("deflection", f"{REF}, Cl. 24.1, note 2", "Span to overall depth", "l_x / D", lx / D, "<=", "allowable", allow, "", 2)
        defl = {"method": "24.1 note 2", "ratio": lx / D, "allow": allow, "kt": None}
    else:
        basic = 20.0 if long_disc == 2 else 26.0
        span_factor = 10000.0 / lx if lx > 10000.0 else 1.0
        fs = is456.service_steel_stress(fy, locs[0].as_req, bottom_x.area)
        kt = is456.tension_modification_factor(fs, pt)
        allow = basic * span_factor * kt
        sheet.step(f"{REF}, Cl. 23.2.1(a)", f"Basic span to effective depth ratio ({'simply supported' if long_disc == 2 else 'continuous'} in the short span)",
                   "", "", basic, "", 0)
        if span_factor != 1.0:
            sheet.step(f"{REF}, Cl. 23.2.1(b)", "Reduction for spans above 10 m", "10 / l", f"10 / {_n(lx / 1000, 2)}", span_factor, "", 3)
        sheet.step(f"{REF}, Fig. 4", "Modification factor for tension steel", "k_t", f"f_s = {_n(fs, 1)} N/mm2, p_t = {_n(pt, 3)} %", kt, "", 3)
        sheet.check("deflection", f"{REF}, Cl. 23.2.1", "Span to effective depth", "l_x / d", lx / d_x, "<=", "allowable", allow, "", 2)
        defl = {"method": "23.2.1", "ratio": lx / d_x, "allow": allow, "kt": kt}

    # ------------------------------------------------------------------ detailing
    sheet.section("8. Detailing")
    torsion = geo["torsion"]
    if not geo["one_way"]:
        sheet.step(f"{REF}, Annex D-1.2, D-1.7", "Edge strips of one-eighth of each side take the minimum steel; the moments above apply to the "
                   "middle strips", "b_edge", f"l_x/8 = {_n(lxc / 8, 0)} mm, l_y/8 = {_n(lyc / 8, 0)} mm", "", "")
        if torsion["corners"]:
            sheet.step(f"{REF}, Annex D-1.8, D-1.9", "Torsion steel at corners: in each of four layers, three-quarters of the steel for the "
                       "maximum mid-span moment (half where only one edge is discontinuous), over one-fifth of the short span",
                       "A_t = 0.75 A_s,x+", f"0.75 x {_n(locs[0].as_flex, 0)} (steel for M_x+); extent {_n(torsion['extent'], 0)} mm", torsion["as_full"], "mm2/m", 0)
            tb = bars.get("torsion")
            if tb:
                sheet.step("Selected", f"Torsion steel: T{dia} at {tb.spacing:.0f} mm "
                           f"({', '.join(c['name'] + (' (half)' if c['factor'] < 1 else '') for c in torsion['corners'])})", "A_t,prov", "", tb.area, "mm2/m", 0)
    sheet.step(f"{REF}, Annex D-1.5", "Top steel over continuous edges extends 0.3 of the span from the face of the support", "", "", "", "")
    if long_disc or short_disc:
        sheet.step(f"{REF}, Annex D-1.6", "Top steel at discontinuous edges: half the mid-span steel, extending 0.1 of the span", "", "", "", "")

    # ------------------------------------------------------------------ flags
    if geo["one_way"] and long_disc < 2:
        sheet.flag("info", "Moments and shears from Tables 12 and 13, which assume three or more spans differing by not more than 15 percent "
                           "of the longest, under uniform load (Cl. 22.5.1). Check the adjacent spans.", f"{REF}, Cl. 22.5.1")
    if geo["one_way"] and long_disc == 0:
        sheet.flag("info", "Interior span: the support moment and shear are taken at a support next to the end support, the larger values "
                           "of Tables 12 and 13.")
    if not geo["one_way"] and (long_disc < 2 or short_disc < 2):
        sheet.flag("info", "Where the support moments of adjacent panels differ, Annex D distributes the difference; this panel's moments "
                           "are used as they are.", f"{REF}, Annex D")
    if geo["table"] == "27":
        sheet.flag("info", "Corners are free to lift: Table 27 moments, no torsion steel. Hold the corners down, or check the edge beams for uplift.",
                   f"{REF}, Annex D-2")
    elif not inp.corners_held_down and not geo["one_way"]:
        sheet.flag("info", "Corners free to lift applies only to a panel discontinuous on all four edges (Table 27); with a continuous edge "
                           "the panel is designed with Table 26 as held down, and the corners must be held down.", f"{REF}, Annex D-1")
    sheet.flag("info", "Shear is taken as for a strip spanning the short way, w_u (l_x/2 - d) per metre, which is on the safe side for two-way panels.")

    reinforcement = {
        "dia": dia,
        "cover": cover,
        "one_way": geo["one_way"],
        "locations": {loc.id: {"label": loc.label, "direction": loc.direction, "layer": loc.layer, "spacing": bars[loc.id].spacing,
                               "area": round(bars[loc.id].area, 1), "as_req": round(loc.as_req, 1)} for loc in locs},
        "edges": {"long_edge_1": inp.long_edge_1, "long_edge_2": inp.long_edge_2, "short_edge_1": inp.short_edge_1, "short_edge_2": inp.short_edge_2},
        "torsion": torsion | ({"spacing": bars["torsion"].spacing} if "torsion" in bars else {}),
        "lx": geo["lx"], "ly": geo["ly"],
    }
    bbs = slab_detailing.bar_schedule(inp, reinforcement)
    quantities = slab_detailing.quantities(inp, bbs)
    drawing = slab_detailing.drawing(inp, reinforcement)

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    bx, by = bars["bottom_x"], bars["bottom_y"]
    key_results = [
        {"label": "Panel", "sym": "", "value": "One-way" if geo["one_way"] else f"Two-way, Table {geo['table']}" + (f" case {geo['case']}" if geo["case"] else ""),
         "unit": "", "dp": 0},
        {"label": "Design load", "sym": "w_u", "value": round(wu, 2), "unit": "kN/m2", "dp": 2},
        {"label": "Short span moment", "sym": "M_x", "value": round(locs[0].moment or 0.0, 2), "unit": "kN m/m", "dp": 2},
        {"label": "Short span bottom", "sym": "", "value": f"T{dia} @ {bx.spacing:.0f}", "unit": "", "dp": 0},
        {"label": "Long span bottom" if not geo["one_way"] else "Distribution", "sym": "", "value": f"T{dia} @ {by.spacing:.0f}", "unit": "", "dp": 0},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
        {"label": "Concrete", "sym": "", "value": quantities["concrete_m3"], "unit": "m3", "dp": 3},
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
            "cover": cover, "dia": dia, "d_x": round(geo["d_x"], 3), "d_y": round(geo["d_y"], 3), "lx": round(geo["lx"], 3), "ly": round(geo["ly"], 3),
            "ratio": round(geo["ly"] / geo["lx"], 6), "one_way": geo["one_way"], "table": geo["table"], "case": geo["case"],
            "w_self": round(w_self, 6), "wd": round(wd, 6), "wl": round(wl, 6), "wu": round(wu, 6),
            "coefficients": geo["coefficients"],
            "moments": {loc.id: (round(loc.moment, 6) if loc.moment is not None else None) for loc in locs},
            "as_flex": {loc.id: round(loc.as_flex, 4) for loc in locs},
            "as_req": {loc.id: round(loc.as_req, 4) for loc in locs},
            "spacing": {loc.id: bars[loc.id].spacing for loc in locs},
            "as_min": round(as_min, 4), "vu": round(vu, 6), "tau_v": round(tau_v, 6), "pt": round(pt, 6), "tau_c": round(tc, 6), "k": round(k, 6),
            "defl_method": defl["method"], "defl_ratio": round(defl["ratio"], 6), "defl_allow": round(defl["allow"], 6),
            "torsion_as": round(torsion["as_full"], 4) if torsion["corners"] else None,
        },
        "reinforcement": reinforcement,
        "sheet": sheet.to_dict(),
        "bbs": bbs,
        "quantities": quantities,
        "drawing": drawing,
        "charts": [],
    }


def _plan(inp: SlabInput, dia: int, cover: float, long_disc: int, short_disc: int, wd: float, wl: float, wu: float) -> tuple[list[Location], dict[str, Any]] | None:
    """Spans, moments and steel requirements for one bar size; None when a moment needs compression steel."""
    D, fck, fy = inp.thickness_mm, float(inp.fck), float(inp.fy)
    lxc, lyc, sw = inp.span_x_mm, inp.span_y_mm, inp.support_width_mm
    d_x = D - cover - dia / 2.0  # short span bars in the outer layer
    d_y = d_x - dia
    if d_y <= 0.4 * D:
        return None
    lx = min(lxc + d_x, lxc + sw)  # Cl. 22.2
    ly = min(lyc + d_y, lyc + sw)
    r = ly / lx
    one_way = r > 2.0  # Annex D-1.11
    as_min = sl.min_steel(1000.0, D, fy)
    s_main_x, s_main_y = sl.max_spacing_main(d_x), sl.max_spacing_main(d_y)
    lines: list[tuple[Any, ...]] = []
    locs: list[Location] = []

    def steel(m: float, d: float) -> float | None:
        mu = m * 1e6
        if mu > is456.limiting_moment(fck, fy, 1000.0, d):
            return None
        return is456.design_rectangular(mu, fck, fy, 1000.0, d, 0.0).ast_req

    lxm = lx / 1000.0
    coeffs: dict[str, Any] = {}
    torsion: dict[str, Any] = {"corners": [], "as_full": 0.0, "extent": sl.TORSION_EXTENT * lx}
    if one_way:
        table, case = "12" if long_disc < 2 else "", None
        if long_disc == 2:
            m_pos, m_neg = wu * lxm**2 / 8.0, None
            lines.append(("Statics", "Simply supported strip: mid-span moment", "M_x+ = w_u l_x^2 / 8", f"{_n(wu, 3)} x {_n(lxm, 3)}^2 / 8", m_pos, "kN m/m"))
            vu = wu * (lxc / 2000.0 - d_x / 1000.0)
            shear = (f"{REF}, Cl. 22.6.2.1", "Shear at d from the face of the support", "V_u = w_u (l_xc/2 - d)",
                     f"{_n(wu, 3)} x ({_n(lxc / 2000, 3)} - {_n(d_x / 1000, 3)})")
            coeffs = {"pos": 1 / 8}
        else:
            span = "end_span_middle" if long_disc == 1 else "interior_span_middle"
            cd, cl = sl.TABLE_12[span]
            nd, nl = sl.TABLE_12["support_next_to_end"]
            m_pos = (cd * wd + cl * wl) * lxm**2
            m_neg = (nd * wd + nl * wl) * lxm**2
            name = "end span" if long_disc == 1 else "interior span"
            lines.append((f"{REF}, Table 12", f"Continuous strip, {name}: mid-span moment", "M_x+ = (c_d w_d + c_l w_l) l_x^2",
                          f"({cd:.4f} x {_n(wd, 3)} + {cl:.4f} x {_n(wl, 3)}) x {_n(lxm, 3)}^2", m_pos, "kN m/m"))
            lines.append((f"{REF}, Table 12", "Support moment at the continuous edge (support next to the end support)", "M_x- = (c_d w_d + c_l w_l) l_x^2",
                          f"({nd:.4f} x {_n(wd, 3)} + {nl:.4f} x {_n(wl, 3)}) x {_n(lxm, 3)}^2", m_neg, "kN m/m"))
            sd, sl_ = sl.TABLE_13["next_to_end_outer"] if long_disc == 1 else sl.TABLE_13["next_to_end_inner"]
            vu = (sd * wd + sl_ * wl) * lxm
            shear = (f"{REF}, Table 13", "Shear at the continuous support", "V_u = (c_d w_d + c_l w_l) l_x", f"({sd} x {_n(wd, 3)} + {sl_} x {_n(wl, 3)}) x {_n(lxm, 3)}")
            coeffs = {"pos": [cd, cl], "neg": [nd, nl], "shear": [sd, sl_]}
        as_pos = steel(m_pos, d_x)
        if as_pos is None:
            return None
        locs.append(Location("bottom_x", "Main bars (bottom, short span)", "x", "bottom", m_pos, d_x, as_pos, as_min, s_main_x, f"{REF}, Annex G"))
        locs.append(Location("bottom_y", "Distribution bars (bottom, long span)", "y", "bottom", None, d_y, 0.0, as_min, sl.max_spacing_distribution(d_y),
                             f"{REF}, Cl. 26.5.2.1"))
        if m_neg is not None:
            as_neg = steel(m_neg, d_x)
            if as_neg is None:
                return None
            locs.append(Location("top_x_cont", "Top bars over continuous long edges", "x", "top", m_neg, d_x, as_neg, 0.0, s_main_x, f"{REF}, Annex G"))
        if long_disc:
            locs.append(Location("top_x_disc", "Top bars at discontinuous long edges (half the mid-span steel)", "x", "top", None, d_x,
                                 sl.DISCONTINUOUS_TOP_FRACTION * max(as_pos, as_min), 0.0, s_main_x, f"{REF}, Annex D-1.6 (applied as practice)"))
        return locs, {"d_x": d_x, "d_y": d_y, "lx": lx, "ly": ly, "one_way": True, "table": table, "case": case, "coefficients": coeffs,
                      "moment_lines": lines, "vu": vu, "shear_ref": shear[0], "shear_text": shear[1], "shear_eq": shear[2], "shear_sub": shear[3],
                      "torsion": torsion}

    # two-way
    simple_free = long_disc == 2 and short_disc == 2 and not inp.corners_held_down
    if simple_free:
        c = sl.coefficients_27(r)
        table, case = "27", None
        lines.append((f"{REF}, Annex D-2, Table 27", f"Simply supported, corners free to lift, l_y/l_x = {_n(r, 3)}", "alpha_x, alpha_y", "",
                      f"{c.pos_x:.4f}, {c.pos_y:.4f}", ""))
    else:
        case = sl.case_26(long_disc, short_disc)
        c = sl.coefficients_26(case, r)
        table = "26"
        lines.append((f"{REF}, Annex D-1.1, Table 26", f"Case {case}, {sl.TABLE_26[case].name.lower()}, l_y/l_x = {_n(r, 3)}",
                      "alpha_x-, alpha_x+, alpha_y-, alpha_y+", "",
                      ", ".join("-" if v is None else f"{v:.4f}" for v in (c.neg_x, c.pos_x, c.neg_y, c.pos_y)), ""))
    coeffs = {"neg_x": c.neg_x, "pos_x": c.pos_x, "neg_y": c.neg_y, "pos_y": c.pos_y}
    m = {k: (v * wu * lxm**2 if v is not None else None) for k, v in coeffs.items()}
    for key, label, sym in (("pos_x", "Short span, mid-span", "M_x+"), ("neg_x", "Short span, continuous long edges", "M_x-"),
                            ("pos_y", "Long span, mid-span", "M_y+"), ("neg_y", "Long span, continuous short edges", "M_y-")):
        if m[key] is not None:
            lines.append((f"{REF}, Annex D-1.1", label, f"{sym} = alpha w_u l_x^2", f"{coeffs[key]:.4f} x {_n(wu, 3)} x {_n(lxm, 3)}^2", m[key], "kN m/m"))
    as_px = steel(m["pos_x"], d_x)
    as_py = steel(m["pos_y"], d_y)
    if as_px is None or as_py is None:
        return None
    locs.append(Location("bottom_x", "Short span bottom, middle strip", "x", "bottom", m["pos_x"], d_x, as_px, as_min, s_main_x, f"{REF}, Annex G"))
    locs.append(Location("bottom_y", "Long span bottom, middle strip", "y", "bottom", m["pos_y"], d_y, as_py, as_min, s_main_y, f"{REF}, Annex G"))
    locs.append(Location("bottom_x_edge", "Short span bottom, edge strips", "x", "bottom", None, d_x, 0.0, as_min, s_main_x, f"{REF}, Annex D-1.7"))
    locs.append(Location("bottom_y_edge", "Long span bottom, edge strips", "y", "bottom", None, d_y, 0.0, as_min, s_main_y, f"{REF}, Annex D-1.7"))
    if m["neg_x"] is not None:
        a = steel(m["neg_x"], d_x)
        if a is None:
            return None
        locs.append(Location("top_x_cont", "Top bars over continuous long edges", "x", "top", m["neg_x"], d_x, a, 0.0, s_main_x, f"{REF}, Annex G"))
    if m["neg_y"] is not None:
        # long-span top bars sit in the inner top layer, under the short-span top bars
        a = steel(m["neg_y"], d_y)
        if a is None:
            return None
        locs.append(Location("top_y_cont", "Top bars over continuous short edges", "y", "top", m["neg_y"], d_y, a, 0.0, s_main_y, f"{REF}, Annex G"))
    if long_disc:
        locs.append(Location("top_x_disc", "Top bars at discontinuous long edges (half the mid-span steel)", "x", "top", None, d_x,
                             sl.DISCONTINUOUS_TOP_FRACTION * max(as_px, as_min), 0.0, s_main_x, f"{REF}, Annex D-1.6"))
    if short_disc:
        locs.append(Location("top_y_disc", "Top bars at discontinuous short edges (half the mid-span steel)", "y", "top", None, d_y,
                             sl.DISCONTINUOUS_TOP_FRACTION * max(as_py, as_min), 0.0, s_main_y, f"{REF}, Annex D-1.6"))
    if table == "26":
        edges = {"L1": inp.long_edge_1, "L2": inp.long_edge_2, "S1": inp.short_edge_1, "S2": inp.short_edge_2}
        corners = []
        for le in ("L1", "L2"):
            for se in ("S1", "S2"):
                n_disc = [edges[le], edges[se]].count("discontinuous")
                if n_disc:  # D-1.10: none where both edges are continuous
                    corners.append({"name": f"{le}-{se}", "long": le, "short": se, "factor": 1.0 if n_disc == 2 else 0.5})
        torsion["corners"] = corners
        torsion["as_full"] = sl.TORSION_FRACTION * as_px  # of the area required for the maximum mid-span moment
        if corners:
            locs.append(Location("torsion", "Torsion steel at corners (each of four layers, full corners)", "x", "top", None, d_x,
                                 torsion["as_full"], 0.0, s_main_x, f"{REF}, Annex D-1.8"))
    vu = wu * (lxc / 2000.0 - d_x / 1000.0)
    return locs, {"d_x": d_x, "d_y": d_y, "lx": lx, "ly": ly, "one_way": False, "table": table, "case": case, "coefficients": coeffs,
                  "moment_lines": lines, "vu": vu, "shear_ref": f"{REF}, Cl. 22.6.2.1",
                  "shear_text": "Shear at d from the face of a long edge, as for a strip spanning the short way", "shear_eq": "V_u = w_u (l_xc/2 - d)",
                  "shear_sub": f"{_n(wu, 3)} x ({_n(lxc / 2000, 3)} - {_n(d_x / 1000, 3)})", "torsion": torsion}


def _spans_section(sheet: CalcSheet, inp: SlabInput, geo: dict[str, Any] | None, long_disc: int, short_disc: int) -> None:
    sheet.section("2. Spans and panel type")
    sheet.step("Input", "Clear spans", "l_xc, l_yc", "", f"{_n(inp.span_x_mm, 0)}, {_n(inp.span_y_mm, 0)}", "mm")
    sheet.step("Input", "Discontinuous edges: long, short", "", "", f"{long_disc}, {short_disc}", "")
    if geo is None:
        return
    sheet.step(f"{REF}, Cl. 22.2", "Effective spans: clear span + d, or centre to centre of supports, whichever is less", "l_x, l_y", "",
               f"{_n(geo['lx'], 0)}, {_n(geo['ly'], 0)}", "mm")
    r = geo["ly"] / geo["lx"]
    if geo["one_way"]:
        sheet.step(f"{REF}, Annex D-1.11", "l_y/l_x more than 2: the panel spans one way, across the short span", "l_y / l_x", "", r, "", 3)
    else:
        sheet.step(f"{REF}, Cl. 24.4, Annex D", "l_y/l_x not more than 2: the panel spans two ways", "l_y / l_x", "", r, "", 3)


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS), "status": "stopped", "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok), "checks_total": len(sheet.checks()), "max_utilisation": None, "key_results": [],
        "data": {}, "reinforcement": None, "sheet": sheet.to_dict(), "bbs": None, "quantities": None, "drawing": None, "charts": [],
    }
