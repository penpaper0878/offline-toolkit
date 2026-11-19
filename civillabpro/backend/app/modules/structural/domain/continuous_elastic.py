"""Continuous beam of any spans, uniform and point loads, by elastic analysis with redistribution (STR-036).

The continuous beam element's second method (``analysis = "elastic"``). Two to twelve spans of their own clear
span and uniform loads, point loads on any span, one section and one support width:

* effective spans by Cl. 22.2(b), with the greatest effective depth the bars allow (on the safe side);
* the three-moment equation for every arrangement of imposed load of Cl. 22.4.1, the end supports free;
* redistribution of the support moments by Cl. 37.1.1 (allowed with an elastic analysis by Cl. 22.7): in
  every arrangement the hogging at a support is held to (1 - r) of its greatest elastic value, the span
  moments following by statics (a); the design envelope is the larger of the redistributed one and 70 percent
  of the elastic one (b); no moment falls by more than 30 percent of the largest in the member (c); and the
  sections where the resistance is below the elastic moment satisfy x_u/d + dM/100 <= 0.6 (d);
* each span and each support designed for its own moment; shear at d from the face (Cl. 22.6.2.1) from the
  envelope; deflection by Cl. 23.2.1; the extents and curtailment of the bars, the stirrup bands and the
  anchorage of the bottom bars (Cl. 26.2.3) from the same envelope.

Worked example (the defaults of the span table): spans of 5.0, 6.5 and 4.5 m clear on 300 mm supports,
300 x 500, M25 / Fe 500, DL 25 + LL 15 kN/m on each span plus self-weight, a point load of 40 + 30 kN at 3.0 m
in span 2, 15 percent redistribution. tests/handcheck/check_continuous_elastic.py reproduces it by moment
distribution. Pure: no framework imports.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.engineering import continuous as analysis
from app.engineering import is456
from app.engineering.rebar import BarGroup, bar_area, bar_unit_weight
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.beam import (
    SECTION_LABELS,
    SETTING_OUT,
    Flange,
    anchorage_check,
    anchorage_ok,
    cutoff_condition,
    effective_cover,
    end_detail,
    end_l0,
    flexure_capacity,
    flexure_design,
    other_candidates,
    practical_spacing,
    split_for_curtailment,
    stirrup_positions,
    tension_candidates,
)
from app.modules.structural.domain.continuous_beam import (
    CODE_BASIS,
    ELEMENT_TYPE,
    ENGINE_VERSION,
    ContinuousBeamInput,
    SpanSection,
    SupportSection,
    _grp,
    _span_steps,
    _stopped,
    _support_steps,
    design_loads,
    make_flange,
)

REF = is456.CODE
STEPS = 400  # stations per span for the envelopes
ELASTIC_FLOOR = 0.7  # Cl. 37.1.1(b)


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


# ----------------------------------------------------------------------------- the analysed beam


@dataclass(frozen=True)
class SpanGeom:
    lc: float  # clear span, mm
    l_eff: float  # effective span, mm (the analysis span)
    off: float  # from the analysis support to the face, mm
    rule: str  # Cl. 22.2: "a", "b1" or "b2"


class Beam:
    """Design envelopes along every span: x in mm from the face of the span's left support, moments in kN m, shear in kN.

    Sagging and hogging are the larger of the redistributed envelope and 70 percent of the elastic one (Cl. 37.1.1(b)).
    """

    def __init__(self, geo: list[SpanGeom], envs: list[analysis.SpanEnvelope]) -> None:
        self.geo, self.envs, self.n = geo, envs, len(geo)
        self.xs = [[x * 1000.0 - g.off for x in e.x] for g, e in zip(geo, envs, strict=True)]
        self.cols = {
            "sag": [[max(r, ELASTIC_FLOOR * e) for r, e in zip(v.sag, v.sag_elastic, strict=True)] for v in envs],
            "hog": [[max(r, ELASTIC_FLOOR * e) for r, e in zip(v.hog, v.hog_elastic, strict=True)] for v in envs],
            "sag_e": [list(v.sag_elastic) for v in envs],
            "hog_e": [list(v.hog_elastic) for v in envs],
            "shear": [list(v.shear) for v in envs],
        }

    def at(self, col: str, i: int, xf: float) -> float:
        xs, ys = self.xs[i], self.cols[col][i]
        if xf <= xs[0]:
            return ys[0]
        if xf >= xs[-1]:
            return ys[-1]
        k = bisect.bisect_right(xs, xf) - 1
        t = (xf - xs[k]) / (xs[k + 1] - xs[k])
        return ys[k] + t * (ys[k + 1] - ys[k])

    def sag(self, i: int, xf: float) -> float:
        return self.at("sag", i, xf)

    def hog(self, i: int, xf: float) -> float:
        return self.at("hog", i, xf)

    def shear(self, i: int, xf: float) -> float:
        return self.at("shear", i, xf)

    def scan(self, i: int, f: Callable[[float], float], x0: float, x1: float, steps: int = STEPS) -> list[tuple[float, float]]:
        """f at evenly spaced points from x0 to x1 and at every station between."""
        pts = {x0 + (x1 - x0) * k / steps for k in range(steps + 1)} | {x for x in self.xs[i] if x0 < x < x1}
        return [(x, f(x)) for x in sorted(pts)]

    def sag_peak(self, i: int) -> float:
        lc = self.geo[i].lc
        return max(m for _, m in self.scan(i, lambda x: self.sag(i, x), 0.0, lc))

    def inflection(self, i: int, from_left: bool) -> float | None:
        """Distance from the face to where the greatest sagging moment begins: the point of inflection of the bottom bars."""
        lc = self.geo[i].lc
        prof = self.scan(i, (lambda x: self.sag(i, x)) if from_left else (lambda x: self.sag(i, lc - x)), 0.0, lc)
        return next((x for x, m in prof if m > 1e-9), None)

    def hog_extent(self, i: int, at_left: bool) -> float:
        """Distance from the face of a support to where its hogging first ends: the point of inflection of the top bars."""
        lc = self.geo[i].lc
        prof = self.scan(i, (lambda x: self.hog(i, x)) if at_left else (lambda x: self.hog(i, lc - x)), 0.0, lc)
        return next((x for x, m in prof if m <= 1e-9), lc)


def effective_spans(inp: ContinuousBeamInput, d: float) -> list[SpanGeom]:
    """Cl. 22.2(b) for every span; supports narrower than l_c/12 and 600 mm follow 22.2(a)."""
    rows, sw = inp.span_table, inp.support_width_mm
    n, out = len(rows), []
    for i, row in enumerate(rows):
        lc = row.clear_span_mm
        if sw <= min(lc / 12.0, 600.0):
            le, rule = min(lc + d, lc + sw), "a"
        elif i in (0, n - 1):
            le, rule = lc + min(d / 2.0, sw / 2.0), "b2"
        else:
            le, rule = lc, "b1"
        out.append(SpanGeom(lc, le, (le - lc) / 2.0, rule))
    return out


def factored_loads(inp: ContinuousBeamInput, geo: list[SpanGeom], w_self: float) -> tuple[list[analysis.SpanLoad], list[analysis.SpanLoad]]:
    """(dead, imposed) on every span, factored, point loads placed on the analysis span (kN/m, kN, m)."""
    g = inp.load_factor
    dead, imposed = [], []
    for i, (row, sg) in enumerate(zip(inp.span_table, geo, strict=True)):
        pts = [p for p in inp.point_loads if p.span == i + 1]
        dead.append(analysis.SpanLoad(g * (row.dead_load_kn_m + w_self),
                                      tuple(((sg.off + p.distance_mm) / 1000.0, g * p.dead_kn) for p in pts if p.dead_kn > 0)))
        imposed.append(analysis.SpanLoad(g * row.live_load_kn_m,
                                         tuple(((sg.off + p.distance_mm) / 1000.0, g * p.live_kn) for p in pts if p.live_kn > 0)))
    return dead, imposed


# ----------------------------------------------------------------------------- sections


def select_span_bars(inp: ContinuousBeamInput, cover: float, kind: str, mu: float, l_eff: float, m_elastic: float,
                     ok_anchor: Callable[[BarGroup, float, Flange | None], bool] | None) -> SpanSection | None:
    """Least steel at the section of greatest sagging, judged at the bars' own depth; bars that fail Cl. 37.1.1(d) or could not be
    anchored (Cl. 26.2.3.3(c)) are passed over."""
    b, D, fy, dst = inp.width_mm, inp.depth_mm, float(inp.fy), inp.stirrup_dia_mm
    as_max = is456.max_steel(b, D)
    others = sorted(other_candidates(inp, cover), key=lambda g: g.area)  # type: ignore[arg-type]
    flg = make_flange(inp, l_eff)
    red = max(0.0, 1.0 - mu / m_elastic) if m_elastic > 0 else 0.0  # reduction of the span moment, Cl. 37.1.1(d)
    best: tuple[tuple[float, int, int], SpanSection] | None = None
    for ten, ybar, clear, gap in sorted(tension_candidates(inp, cover), key=lambda c: c[0].area):  # type: ignore[arg-type]
        if best is not None and ten.area + others[0].area > best[0][0] + 1e-6:
            break
        d = D - ybar
        if ten.area > as_max or ten.area < is456.min_tension_steel(b, d, fy):
            continue
        for oth in others:
            if best is not None and ten.area + oth.area > best[0][0] + 1e-6:
                break
            d_c = cover + dst + oth.dia / 2.0
            fl = flexure_design(inp, flg, mu * 1e6, d, d_c)  # type: ignore[arg-type]
            if ten.area < fl.ast_req or oth.area < fl.asc_req:
                continue
            cap = flexure_capacity(inp, flg, d, ten.area, oth.area, d_c)  # type: ignore[arg-type]
            if cap.limited or cap.mu < mu * 1e6:
                continue
            if red > 0 and cap.mu < m_elastic * 1e6 and cap.xu / d + red > 0.6 + 1e-9:
                continue
            if ok_anchor is not None and not ok_anchor(ten, d, flg):
                continue
            key = (round(ten.area + oth.area, 3), len(ten.layers), ten.count + oth.count)
            if best is None or key < best[0]:
                best = (key, SpanSection(kind, ten, oth, d, d_c, ybar, clear, gap, l_eff, mu, flg, fl, cap))
    return best[1] if best else None


def select_support_bars(inp: ContinuousBeamInput, cover: float, kind: str, mu: float, comp: BarGroup, comp_y: float, m_elastic: float
                        ) -> SupportSection | None:
    """Least top steel over a support (the web as a rectangle, the bottom bars as compression steel), with Cl. 37.1.1(d)."""
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    as_max = is456.max_steel(b, D)
    red = max(0.0, 1.0 - mu / m_elastic) if m_elastic > 0 else 0.0
    cands = sorted(tension_candidates(inp, cover), key=lambda c: (round(c[0].area, 3), len(c[0].layers), c[0].count))  # type: ignore[arg-type]
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
        if red > 0 and cap.mu < m_elastic * 1e6 and cap.xu / d + red > 0.6 + 1e-9:
            continue
        return SupportSection(kind, top, ybar, d, clear, gap, mu, comp, comp_y, fl, cap)
    return None


# ------------------------------------------------------------------------------ design


def design(inp: ContinuousBeamInput) -> dict[str, Any]:
    from app.modules.structural.domain import continuous_elastic_detailing as detailing

    sheet = CalcSheet()
    rows = inp.span_table
    n = len(rows)
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    sw, dst, legs = inp.support_width_mm, inp.stirrup_dia_mm, inp.stirrup_legs
    frac = inp.redistribution_pct / 100.0
    cover = effective_cover(inp)  # type: ignore[arg-type]
    fyv = is456.shear_fy(inp.fy_stirrup)
    flanged = inp.section != "rectangular"
    bw = "b_w" if flanged else "b"

    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.step(f"{REF}, Cl. 40.4", "Steel strength taken for stirrups (not above 415)", "f_yv", f"min({inp.fy_stirrup}, 415)", fyv, "N/mm2", 0)
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.check("cover", f"{REF}, Table 16", "Nominal cover to all reinforcement", "c", cover, ">=", "c_nom", is456.nominal_cover(inp.exposure), "mm", 0,
                ratio=False)

    # ------------------------------------------------------------------ spans, loads and analysis
    w_self = design_loads(inp)[0]
    d_max = D - cover - dst - (inp.main_bar_dia_mm or 12) / 2.0  # one layer of the smallest bar: the longest effective spans
    geo = effective_spans(inp, d_max)
    if min(g.l_eff / D for g in geo) < 2.5:
        return _stopped(sheet, "An effective span is less than 2.5 times the overall depth: that span is a continuous deep beam "
                               "(IS 456:2000, Cl. 29), which this engine does not design.")
    dead, imposed = factored_loads(inp, geo, w_self)
    spans_m = [g.l_eff / 1000.0 for g in geo]
    cases = analysis.arrangements(dead, imposed)
    fl_sw = inp.support_width_mm
    # the redistribution entered is the most applied: where a support's section cannot meet Cl. 37.1.1(d) with it, that support
    # takes 5 percent less, and the envelope is worked out again
    fr = [0.0] + [frac] * (n - 1) + [0.0]
    stepped: list[tuple[int, float]] = []
    while True:
        envs, hog_e, caps = analysis.envelopes(spans_m, [loads for _, loads in cases], fr, STEPS)
        beam = Beam(geo, envs)
        m_span = [beam.sag_peak(i) for i in range(n)]
        m_span_e = [max(e.sag_elastic) for e in envs]
        m_sup = [max(caps[j], ELASTIC_FLOOR * hog_e[j]) for j in range(n + 1)]

        def shear_at_end(i: int, left: bool, beam: Beam = beam) -> float:
            return beam.shear(i, 0.0 if left else geo[i].lc)

        def anchor_fn(i: int, beam: Beam = beam) -> Callable[[BarGroup, float, Flange | None], bool]:
            sides = ([True] if i > 0 else []) + ([False] if i < n - 1 else [])
            infl = [(x, beam.shear(i, x if left else geo[i].lc - x)) for left in sides if (x := beam.inflection(i, left)) is not None]
            ends = ([beam.shear(i, 0.0)] if i == 0 else []) + ([beam.shear(i, geo[i].lc)] if i == n - 1 else [])

            def ok(g: BarGroup, d: float, flg: Flange | None) -> bool:
                m1 = is456.moment_at_design_stress(fck, fy, b, d, g.area, flg.bf if flg else None, flg.df if flg else 0.0) / 1e6
                if any(end_detail(fl_sw, cover, g.dia, fck, fy, m1, v, "straight") is None for v in ends):
                    return False
                return all(anchorage_ok(g.dia, fck, fy, m1, v, max(d, 12.0 * g.dia), False)[0] for _, v in infl)
            return ok

        secs: list[SpanSection] = []
        for i in range(n):
            sec = select_span_bars(inp, cover, f"span_{i + 1}", m_span[i], geo[i].l_eff, m_span_e[i], anchor_fn(i))
            if sec is None:
                if select_span_bars(inp, cover, f"span_{i + 1}", m_span[i], geo[i].l_eff, m_span_e[i], None) is not None:
                    return _stopped(sheet, f"The bottom bars that carry the moment of span {i + 1} are too large to be anchored at the end supports "
                                           "or the points of inflection (Cl. 26.2.3.3(c)): use a smaller bar size, wider supports or a deeper section.")
                return _stopped(sheet, f"No arrangement of up to two layers of bars carries the moment of span {i + 1} within the steel limits of "
                                       "Cl. 26.5.1 and Cl. 37.1.1(d): increase the section, the concrete grade or the bar size, or redistribute less.")
            secs.append(sec)
        sups: list[SupportSection | None] = [None] * (n + 1)
        short = []
        for j in range(1, n):
            comp_sec = secs[j - 1] if secs[j - 1].bottom.area <= secs[j].bottom.area else secs[j]  # the lighter bars reach from both sides
            sups[j] = select_support_bars(inp, cover, f"s{j + 1}", m_sup[j], comp_sec.bottom, comp_sec.ybar, hog_e[j])
            if sups[j] is None:
                short.append(j)
        if not short:
            break
        if all(fr[j] <= 1e-9 for j in short):
            j = short[0]
            return _stopped(sheet, f"No arrangement of top bars carries the moment at support {j + 1} with the bottom bars as compression steel "
                                   "within Cl. 26.5.1" + (" and Cl. 37.1.1(d)" if frac > 0 else "") + ": deepen the section or raise the concrete grade.")
        for j in short:
            if fr[j] > 1e-9:
                fr[j] = max(0.0, round(fr[j] - 0.05, 6))
                stepped.append((j, fr[j]))
    inner_sups = [s for s in sups if s is not None]

    # ------------------------------------------------------------------ sheet: geometry, loads, analysis
    sheet.section("2. Section, spans and loads")
    if flanged:
        sheet.step("Input", f"{SECTION_LABELS[inp.section]}: web width, overall depth, flange thickness", "b_w x D, D_f", "",
                   f"{_n(b, 0)} x {_n(D, 0)}, {_n(inp.flange_thickness_mm, 0)}", "mm")
    else:
        sheet.step("Input", "Width and overall depth", "b x D", "", f"{_n(b, 0)} x {_n(D, 0)}", "mm")
    sheet.step("Input", f"{n} spans on supports {_n(sw, 0)} mm wide: clear spans, left to right", "l_c", "",
               ", ".join(_n(r.clear_span_mm, 0) for r in rows), "mm")
    sheet.step(f"{REF}, Cl. 22.2(b)", "Effective spans, with the greatest effective depth the bars allow (one layer of "
               f"T{inp.main_bar_dia_mm or 12}), on the safe side: narrow supports l_c + d, not more than centre to centre; wide supports "
               "the clear span, or for an end span l_c + min(d/2, w_s/2)", "l", f"d = {_n(d_max, 1)}", ", ".join(_n(g.l_eff, 0) for g in geo), "mm")
    if inp.include_self_weight:
        if flanged:
            sheet.step("IS 875 (Part 1):1987", "Self-weight of the rib below the slab", "w_sw = gamma b_w (D - D_f)", "", w_self, "kN/m", 3)
        else:
            sheet.step("IS 875 (Part 1):1987", "Self-weight", "w_sw = gamma b D",
                       f"{_n(inp.unit_weight_kn_m3, 0)} x {_n(b / 1000, 3)} x {_n(D / 1000, 3)}", w_self, "kN/m", 3)
    sheet.step(f"{REF}, Table 18", "Factored uniform loads on each span, dead (with self-weight, fixed) and imposed (not fixed)",
               "w_d = gamma_f (DL + w_sw), w_l = gamma_f LL", f"gamma_f = {_n(inp.load_factor)}",
               "; ".join(f"{_n(dl.udl, 2)} + {_n(il.udl, 2)}" for dl, il in zip(dead, imposed, strict=True)), "kN/m")
    for k, p in enumerate(inp.point_loads, 1):
        sheet.step(f"{REF}, Table 18", f"Point load {k}: span {p.span}, {_n(p.distance_mm, 0)} mm from the left face; factored dead and imposed",
                   "P_d, P_l", "", f"{_n(inp.load_factor * p.dead_kn)}, {_n(inp.load_factor * p.live_kn)}", "kN")

    sheet.section("3. Elastic analysis and redistribution of moments")
    sheet.step(f"{REF}, Cl. 22.4.1", f"Arrangements: dead load on every span with the imposed load on all spans, on alternate spans and on each "
               f"pair of adjacent spans ({len(cases)} arrangements); three-moment equation, the end supports free", "", "", len(cases), "", 0)
    sheet.step(f"{REF}, Cl. 22.7, 37.1.1", "Redistribution: in every arrangement the hogging at each support is held to (1 - r) of its greatest "
               "elastic value; the span moments follow from statics, so equilibrium holds (37.1.1(a))", "r", "", frac * 100.0, "%", 1)
    for j in sorted({j for j, _ in stepped}):
        sheet.step(f"{REF}, Cl. 37.1.1(d)", f"Support {j + 1}: no arrangement of top bars meets x_u/d + dM/100 <= 0.6 with the redistribution "
                   "entered, so less is applied there", "r", "", fr[j] * 100.0, "%", 1)
    m_member = max([*hog_e, *m_span_e])
    for j in range(1, n):
        sheet.step(f"{REF}, Cl. 37.1.1", f"Support {j + 1}: greatest elastic hogging, and after redistribution", "M_e, (1 - r) M_e", "",
                   f"{_n(hog_e[j])}, {_n(caps[j])}", "kN m")
        sheet.check(f"redistribution_{j + 1}", f"{REF}, Cl. 37.1.1(c)", f"Support {j + 1}: reduction not more than 30 percent of the largest "
                    "elastic moment in the member", "dM", hog_e[j] - caps[j], "<=", "0.3 M_max", 0.3 * m_member, "kN m")
    sheet.step(f"{REF}, Cl. 37.1.1(b)", "Design envelope: the larger of the redistributed envelope and 70 percent of the elastic one, so that the "
               "resistance provided is nowhere below 70 percent of the elastic moment", "M_d = max(M_r, 0.7 M_e)", "", "", "")
    sheet.step("Design moments", "Greatest sagging in each span (design envelope), and in the elastic envelope", "M_span", "",
               "; ".join(f"{_n(m)} ({_n(e)})" for m, e in zip(m_span, m_span_e, strict=True)), "kN m")
    sheet.step("Design moments", "Hogging at the interior supports (design)", "M_sup", "", ", ".join(_n(m_sup[j]) for j in range(1, n)), "kN m")

    # ------------------------------------------------------------------ flexure
    as_max = is456.max_steel(b, D)
    sheet.section("4. Flexure at the sections of greatest sagging")
    for i, sec in enumerate(secs):
        _span_steps(sheet, inp, sec, f"Span {i + 1}", fck, fy, b, as_max, bw)
        _redistribution_d(sheet, f"span_{i + 1}", f"Span {i + 1}", sec.mu, m_span_e[i], sec.cap.mu / 1e6, sec.cap.xu, sec.d)
    sheet.section("5. Flexure at the interior supports (top in tension: the web as a rectangle)")
    for j in range(1, n):
        sup = sups[j]
        assert sup is not None
        _support_steps(sheet, sup, f"Support {j + 1}", fck, fy, b, as_max, bw)
        _redistribution_d(sheet, f"s{j + 1}", f"Support {j + 1}", sup.mu, hog_e[j], sup.cap.mu / 1e6, sup.cap.xu, sup.d)

    # ------------------------------------------------------------------ shear
    sheet.section("6. Shear (critical section at d from the face of the support)")
    asv = legs * bar_area(dst)
    tc_max = is456.tau_c_max(fck)
    stirrups: list[dict[str, Any]] = []
    for i, sec in enumerate(secs):
        lc = geo[i].lc
        pts = [p.distance_mm for p in inp.point_loads if p.span == i + 1]
        ends: dict[str, float] = {}
        worst = 0.0
        limits_all: dict[str, float] = {}
        for left in (True, False):
            sup = sups[i] if left else sups[i + 1]
            at = "left" if left else "right"
            d = sup.d if sup is not None else sec.d
            if sup is not None:  # top steel in tension: the bars that certainly reach d from the face
                grp = (split_for_curtailment(sup.top) or (sup.top, None))[0]
            else:  # end support: the bottom bars that certainly run into it
                grp = (split_for_curtailment(sec.bottom) or (sec.bottom, None))[0]
            near = any((a if left else lc - a) < d for a in pts)
            x = 0.0 if near else d
            v = beam.shear(i, x if left else lc - x)
            tau = v * 1e3 / (b * d)
            pt = 100.0 * grp.area / (b * d)
            tc = is456.tau_c(fck, pt)
            worst = max(worst, tau)
            sheet.step(f"{REF}, Cl. 22.6.2.1 and 40.1", f"Span {i + 1}, {at} end: shear at " + ("the face (a point load lies within d)" if near else "d from the face")
                       + ", nominal stress", f"tau_v = V/({bw} d)", f"{_n(v)} x 10^3 / ({_n(b, 0)} x {_n(d, 1)})", tau, "N/mm2", 3)
            sheet.step(f"{REF}, Table 19", f"Span {i + 1}, {at} end: tension steel ({grp.label()}) and tau_c", "p_t, tau_c", "",
                       f"{_n(pt, 3)} %, {_n(tc, 3)}", "N/mm2")
            limits = {"0.75 d, Cl. 26.5.1.5": 0.75 * d, "minimum shear steel, Cl. 26.5.1.6": is456.stirrup_spacing_minimum_steel(fyv, asv, b),
                      "300 mm, Cl. 26.5.1.5": 300.0}
            vus = v - tc * b * d / 1e3
            if vus > 0:
                limits["shear strength, Cl. 40.4(a)"] = is456.stirrup_spacing_for_shear(vus * 1e3, fyv, asv, d)
            gov = min(limits, key=lambda k: limits[k])
            ends[at] = practical_spacing(limits[gov])
            limits_all[at] = limits[gov]
            sheet.step("Selected", f"Span {i + 1}, {at} end: {legs}-legged T{dst} stirrups (governed by {gov})", "s_v", "", ends[at], "mm", 0)
            sheet.check(f"sv_{i + 1}_{at}", f"{REF}, Cl. 26.5.1.5 and 40.4", f"Span {i + 1}, {at} end: stirrup spacing", "s_v", ends[at], "<=",
                        "s_v,allow", limits[gov], "mm", 0, ratio=False)
            sheet.check(f"sv_min_{i + 1}_{at}", "Practice", f"Span {i + 1}, {at} end: stirrup spacing workable (75 mm or more)", "s_v", ends[at], ">=",
                        "s_v,min", 75.0, "mm", 0, ratio=False)
        sheet.check(f"tau_max_{i + 1}", f"{REF}, Table 20", f"Span {i + 1}: maximum shear stress", "tau_v", worst, "<=", "tau_c,max", tc_max, "N/mm2", 3)
        s_min = min(ends.values())
        stirrups.append({"dia": dst, "legs": legs, "left": ends["left"], "right": ends["right"], "spacing": s_min,
                         "allow": min(limits_all.values()), "label": f"T{dst} {legs}-legged @ {_n(s_min, 0)} c/c"})

    # ------------------------------------------------------------------ deflection
    sheet.section("7. Deflection control (span to effective depth)")
    basic = is456.BASIC_SPAN_DEPTH["continuous"]
    defl: list[dict[str, float]] = []
    for i, sec in enumerate(secs):
        span_factor = 10000.0 / sec.l_eff if sec.l_eff > 10000.0 else 1.0
        fs = is456.service_steel_stress(fy, max(sec.fl.ast_req, 1e-9), sec.bottom.area)
        b_d = sec.flange.bf if sec.flange else b
        pt = 100.0 * sec.bottom.area / (b_d * sec.d)
        kt = is456.tension_modification_factor(fs, pt)
        kc = is456.compression_modification_factor(100.0 * sec.top.area / (b_d * sec.d)) if sec.fl.doubly else 1.0
        kf = is456.flanged_reduction_factor(b / sec.flange.bf) if sec.flange else 1.0
        allow = basic * span_factor * kt * kc * kf
        sub = f"{_n(basic, 0)}" + (f" x {_n(span_factor, 3)}" if span_factor != 1 else "") + f" x {_n(kt, 3)} x {_n(kc, 3)}" + (
            f" x {_n(kf, 3)}" if sec.flange else "")
        sheet.step(f"{REF}, Cl. 23.2.1, Fig. 4" + (", 5" if sec.fl.doubly else "") + (", Fig. 6" if sec.flange else ""),
                   f"Span {i + 1}: allowable ratio, continuous (f_s = {_n(fs, 1)} N/mm2, p_t = {_n(pt, 3)} % on {'b_f' if sec.flange else bw} d)",
                   "26 k_t k_c" + (" k_f" if sec.flange else ""), sub, allow, "", 2)
        sheet.check(f"deflection_{i + 1}", f"{REF}, Cl. 23.2.1", f"Span {i + 1}: span to effective depth ratio", "l/d", sec.l_eff / sec.d, "<=",
                    "allowable", allow, "", 2)
        defl.append({"ratio": sec.l_eff / sec.d, "allow": allow, "kt": kt, "kc": kc, "kf": kf, "fs": fs, "pt": pt})

    # ------------------------------------------------------------------ detailing checks
    sheet.section("8. Detailing")
    groups = [(f"span {i + 1} bottom", s.bottom, s.clear) for i, s in enumerate(secs)] + [
        (f"top over support {j + 1}", s.top, s.clear) for j, s in enumerate(sups) if s is not None]
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
    i_long = max(range(n), key=lambda k: geo[k].lc)
    bc = secs[i_long].flange.bf if secs[i_long].flange else b
    ls_lim = min(60.0 * bc, 250.0 * bc * bc / secs[i_long].d)
    sheet.check("lateral", f"{REF}, Cl. 23.3(a)", f"Lateral stability, the longest span ({i_long + 1}): clear span not above 60 b or 250 b^2/d"
                + (" (b: the flange)" if flanged else ""), "l", geo[i_long].lc, "<=", "limit", ls_lim, "mm", 0)

    # extents of the top bars: beyond the point of inflection by the greatest of d, 12 phi and l_c/16, at least L_d (Cl. 26.2.3.4)
    ext: list[dict[str, float]] = [{} for _ in range(n + 1)]
    for j in range(1, n):
        sup = sups[j]
        assert sup is not None
        ld = is456.development_length(sup.top.dia, fck, fy)
        for side, i, at_left in (("left", j - 1, False), ("right", j, True)):
            lc = geo[i].lc
            x0 = beam.hog_extent(i, at_left)
            a = min(max(x0 + max(sup.d, 12.0 * sup.top.dia, lc / 16.0), ld), lc)
            ext[j][side], ext[j][f"x0_{side}"] = a, x0
            sheet.step(f"{REF}, Cl. 26.2.3.4", f"Top bars over support {j + 1} into span {i + 1}: beyond the point of inflection by the greatest "
                       "of d, 12 phi and l_c/16; not less than L_d from the face", "a = max(x_0 + max(d, 12 phi, l_c/16), L_d)",
                       f"x_0 = {_n(x0, 0)}, L_d = {_n(ld, 0)}", a, "mm", 0)

    side = None
    if D > 750.0:
        from app.modules.structural.domain.beam_detailing import side_face_bars
        side = side_face_bars(inp, cover, max((s.bottom for s in secs), key=lambda g: g.area), max((s.top for s in inner_sups), key=lambda g: g.area),
                              torsion=False)
        if side:
            sheet.step(f"{REF}, Cl. 26.5.1.3", "Side face reinforcement: 0.1 % of the web area, half on each face", "A_s = 0.001 b D", "",
                       0.001 * b * D, "mm2", 0)

    reinforcement: dict[str, Any] = {
        "method": "elastic", "spans": n, "cover": cover,
        "span": [{"bottom": _grp(s.bottom), "top": _grp(s.top), "gap": s.gap, "doubly": s.fl.doubly, "lc": geo[i].lc, "l": geo[i].l_eff,
                  "d": s.d, "ybar": s.ybar} for i, s in enumerate(secs)],
        "support": [None] + [{"top": _grp(s.top), "gap": s.gap, "doubly": s.fl.doubly, "d": s.d, "into_left": ext[j]["left"],
                              "into_right": ext[j]["right"]} for j, s in enumerate(sups) if s is not None] + [None],
        "stirrups": stirrups,
        "side_face": side,
        "section": {"kind": inp.section, "bw": b, "D": D} | (
            {"df": inp.flange_thickness_mm, "bf": round(min(s.flange.bf for s in secs if s.flange), 1), "b_actual": inp.flange_width_mm}
            if flanged else {}),
    }
    lay = detailing.layout(inp, reinforcement)
    reinforcement["layout"] = lay
    for i, s_ in enumerate(lay):
        if s_["kind"] == "run_on":
            sheet.step(f"{REF}, Cl. 26.2.3.4", f"Span {i + 1}: no room for a lapped hanger, so the top bars over the interior support run on to the "
                       "end support", "", "", "", "")

    cut_plan = plan(sheet, inp, cover, beam, geo, secs, sups, lay, stirrups)
    reinforcement["curtailment"] = cut_plan["record"]
    meets = [i for i, s_ in enumerate(lay) if s_["kind"] == "meet"]
    if meets:
        sheet.section("11. Top bars lapped within a span")
    for i in meets:
        s_, left, right = lay[i], sups[i], sups[i + 1]
        assert left is not None and right is not None
        bottom = cut_plan["record"]["bottom"][i]
        reach = BarGroup(bottom["continuing"]["dia"], tuple(bottom["continuing"]["layers"])) if bottom else secs[i].bottom
        sheet.step(f"{REF}, Cl. 26.2.5.1(c)", f"Span {i + 1}: the top bars from both supports meet; each runs past mid-span and they lap in tension "
                   f"by at least {_n(s_['lap'], 0)} mm", "a_left, a_right", "", f"{_n(s_['a_left'], 0)}, {_n(s_['a_right'], 0)}", "mm")
        x_w, m_w, r_w = meet_resistance(inp, cover, beam, i, geo[i].lc, left, right, s_["a_left"], s_["a_right"], reach)
        sheet.check(f"lap_hogging_{i + 1}", f"{REF}, Cl. 26.2.1, 26.2.5.1(c)", f"Span {i + 1}: hogging within the resistance of the top bars "
                    f"developed at each section (each set in proportion to its embedment, up to L_d; worst at {_n(x_w, 0)} from the left face)",
                    "M_u", m_w, "<=", "M_u,R", r_w, "kN m")
    bbs = detailing.bar_schedule(inp, reinforcement, sheet)
    quantities = detailing.quantities(inp, bbs)
    drawing = detailing.drawing(inp, reinforcement, bbs)
    charts = _charts(inp, beam, geo)

    if frac > 0:
        applied = ", ".join(f"{100 * fr[j]:.0f}" for j in range(1, n))
        sheet.flag("info", f"Support moments redistributed (Cl. 37.1.1) by {applied} percent at supports 2 to {n}"
                           + (f" ({inp.redistribution_pct:.0f} entered; less where Cl. 37.1.1(d) allows no more)" if stepped else "")
                           + "; the span moments rise to keep equilibrium, and nowhere is the resistance below 70 percent of the elastic moment.",
                   f"{REF}, Cl. 37.1.1")
    sheet.flag("info", "Support moments are taken at the centre line of each support, on the safe side; the face moments of Cl. 22.6.2 "
                       "would be smaller where the beam is monolithic with its supports.", f"{REF}, Cl. 22.6.2")
    if flanged:
        sheet.flag("info", "Where the slab spans parallel to this beam, provide transverse bars over the beam, at least 60 percent of the "
                           "slab's mid-span steel, so that the slab acts as the flange.", f"{REF}, Cl. 23.1.1(b)")
    if any(s.fl.doubly for s in inner_sups):
        sheet.flag("info", "A support section uses the bottom bars as compression steel; they are continued past the face of the support by "
                           "the development length in compression.", f"{REF}, Cl. 26.2.1")

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    j_max = max(range(1, n), key=lambda j: m_sup[j])
    i_max = max(range(n), key=lambda i: m_span[i])
    key_results = [
        {"label": f"Greatest span moment (span {i_max + 1})", "sym": "M_span", "value": round(m_span[i_max], 2), "unit": "kN m", "dp": 2},
        {"label": f"Greatest support moment (support {j_max + 1})", "sym": "M_sup", "value": round(m_sup[j_max], 2), "unit": "kN m", "dp": 2},
        {"label": "Redistribution, least at a support" if stepped else "Redistribution", "sym": "r",
         "value": round(100.0 * min(fr[1:n]), 1), "unit": "%", "dp": 1},
        *({"label": f"Span {i + 1} bottom", "sym": "", "value": s.bottom.label(), "unit": "", "dp": 0} for i, s in enumerate(secs)),
        *({"label": f"Top over support {j + 1}", "sym": "", "value": s.top.label(), "unit": "", "dp": 0} for j, s in enumerate(sups) if s),
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
    ]
    data: dict[str, Any] = {
        "method": "elastic", "cover": cover, "w_self": round(w_self, 4), "d_max": round(d_max, 2), "redistribution": frac,
        "redistribution_applied": [round(x, 6) for x in fr],
        "l_eff": [round(g.l_eff, 2) for g in geo], "rules": [g.rule for g in geo],
        "m_span": [round(m, 4) for m in m_span], "m_span_elastic": [round(m, 4) for m in m_span_e],
        "m_sup": [round(m, 4) for m in m_sup], "m_sup_elastic": [round(m, 4) for m in hog_e],
        "v_end": [round(shear_at_end(0, True), 4), round(shear_at_end(n - 1, False), 4)],
        "ext": [{k: round(v, 1) for k, v in e.items()} for e in ext],
        "defl": [{k: round(v, 5) for k, v in x.items()} for x in defl],
        "span": [{"d": round(s.d, 2), "d_c": round(s.d_c, 2), "ast_req": round(s.fl.ast_req, 2), "asc_req": round(s.fl.asc_req, 2),
                  "ast_prov": round(s.bottom.area, 2), "asc_prov": round(s.top.area, 2), "capacity": round(s.cap.mu / 1e6, 4),
                  "xu": round(s.cap.xu, 3), "xu_max": round(s.fl.xu_max, 3), "doubly": s.fl.doubly,
                  "bf": round(s.flange.bf, 2) if s.flange else None} for s in secs],
        "support": [None] + [{"d": round(s.d, 2), "d_c": round(s.d_c, 2), "ast_req": round(s.fl.ast_req, 2), "asc_req": round(s.fl.asc_req, 2),
                              "ast_prov": round(s.top.area, 2), "asc_prov": round(s.compression.area, 2), "capacity": round(s.cap.mu / 1e6, 4),
                              "xu": round(s.cap.xu, 3), "xu_max": round(s.fl.xu_max, 3), "doubly": s.fl.doubly} for s in inner_sups] + [None],
        "stirrups": [{"left": s["left"], "right": s["right"]} for s in stirrups],
        "curtailment": cut_plan["summary"],
    }
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok", "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok), "checks_total": len(checks),
        "max_utilisation": max(utils) if utils else None,
        "key_results": key_results, "data": data, "reinforcement": reinforcement, "sheet": sheet.to_dict(),
        "bbs": bbs, "quantities": quantities, "drawing": drawing, "charts": charts,
    }


def meet_resistance(inp: ContinuousBeamInput, cover: float, beam: Beam, i: int, lc: float, left: SupportSection, right: SupportSection,
                    a_left: float, a_right: float, comp: BarGroup) -> tuple[float, float, float]:
    """Where the top bars of a span's two supports lap with each other: the section where the hogging comes closest to the resistance of
    the bars developed there. Each set counts in proportion to its embedment beyond the section, up to L_d (Cl. 26.2.1), at its own depth;
    the bottom bars that run the length of the span (``comp``) act as compression steel. Returns (x from the left face, hogging,
    resistance), kN m."""
    b, fck, fy, dst = inp.width_mm, float(inp.fck), float(inp.fy), inp.stirrup_dia_mm
    ld_l, ld_r = is456.development_length(left.top.dia, fck, fy), is456.development_length(right.top.dia, fck, fy)
    worst = (lc / 2.0, 0.0, math.inf)
    for x, m in beam.scan(i, lambda x: beam.hog(i, x), 0.0, lc):
        a_l = left.top.area * min(1.0, max(a_left - x, 0.0) / ld_l)
        a_r = right.top.area * min(1.0, max(x - (lc - a_right), 0.0) / ld_r)
        a_eff = a_l + a_r
        if m <= 1e-9:
            continue
        r = 0.0
        if a_eff > 0:
            d = (a_l * left.d + a_r * right.d) / a_eff  # the centroid of the developed bars
            r = is456.moment_capacity(fck, fy, b, d, a_eff, comp.area, cover + dst + comp.dia / 2.0).mu / 1e6
        if worst[2] == math.inf or m * worst[2] > worst[1] * r:
            worst = (x, m, r)
    return worst if worst[2] != math.inf else (lc / 2.0, 0.0, 0.0)


def _redistribution_d(sheet: CalcSheet, key: str, label: str, md: float, me: float, mr: float, xu: float, d: float) -> None:
    """Cl. 37.1.1(d) where the resistance provided is below the elastic moment and the moment was reduced."""
    red = max(0.0, 1.0 - md / me) if me > 0 else 0.0
    if red <= 0 or mr >= me:
        return
    sheet.check(f"xu_redistribution_{key}", f"{REF}, Cl. 37.1.1(d)", f"{label}: resistance below the elastic moment ({_n(mr)} < {_n(me)} kN m), "
                f"moment reduced by {_n(100 * red, 1)} percent", "x_u/d + dM/100", xu / d + red, "<=", "0.6", 0.6, "", 3)


# ----------------------------------------------------------------------------- curtailment, stirrups, anchorage


def plan(sheet: CalcSheet, inp: ContinuousBeamInput, cover: float, beam: Beam, geo: list[SpanGeom], secs: list[SpanSection],
         sups: list[SupportSection | None], lay: list[dict[str, Any]], stirrups: list[dict[str, Any]]) -> dict[str, Any]:
    """Stirrup bands, cut-offs of the top and bottom bars, and the anchorage of the bottom bars, from the design envelope."""
    n, b, D, dst = len(geo), inp.width_mm, inp.depth_mm, inp.stirrup_dia_mm
    fck, fy, fyv = float(inp.fck), float(inp.fy), is456.shear_fy(inp.fy_stirrup)
    asv = inp.stirrup_legs * bar_area(dst)

    def tc_of(area: float, d: float) -> float:
        return is456.tau_c(fck, 100.0 * area / (b * d))

    def certain(g: BarGroup) -> BarGroup:  # the bars that reach the supports whatever the curtailment
        return (split_for_curtailment(g) or (g, None))[0]

    # ---------------------------------------------------------------- stirrup bands from the shear envelope
    sheet.section("9. Stirrup bands and curtailment")
    zones: list[dict[str, Any]] = []
    for i, sec in enumerate(secs):
        lc = geo[i].lc
        adj = [s for s in (sups[i], sups[i + 1]) if s is not None]
        d_min = min(sec.d, *(s.d for s in adj))
        a_min = min(certain(sec.bottom).area, *(certain(s.top).area for s in adj))
        tc = tc_of(a_min, d_min)
        s_mid = practical_spacing(min(is456.stirrup_spacing_minimum_steel(fyv, asv, b), 0.75 * d_min, 300.0))
        pts = [p.distance_mm for p in inp.point_loads if p.span == i + 1]
        x_lo = 0.0 if any(a < d_min for a in pts) else d_min  # the critical sections (Cl. 22.6.2.1)
        x_hi = lc if any(lc - a < d_min for a in pts) else lc - d_min

        def s_req(x: float, i: int = i, tc: float = tc, d_min: float = d_min, x_lo: float = x_lo, x_hi: float = x_hi) -> float:
            vus = beam.shear(i, min(max(x, x_lo), x_hi)) - tc * b * d_min / 1e3
            return math.inf if vus <= 0 else 0.87 * fyv * asv * d_min / (vus * 1e3)

        prof = beam.scan(i, s_req, 0.0, lc)
        bands: list[tuple[float, float, float]] = []
        run: list[tuple[float, float]] = []
        for x, s in [*prof, (lc + 1.0, math.inf)]:
            if s < s_mid:
                run.append((x, s))
            elif run:
                x0, x1 = run[0][0], run[-1][0]
                sp = practical_spacing(min(s for _, s in run))
                if x0 <= 1e-6:
                    sp, x0 = min(sp, stirrups[i]["left"]), 0.0
                if x1 >= lc - 1e-6:
                    sp, x1 = min(sp, stirrups[i]["right"]), lc
                bands.append((round(x0, 1), round(x1, 1), sp))
                run = []
        zones.append({"s_mid": s_mid, "shear_bands": bands, "tc": tc, "d": d_min})
        if bands:
            sheet.step(f"{REF}, Cl. 40.4, 26.5.1.6", f"Span {i + 1}: closer stirrups where the shear exceeds the resistance at {s_mid:.0f} c/c "
                       f"(minimum shear steel; tau_c = {tc:.3f} with the least tension steel and d along the span)", "from - to @ s", "",
                       "; ".join(f"{x0:.0f} - {x1:.0f} @ {s:.0f}" for x0, x1, s in bands), "mm")
        else:
            sheet.step(f"{REF}, Cl. 40.4, 26.5.1.6", f"Span {i + 1}: minimum shear steel suffices throughout", "s_v", "", s_mid, "mm", 0)

    def spacing_at(i: int, x: float) -> float:
        z = zones[i]
        return min([s for x0, x1, s in z["shear_bands"] + z.get("cut_bands", []) if x0 - 1e-6 <= x <= x1 + 1e-6], default=z["s_mid"])

    hoop = 2.0 * ((b - 2.0 * cover) + (D - 2.0 * cover)) + 2.0 * max(10.0 * dst, 75.0) - 12.0 * dst
    hoop_kg = hoop / 1000.0 * bar_unit_weight(dst) * (2 if inp.stirrup_legs == 4 else 1)

    # ---------------------------------------------------------------- anchorage helpers (Cl. 26.2.3.3(c))
    def m1_of(sec: SpanSection, d: float, area: float) -> float:
        bf = sec.flange.bf if sec.flange is not None else None
        return is456.moment_at_design_stress(fck, fy, b, d, area, bf, sec.flange.df if bf else 0.0) / 1e6

    def end_shear(i: int, left: bool) -> float:
        return beam.shear(i, 0.0 if left else geo[i].lc)

    def end_sides(i: int) -> list[bool]:
        return ([True] if i == 0 else []) + ([False] if i == n - 1 else [])

    def infl_sides(i: int) -> list[tuple[bool, float, float]]:
        lc, out = geo[i].lc, []
        for left in ([True] if i > 0 else []) + ([False] if i < n - 1 else []):
            x = beam.inflection(i, left)
            if x is not None:
                out.append((left, x, beam.shear(i, x if left else lc - x)))
        return out

    def bars_anchor(i: int, grp: BarGroup, d: float) -> bool:
        m1 = m1_of(secs[i], d, grp.area)
        if any(end_detail(inp.support_width_mm, cover, grp.dia, fck, fy, m1, end_shear(i, left), "straight") is None for left in end_sides(i)):
            return False
        return all(anchorage_ok(grp.dia, fck, fy, m1, v, max(d, 12.0 * grp.dia), False)[0] for _, _, v in infl_sides(i))

    # ---------------------------------------------------------------- bottom bars in each span
    def bottom_cut(i: int) -> dict[str, Any] | None:
        sec, lc = secs[i], geo[i].lc
        label = f"Span {i + 1} bottom bars"
        split = split_for_curtailment(sec.bottom)
        if split is None:
            sheet.step(f"{REF}, Cl. 26.2.3.3", f"{label}: {sec.bottom.label()}, too few bars to curtail", "", "", "", "")
            return None
        cont, cut = split
        for sup in (s for s in (sups[i], sups[i + 1]) if s is not None):  # their compression steel: only the continuing bars reach them
            cap = is456.moment_capacity(fck, fy, b, sup.d, sup.top.area, cont.area, cover + dst + cont.dia / 2.0)
            if cont.area < sup.fl.asc_req or cap.limited or cap.mu < sup.mu * 1e6:
                sheet.step(f"{REF}, Cl. 38.1, Annex G-1.2", f"{label}: support {sup.kind} needs these bars as compression steel; {cont.label()} alone "
                           "would not do: no curtailment", "A_sc,req", "", sup.fl.asc_req, "mm2", 0)
                return None
        d_c = D - (cover + dst + cont.dia / 2.0)
        if sec.flange is not None:
            m_cont = is456.moment_capacity_flanged(fck, fy, sec.flange.bf, b, sec.flange.df, d_c, cont.area, sec.top.area, sec.d_c).mu / 1e6
        else:
            m_cont = is456.moment_capacity(fck, fy, b, d_c, cont.area, sec.top.area, sec.d_c).mu / 1e6
        ld = is456.development_length(cut.dia, fck, fy)
        beyond = max(sec.d, 12.0 * cut.dia)
        sheet.step(f"{REF}, Cl. 26.2.3.3", f"{label}: {cont.label()} of {sec.bottom.label()} run into the supports; moment of resistance", "M_R,cont",
                   f"d = {d_c:.1f}", m_cont, "kN m")
        prof = beam.scan(i, lambda x: beam.sag(i, x), 0.0, lc)
        peak = max(m for _, m in prof)
        if peak <= 1e-9:
            sheet.step(f"{REF}, Cl. 26.2.3.3", f"{label}: no sagging in this span: no curtailment", "", "", "", "")
            return None
        plateau = [x for x, m in prof if m >= 0.995 * peak]
        p1, p2 = min(plateau), max(plateau)
        need = [x for x, m in prof if m > m_cont]
        tl, tr = (min(need), lc - max(need)) if need else (p1, lc - p2)
        xl = math.floor(min(tl - beyond, p1 - ld) / SETTING_OUT + 1e-9) * SETTING_OUT
        xr = math.floor(min(tr - beyond, lc - p2 - ld) / SETTING_OUT + 1e-9) * SETTING_OUT
        sheet.step(f"{REF}, Cl. 26.2.3.1, 26.2.1", f"{label}: the other bars stop the greater of d and 12 phi short of where the continuing bars "
                   "suffice, and at least L_d from the section of greatest moment", "x_left, x_right", "", f"{xl:.0f}, {xr:.0f}", "mm")
        if min(xl, xr) < sec.d:
            sheet.step(f"{REF}, Cl. 26.2.3.1", f"{label}: a cut-off would fall within d of a support: no curtailment", "", "", "", "")
            return None
        res: dict[str, Any] = {"cont": cont, "cut": cut, "left": xl, "right": xr, "bands": [], "conditions": [], "d_cont": d_c, "m_cont": m_cont}
        for side, xs in (("left", xl), ("right", lc - xr)):
            a_req = is456.design_rectangular(beam.sag(i, xs) * 1e6, fck, fy, b, d_c, sec.d_c).ast_req
            cond, s_b = cutoff_condition(sheet, f"cut_{i + 1}_{side}", f"{label}, {side} cut-off", beam.shear(i, xs), tc_of(cont.area, d_c), b, d_c,
                                         fyv, asv, spacing_at(i, xs), cont, cut, a_req)
            if cond is None:
                return None
            res["conditions"].append({"side": side, "condition": cond, "s_b": s_b})
            if cond == "b":
                z = (xs, xs + 0.75 * d_c) if side == "left" else (xs - 0.75 * d_c, xs)
                res["bands"].append((max(z[0], 0.0), min(z[1], lc), s_b))
        if res["bands"]:
            saved = (xl + xr) * cut.count / 1000.0 * bar_unit_weight(cut.dia)
            extra = sum(max(1, math.ceil((z[1] - z[0]) / z[2])) for z in res["bands"]) * hoop_kg
            if extra >= saved:
                sheet.step("Practice", f"{label}: the closer stirrups would weigh as much as the steel saved: no curtailment", "", "", "", "")
                return None
        if not bars_anchor(i, cont, d_c):
            sheet.step(f"{REF}, Cl. 26.2.3.3(c)", f"{label}: the continuing bars alone could not be anchored at the supports or the points of "
                       "inflection: no curtailment", "", "", "", "")
            return None
        sheet.check(f"cut_{i + 1}_third", f"{REF}, Cl. 26.2.3.3", f"{label}: at least a third of the bottom steel runs into the supports",
                    "A_st,cont", cont.area, ">=", "A_st/3", sec.bottom.area / 3.0, "mm2", 0, ratio=False)
        return res

    bottoms = [bottom_cut(i) for i in range(n)]
    for i, res in enumerate(bottoms):
        zones[i]["cut_bands"] = list((res or {}).get("bands", []))

    def reaching(i: int) -> BarGroup:
        return bottoms[i]["cont"] if bottoms[i] else secs[i].bottom

    # ---------------------------------------------------------------- top bars over each interior support
    def top_cut(j: int) -> dict[str, Any] | None:
        sup = sups[j]
        assert sup is not None
        label = f"Top bars over support {j + 1}"
        split = split_for_curtailment(sup.top)
        if split is None:
            sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: {sup.top.label()}, too few bars to curtail; all run to the point of inflection", "", "", "", "")
            return None
        long_, short = split
        d_l = D - (cover + dst + long_.dia / 2.0)
        comp = min((reaching(j - 1), reaching(j)), key=lambda g: g.area)
        comp_y = cover + dst + comp.dia / 2.0
        m_long = is456.moment_capacity(fck, fy, b, d_l, long_.area, comp.area, comp_y).mu / 1e6
        ld = is456.development_length(short.dia, fck, fy)
        beyond = max(sup.d, 12.0 * short.dia)
        sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: {long_.label()} of {sup.top.label()} run to the point of inflection; moment of resistance "
                   f"with {comp.label()} as compression steel", "M_R,long", f"d = {d_l:.1f}", m_long, "kN m")
        res: dict[str, Any] = {"long": long_, "short": short, "cut": {}, "bands": [], "conditions": [], "d_long": d_l, "m_long": m_long}
        for side, i, at_left in (("left", j - 1, False), ("right", j, True)):
            lc = geo[i].lc
            ext = lay[i]["a_left" if at_left else "a_right"]

            def hog(x: float, i: int = i, at_left: bool = at_left, lc: float = lc) -> float:
                return beam.hog(i, x if at_left else lc - x)

            x_t = max((x for x, m in beam.scan(i, hog, 0.0, min(ext, lc)) if m > m_long), default=0.0)
            x_cut = math.ceil(max(x_t + beyond, ld) / SETTING_OUT - 1e-9) * SETTING_OUT
            sheet.step(f"{REF}, Cl. 26.2.3.1, 26.2.1", f"{label}, into span {i + 1}: the other bars stop beyond the point where the long ones suffice "
                       "by the greater of d and 12 phi, and at least L_d from the face", "x_cut = max(x_t + max(d, 12 phi), L_d)", f"x_t = {x_t:.0f}",
                       x_cut, "mm", 0)
            if x_cut >= ext - SETTING_OUT:
                sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: that is as far as the long bars go: no curtailment", "", "", "", "")
                return None
            xs = x_cut if at_left else lc - x_cut
            a_req = is456.design_rectangular(hog(x_cut) * 1e6, fck, fy, b, d_l, comp_y).ast_req
            cond, s_b = cutoff_condition(sheet, f"cut_s{j + 1}_{side}", f"{label}, into span {i + 1}", beam.shear(i, xs), tc_of(long_.area, d_l), b, d_l,
                                         fyv, asv, spacing_at(i, xs), long_, short, a_req)
            if cond is None:
                return None
            res["conditions"].append({"span": i + 1, "side": side, "x_cut": x_cut, "condition": cond, "s_b": s_b})
            if cond == "b":
                z = (xs - 0.75 * d_l, xs) if at_left else (xs, xs + 0.75 * d_l)
                res["bands"].append((i, (max(z[0], 0.0), min(z[1], lc), s_b)))
            res["cut"][side] = x_cut
        if res["bands"]:
            saved = sum(lay[i]["a_left" if side == "right" else "a_right"] - res["cut"][side] for side, i in (("left", j - 1), ("right", j))) * \
                short.count / 1000.0 * bar_unit_weight(short.dia)
            extra = sum(max(1, math.ceil((z[1] - z[0]) / z[2])) for _, z in res["bands"]) * hoop_kg
            if extra >= saved:
                sheet.step("Practice", f"{label}: the closer stirrups would weigh as much as the steel saved: no curtailment", "", "", "", "")
                return None
        sheet.check(f"cut_s{j + 1}_third", f"{REF}, Cl. 26.2.3.4", f"{label}: at least a third of the top steel runs beyond the point of inflection",
                    "A_st,long", long_.area, ">=", "A_st/3", sup.top.area / 3.0, "mm2", 0, ratio=False)
        return res

    tops: list[dict[str, Any] | None] = [None] + [top_cut(j) for j in range(1, n)] + [None]
    for res in tops:
        for i, z in (res or {}).get("bands", []):
            zones[i]["cut_bands"].append(z)

    # ---------------------------------------------------------------- Cl. 26.2.3.3(c) with the bars that reach each point
    sheet.section("10. Anchorage of the bottom bars")
    end_details = {"left": "straight", "right": "straight"}
    embed = inp.support_width_mm - cover
    for i, sec in enumerate(secs):
        res = bottoms[i]
        grp = res["cont"] if res else sec.bottom
        d = res["d_cont"] if res else sec.d
        m1 = m1_of(sec, d, grp.area)
        for left in end_sides(i):
            side = "left" if left else "right"
            v = end_shear(i, left)
            start = "bend" if embed < is456.development_length(grp.dia, fck, fy) / 3.0 else "straight"  # Cl. 26.2.3.3(a) bends them already
            detail = end_details[side] = end_detail(inp.support_width_mm, cover, grp.dia, fck, fy, m1, v, start) or "hook"
            if detail != start:
                sheet.step(f"{REF}, Cl. 26.2.2.1(b)", f"Support {1 if left else n + 1}: a {'straight bar' if start == 'straight' else '90 degree bend'} "
                           "does not meet Cl. 26.2.3.3(c): " + ("bent up, a 90 degree bend worth 8 diameters" if detail == "bend"
                                                                 else "a standard U-hook, worth 16 diameters"), "", "", "", "")
            l0 = end_l0(inp.support_width_mm, cover, grp.dia, fy, detail)
            text = {"straight": "beyond the centre of the support", "bend": "to the start of the bend, plus 8 phi",
                    "hook": "to the start of the hook, plus 16 phi"}[detail]
            if not anchorage_check(sheet, f"anchorage_end_{side}", f"End support {1 if left else n + 1}: {grp.label()} of span {i + 1}", grp.dia, fck,
                                   fy, m1, v, l0, True, text):
                sheet.flag("error", f"The bottom bars of span {i + 1} are too large to develop their stress at the end support (Cl. 26.2.3.3(c)): "
                                    "use smaller bars or wider supports.", f"{REF}, Cl. 26.2.3.3(c)")
        sides = infl_sides(i)
        if not sides:
            if i not in (0, n - 1) or n == 1:
                sheet.step(f"{REF}, Cl. 26.2.3.3(c)", f"Span {i + 1}: no sagging, so no point of inflection for the bottom bars", "", "", "", "")
            continue
        left, x, v = max(sides, key=lambda t: t[2])
        if not anchorage_check(sheet, f"anchorage_inflection_{i + 1}", f"Span {i + 1}, point of inflection near support "
                               f"{i + 1 if left else i + 2} ({x:.0f} from the face): {grp.label()}", grp.dia, fck, fy, m1, v, max(d, 12.0 * grp.dia),
                               False, "the greater of d and 12 phi"):
            sheet.flag("error", f"The bottom bars of span {i + 1} are too large to develop their stress at the point of inflection "
                                "(Cl. 26.2.3.3(c)): use smaller bars.", f"{REF}, Cl. 26.2.3.3(c)")

    # ---------------------------------------------------------------- stirrup positions
    for i in range(n):
        z = zones[i]
        z["bands"] = sorted(set(z["shear_bands"] + [(round(a, 1), round(c, 1), s) for a, c, s in z["cut_bands"]]))
        z["positions"] = list(stirrup_positions(geo[i].lc, cover, False, z["s_mid"], z["bands"], symmetric=False))

    def grp_label(g: BarGroup | None) -> str | None:
        return g.label() if g else None

    record = {
        "top": [({"long": _grp(t["long"]), "short": _grp(t["short"]), "cut": t["cut"]} if t else None) for t in tops],
        "bottom": [({"continuing": _grp(r["cont"]), "curtailed": _grp(r["cut"]), "left": r["left"], "right": r["right"]} if r else None)
                   for r in bottoms],
        "zones": [{"s_mid": z["s_mid"], "bands": z["bands"], "positions": z["positions"]} for z in zones],
        "end_detail": end_details,
    }
    summary = {
        "top": [({"long": grp_label(t["long"]), "short": grp_label(t["short"]), "cut": t["cut"], "conditions": t["conditions"],
                  "d_long": round(t["d_long"], 2), "m_long": round(t["m_long"], 4)} if t else None) for t in tops],
        "bottom": [({"continuing": grp_label(r["cont"]), "curtailed": grp_label(r["cut"]), "left": r["left"], "right": r["right"],
                     "conditions": r["conditions"], "d_cont": round(r["d_cont"], 2), "m_cont": round(r["m_cont"], 4)} if r else None)
                   for r in bottoms],
        "zones": [{"s_mid": z["s_mid"], "bands": z["bands"], "count": len(z["positions"]), "tc": round(z["tc"], 4), "d": round(z["d"], 2)}
                  for z in zones],
        "end_detail": end_details,
    }
    return {"record": record, "summary": summary}


# ------------------------------------------------------------------------------ charts


def _charts(inp: ContinuousBeamInput, beam: Beam, geo: list[SpanGeom]) -> list[dict[str, Any]]:
    """Design envelopes along the beam, x from the face of the first support."""
    sw = inp.support_width_mm
    sag, hog, shear = [], [], []
    x0 = 0.0
    for i, g in enumerate(geo):
        for k in range(41):
            xf = g.lc * k / 40.0
            x = round((x0 + xf) / 1000.0, 3)
            sag.append([x, round(beam.sag(i, xf), 2)])
            hog.append([x, round(-beam.hog(i, xf), 2)])
            shear.append([x, round(beam.shear(i, xf), 2)])
        x0 += g.lc + sw
    return [
        {"id": "moments", "title": "Design moment envelope (after redistribution, not below 0.7 of the elastic)",
         "x": {"label": "x", "unit": "m"}, "y": {"label": "M_u", "unit": "kN m"},
         "series": [{"name": "Greatest sagging", "kind": "line", "points": sag}, {"name": "Greatest hogging", "kind": "line", "points": hog}],
         "note": "Clear spans only, x from the face of the first support; hogging drawn negative. The supports lie between the spans."},
        {"id": "shear", "title": "Design shear envelope", "x": {"label": "x", "unit": "m"}, "y": {"label": "V_u", "unit": "kN"},
         "series": [{"name": "Greatest shear", "kind": "line", "points": shear}],
         "note": "Greatest shear in any arrangement after redistribution, clear spans only."},
    ]
