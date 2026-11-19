"""Curtailment of bars and stirrup zones for the continuous beam (STR-016).

The moment and shear along each span come from the elastic envelope of the arrangements of Cl. 22.4.1
(`engineering/continuous.py`), scaled up where needed so that its peaks are not below the Table 12 and 13
values the sections were designed for. With those diagrams, as for the simple beam:

* top bars over each support: at least a third (and two bars) run to the point of inflection and beyond
  (Cl. 26.2.3.4, as before); the others stop where the long ones suffice, beyond it by the greater of d and
  12 phi and at least L_d from the face (Cl. 26.2.3.1, 26.2.1);
* bottom bars in each span: at least a third (and the corner bars) run into the supports (Cl. 26.2.3.3); the
  others stop where the continuing ones suffice, less the greater of d and 12 phi, and at least L_d from the
  section of greatest moment;
* Cl. 26.2.3.2 at every cut-off, by (a), (c) or (b) as for the simple beam;
* stirrups at the designed spacing near the supports and at the minimum-steel spacing where the shear allows.

Pure: no framework imports.
"""

from __future__ import annotations

import math
from typing import Any

from app.engineering import continuous as analysis
from app.engineering import is456
from app.engineering.rebar import BarGroup, bar_unit_weight
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.beam import (
    BEND_90_ANCHORAGE,
    SETTING_OUT,
    anchorage_check,
    anchorage_ok,
    cutoff_condition,
    practical_spacing,
    split_for_curtailment,
    stirrup_positions,
)

REF = is456.CODE
POINTS = 401


def _interp(rows: list[tuple[float, ...]], x: float, col: int) -> float:
    if x <= rows[0][0]:
        return rows[0][col]
    if x >= rows[-1][0]:
        return rows[-1][col]
    step = rows[1][0] - rows[0][0]
    i = min(int(x / step), len(rows) - 2)
    t = (x - rows[i][0]) / step
    return rows[i][col] + t * (rows[i + 1][col] - rows[i][col])


class Diagrams:
    """Scaled moment and shear along every span, x in mm from the face of the span's left support."""

    def __init__(self, spans_m: list[float], lc: float, wd: float, wl: float, m_span: list[float], m_support: list[float],
                 v_left: list[float], v_right: list[float]) -> None:
        self.n, self.lc = len(spans_m), lc
        self.off = [(s * 1000.0 - lc) / 2.0 for s in spans_m]
        self.m = analysis.envelope(spans_m, wd, wl, POINTS)
        self.v = analysis.shear_envelope(spans_m, wd, wl, POINTS)
        self.k_sag = [max(1.0, m_span[i] / max(max(r[2] for r in self.m[i]), 1e-9)) for i in range(self.n)]
        self.k_hog = [(max(1.0, m_support[i] / max(-self.m[i][0][1], 1e-9)) if m_support[i] > 0 else 1.0,
                       max(1.0, m_support[i + 1] / max(-self.m[i][-1][1], 1e-9)) if m_support[i + 1] > 0 else 1.0) for i in range(self.n)]
        self.k_v = [(max(1.0, v_left[i] / max(self.v[i][0][1], 1e-9)), max(1.0, v_right[i] / max(self.v[i][-1][1], 1e-9))) for i in range(self.n)]

    def _x(self, i: int, xf: float) -> float:
        return (xf + self.off[i]) / 1000.0

    def sag(self, i: int, xf: float) -> float:
        return self.k_sag[i] * max(_interp(self.m[i], self._x(i, xf), 2), 0.0)

    def hog(self, i: int, xf: float) -> float:
        k = self.k_hog[i][0] if xf <= self.lc / 2.0 else self.k_hog[i][1]
        return k * max(-_interp(self.m[i], self._x(i, xf), 1), 0.0)

    def shear(self, i: int, xf: float) -> float:
        k = self.k_v[i][0] if xf <= self.lc / 2.0 else self.k_v[i][1]
        return k * _interp(self.v[i], self._x(i, xf), 1)


def diagrams(n: int, spans_m: list[float], lc: float, wd: float, wl: float, moments: dict[str, float], shears: dict[str, float]) -> Diagrams:
    """The scaled diagrams of a beam of n spans: Table 12 moments (end, interior, b, c) and Table 13 shears (A, B1, B2, C)."""
    m_span = [moments["end"]] + [moments["interior"]] * (n - 2) + [moments["end"]]
    m_sup = [0.0, moments["b"]] + [moments["c"]] * (n - 3) + [moments["b"], 0.0]
    v_left = [shears["A"], shears["B2"]] + [shears["C"]] * (n - 3) + [shears["B1"]]
    v_right = [shears["B1"]] + [shears["C"]] * (n - 3) + [shears["B2"], shears["A"]]
    if n == 3:
        v_left, v_right = [shears["A"], shears["B2"], shears["B1"]], [shears["B1"], shears["B2"], shears["A"]]
    return Diagrams(spans_m, lc, wd, wl, m_span, m_sup, v_left, v_right)


def inflection_point(dg: Diagrams, i: int, from_left: bool) -> float:
    """Distance from the face to where the greatest moment turns positive: the point of inflection of the bottom bars."""
    lc = dg.lc
    prof = _scan((lambda x: dg.sag(i, x)) if from_left else (lambda x: dg.sag(i, lc - x)), 0.0, lc / 2.0)
    return next((x for x, m in prof if m > 1e-9), lc / 2.0)


def inflection_shear(dg: Diagrams, kind: str) -> float:
    """The greatest shear at a point of inflection of the bottom bars next to an interior support, over the spans of a type, kN."""
    n, lc = dg.n, dg.lc
    sides = [(0, False)] if kind == "end" else [(i, fl) for i in range(1, n - 1) for fl in (True, False)]
    worst = 0.0
    for i, from_left in sides:
        x = inflection_point(dg, i, from_left)
        worst = max(worst, dg.shear(i, x if from_left else lc - x))
    return worst


def _scan(f: Any, x0: float, x1: float, steps: int = 400) -> list[tuple[float, float]]:
    return [(x0 + (x1 - x0) * k / steps, f(x0 + (x1 - x0) * k / steps)) for k in range(steps + 1)]


def _tc(fck: float, area: float, b: float, d: float) -> float:
    return is456.tau_c(fck, 100.0 * area / (b * d))


def plan(sheet: CalcSheet, inp: Any, cover: float, sections: dict[str, Any], spans_m: list[float], wd: float, wl: float,
         moments: dict[str, float], shears: dict[str, float], extents: dict[str, float], stirrups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Cut-offs, stirrup positions and the steps for the sheet. ``sections``: end, interior, support_b, support_c (or None)."""
    n, lc, b, D, dst = inp.spans, inp.clear_span_mm, inp.width_mm, inp.depth_mm, inp.stirrup_dia_mm
    fck, fy, fyv = float(inp.fck), float(inp.fy), is456.shear_fy(inp.fy_stirrup)
    asv = inp.stirrup_legs * math.pi * dst**2 / 4.0
    end, inner, sup_b, sup_c = sections["end"], sections["interior"], sections["support_b"], sections["support_c"]
    dg = diagrams(n, spans_m, lc, wd, wl, moments, shears)
    interior = list(range(1, n - 1))

    sheet.section("9. Curtailment and stirrup zones")
    sheet.step(f"{REF}, Cl. 22.4.1", "Moments and shears along the spans: elastic envelope of the load arrangements, scaled up where its peaks fall "
               "below the Table 12 and 13 values", "k", ", ".join(f"span {i + 1}: {dg.k_sag[i]:.3f}" for i in range(min(n, 3))), "", "")

    # ---------------------------------------------------------------- stirrup zones
    def zone_lengths(i: int, s_mid: float, d: float, area: float) -> tuple[float, float] | None:
        v_r = (_tc(fck, area, b, d) * b * d + 0.87 * fyv * asv * d / s_mid) / 1e3
        left = max((x for x, v in _scan(lambda x: dg.shear(i, x), 0.0, lc / 2.0) if v > v_r), default=0.0)
        right = max((x for x, v in _scan(lambda x: dg.shear(i, lc - x), 0.0, lc / 2.0) if v > v_r), default=0.0)
        if left >= lc / 2.0 - s_mid or right >= lc / 2.0 - s_mid:
            return None
        return left, right

    zones: dict[str, dict[str, Any]] = {}
    for kind, sec, idx in (("end", end, [0]), ("interior", inner, interior)):
        s_end = stirrups[kind]["spacing"]
        d_min = min(sec.d, sup_b.d, *(x.d for x in [sup_c] if x))
        a_min = min(sec.bottom.area, sup_b.top.area, *(x.top.area for x in [sup_c] if x))
        s_mid = practical_spacing(min(is456.stirrup_spacing_minimum_steel(fyv, asv, b), 0.75 * d_min, 300.0))
        lens = [zone_lengths(i, s_mid, d_min, a_min) for i in idx] if s_mid > s_end else [None]
        if any(z is None for z in lens):
            zones[kind] = {"applied": False, "s_end": s_end, "s_mid": s_end, "left": 0.0, "right": 0.0}
            sheet.step(f"{REF}, Cl. 40.4", f"{'End' if kind == 'end' else 'Interior'} spans: one stirrup spacing throughout", "s_v", "", s_end, "mm", 0)
            continue
        left = max(z[0] for z in lens if z)
        right = max(z[1] for z in lens if z)
        if kind == "interior":
            left = right = max(left, right)
        zones[kind] = {"applied": True, "s_end": s_end, "s_mid": s_mid, "left": left, "right": right}
        sheet.step(f"{REF}, Cl. 40.4, 26.5.1.6", f"{'End' if kind == 'end' else 'Interior'} spans: stirrups at {s_end:.0f} c/c from the faces to where "
                   f"the shear falls to the resistance at {s_mid:.0f} c/c (minimum shear steel)", "x_left, x_right", "", f"{left:.0f}, {right:.0f}", "mm")

    def spacing_at(kind: str, xf: float) -> float:
        z = zones[kind]
        return z["s_end"] if not z["applied"] or xf <= z["left"] + 1e-6 or xf >= lc - z["right"] - 1e-6 else z["s_mid"]

    bands: dict[str, list[tuple[float, float, float]]] = {"end": [], "interior": []}
    out: dict[str, Any] = {"zones": zones}
    hoop = 2.0 * ((b - 2.0 * cover) + (D - 2.0 * cover)) + 2.0 * max(10.0 * dst, 75.0) - 12.0 * dst
    hoop_kg = hoop / 1000.0 * bar_unit_weight(dst) * (2 if inp.stirrup_legs == 4 else 1)

    # ---------------------------------------------------------------- top bars over the supports
    def top_cut(label: str, key: str, sup: Any, sides: list[tuple[str, int, bool, float]]) -> dict[str, Any] | None:
        """sides: (span kind, span index, support at the span's left end, extent of the long bars from the face)."""
        split = split_for_curtailment(sup.top)
        if split is None:
            sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: {sup.top.label()}, too few bars to curtail; all run to the point of inflection", "", "", "", "")
            return None
        long_, short = split
        d_l = D - (cover + dst + long_.dia / 2.0)
        m_long = is456.moment_capacity(fck, fy, b, d_l, long_.area, sup.compression.area, sup.d_c).mu / 1e6
        ld = is456.development_length(short.dia, fck, fy)
        beyond = max(sup.d, 12.0 * short.dia)
        sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: {long_.label()} of {sup.top.label()} run to the point of inflection; moment of resistance",
                   "M_R,long", f"d = {d_l:.1f}", m_long, "kN m")
        res: dict[str, Any] = {"long": long_, "short": short, "cut": {}, "bands": [], "conditions": [], "d_long": d_l, "m_long": m_long}
        for kind, i, at_left, ext in sides:
            def hog(x: float, i: int = i, at_left: bool = at_left) -> float:
                return dg.hog(i, x if at_left else lc - x)
            x_t = max((x for x, m in _scan(hog, 0.0, ext) if m > m_long), default=0.0)
            x_cut = math.ceil(max(x_t + beyond, ld) / SETTING_OUT - 1e-9) * SETTING_OUT
            sheet.step(f"{REF}, Cl. 26.2.3.1, 26.2.1", f"{label}, into span {i + 1}: the other bars stop beyond the point where the long ones "
                       "suffice by the greater of d and 12 phi, and at least L_d from the face", "x_cut = max(x_t + max(d, 12 phi), L_d)",
                       f"x_t = {x_t:.0f}", x_cut, "mm", 0)
            if x_cut >= ext - SETTING_OUT:
                sheet.step(f"{REF}, Cl. 26.2.3.4", f"{label}: that is as far as the long bars go: no curtailment", "", "", "", "")
                return None
            xs = x_cut if at_left else lc - x_cut
            a_req = is456.design_rectangular(hog(x_cut) * 1e6, fck, fy, b, d_l, sup.d_c).ast_req
            where = f"into span {i + 1}"
            cond, s_b = cutoff_condition(sheet, f"{key}_{i + 1}{'l' if at_left else 'r'}", f"{label}, {where}", dg.shear(i, xs),
                                         _tc(fck, long_.area, b, d_l), b, d_l, fyv, asv, spacing_at(kind, xs), long_, short, a_req)
            if cond is None:
                return None
            res["conditions"].append({"span": i + 1, "at_left": at_left, "x_cut": x_cut, "condition": cond, "s_b": s_b})
            if cond == "b":
                z = (xs - 0.75 * d_l, xs) if at_left else (xs, xs + 0.75 * d_l)
                res["bands"].append((kind, (max(z[0], 0.0), min(z[1], lc), s_b)))
            res["cut"][kind] = max(res["cut"].get(kind, 0.0), x_cut)  # the farthest any side needs
        if res["bands"]:  # closer stirrups only if they weigh less than the steel the short bars save
            saved = sum(ext - res["cut"][k] for k, _, _, ext in sides) * short.count / 1000.0 * bar_unit_weight(short.dia)
            extra = sum(max(1, math.ceil((z[1] - z[0]) / z[2])) for _, z in res["bands"]) * hoop_kg
            if extra >= saved:
                sheet.step("Practice", f"{label}: the closer stirrups would weigh as much as the steel saved: no curtailment", "", "", "", "")
                return None
        sheet.check(f"{key}_third", f"{REF}, Cl. 26.2.3.4", f"{label}: at least a third of the top steel runs beyond the point of inflection",
                    "A_st,long", long_.area, ">=", "A_st/3", sup.top.area / 3.0, "mm2", 0, ratio=False)
        return res

    tb = top_cut("Top bars over B", "cut_b", sup_b, [("end", 0, False, extents["B_end"]), ("interior", 1, True, extents["B_int"])])
    tc_ = None
    if sup_c is not None:
        # every distinct side of a C support: span 2's end at C, span 3's start, and a span between two C supports (the rest repeat by symmetry)
        sides = [("interior", i, False, extents["C_int"]) for i in range(1, min(n - 2, 3))]
        sides += [("interior", i, True, extents["C_int"]) for i in range(2, min(n - 1, 4))]
        tc_ = top_cut("Top bars over C", "cut_c", sup_c, sides)
    for res in (tb, tc_):
        for kind, z in (res or {}).get("bands", []):
            bands[kind].append(z)
    out["top_b"], out["top_c"] = tb, tc_

    # ---------------------------------------------------------------- anchorage of the bottom bars (Cl. 26.2.3.3(c))
    def m1_of(sec: Any, d: float, area: float) -> float:
        bf = sec.flange.bf if sec.flange is not None else None
        return is456.moment_at_design_stress(fck, fy, b, d, area, bf, sec.flange.df if bf else 0.0) / 1e6

    def inflection(i: int, from_left: bool) -> float:
        return inflection_point(dg, i, from_left)

    embed = inp.support_width_mm - cover

    def end_support(dia: float, m1: float, bend: bool) -> tuple[bool, float]:
        l0 = inp.support_width_mm / 2.0 - cover + (BEND_90_ANCHORAGE * dia if bend else 0.0)
        return anchorage_ok(dia, fck, fy, m1, shears["A"], l0, True)[0], l0

    def bars_anchor(sec: Any, grp: BarGroup, d: float, idx: list[int], has_end: bool) -> bool:
        """Can these bars be anchored at the end support (a bend allowed) and at every point of inflection near an interior support?"""
        m1 = m1_of(sec, d, grp.area)
        if has_end and not end_support(grp.dia, m1, True)[0]:
            return False
        for i in idx:
            for from_left in ((False,) if has_end else (True, False)):
                x = inflection(i, from_left)
                v = dg.shear(i, x if from_left else lc - x)
                if not anchorage_ok(grp.dia, fck, fy, m1, v, max(d, 12.0 * grp.dia), False)[0]:
                    return False
        return True

    # ---------------------------------------------------------------- bottom bars in the spans
    def bottom_cut(label: str, kind: str, sec: Any, idx: list[int]) -> dict[str, Any] | None:
        split = split_for_curtailment(sec.bottom)
        if split is None:
            sheet.step(f"{REF}, Cl. 26.2.3.3", f"{label}: {sec.bottom.label()}, too few bars to curtail", "", "", "", "")
            return None
        cont, cut = split
        d_c = D - (cover + dst + cont.dia / 2.0)
        if sec.flange is not None:
            m_cont = is456.moment_capacity_flanged(fck, fy, sec.flange.bf, b, sec.flange.df, d_c, cont.area, sec.top.area, sec.d_c).mu / 1e6
        else:
            m_cont = is456.moment_capacity(fck, fy, b, d_c, cont.area, sec.top.area, sec.d_c).mu / 1e6
        ld = is456.development_length(cut.dia, fck, fy)
        beyond = max(sec.d, 12.0 * cut.dia)
        sheet.step(f"{REF}, Cl. 26.2.3.3", f"{label}: {cont.label()} of {sec.bottom.label()} run into the supports; moment of resistance", "M_R,cont",
                   f"d = {d_c:.1f}", m_cont, "kN m")
        xl = xr = math.inf
        for i in idx:
            prof = _scan(lambda x, i=i: dg.sag(i, x), 0.0, lc)
            peak = max(m for _, m in prof)
            plateau = [x for x, m in prof if m >= 0.995 * peak]  # the section of greatest moment, wherever in a flat top it falls
            p1, p2 = min(plateau), max(plateau)
            need = [x for x, m in prof if m > m_cont]
            tl, tr = (min(need), lc - max(need)) if need else (p1, lc - p2)
            xl = min(xl, min(tl - beyond, p1 - ld))
            xr = min(xr, min(tr - beyond, lc - p2 - ld))
        if kind == "interior":
            xl = xr = min(xl, xr)
        xl = math.floor(xl / SETTING_OUT + 1e-9) * SETTING_OUT
        xr = math.floor(xr / SETTING_OUT + 1e-9) * SETTING_OUT
        sheet.step(f"{REF}, Cl. 26.2.3.1, 26.2.1", f"{label}: the other bars stop the greater of d and 12 phi short of where the continuing bars "
                   "suffice, and at least L_d from the section of greatest moment", "x_left, x_right", "", f"{xl:.0f}, {xr:.0f}", "mm")
        if min(xl, xr) < sec.d:
            sheet.step(f"{REF}, Cl. 26.2.3.1", f"{label}: a cut-off would fall within d of a support: no curtailment", "", "", "", "")
            return None
        res: dict[str, Any] = {"cont": cont, "cut": cut, "left": xl, "right": xr, "bands": [], "conditions": [], "d_cont": d_c, "m_cont": m_cont}
        for side, xs in (("left", xl), ("right", lc - xr)):
            i = max(idx, key=lambda j: dg.shear(j, xs))
            a_req = is456.design_rectangular(dg.sag(i, xs) * 1e6, fck, fy, b, d_c, sec.d_c).ast_req
            cond, s_b = cutoff_condition(sheet, f"cut_{kind}_{side}", f"{label}, {side} cut-off", dg.shear(i, xs), _tc(fck, cont.area, b, d_c), b, d_c,
                                         fyv, asv, spacing_at(kind, xs), cont, cut, a_req)
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
        if not bars_anchor(sec, cont, d_c, idx, kind == "end"):
            sheet.step(f"{REF}, Cl. 26.2.3.3(c)", f"{label}: the continuing bars alone could not be anchored at the supports or the points of "
                       "inflection: no curtailment", "", "", "", "")
            return None
        sheet.check(f"cut_{kind}_third", f"{REF}, Cl. 26.2.3.3", f"{label}: at least a third of the bottom steel runs into the supports",
                    "A_st,cont", cont.area, ">=", "A_st/3", sec.bottom.area / 3.0, "mm2", 0, ratio=False)
        return res

    be = bottom_cut("End span bottom bars", "end", end, [0])
    bi = bottom_cut("Interior span bottom bars", "interior", inner, interior)
    for kind, res in (("end", be), ("interior", bi)):
        bands[kind] += (res or {}).get("bands", [])
    out["bottom_end"], out["bottom_interior"] = be, bi

    # ---------------------------------------------------------------- Cl. 26.2.3.3(c) with the bars that reach each point
    sheet.section("10. Anchorage of the bottom bars")
    out["end_bend"] = False
    for kind, sec, idx, res in (("end", end, [0], be), ("interior", inner, interior, bi)):
        grp = res["cont"] if res else sec.bottom
        d = res["d_cont"] if res else sec.d
        m1 = m1_of(sec, d, grp.area)
        if kind == "end":
            bent = embed < is456.development_length(grp.dia, fck, fy) / 3.0  # the schedule bends them for Cl. 26.2.3.3(a)
            if not bent and not end_support(grp.dia, m1, False)[0]:
                bent = out["end_bend"] = True
                sheet.step(f"{REF}, Cl. 26.2.2.1(b)", "End supports: straight bars do not meet Cl. 26.2.3.3(c); bent up, a 90 degree bend worth 8 "
                           "diameters", "", "", "", "")
            l0 = end_support(grp.dia, m1, bent)[1]
            if not anchorage_check(sheet, "anchorage_end", f"End supports: {grp.label()}", grp.dia, fck, fy, m1, shears["A"], l0, True,
                                   "beyond the centre of the support" + (", with the bend" if bent else "")):
                sheet.flag("error", "The end span's bottom bars are too large to develop their stress at the end supports (Cl. 26.2.3.3(c)): use "
                                    "smaller bars or wider supports.", f"{REF}, Cl. 26.2.3.3(c)")
        sides = [(i, fl) for i in idx for fl in ((False,) if kind == "end" else (True, False))]
        worst = max(sides, key=lambda t: dg.shear(t[0], inflection(t[0], t[1]) if t[1] else lc - inflection(t[0], t[1])))
        i, from_left = worst
        x = inflection(i, from_left)
        v = dg.shear(i, x if from_left else lc - x)
        side = "B" if kind == "end" else "the interior supports"
        if not anchorage_check(sheet, f"anchorage_inflection_{kind}", f"{'End' if kind == 'end' else 'Interior'} span, point of inflection near "
                               f"{side} ({x:.0f} from the face): {grp.label()}", grp.dia, fck, fy, m1, v, max(d, 12.0 * grp.dia), False,
                               "the greater of d and 12 phi"):
            sheet.flag("error", f"The {kind} span's bottom bars are too large to develop their stress at the point of inflection (Cl. 26.2.3.3(c)): "
                                "use smaller bars.", f"{REF}, Cl. 26.2.3.3(c)")

    # ---------------------------------------------------------------- stirrup positions per span type
    for kind in ("end", "interior"):
        z = zones[kind]
        zl = [(0.0, z["left"], z["s_end"]), (lc - z["right"], lc, z["s_end"])] if z["applied"] else []
        bl = bands[kind]
        if kind == "interior":  # one schedule for every interior span: bands on both sides
            bl = sorted(set(bl + [(lc - b1, lc - b0, s) for b0, b1, s in bl]))
        z["bands"] = [(round(a, 1), round(c, 1), s) for a, c, s in bl]
        z["positions"] = list(stirrup_positions(lc, cover, False, z["s_mid"] if z["applied"] else z["s_end"], zl + bl, symmetric=False))
    return out


def summary(p: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe digest for the result data."""

    def grp(g: BarGroup | None) -> str | None:
        return g.label() if g else None

    tops = {k: ({"long": grp(v["long"]), "short": grp(v["short"]), "cut": v["cut"], "conditions": v["conditions"], "d_long": round(v["d_long"], 2),
                 "m_long": round(v["m_long"], 4)} if v else None) for k, v in (("b", p["top_b"]), ("c", p["top_c"]))}
    bots = {k: ({"continuing": grp(v["cont"]), "curtailed": grp(v["cut"]), "left": v["left"], "right": v["right"], "conditions": v["conditions"],
                 "d_cont": round(v["d_cont"], 2), "m_cont": round(v["m_cont"], 4)} if v else None)
            for k, v in (("end", p["bottom_end"]), ("interior", p["bottom_interior"]))}
    zones = {k: {kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "positions"} | {"count": len(v["positions"])}
             for k, v in p["zones"].items()}
    return {"top": tops, "bottom": bots, "zones": zones}
