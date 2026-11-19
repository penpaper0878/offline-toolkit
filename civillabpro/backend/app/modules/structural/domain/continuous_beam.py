"""Continuous reinforced concrete beam of equal spans to IS 456:2000, by the coefficients of Tables 12 and 13.

One design covers the whole beam: three or more spans of one clear span and one section under uniformly
distributed dead and imposed load (Cl. 22.5.1). Four sections are designed:

* mid-span of the end spans and of the interior spans: bottom steel, with a T or L flange in compression
  where the slab is cast with the beam (Annex G-2);
* the support next to the end support and the other interior supports: top steel, the web as a rectangle,
  with the bottom bars that run into the support as compression steel (Annex G-1).

Shear by Table 13 at d from the face of the support (Cl. 22.6.2.1), deflection by Cl. 23.2.1 for continuous
beams, and the extent of the top bars over each support from the hogging envelope: an elastic analysis of the
arrangements of imposed load of Cl. 22.4.1 places the furthest point of inflection, and the bars run beyond it
by the greatest of d, 12 bar diameters and one sixteenth of the clear span (Cl. 26.2.3.4), and not less than
the development length from the face. The design moments are those of Table 12.

Worked example (the defaults): four spans of 5.0 m clear on 300 mm supports, 300 x 500, M25 / Fe 500,
moderate exposure, DL 25 + LL 15 kN/m plus self-weight. tests/handcheck/check_continuous_beam.py
reproduces the results independently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.engineering import continuous as analysis
from app.engineering import is456
from app.engineering import is456_slabs as tables
from app.engineering.is456 import FlangeKind
from app.engineering.rebar import BarGroup, bar_area
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.beam import (
    _FLANGED,
    SECTION_LABELS,
    Flange,
    _f,
    anchorage_ok,
    effective_cover,
    end_detail,
    flange_steps,
    flanged_flexure_steps,
    flexure_capacity,
    flexure_design,
    other_candidates,
    practical_spacing,
    tension_candidates,
)

ELEMENT_TYPE = "continuous_beam"
ENGINE_VERSION = "1.5.0"
CODE_BASIS = ("IS 456:2000", "SP 16:1980", "IS 2502:1963")
REF = is456.CODE
FIRST_STIRRUP_MM = 50.0


class ContinuousBeamInput(BaseModel):
    """Everything the continuous beam engine reads. Lengths in mm, loads in kN/m."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("CB1", "Member mark", "Member", min_length=1, max_length=40)
    spans: int = _f(4, "Number of spans", "Member", ge=3, le=12, description="Tables 12 and 13 need three or more spans")
    clear_span_mm: float = _f(5000, "Clear span of each span", "Geometry", "mm", ge=1000, le=20000,
                              description="Spans may differ by up to 15 percent of the longest (Cl. 22.5.1): enter the longest")
    support_width_mm: float = _f(300, "Support width", "Geometry", "mm", ge=100, le=2000, description="Along the beam, each support")
    section: Literal["rectangular", "t_beam", "l_beam"] = _f("rectangular", "Section", "Geometry", labels=SECTION_LABELS)
    width_mm: float = _f(300, "Width b", "Geometry", "mm", ge=150, le=2000, description="The web width b_w of a T or L beam")
    depth_mm: float = _f(500, "Overall depth D", "Geometry", "mm", ge=200, le=3000, description="Including the slab for a T or L beam")
    flange_thickness_mm: float = _f(120, "Flange thickness D_f", "Geometry", "mm", _FLANGED, ge=50, le=500, description="The slab thickness")
    flange_width_mm: float = _f(3000, "Flange width available", "Geometry", "mm", _FLANGED, ge=150, le=20000,
                                description="T-beam: spacing of the beams; L-beam: web plus half the clear distance to the next beam")
    isolated_flange: bool = _f(False, "Isolated beam", "Geometry", "", _FLANGED, description="The flange is not part of a continuous slab")
    l0_mm: float | None = _f(None, "Distance between points of zero moment l_0", "Geometry", "mm", _FLANGED, gt=0, le=60000,
                             description="Blank: 0.7 times the effective span (Cl. 23.1.2, note)")

    fck: Literal[20, 25, 30, 35, 40, 45, 50, 55] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in is456.CONCRETE_GRADES})
    fy: Literal[250, 415, 500, 550] = _f(500, "Main steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    fy_stirrup: Literal[250, 415, 500, 550] = _f(500, "Stirrup steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Cover to stirrups", "Materials", "mm", ge=15, le=100, description="Blank takes IS 456 Table 16")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)

    dead_load_kn_m: float = _f(25, "Dead load", "Loading", "kN/m", ge=0, le=5000, description="Characteristic, on every span, excluding self-weight")
    live_load_kn_m: float = _f(15, "Imposed load", "Loading", "kN/m", ge=0, le=5000, description="Characteristic, on any span (Table 12, not fixed)")
    include_self_weight: bool = _f(True, "Add self-weight", "Loading")
    unit_weight_kn_m3: float = _f(25, "Unit weight of concrete", "Loading", "kN/m3", ge=20, le=30, description="IS 875 (Part 1)")
    load_factor: float = _f(1.5, "Load factor", "Loading", "", ge=1.0, le=2.0, description="On DL + LL, IS 456 Table 18")

    main_bar_dia_mm: Literal[12, 16, 20, 25, 32] | None = _f(None, "Main bar size", "Reinforcement", "mm", description="Blank lets the engine choose")
    hanger_bar_dia_mm: Literal[10, 12, 16] = _f(12, "Hanger bar size", "Reinforcement", "mm")
    stirrup_dia_mm: Literal[8, 10, 12] = _f(8, "Stirrup size", "Reinforcement", "mm")
    stirrup_legs: Literal[2, 4] = _f(2, "Stirrup legs", "Reinforcement")

    @model_validator(mode="after")
    def _consistent(self) -> ContinuousBeamInput:
        if self.section != "rectangular":
            if self.flange_thickness_mm > self.depth_mm - 100:
                raise ValueError("The flange must be at least 100 mm thinner than the overall depth of the beam.")
            if self.flange_width_mm <= self.width_mm:
                raise ValueError("The flange width available must be more than the web width.")
        if self.dead_load_kn_m + self.live_load_kn_m <= 0 and not self.include_self_weight:
            raise ValueError("Enter a dead or imposed load, or include the self-weight.")
        return self


# ----------------------------------------------------------------------------- forces


def effective_spans(inp: ContinuousBeamInput, d: float) -> tuple[float, float, str]:
    """Cl. 22.2(b): (end span, interior span, rule). Narrow supports follow 22.2(a)."""
    lc, sw = inp.clear_span_mm, inp.support_width_mm
    if sw <= min(lc / 12.0, 600.0):
        le = min(lc + d, lc + sw)
        return le, le, "a"
    return lc + min(d / 2.0, sw / 2.0), lc, "b"


def design_loads(inp: ContinuousBeamInput) -> tuple[float, float, float]:
    """(self-weight, factored dead, factored imposed) in kN/m."""
    rib = inp.depth_mm - inp.flange_thickness_mm if inp.section != "rectangular" else inp.depth_mm
    w_self = inp.unit_weight_kn_m3 * inp.width_mm * rib * 1e-6 if inp.include_self_weight else 0.0
    g = inp.load_factor
    return w_self, g * (inp.dead_load_kn_m + w_self), g * inp.live_load_kn_m


def span_moment(kind: Literal["end", "interior"], wd: float, wl: float, l_mm: float) -> float:
    """Table 12, kN m: near the middle of the end span, or at the middle of an interior span."""
    cd, cl = tables.TABLE_12["end_span_middle" if kind == "end" else "interior_span_middle"]
    return (cd * wd + cl * wl) * (l_mm / 1000.0) ** 2


def support_moment(kind: Literal["B", "C"], wd: float, wl: float, l1_mm: float, l2_mm: float) -> float:
    """Table 12, kN m, hogging: at the support next to the end support (B) or another interior support (C).

    Where the spans on the two sides differ, the average of the two values (Cl. 22.5.1).
    """
    cd, cl = tables.TABLE_12["support_next_to_end" if kind == "B" else "interior_support"]
    return (cd * wd + cl * wl) * ((l1_mm / 1000.0) ** 2 + (l2_mm / 1000.0) ** 2) / 2.0


def support_shear(kind: str, wd: float, wl: float, l_mm: float) -> float:
    """Table 13, kN: coefficient times the total design load on the span."""
    cd, cl = tables.TABLE_13[kind]
    return (cd * wd + cl * wl) * l_mm / 1000.0


# --------------------------------------------------------------------------- sections


@dataclass(frozen=True)
class SpanSection:
    kind: Literal["end", "interior"]
    bottom: BarGroup
    top: BarGroup  # hangers, or compression steel where the section is doubly reinforced
    d: float
    d_c: float
    ybar: float  # centroid of the bottom bars from the soffit
    clear: float
    gap: float
    l_eff: float
    mu: float  # kN m
    flange: Flange | None
    fl: is456.FlexureDesign
    cap: is456.MomentCapacity


@dataclass(frozen=True)
class SupportSection:
    kind: Literal["B", "C"]
    top: BarGroup
    ybar: float  # centroid of the top bars from the top face
    d: float
    clear: float
    gap: float
    mu: float  # kN m, hogging
    compression: BarGroup  # the bottom bars that run into the support
    d_c: float  # their centroid from the soffit
    fl: is456.FlexureDesign
    cap: is456.MomentCapacity


def make_flange(inp: ContinuousBeamInput, l_eff: float) -> Flange | None:
    if inp.section == "rectangular":
        return None
    kind: FlangeKind = "T" if inp.section == "t_beam" else "L"
    l0 = float(inp.l0_mm) if inp.l0_mm else 0.7 * l_eff  # Cl. 23.1.2, note: continuous beams
    bf = is456.effective_flange_width(kind, l0, inp.width_mm, inp.flange_thickness_mm, inp.flange_width_mm, inp.isolated_flange)
    return Flange(kind, inp.flange_thickness_mm, inp.flange_width_mm, l0, bf, True)


def _anchorage_limits(inp: ContinuousBeamInput, d: float, wd: float, wl: float) -> dict[str, float]:
    """Shears for Cl. 26.2.3.3(c) with the spans of an effective depth d: at the end support, and at the points of inflection, kN."""
    from app.modules.structural.domain import continuous_curtailment as curtail

    le, li, _ = effective_spans(inp, d)
    n = inp.spans
    mom = {"end": span_moment("end", wd, wl, le), "interior": span_moment("interior", wd, wl, li), "b": support_moment("B", wd, wl, le, li),
           "c": support_moment("C", wd, wl, li, li) if n >= 4 else 0.0}
    sh = {"A": support_shear("end_support", wd, wl, le), "B1": support_shear("next_to_end_outer", wd, wl, le),
          "B2": support_shear("next_to_end_inner", wd, wl, li), "C": support_shear("interior_support", wd, wl, li) if n >= 4 else 0.0}
    dg = curtail.diagrams(n, [le / 1000.0] + [li / 1000.0] * (n - 2) + [le / 1000.0], inp.clear_span_mm, wd, wl, mom, sh)
    return {"A": sh["A"], "end": curtail.inflection_shear(dg, "end"), "interior": curtail.inflection_shear(dg, "interior")}


def anchorable(inp: ContinuousBeamInput, kind: Literal["end", "interior"], g: BarGroup, d: float, flg: Flange | None, cover: float,
               limits: dict[str, float]) -> bool:
    """Cl. 26.2.3.3(c) for bottom bars: at the end support (1.3 M_1/V + L_0, a U-hook allowed) and at the points of inflection
    (M_1/V + max(d, 12 phi)). The shears carry a 2 percent margin, as the final check uses the spans of the bars chosen."""
    fck, fy = float(inp.fck), float(inp.fy)
    bf = flg.bf if flg is not None else None
    m1 = is456.moment_at_design_stress(fck, fy, inp.width_mm, d, g.area, bf, flg.df if flg is not None else 0.0) / 1e6
    if kind == "end":
        if end_detail(inp.support_width_mm, cover, g.dia, fck, fy, m1, 1.02 * limits["A"], "straight") is None:
            return False
    return anchorage_ok(g.dia, fck, fy, m1, 1.02 * limits[kind], max(d, 12.0 * g.dia), False)[0]


def select_span(inp: ContinuousBeamInput, cover: float, kind: Literal["end", "interior"], wd: float, wl: float,
                anchorage: bool = True) -> SpanSection | None:
    """Least steel at mid-span: bottom bars in one or two layers and top bars in one, each judged at its own depth; bars that
    could not be anchored at the end support or the points of inflection (Cl. 26.2.3.3(c)) are passed over."""
    limits_cache: dict[float, dict[str, float]] = {}
    b, D, fy, dst = inp.width_mm, inp.depth_mm, float(inp.fy), inp.stirrup_dia_mm
    as_max = is456.max_steel(b, D)
    others = sorted(other_candidates(inp, cover), key=lambda g: g.area)
    best: tuple[tuple[float, int, int], SpanSection] | None = None
    for ten, ybar, clear, gap in sorted(tension_candidates(inp, cover), key=lambda c: c[0].area):
        if best is not None and ten.area + others[0].area > best[0][0] + 1e-6:
            break
        d = D - ybar
        if ten.area > as_max or ten.area < is456.min_tension_steel(b, d, fy):
            continue
        le, li, _ = effective_spans(inp, d)
        l_eff = le if kind == "end" else li
        mu = span_moment(kind, wd, wl, l_eff)
        flg = make_flange(inp, l_eff)
        for oth in others:
            if best is not None and ten.area + oth.area > best[0][0] + 1e-6:
                break
            d_c = cover + dst + oth.dia / 2.0
            fl = flexure_design(inp, flg, mu * 1e6, d, d_c)
            if ten.area < fl.ast_req or oth.area < fl.asc_req:
                continue
            cap = flexure_capacity(inp, flg, d, ten.area, oth.area, d_c)
            if cap.limited or cap.mu < mu * 1e6:
                continue
            if anchorage:
                lim = limits_cache.get(round(d, 1)) or limits_cache.setdefault(round(d, 1), _anchorage_limits(inp, d, wd, wl))
                if not anchorable(inp, kind, ten, d, flg, cover, lim):
                    continue
            key = (round(ten.area + oth.area, 3), len(ten.layers), ten.count + oth.count)
            if best is None or key < best[0]:
                best = (key, SpanSection(kind, ten, oth, d, d_c, ybar, clear, gap, l_eff, mu, flg, fl, cap))
    return best[1] if best else None


def select_support(inp: ContinuousBeamInput, cover: float, kind: Literal["B", "C"], mu: float, comp: BarGroup, comp_y: float) -> SupportSection | None:
    """Least top steel over a support, the web as a rectangle, with the bottom bars ``comp`` as compression steel."""
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    as_max = is456.max_steel(b, D)
    cands = sorted(tension_candidates(inp, cover), key=lambda c: (round(c[0].area, 3), len(c[0].layers), c[0].count))
    for top, ybar, clear, gap in cands:
        d = D - ybar
        if top.area > as_max or top.area < is456.min_tension_steel(b, d, fy) or d <= comp_y:
            continue
        fl = is456.design_rectangular(mu * 1e6, fck, fy, b, d, comp_y)
        if top.area < fl.ast_req or comp.area < fl.asc_req:
            continue
        cap = is456.moment_capacity(fck, fy, b, d, top.area, comp.area, comp_y)
        if cap.limited or cap.mu < mu * 1e6:
            continue
        return SupportSection(kind, top, ybar, d, clear, gap, mu, comp, comp_y, fl, cap)
    return None


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


# ------------------------------------------------------------------------------ design


def design_continuous_beam(inp: ContinuousBeamInput) -> dict[str, Any]:
    from app.modules.structural.domain import continuous_beam_detailing as detailing

    sheet = CalcSheet()
    b, D, fck, fy, n = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy), inp.spans
    lc, sw, dst, legs = inp.clear_span_mm, inp.support_width_mm, inp.stirrup_dia_mm, inp.stirrup_legs
    cover = effective_cover(inp)
    fyv = is456.shear_fy(inp.fy_stirrup)
    flanged = inp.section != "rectangular"
    bw = "b_w" if flanged else "b"
    has_c = n >= 4

    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.step(f"{REF}, Cl. 40.4", "Steel strength taken for stirrups (not above 415)", "f_yv", f"min({inp.fy_stirrup}, 415)", fyv, "N/mm2", 0)
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.check("cover", f"{REF}, Table 16", "Nominal cover to all reinforcement", "c", cover, ">=", "c_nom", is456.nominal_cover(inp.exposure), "mm", 0,
                ratio=False)

    w_self, wd, wl = design_loads(inp)
    d_est = D - cover - dst - (inp.main_bar_dia_mm or 20) / 2.0
    le0, _, _ = effective_spans(inp, d_est)
    if le0 / D < 2.5:
        return _stopped(sheet, "The effective span is less than 2.5 times the overall depth: this is a continuous deep beam "
                               "(IS 456:2000, Cl. 29), which this engine does not design.")
    end = select_span(inp, cover, "end", wd, wl)
    inner = select_span(inp, cover, "interior", wd, wl)
    if end is None or inner is None:
        if all(select_span(inp, cover, k, wd, wl, anchorage=False) for k in ("end", "interior")):
            return _stopped(sheet, "The bottom bars that carry the span moments are too large to be anchored at the end supports or the points "
                                   "of inflection (Cl. 26.2.3.3(c)): use a smaller bar size, wider supports or a deeper section.")
        return _stopped(sheet, "No arrangement of up to two layers of bars carries the span moment within the steel limits of "
                               "Cl. 26.5.1: increase the section, the concrete grade or the bar size.")
    comp_b = end if end.bottom.area <= inner.bottom.area else inner  # the lighter bottom bars reach support B from both sides
    mb = support_moment("B", wd, wl, end.l_eff, inner.l_eff)
    sup_b = select_support(inp, cover, "B", mb, comp_b.bottom, comp_b.ybar)
    mc = support_moment("C", wd, wl, inner.l_eff, inner.l_eff) if has_c else 0.0
    sup_c = select_support(inp, cover, "C", mc, inner.bottom, inner.ybar) if has_c else None
    if sup_b is None or (has_c and sup_c is None):
        return _stopped(sheet, "No arrangement of top bars carries the support moment with the bottom bars as compression steel "
                               "within Cl. 26.5.1: increase the depth of the section or the concrete grade.")

    # ------------------------------------------------------------------ geometry and forces
    sheet.section("2. Section, spans and loads")
    if flanged:
        sheet.step("Input", f"{SECTION_LABELS[inp.section]}: web width, overall depth, flange thickness", "b_w x D, D_f", "",
                   f"{_n(b, 0)} x {_n(D, 0)}, {_n(inp.flange_thickness_mm, 0)}", "mm")
    else:
        sheet.step("Input", "Width and overall depth", "b x D", "", f"{_n(b, 0)} x {_n(D, 0)}", "mm")
    sheet.step("Input", f"{n} spans of equal clear span on supports {_n(sw, 0)} mm wide", "n x l_c", "", f"{n} x {_n(lc, 0)}", "mm")
    sheet.step(f"{REF}, Cl. 22.5.1", "Three or more spans, differing by not more than 15 percent, uniform load: Tables 12 and 13 apply",
               "n", "", n, "", 0)
    rule = effective_spans(inp, end.d)[2]
    if rule == "a":
        sheet.step(f"{REF}, Cl. 22.2(b) and (a)", "Supports not wider than l_c/12 or 600 mm: clear span + d, not more than centre to centre",
                   "l = min(l_c + d, l_c + w_s)", f"d = {_n(end.d, 1)} (end), {_n(inner.d, 1)} (interior)",
                   f"{_n(end.l_eff, 0)}, {_n(inner.l_eff, 0)}", "mm")
    else:
        sheet.step(f"{REF}, Cl. 22.2(b)(2)", "End span, wide supports: clear span + the lesser of d/2 and half the end support",
                   "l_1 = l_c + min(d/2, w_s/2)", f"{_n(lc, 0)} + min({_n(end.d / 2, 1)}, {_n(sw / 2, 0)})", end.l_eff, "mm", 0)
        sheet.step(f"{REF}, Cl. 22.2(b)(1)", "Interior spans, wide supports: the clear span", "l_2 = l_c", "", inner.l_eff, "mm", 0)
    if inp.include_self_weight:
        if flanged:
            sheet.step("IS 875 (Part 1):1987", "Self-weight of the rib below the slab", "w_sw = gamma b_w (D - D_f)", "", w_self, "kN/m", 3)
        else:
            sheet.step("IS 875 (Part 1):1987", "Self-weight", "w_sw = gamma b D",
                       f"{_n(inp.unit_weight_kn_m3, 0)} x {_n(b / 1000, 3)} x {_n(D / 1000, 3)}", w_self, "kN/m", 3)
    sheet.step(f"{REF}, Table 18", "Factored dead load (fixed)", "w_d = gamma_f (DL + w_sw)",
               f"{_n(inp.load_factor)} x ({_n(inp.dead_load_kn_m)} + {_n(w_self, 3)})", wd, "kN/m", 3)
    sheet.step(f"{REF}, Table 18", "Factored imposed load (not fixed)", "w_l = gamma_f LL", f"{_n(inp.load_factor)} x {_n(inp.live_load_kn_m)}",
               wl, "kN/m", 3)

    sheet.section("3. Moments and shears (Tables 12 and 13)")
    sheet.step(f"{REF}, Table 12", "Near the middle of the end span", "M_1 = (w_d/12 + w_l/10) l_1^2",
               f"({_n(wd, 3)}/12 + {_n(wl, 3)}/10) x {_n(end.l_eff / 1000, 3)}^2", end.mu, "kN m")
    sheet.step(f"{REF}, Table 12", "At the support next to the end support (hogging), the average over the two spans",
               "M_B = (w_d/10 + w_l/9)(l_1^2 + l_2^2)/2",
               f"({_n(wd, 3)}/10 + {_n(wl, 3)}/9) x ({_n(end.l_eff / 1000, 3)}^2 + {_n(inner.l_eff / 1000, 3)}^2)/2", mb, "kN m")
    sheet.step(f"{REF}, Table 12", "At the middle of an interior span", "M_2 = (w_d/16 + w_l/12) l_2^2",
               f"({_n(wd, 3)}/16 + {_n(wl, 3)}/12) x {_n(inner.l_eff / 1000, 3)}^2", inner.mu, "kN m")
    if has_c:
        sheet.step(f"{REF}, Table 12", "At the other interior supports (hogging)", "M_C = (w_d/12 + w_l/9) l_2^2",
                   f"({_n(wd, 3)}/12 + {_n(wl, 3)}/9) x {_n(inner.l_eff / 1000, 3)}^2", mc, "kN m")
    shears = {
        "A": support_shear("end_support", wd, wl, end.l_eff),
        "B1": support_shear("next_to_end_outer", wd, wl, end.l_eff),
        "B2": support_shear("next_to_end_inner", wd, wl, inner.l_eff),
        "C": support_shear("interior_support", wd, wl, inner.l_eff) if has_c else 0.0,
    }
    sheet.step(f"{REF}, Table 13", "At the end support", "V_A = (0.40 w_d + 0.45 w_l) l_1", "", shears["A"], "kN")
    sheet.step(f"{REF}, Table 13", "At the support next to the end, outer side", "V_B1 = (0.60 w_d + 0.60 w_l) l_1", "", shears["B1"], "kN")
    sheet.step(f"{REF}, Table 13", "At the support next to the end, inner side", "V_B2 = (0.55 w_d + 0.60 w_l) l_2", "", shears["B2"], "kN")
    if has_c:
        sheet.step(f"{REF}, Table 13", "At the other interior supports", "V_C = (0.50 w_d + 0.60 w_l) l_2", "", shears["C"], "kN")

    # ------------------------------------------------------------------ flexure
    as_max = is456.max_steel(b, D)
    sheet.section("4. Flexure at mid-span")
    for sec, label in ((end, "End span"), (inner, "Interior span")):
        _span_steps(sheet, inp, sec, label, fck, fy, b, as_max, bw)
    sheet.section("5. Flexure at the supports (top in tension: the web as a rectangle)")
    for sup, label in ((sup_b, "Support next to the end (B)"), (sup_c, "Other interior supports (C)")):
        if sup is not None:
            _support_steps(sheet, sup, label, fck, fy, b, as_max, bw)

    # ------------------------------------------------------------------ shear
    sheet.section("6. Shear (critical section at d from the face of the support)")
    w_total = wd + wl
    stirrups: dict[str, dict[str, Any]] = {}
    ends_of = {
        "end": [("A", shears["A"], end.bottom.area, end.d), ("B", shears["B1"], sup_b.top.area, sup_b.d)],
        "interior": [("B", shears["B2"], sup_b.top.area, sup_b.d)] + ([("C", shears["C"], sup_c.top.area, sup_c.d)] if sup_c else []),
    }
    asv = legs * bar_area(dst)
    tc_max = is456.tau_c_max(fck)
    for kind, label in (("end", "End span"), ("interior", "Interior span")):
        limits: dict[str, float] = {}
        worst = 0.0
        for at, v_face, ast, d in ends_of[kind]:
            vu = max(v_face - w_total * d / 1000.0, 0.0)
            tau = vu * 1e3 / (b * d)
            pt = 100.0 * ast / (b * d)
            tc = is456.tau_c(fck, pt)
            worst = max(worst, tau)
            sheet.step(f"{REF}, Cl. 22.6.2.1 and 40.1", f"{label} at support {at}: shear at d from the face, nominal stress",
                       f"tau_v = (V - w d)/({bw} d)", f"({_n(v_face)} - {_n(w_total, 3)} x {_n(d / 1000, 3)}) x 10^3 / ({_n(b, 0)} x {_n(d, 1)})",
                       tau, "N/mm2", 3)
            sheet.step(f"{REF}, Table 19", f"{label} at support {at}: tension steel and tau_c", "p_t, tau_c", "", f"{_n(pt, 3)} %, {_n(tc, 3)}",
                       "N/mm2")
            vus = vu - tc * b * d / 1e3
            if vus > 0:
                limits[f"shear strength at {at}, Cl. 40.4(a)"] = is456.stirrup_spacing_for_shear(vus * 1e3, fyv, asv, d)
            limits["0.75 d, Cl. 26.5.1.5"] = min(limits.get("0.75 d, Cl. 26.5.1.5", math.inf), 0.75 * d)
        limits["minimum shear steel, Cl. 26.5.1.6"] = is456.stirrup_spacing_minimum_steel(fyv, asv, b)
        limits["300 mm, Cl. 26.5.1.5"] = 300.0
        governing = min(limits, key=lambda k: limits[k])
        sv = practical_spacing(limits[governing])
        sheet.check(f"tau_max_{kind}", f"{REF}, Table 20", f"{label}: maximum shear stress", "tau_v", worst, "<=", "tau_c,max", tc_max, "N/mm2", 3)
        sheet.step("Selected", f"{label}: {legs}-legged T{dst} stirrups (governed by {governing})", "s_v", "", sv, "mm", 0)
        sheet.check(f"sv_{kind}", f"{REF}, Cl. 26.5.1.5 and 40.4", f"{label}: stirrup spacing", "s_v", sv, "<=", "s_v,allow", limits[governing], "mm", 0,
                    ratio=False)
        sheet.check(f"sv_min_{kind}", "Practice", f"{label}: stirrup spacing workable (75 mm or more)", "s_v", sv, ">=", "s_v,min", 75.0, "mm", 0,
                    ratio=False)
        stirrups[kind] = {"dia": dst, "legs": legs, "spacing": sv, "allow": limits[governing], "governing": governing,
                          "label": f"T{dst} {legs}-legged @ {_n(sv, 0)} c/c"}

    # ------------------------------------------------------------------ deflection
    sheet.section("7. Deflection control (span to effective depth)")
    basic = is456.BASIC_SPAN_DEPTH["continuous"]
    defl: dict[str, dict[str, float]] = {}
    for sec, label in ((end, "End span"), (inner, "Interior span")):
        span_factor = 10000.0 / sec.l_eff if sec.l_eff > 10000.0 else 1.0
        fs = is456.service_steel_stress(fy, sec.fl.ast_req, sec.bottom.area)
        b_d = sec.flange.bf if sec.flange else b
        pt = 100.0 * sec.bottom.area / (b_d * sec.d)
        kt = is456.tension_modification_factor(fs, pt)
        kc = is456.compression_modification_factor(100.0 * sec.top.area / (b_d * sec.d)) if sec.fl.doubly else 1.0
        kf = is456.flanged_reduction_factor(b / sec.flange.bf) if sec.flange else 1.0
        allow = basic * span_factor * kt * kc * kf
        sub = f"{_n(basic, 0)}" + (f" x {_n(span_factor, 3)}" if span_factor != 1 else "") + f" x {_n(kt, 3)} x {_n(kc, 3)}" + (
            f" x {_n(kf, 3)}" if sec.flange else "")
        sheet.step(f"{REF}, Cl. 23.2.1, Fig. 4" + (", 5" if sec.fl.doubly else "") + (", Fig. 6" if sec.flange else ""),
                   f"{label}: allowable ratio, continuous (f_s = {_n(fs, 1)} N/mm2, p_t = {_n(pt, 3)} % on {'b_f' if sec.flange else bw} d)",
                   "26 k_t k_c" + (" k_f" if sec.flange else ""), sub, allow, "", 2)
        sheet.check(f"deflection_{sec.kind}", f"{REF}, Cl. 23.2.1", f"{label}: span to effective depth ratio", "l/d", sec.l_eff / sec.d, "<=",
                    "allowable", allow, "", 2)
        defl[sec.kind] = {"ratio": sec.l_eff / sec.d, "allow": allow, "kt": kt, "kc": kc, "kf": kf, "fs": fs, "pt": pt}

    # ------------------------------------------------------------------ detailing
    sheet.section("8. Detailing")
    groups = [("end span bottom", end.bottom, end.clear), ("interior span bottom", inner.bottom, inner.clear), ("top over B", sup_b.top, sup_b.clear)]
    if sup_c:
        groups.append(("top over C", sup_c.top, sup_c.clear))
    s_max = is456.max_clear_bar_spacing(fy)
    for name, grp, clear in groups:
        key = name.replace(" ", "_")
        sheet.check(f"spacing_min_{key}", f"{REF}, Cl. 26.3.2(a)", f"Minimum clear distance, {name} bars", "s", clear, ">=", "s_min",
                    is456.min_clear_bar_spacing_horizontal(grp.dia, inp.max_aggregate_mm), "mm", 0, ratio=False)
        sheet.check(f"spacing_max_{key}", f"{REF}, Cl. 26.3.3(a), Table 15", f"Maximum clear distance, {name} bars", "s", clear, "<=", "s_max",
                    s_max, "mm", 0)
    big = max(g.dia for _, g, _ in groups)
    sheet.check("cover_bar", f"{REF}, Cl. 26.4.1", "Cover to main bars not less than the bar diameter", "c + d_st", cover + dst, ">=", "d_b",
                float(big), "mm", 0, ratio=False)
    bc = end.flange.bf if end.flange else b
    ls_lim = min(60.0 * bc, 250.0 * bc * bc / end.d)
    sheet.check("lateral", f"{REF}, Cl. 23.3(a)", "Lateral stability: clear span not above 60 b or 250 b^2/d"
                + (" (b: the flange at mid-span)" if end.flange else ""), "l", lc, "<=", "limit", ls_lim, "mm", 0)

    # extent of the top bars over the supports: furthest point of inflection over the load arrangements of Cl. 22.4.1
    spans_m = [end.l_eff / 1000.0] + [inner.l_eff / 1000.0] * (n - 2) + [end.l_eff / 1000.0]
    infl = analysis.hogging_extents(spans_m, wd, wl)

    def from_face(x_m: float, l_eff: float) -> float:  # the analysis runs between centre lines; bars are set out from the faces
        return min(max(x_m * 1000.0 - (l_eff - lc) / 2.0, 0.0), lc)

    hog = {"B_end": from_face(infl[0][1], end.l_eff), "B_int": from_face(infl[1][0], inner.l_eff)}
    if has_c:
        c_ends = [infl[1][1]] + [x for i in range(2, n - 2) for x in infl[i]]
        hog["C_int"] = from_face(max(c_ends), inner.l_eff)
    sheet.step(f"{REF}, Cl. 22.4.1", "Points of inflection: elastic analysis (three-moment equation) of dead load on every span with imposed "
               "load on all spans, on alternate spans and on each pair of adjacent spans; furthest point from each support face",
               "x_0", ", ".join(f"{k.replace('_', ' into ')}: {_n(v, 0)}" for k, v in hog.items()), "", "mm")
    ld = {g: is456.development_length(g.dia, fck, fy) for g in {sup_b.top, *(x.top for x in [sup_c] if x)}}
    ext: dict[str, float] = {}
    for key, sup in (("B_end", sup_b), ("B_int", sup_b), ("C_int", sup_c)):
        if sup is None:
            continue
        beyond = max(sup.d, 12.0 * sup.top.dia, lc / 16.0)
        ext[key] = min(max(hog[key] + beyond, ld[sup.top]), lc)
        sheet.step(f"{REF}, Cl. 26.2.3.4", f"Top bars over {key[0]} into the {'end' if key == 'B_end' else 'interior'} span: beyond the point of "
                   "inflection by the greatest of d, 12 phi and l_c/16; not less than L_d from the face",
                   "a = max(x_0 + max(d, 12 phi, l_c/16), L_d)", f"x_0 = {_n(hog[key], 0)}, L_d = {_n(ld[sup.top], 0)}", ext[key], "mm", 0)

    side = None
    if D > 750.0:
        from app.modules.structural.domain.beam_detailing import side_face_bars
        side = side_face_bars(inp, cover, end.bottom, sup_b.top, torsion=False)
        if side:
            sheet.step(f"{REF}, Cl. 26.5.1.3", "Side face reinforcement: 0.1 % of the web area, half on each face", "A_s = 0.001 b D", "",
                       0.001 * b * D, "mm2", 0)

    reinforcement = {
        "spans": n, "cover": cover,
        "end": {"bottom": _grp(end.bottom), "top": _grp(end.top), "gap": end.gap, "doubly": end.fl.doubly},
        "interior": {"bottom": _grp(inner.bottom), "top": _grp(inner.top), "gap": inner.gap, "doubly": inner.fl.doubly},
        "support_b": {"top": _grp(sup_b.top), "gap": sup_b.gap, "doubly": sup_b.fl.doubly, "into_end": ext["B_end"], "into_interior": ext["B_int"]},
        "support_c": ({"top": _grp(sup_c.top), "gap": sup_c.gap, "doubly": sup_c.fl.doubly, "into_interior": ext["C_int"]} if sup_c else None),
        "stirrups": stirrups,
        "side_face": side,
        "section": {"kind": inp.section, "bw": b, "D": D} | (
            {"df": inp.flange_thickness_mm, "bf": round(end.flange.bf, 1), "b_actual": inp.flange_width_mm} if end.flange else {}),
    }
    lay = detailing.layout(inp, reinforcement)
    reinforcement["layout"] = lay
    if lay["end"]["hanger"] == 0:
        sheet.step(f"{REF}, Cl. 26.2.3.4", "End span: no room for a lapped hanger, so the top bars over B run on to the end support", "", "", "", "")
    env = analysis.envelope(spans_m, wd, wl, 21)
    for i, s_ in enumerate(lay["interior"]):
        if not s_["meet"]:
            continue
        span_index = 1 if i == 0 else 2  # span 2, or a span between two C supports
        m_mid = min(row[1] for row in env[span_index] if abs(row[0] - spans_m[span_index] / 2.0) <= spans_m[span_index] / 4.0)
        weak = min((sup_b, sup_c) if s_["left"] != s_["right"] else ((sup_b,) if s_["left"] == "B" else (sup_c,)),
                   key=lambda x: x.top.area if x else math.inf)
        assert weak is not None
        cap = is456.moment_capacity(fck, fy, b, weak.d, weak.top.area, 0.0, weak.d_c).mu / 1e6
        sheet.step(f"{REF}, Cl. 26.2.5.1(c)", f"Span between {s_['left']} and {s_['right']}: the top bars from both supports meet; each runs "
                   f"to mid-span and they lap there by {_n(s_['lap'], 0)} mm", "a", "", s_["a_left"], "mm", 0)
        sheet.check(f"lap_hogging_{i}", f"{REF}, Cl. 22.4.1", f"Span between {s_['left']} and {s_['right']}: hogging over the middle half "
                    f"(elastic envelope) within the lapped top bars ({weak.top.label()}, compression steel ignored)",
                    "M_u", max(-m_mid, 0.0), "<=", "M_u,R", cap, "kN m")
    from app.modules.structural.domain import continuous_curtailment as curtail
    cut_plan = curtail.plan(sheet, inp, cover, {"end": end, "interior": inner, "support_b": sup_b, "support_c": sup_c}, spans_m, wd, wl,
                            {"end": end.mu, "interior": inner.mu, "b": mb, "c": mc}, shears,
                            {"B_end": lay["end"]["a_b"], "B_int": lay["b_into_interior"], "C_int": lay["c_into_interior"]}, stirrups)
    reinforcement["curtailment"] = _plan_record(cut_plan)
    bbs = detailing.bar_schedule(inp, reinforcement, sheet)
    quantities = detailing.quantities(inp, bbs)
    drawing = detailing.drawing(inp, reinforcement, bbs)

    if not any(cut_plan[k] for k in ("top_b", "top_c", "bottom_end", "bottom_interior")):
        sheet.flag("info", "No bars are curtailed (the sheet says why for each set); bottom bars run the full length of each span and the top "
                           "bars over the supports to the extent shown.")
    if flanged:
        sheet.flag("info", "Where the slab spans parallel to this beam, provide transverse bars over the beam, at least 60 percent of the "
                           "slab's mid-span steel, so that the slab acts as the flange.", f"{REF}, Cl. 23.1.1(b)")
    if sup_b.fl.doubly or (sup_c and sup_c.fl.doubly):
        sheet.flag("info", "A support section uses the bottom bars as compression steel; they are continued past the face of the support by "
                           "the development length in compression.", f"{REF}, Cl. 26.2.1")
    sheet.flag("info", "The coefficients of Table 12 do not allow redistribution of moments (Cl. 22.5.1).", f"{REF}, Cl. 22.5.1")

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    key_results = [
        {"label": "End span moment", "sym": "M_1", "value": round(end.mu, 2), "unit": "kN m", "dp": 2},
        {"label": "Support moment B", "sym": "M_B", "value": round(mb, 2), "unit": "kN m", "dp": 2},
        {"label": "End span bottom", "sym": "", "value": end.bottom.label(), "unit": "", "dp": 0},
        {"label": "Interior span bottom", "sym": "", "value": inner.bottom.label(), "unit": "", "dp": 0},
        {"label": "Top over B", "sym": "", "value": sup_b.top.label(), "unit": "", "dp": 0},
        *([{"label": "Top over C", "sym": "", "value": sup_c.top.label(), "unit": "", "dp": 0}] if sup_c else []),
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
    ]
    data: dict[str, Any] = {
        "cover": cover, "w_self": round(w_self, 4), "wd": round(wd, 4), "wl": round(wl, 4), "rule": rule,
        "l_end": round(end.l_eff, 2), "l_int": round(inner.l_eff, 2),
        "m_end": round(end.mu, 4), "m_int": round(inner.mu, 4), "m_b": round(mb, 4), "m_c": round(mc, 4),
        "v_a": round(shears["A"], 4), "v_b1": round(shears["B1"], 4), "v_b2": round(shears["B2"], 4), "v_c": round(shears["C"], 4),
        "hog": {k: round(v, 1) for k, v in hog.items()}, "ext": {k: round(v, 1) for k, v in ext.items()},
        "defl": {k: {kk: round(vv, 5) for kk, vv in v.items()} for k, v in defl.items()},
    }
    for sec in (end, inner):
        data[sec.kind] = {"d": round(sec.d, 2), "d_c": round(sec.d_c, 2), "ast_req": round(sec.fl.ast_req, 2), "asc_req": round(sec.fl.asc_req, 2),
                          "ast_prov": round(sec.bottom.area, 2), "asc_prov": round(sec.top.area, 2), "mu_lim": round(sec.fl.mu_lim / 1e6, 4),
                          "capacity": round(sec.cap.mu / 1e6, 4), "xu": round(sec.cap.xu, 3), "xu_max": round(sec.fl.xu_max, 3),
                          "doubly": sec.fl.doubly, "bf": round(sec.flange.bf, 2) if sec.flange else None,
                          "na_in_flange": sec.fl.na_in_flange, "min_steel": round(is456.min_tension_steel(b, sec.d, fy), 2)}
    for sup in (sup_b, sup_c):
        if sup is not None:
            data[f"support_{sup.kind.lower()}"] = {
                "d": round(sup.d, 2), "d_c": round(sup.d_c, 2), "ast_req": round(sup.fl.ast_req, 2), "asc_req": round(sup.fl.asc_req, 2),
                "ast_prov": round(sup.top.area, 2), "asc_prov": round(sup.compression.area, 2), "mu_lim": round(sup.fl.mu_lim / 1e6, 4),
                "capacity": round(sup.cap.mu / 1e6, 4), "xu": round(sup.cap.xu, 3), "xu_max": round(sup.fl.xu_max, 3), "doubly": sup.fl.doubly,
                "min_steel": round(is456.min_tension_steel(b, sup.d, fy), 2)}
    data["stirrups"] = {k: {"spacing": v["spacing"], "allow": round(v["allow"], 2)} for k, v in stirrups.items()}
    data["curtailment"] = curtail.summary(cut_plan)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok", "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok), "checks_total": len(checks),
        "max_utilisation": max(utils) if utils else None,
        "key_results": key_results, "data": data, "reinforcement": reinforcement, "sheet": sheet.to_dict(),
        "bbs": bbs, "quantities": quantities, "drawing": drawing,
    }


def _plan_record(p: dict[str, Any]) -> dict[str, Any]:
    """The curtailment plan as the detailing reads it."""
    top = {k: ({"long": _grp(v["long"]), "short": _grp(v["short"]), "cut": v["cut"]} if v else None) for k, v in (("b", p["top_b"]), ("c", p["top_c"]))}
    bottom = {k: ({"continuing": _grp(v["cont"]), "curtailed": _grp(v["cut"]), "left": v["left"], "right": v["right"]} if v else None)
              for k, v in (("end", p["bottom_end"]), ("interior", p["bottom_interior"]))}
    return {"top": top, "bottom": bottom, "zones": p["zones"], "end_detail": p["end_detail"]}


def _grp(g: BarGroup) -> dict[str, Any]:
    return {"count": g.count, "dia": g.dia, "layers": list(g.layers), "area": round(g.area, 1), "label": g.label()}


def _span_steps(sheet: CalcSheet, inp: ContinuousBeamInput, sec: SpanSection, label: str, fck: float, fy: float, b: float, as_max: float,
                bw: str) -> None:
    d, fl, kind = sec.d, sec.fl, sec.kind
    sheet.step("Geometry", f"{label}: effective depth to the bottom steel" + (f" ({sec.bottom.layers[0]} + {sec.bottom.layers[1]} bars)"
               if len(sec.bottom.layers) == 2 else ""), "d", "", d, "mm", 1)
    if sec.flange:
        flange_steps(sheet, inp, sec.flange, sec.l_eff, continuous=True)
        flanged_flexure_steps(sheet, sec.flange, fl, sec.mu * 1e6, fck, fy, b, d)
    else:
        sheet.step(f"{REF}, Annex G-1.1(c)", f"{label}: limiting moment of resistance", "M_u,lim = 0.36 f_ck b x_u,max (d - 0.42 x_u,max)",
                   f"x_u,max = {_n(fl.xu_max, 1)}", fl.mu_lim / 1e6, "kN m")
        if fl.doubly:
            sheet.step(f"{REF}, Annex G-1.2", f"{label}: M_u exceeds M_u,lim: compression steel", "A_sc", "", fl.asc_req, "mm2", 0)
            sheet.step(f"{REF}, Annex G-1.2", f"{label}: tension steel", "A_st = A_st1 + A_sc (f_sc - f_cc)/(0.87 f_y)", "", fl.ast_req, "mm2", 0)
        else:
            sheet.step(f"{REF}, Annex G-1.1(b)", f"{label}: tension steel required", "A_st = 0.5 (f_ck/f_y)[1 - sqrt(1 - 4.6 M_u/(f_ck b d^2))] b d",
                       f"M_u = {_n(sec.mu)} kN m", fl.ast_req, "mm2", 0)
    ast_min = is456.min_tension_steel(b, d, fy)
    sheet.step(f"{REF}, Cl. 26.5.1.1(a)", f"{label}: minimum tension steel", f"A_s,min = 0.85 {bw} d / f_y", "", ast_min, "mm2", 0)
    sheet.step("Selected", f"{label}: bottom bars and top bars", "", f"{sec.bottom.label()}; {sec.top.label()}", sec.bottom.area, "mm2", 0)
    sheet.check(f"ast_{kind}", f"{REF}, Annex G", f"{label}: tension steel provided", "A_st,req", max(fl.ast_req, ast_min), "<=", "A_st,prov",
                sec.bottom.area, "mm2", 0)
    if fl.doubly:
        sheet.check(f"asc_{kind}", f"{REF}, Annex G-1.2", f"{label}: compression steel provided", "A_sc,req", fl.asc_req, "<=", "A_sc,prov",
                    sec.top.area, "mm2", 0)
    sheet.check(f"ast_max_{kind}", f"{REF}, Cl. 26.5.1.1(b)", f"{label}: maximum tension steel (0.04 {bw} D)", "A_st,prov", sec.bottom.area, "<=",
                f"0.04 {bw} D", as_max, "mm2", 0)
    sheet.check(f"ductility_{kind}", f"{REF}, Cl. 38.1(f)", f"{label}: under-reinforced as detailed", "x_u", sec.cap.xu, "<=", "x_u,max", fl.xu_max, "mm", 1)
    sheet.check(f"moment_{kind}", f"{REF}, Cl. 38.1", f"{label}: moment of resistance as detailed", "M_u", sec.mu, "<=", "M_u,R", sec.cap.mu / 1e6, "kN m")


def _support_steps(sheet: CalcSheet, sup: SupportSection, label: str, fck: float, fy: float, b: float, as_max: float, bw: str) -> None:
    fl, k = sup.fl, sup.kind.lower()
    sheet.step("Geometry", f"{label}: effective depth to the top steel; bottom bars {sup.compression.label()} at d' from the soffit",
               "d, d'", "", f"{_n(sup.d, 1)}, {_n(sup.d_c, 1)}", "mm")
    sheet.step(f"{REF}, Annex G-1.1(c)", f"{label}: limiting moment of the web", "M_u,lim = 0.36 f_ck b_w x_u,max (d - 0.42 x_u,max)",
               f"x_u,max = {_n(fl.xu_max, 1)}", fl.mu_lim / 1e6, "kN m")
    if fl.doubly:
        sheet.step(f"{REF}, Annex G-1.2", f"{label}: M_u exceeds M_u,lim: the bottom bars act as compression steel", "A_sc,req", "",
                   fl.asc_req, "mm2", 0)
    sheet.step(f"{REF}, Annex G-1.1(b)" if not fl.doubly else f"{REF}, Annex G-1.2", f"{label}: top steel required", "A_st", f"M_u = {_n(sup.mu)} kN m",
               fl.ast_req, "mm2", 0)
    ast_min = is456.min_tension_steel(b, sup.d, fy)
    sheet.step("Selected", f"{label}: top bars", "", sup.top.label(), sup.top.area, "mm2", 0)
    sheet.check(f"ast_{k}", f"{REF}, Annex G", f"{label}: top steel provided", "A_st,req", max(fl.ast_req, ast_min), "<=", "A_st,prov", sup.top.area,
                "mm2", 0)
    if fl.doubly:
        sheet.check(f"asc_{k}", f"{REF}, Annex G-1.2", f"{label}: compression steel (bottom bars)", "A_sc,req", fl.asc_req, "<=", "A_sc,prov",
                    sup.compression.area, "mm2", 0)
    sheet.check(f"ast_max_{k}", f"{REF}, Cl. 26.5.1.1(b)", f"{label}: maximum tension steel (0.04 {bw} D)", "A_st,prov", sup.top.area, "<=",
                f"0.04 {bw} D", as_max, "mm2", 0)
    sheet.check(f"ductility_{k}", f"{REF}, Cl. 38.1(f)", f"{label}: under-reinforced as detailed", "x_u", sup.cap.xu, "<=", "x_u,max", fl.xu_max, "mm", 1)
    sheet.check(f"moment_{k}", f"{REF}, Cl. 38.1", f"{label}: moment of resistance as detailed", "M_u", sup.mu, "<=", "M_u,R", sup.cap.mu / 1e6, "kN m")


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS), "status": "stopped",
        "stop_message": message, "checks_passed": sum(1 for c in sheet.checks() if c.ok), "checks_total": len(sheet.checks()),
        "max_utilisation": None, "key_results": [], "data": {}, "reinforcement": None, "sheet": sheet.to_dict(),
        "bbs": None, "quantities": None, "drawing": None,
    }

