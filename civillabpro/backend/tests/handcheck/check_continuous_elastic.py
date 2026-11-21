#!/usr/bin/env python3
"""Independent hand check of the continuous beam's elastic method (STR-036).

From the clauses of IS 456:2000 and SP 16, by a different route wherever one exists:

  * effective spans by Cl. 22.2(b), typed again, with the greatest effective depth of one layer of bars;
  * the arrangements of Cl. 22.4.1 by Hardy Cross moment distribution with fixed-end moments for uniform and point
    loads (w l^2/12, P a b^2/l^2, P a^2 b/l^2; end spans released to 3EI/l), the diagrams by statics from the
    left reaction (engine: three-moment equation and superposition of free diagrams);
  * redistribution by Cl. 37.1.1 as the code register states it: every arrangement's support hogging held to
    (1 - r) of its greatest elastic value, the design envelope not below 0.7 of the elastic one;
  * flexure by the stress block (bisection, SP 16 Table A for compression steel), Cl. 37.1.1(d) with the neutral
    axis of the bars provided, tau_c by the SP 16 closed form, k_t of Fig. 4 by its closed form;
  * the extents of the top bars from the hogging envelope (Cl. 26.2.3.4), every cut-off moved back by the greater of
    d and 12 phi within the bars that remain, the anchorage of Cl. 26.2.3.3(c) at the end supports and the points
    of inflection, and every gap between stirrups within the spacing the shear asks for there.

Run:  python tests/handcheck/check_continuous_elastic.py
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from check_continuous_beam import resistance, steel, tau_c  # noqa: E402  (the stress block and SP 16 by hand)

from app.modules.structural.domain.continuous_beam import ContinuousBeamInput, design_continuous_beam  # noqa: E402

BASE = dict(
    mark="CB1", analysis="elastic", spans=4, clear_span_mm=5000, support_width_mm=300, support_table=[], section="rectangular", width_mm=300,
    depth_mm=500,
    flange_thickness_mm=120, flange_width_mm=3000, isolated_flange=False, l0_mm=None, fck=25, fy=500, fy_stirrup=500,
    exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20, dead_load_kn_m=25, live_load_kn_m=15, include_self_weight=True,
    unit_weight_kn_m3=25, load_factor=1.5, main_bar_dia_mm=None, hanger_bar_dia_mm=12, stirrup_dia_mm=8, stirrup_legs=2,
    redistribution_pct=15.0, support_moments_at="centre",
    cantilever_left_mm=0.0, cantilever_left_dead_kn_m=20.0, cantilever_left_live_kn_m=10.0, cantilever_left_tip_kn=0.0,
    cantilever_right_mm=0.0, cantilever_right_dead_kn_m=20.0, cantilever_right_live_kn_m=10.0, cantilever_right_tip_kn=0.0,
    span_table=[dict(clear_span_mm=c, dead_load_kn_m=25.0, live_load_kn_m=15.0) for c in (5000.0, 6500.0, 4500.0)],
    point_loads=[dict(span=2, distance_mm=3000.0, dead_kn=40.0, live_kn=30.0)],
)


def spans(*c: float, dl: float = 25.0, ll: float = 15.0) -> list[dict]:
    return [dict(clear_span_mm=x, dead_load_kn_m=dl, live_load_kn_m=ll) for x in c]


CASES: list[tuple[str, dict]] = [
    ("two spans", dict(span_table=spans(5500, 4000), point_loads=[])),
    ("five unequal spans, no redistribution", dict(span_table=spans(4000, 6000, 5000, 6000, 4000), point_loads=[], redistribution_pct=0.0)),
    ("30 percent redistribution", dict(redistribution_pct=30.0, depth_mm=550)),
    ("point load within d of a support", dict(point_loads=[dict(span=1, distance_mm=200.0, dead_kn=60.0, live_kn=40.0)])),
    ("several point loads, imposed only", dict(point_loads=[dict(span=1, distance_mm=2500.0, dead_kn=0.0, live_kn=50.0),
                                                            dict(span=3, distance_mm=1500.0, dead_kn=20.0, live_kn=30.0)])),
    ("short middle span: top bars lap within it", dict(span_table=spans(7000, 3000, 7000), point_loads=[], depth_mm=600)),
    ("T-beam floor", dict(section="t_beam", flange_thickness_mm=125, flange_width_mm=3000, dead_load_kn_m=35, live_load_kn_m=20,
                          span_table=spans(6000, 6500, 5500, dl=35, ll=20))),
    ("L-beam, l_0 entered", dict(section="l_beam", width_mm=250, depth_mm=450, flange_thickness_mm=120, flange_width_mm=1200, l0_mm=3500,
                                 span_table=spans(4500, 5000, 4500, dl=20, ll=10), point_loads=[])),
    ("wide supports (Cl. 22.2(b))", dict(support_width_mm=600, span_table=spans(6000, 7000, 6000), point_loads=[], depth_mm=600)),
    ("Fe 415 M30 severe", dict(fy=415, fy_stirrup=415, fck=30, exposure="severe")),
    ("deep, four legs, side face bars", dict(width_mm=400, depth_mm=900, span_table=spans(9000, 10000, 8000, dl=60, ll=30), stirrup_legs=4,
                                             stirrup_dia_mm=10, fck=30, support_width_mm=450,
                                             point_loads=[dict(span=2, distance_mm=5000.0, dead_kn=150.0, live_kn=100.0)])),
    ("fixed bar size T20", dict(main_bar_dia_mm=20, depth_mm=550)),
    ("monolithic supports: moments at the faces (Cl. 22.6.2)", dict(support_moments_at="faces", support_width_mm=450,
                                                                   span_table=spans(6000, 7000, 5000))),
    ("light load", dict(span_table=spans(4000, 4500, 4000, dl=6, ll=3), point_loads=[])),
    ("a cantilever at each end", dict(cantilever_left_mm=1500, cantilever_right_mm=2000, cantilever_right_tip_kn=12, depth_mm=550)),
    ("a long left cantilever, monolithic supports", dict(cantilever_left_mm=2500, cantilever_left_live_kn_m=20, support_moments_at="faces",
                                                        depth_mm=650, span_table=spans(6000, 5000))),
    ("T32 on 230 mm supports: anchorage picks four bars in the end spans", dict(support_width_mm=230, main_bar_dia_mm=32,
                                                                              span_table=spans(3000, 3500, 3000, dl=80, ll=48), point_loads=[])),
    # supports of their own widths (STR-041): a wall at the left end, columns inside, a wide column at the right
    ("supports of different widths", dict(support_table=[dict(width_mm=230), dict(width_mm=300), dict(width_mm=450), dict(width_mm=600)],
                                          span_table=spans(5000, 6500, 4500))),
    ("narrow supports on one span only (Cl. 22.2(a) there)", dict(support_table=[dict(width_mm=230), dict(width_mm=300), dict(width_mm=900)],
                                                                  span_table=spans(5000, 6000), point_loads=[])),
    ("a cantilever beyond a wide end support", dict(support_table=[dict(width_mm=600), dict(width_mm=300), dict(width_mm=300), dict(width_mm=230)],
                                                    cantilever_left_mm=1500, depth_mm=550, span_table=spans(5000, 6000, 4500))),
    ("faces of unequal supports", dict(support_moments_at="faces", support_table=[dict(width_mm=300), dict(width_mm=600), dict(width_mm=400),
                                                                                  dict(width_mm=300)], span_table=spans(6000, 7000, 5000))),
]

STOPS: list[tuple[str, dict, str]] = [
    ("continuous deep beam", dict(span_table=spans(1000, 1200), point_loads=[], depth_mm=600), "An effective span is less than 2.5 times"),
    ("section too small", dict(depth_mm=300, width_mm=200, span_table=spans(7000, 7000, dl=80, ll=60), point_loads=[]), "No arrangement"),
]

BOND = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}
COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}


# ----------------------------------------------------------------------------- analysis by hand


def fem(l: float, w: float, pts: list[tuple[float, float]]) -> tuple[float, float]:  # noqa: E741
    """Fixed-end moments, clockwise positive on the member: (left, right)."""
    ml, mr = -w * l * l / 12, w * l * l / 12
    for a, p in pts:
        b = l - a
        ml -= p * a * b * b / (l * l)
        mr += p * a * a * b / (l * l)
    return ml, mr


def distribute(L: list[float], loads: list[tuple[float, list[tuple[float, float]]]], ends: tuple[float, float] = (0.0, 0.0)) -> list[float]:
    """Bending moments at the supports (sagging positive) by Hardy Cross; the end supports pinned, held at ``ends`` (a cantilever's
    moment beyond them, known by statics)."""
    n = len(L)
    k = [3 / s if i in (0, n - 1) else 4 / s for i, s in enumerate(L)]
    mem = []
    for i, (s, (w, pts)) in enumerate(zip(L, loads, strict=True)):
        ml, mr = fem(s, w, pts)
        if i == 0 and n > 1:
            ml, mr = ends[0], mr + (ends[0] - ml) / 2  # release the end to its known moment, carry half the change over
        if i == n - 1:  # at a right end the member-end moment is minus the bending moment
            ml, mr = ml + (-ends[1] - mr) / 2, -ends[1]
        mem.append([ml, mr])
    for _ in range(5000):
        worst = 0.0
        for j in range(1, n):
            unb = mem[j - 1][1] + mem[j][0]
            worst = max(worst, abs(unb))
            kl, kr = k[j - 1], k[j]
            dl, dr = -unb * kl / (kl + kr), -unb * kr / (kl + kr)
            mem[j - 1][1] += dl
            mem[j][0] += dr
            if j - 1 not in (0, n - 1):
                mem[j - 1][0] += dl / 2
            if j not in (0, n - 1):
                mem[j][1] += dr / 2
        if worst < 1e-11:
            break
    return [ends[0]] + [mem[j][0] for j in range(1, n)] + [ends[1]]


def by_statics(ml: float, mr: float, l: float, w: float, pts: list[tuple[float, float]], x: float) -> tuple[float, float]:  # noqa: E741
    """(moment, shear just right of x) from the left reaction."""
    rl = (mr - ml + w * l * l / 2 + sum(p * (l - a) for a, p in pts)) / l
    m = ml + rl * x - w * x * x / 2 - sum(p * (x - a) for a, p in pts if a < x)
    v = rl - w * x - sum(p for a, p in pts if a <= x)
    return m, v


class Hand:
    """The beam by hand: envelopes along every span, x in mm from the left face."""

    def __init__(self, s: dict, fr: list[float]) -> None:
        self.s = s
        rows, D = s["span_table"], s["depth_mm"]
        n = self.n = len(rows)
        ws = self.ws = [r["width_mm"] for r in s["support_table"]] or [s["support_width_mm"]] * (n + 1)
        cover = self.cover = s["clear_cover_mm"] or COVER[s["exposure"]]
        dst = s["stirrup_dia_mm"]
        self.d_max = D - cover - dst - (s["main_bar_dia_mm"] or 12) / 2
        self.lc = [r["clear_span_mm"] for r in rows]
        self.l = []
        for i, lc in enumerate(self.lc):  # Cl. 22.2, each span on its own two supports
            if ws[i] <= min(lc / 12, 600) and ws[i + 1] <= min(lc / 12, 600):
                self.l.append(min(lc + self.d_max, lc + ws[i] / 2 + ws[i + 1] / 2))
            elif i in (0, n - 1):
                self.l.append(lc + min(self.d_max / 2, (ws[0] if i == 0 else ws[n]) / 2))
            else:
                self.l.append(lc)
        self.off = [(le - c) / 2 for le, c in zip(self.l, self.lc, strict=True)]
        flanged = s["section"] != "rectangular"
        rib = D - s["flange_thickness_mm"] if flanged else D
        w_self = s["unit_weight_kn_m3"] * s["width_mm"] * rib / 1e6 if s["include_self_weight"] else 0.0
        g = s["load_factor"]
        self.dead, self.live = [], []
        for i, r in enumerate(rows):
            pl = [p for p in s["point_loads"] if p["span"] == i + 1]
            self.dead.append((g * (r["dead_load_kn_m"] + w_self), [((self.off[i] + p["distance_mm"]) / 1000, g * p["dead_kn"]) for p in pl if p["dead_kn"]]))
            self.live.append((g * r["live_load_kn_m"], [((self.off[i] + p["distance_mm"]) / 1000, g * p["live_kn"]) for p in pl if p["live_kn"]]))
        pats = [[True] * n, [i % 2 == 0 for i in range(n)], [i % 2 == 1 for i in range(n)]] + [[j in (i, i + 1) for j in range(n)] for i in range(n - 1)]
        Lm = [x / 1000 for x in self.l]
        # cantilevers (Cl. 22.2(c): length to the centre of the support at the end of a continuous beam), each loaded and not
        self.cant = {}
        for j, key in ((0, "left"), (n, "right")):
            if s.get(f"cantilever_{key}_mm", 0) > 0:
                lc_c = s[f"cantilever_{key}_mm"]
                self.cant[j] = dict(lc=lc_c, L=lc_c + ws[j] / 2, wd=g * (s[f"cantilever_{key}_dead_kn_m"] + w_self), wl=g * s[f"cantilever_{key}_live_kn_m"],
                                    P=g * s[f"cantilever_{key}_tip_kn"])

        def cant_m(j: int, loaded: bool, x_mm: float | None = None) -> float:
            c = self.cant[j]
            x = (c["L"] if x_mm is None else x_mm) / 1000
            return (c["wd"] + (c["wl"] if loaded else 0.0)) * x * x / 2 + c["P"] * x

        self.cant_m = cant_m
        states = [(a, b) for a in ((True, False) if 0 in self.cant else (False,)) for b in ((True, False) if n in self.cant else (False,))]
        self.cases = []
        for p in pats:
            loads = [(self.dead[i][0] + (self.live[i][0] if p[i] else 0.0), self.dead[i][1] + (self.live[i][1] if p[i] else [])) for i in range(n)]
            for a, b in states:
                ends = (-cant_m(0, a) if 0 in self.cant else 0.0, -cant_m(n, b) if n in self.cant else 0.0)
                self.cases.append((loads, distribute(Lm, loads, ends)))
        self.me = [max(max(-m[j], 0.0) for _, m in self.cases) for j in range(n + 1)]
        cap = [(1 - fr[j]) * x for j, x in enumerate(self.me)]
        self.red = [(loads, [-min(-m[j], cap[j]) if m[j] < 0 else m[j] for j in range(n + 1)]) for loads, m in self.cases]
        self.m_sup = [max(cap[j], 0.7 * self.me[j]) for j in range(n + 1)]
        self.Lm = Lm

    def _vals(self, i: int, xf: float, cases: list) -> tuple[list[float], list[float]]:
        x = (xf + self.off[i]) / 1000
        out = [by_statics(m[i], m[i + 1], self.Lm[i], loads[i][0], loads[i][1], x) for loads, m in cases]
        return [o[0] for o in out], [o[1] for o in out]

    def sag(self, i: int, xf: float) -> float:
        e, r = self._vals(i, xf, self.cases)[0], self._vals(i, xf, self.red)[0]
        return max(max(max(r), 0.0), 0.7 * max(max(e), 0.0))

    def sag_e(self, i: int, xf: float) -> float:
        return max(max(self._vals(i, xf, self.cases)[0]), 0.0)

    def hog_e(self, i: int, xf: float) -> float:
        return max(-min(self._vals(i, xf, self.cases)[0]), 0.0)

    def hog(self, i: int, xf: float) -> float:
        e, r = self._vals(i, xf, self.cases)[0], self._vals(i, xf, self.red)[0]
        return max(max(-min(r), 0.0), 0.7 * max(-min(e), 0.0))

    def shear(self, i: int, xf: float) -> float:
        return max(abs(v) for v in self._vals(i, xf, self.red)[1])

    def xs(self, i: int, steps: int = 400) -> list[float]:
        """Stations in face coordinates: evenly over the analysis span and either side of every point load."""
        L = self.l[i]
        pts = {L * k / steps for k in range(steps + 1)}
        for a, _ in self.dead[i][1] + self.live[i][1]:
            pts.update({a * 1000 - 1e-6 * L, a * 1000 + 1e-6 * L})
        return sorted(x - self.off[i] for x in pts)


# ----------------------------------------------------------------------------- sections by hand


def bars(g: dict) -> tuple[int, int, float]:
    return g["count"], g["dia"], g["count"] * math.pi * g["dia"] ** 2 / 4


def certain(g: dict) -> tuple[int, float]:
    """The bars that reach the supports whatever the curtailment: the first layer, or more than half of a single layer and two at least."""
    if len(g["layers"]) == 2:
        c = g["layers"][0]
    else:
        c = max(2, math.ceil(g["layers"][0] / 2)) if g["layers"][0] > 2 else g["layers"][0]
    return c, c * math.pi * g["dia"] ** 2 / 4


def flange_width(s: dict, l_eff: float) -> float | None:
    if s["section"] == "rectangular":
        return None
    b, df, bact = s["width_mm"], s["flange_thickness_mm"], s["flange_width_mm"]
    l0 = s["l0_mm"] or 0.7 * l_eff
    if s["isolated_flange"]:
        bf = (1 if s["section"] == "t_beam" else 0.5) * l0 / (l0 / bact + 4) + b
    else:
        bf = l0 / 6 + b + 6 * df if s["section"] == "t_beam" else l0 / 12 + b + 3 * df
    return min(bf, bact)


def xu_of(fck: float, fy: float, b: float, d: float, ast: float) -> float:
    """Neutral axis of a rectangle with its tension steel at f_d, compression steel left out (on the safe side for Cl. 37.1.1(d))."""
    return 0.87 * fy * ast / (0.36 * fck * b)


def names(description: str, kind: str) -> list[int]:
    """The spans (or supports) a merged schedule row names: "..., span 2" or "..., spans 1, 3 and 4"."""
    tail = description.rsplit(f", {kind}", 1)[-1].lstrip("s ")
    return [int(t) for t in tail.replace(" and ", ",").split(",") if t.strip().isdigit()]


def ld(dia: float, fck: float, fy: float) -> float:
    tbd = BOND[max(g for g in BOND if g <= min(fck, 40))] * (1.6 if fy > 250 else 1.0)
    return dia * 0.87 * fy / (4 * tbd)


# ----------------------------------------------------------------------------- comparison


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    eng, reinf = res["data"], res["reinforcement"]
    fr = eng["redistribution_applied"]  # the engine steps down at a support whose section cannot meet Cl. 37.1.1(d)
    h = Hand(s, fr)
    cur = reinf["curtailment"]
    n, b, D, fck, fy = h.n, s["width_mm"], s["depth_mm"], s["fck"], s["fy"]
    cover, dst = h.cover, s["stirrup_dia_mm"]
    bad: list[str] = []
    k = 0

    def near(label: str, e: float, hv: float, tol: float = 2e-3, abs_tol: float = 1e-3) -> None:
        nonlocal k
        k += 1
        if abs(e - hv) > tol * max(abs(hv), 1.0) + abs_tol:
            bad.append(f"{name}: {label} engine {e:.4f} hand {hv:.4f}")

    for i in range(n):
        near(f"l_eff {i + 1}", eng["l_eff"][i], h.l[i], 1e-9)
    for j in range(n + 1):
        near(f"elastic hogging at support {j + 1}", eng["m_sup_elastic_node"][j], h.me[j])
        near(f"design hogging at support {j + 1}", eng["m_sup_node"][j], h.m_sup[j])
    # the sections the supports are designed for: the centre lines, or the faces where the construction is monolithic (Cl. 22.6.2)
    faces = s.get("support_moments_at") == "faces"
    msec, mesec = list(h.m_sup), list(h.me)
    tops = [j for j in range(n + 1) if 0 < j < n or j in h.cant]
    k += 1
    if [j for j in range(n + 1) if reinf["support"][j] is not None] != tops:
        bad.append(f"{name}: top bars over supports {[j + 1 for j in range(n + 1) if reinf['support'][j]]}, expected over {[j + 1 for j in tops]}")
    for j in tops:
        if faces:
            sides_d = ([h.hog(j - 1, h.lc[j - 1])] if j > 0 else []) + ([h.hog(j, 0.0)] if j < n else [])
            sides_e = ([h.hog_e(j - 1, h.lc[j - 1])] if j > 0 else []) + ([h.hog_e(j, 0.0)] if j < n else [])
            if j in h.cant:  # the cantilever's own face
                sides_d.append(h.cant_m(j, True, h.cant[j]["lc"]))
                sides_e.append(h.cant_m(j, True, h.cant[j]["lc"]))
            msec[j], mesec[j] = max(sides_d), max(sides_e)
        near(f"design moment of support {j + 1}", eng["m_sup"][j], msec[j])
        near(f"elastic moment at that section, support {j + 1}", eng["m_sup_elastic"][j], mesec[j])
    # greatest sagging in each span: stations by hand, the engine at its own; a station apart at most
    for i in range(n):
        xs = h.xs(i)
        near(f"design sagging, span {i + 1}", eng["m_span"][i], max(h.sag(i, x) for x in xs), 3e-3)
        near(f"elastic sagging, span {i + 1}", eng["m_span_elastic"][i], max(h.sag_e(i, x) for x in xs), 3e-3)
    k += 1
    if fr[0] or fr[-1] or any(f > s["redistribution_pct"] / 100 + 1e-9 or f < 0 for f in fr):
        bad.append(f"{name}: redistribution applied {fr} outside 0 to {s['redistribution_pct']} percent, or at an end support")
    near("shear at the first end support", eng["v_end"][0], h.shear(0, 0.0), 2e-3)
    near("shear at the last end support", eng["v_end"][1], h.shear(n - 1, h.lc[-1]), 2e-3)

    # flexure: the bars provided carry the design moments; Cl. 37.1.1(d) where the resistance is below the elastic moment
    for i in range(n):
        sp = reinf["span"][i]
        _, _, ast = bars(sp["bottom"])
        _, tdia, asc = bars(sp["top"])
        d, dc = sp["d"], cover + dst + tdia / 2
        bf = flange_width(s, h.l[i])
        m = eng["m_span"][i]
        a_req, c_req = steel(m, b, d, fck, fy, dc, bf, s["flange_thickness_mm"])
        k += 2
        if ast < max(a_req, 0.85 * b * d / fy) * (1 - 6e-3) or asc < c_req * (1 - 1e-2):
            bad.append(f"{name}: span {i + 1} steel {ast:.0f}/{asc:.0f} below the hand requirement {a_req:.0f}/{c_req:.0f}")
        if resistance(fck, fy, b, d, ast, asc, dc, bf, s["flange_thickness_mm"]) * 1.003 < m:
            bad.append(f"{name}: span {i + 1} resists less than {m:.1f} kN m")
    for j in tops:
        sup = reinf["support"][j]
        _, _, ast = bars(sup["top"])
        lo = min((q for q in (j - 1, j) if 0 <= q < n), key=lambda q: reinf["span"][q]["bottom"]["area"])
        _, cdia, asc = bars(reinf["span"][lo]["bottom"])
        d, dc = sup["d"], D - reinf["span"][lo]["d"]
        m = msec[j]
        a_req, c_req = steel(m, b, d, fck, fy, dc)
        mr = resistance(fck, fy, b, d, ast, asc, dc)
        k += 3
        if ast < max(a_req, 0.85 * b * d / fy) * (1 - 6e-3) or asc < c_req * (1 - 1e-2):
            bad.append(f"{name}: support {j + 1} steel {ast:.0f}/{asc:.0f} below the hand requirement {a_req:.0f}/{c_req:.0f}")
        if mr * 1.003 < m:
            bad.append(f"{name}: support {j + 1} resists {mr:.1f}, less than {m:.1f} kN m")
        if fr[j] > 0 and mr < mesec[j] and m < mesec[j]:
            red = 1 - m / mesec[j]
            xu = eng["support"][j]["xu"]
            if xu / d + red > 0.6 + 1e-6:
                bad.append(f"{name}: support {j + 1}: x_u/d + dM/100 = {xu / d + red:.3f} > 0.6 (Cl. 37.1.1(d))")
            if xu > xu_of(fck, fy, b, d, ast) + 1e-6:
                bad.append(f"{name}: support {j + 1}: engine x_u {xu:.1f} above the value without compression steel")

    # shear: every stirrup gap within the spacing the shear asks for there (critical sections at d; least tau_c along the span)
    fyv = min(s["fy_stirrup"], 415)
    asv = s["stirrup_legs"] * math.pi * dst**2 / 4
    for i in range(n):
        sp, lc = reinf["span"][i], h.lc[i]
        adj = [reinf["support"][j] for j in (i, i + 1) if reinf["support"][j]]
        d_min = min([sp["d"]] + [a["d"] for a in adj])
        a_min = min([certain(sp["bottom"])[1]] + [certain(a["top"])[1] for a in adj])
        tc = tau_c(fck, 100 * a_min / (b * d_min))
        pts = [p["distance_mm"] for p in s["point_loads"] if p["span"] == i + 1]
        x_lo = 0.0 if any(a < d_min for a in pts) else d_min
        x_hi = lc if any(lc - a < d_min for a in pts) else lc - d_min
        s_cap = min(0.87 * fyv * asv / (0.4 * b), 0.75 * d_min, 300.0)

        def s_need(x: float, i: int = i, tc: float = tc, d_min: float = d_min, x_lo: float = x_lo, x_hi: float = x_hi, s_cap: float = s_cap) -> float:
            v = h.shear(i, min(max(x, x_lo), x_hi))
            vus = v - tc * b * d_min / 1e3
            return min(s_cap, 0.87 * fyv * asv * d_min / (vus * 1e3)) if vus > 0 else s_cap

        pos = cur["zones"][i]["positions"]
        worst = 0.0
        for p0, p1 in zip(pos, pos[1:], strict=False):
            need = min(s_need(p0 + (p1 - p0) * t / 4) for t in range(5))
            worst = max(worst, (p1 - p0) / need)
        k += 1
        if worst > 1.01:  # stations a hair apart either side of a point load
            bad.append(f"{name}: span {i + 1}: a stirrup gap is {worst:.3f} times the spacing the shear asks for")
        if pos[0] != 50 or pos[-1] > lc - 50 + 1e-6:
            bad.append(f"{name}: span {i + 1}: stirrups not set out 50 mm from the faces")

    # the cantilevers: top bars developed between the face and the tip (bent down there), shear, and span/depth (Cl. 23.2.1, basic 7)
    for j, c in h.cant.items():
        key = "left" if j == 0 else "right"
        sup, ec = reinf["support"][j], eng["cantilever"][key]
        _, tdia, ast = bars(sup["top"])
        r_b = (2 if fy <= 250 else 4) * tdia
        avail = c["lc"] - cover - (r_b + tdia) + 8 * tdia
        near(f"{key} cantilever: length to develop its top bars", ec["available"], avail, 1e-9, 0.01)
        k += 1
        if ld(tdia, fck, fy) > avail + 1e-6:
            bad.append(f"{name}: the {key} cantilever's top bars (T{tdia}) cannot develop between the face and the tip")
        d = sup["d"]
        v = (c["wd"] + c["wl"]) * max(c["lc"] - d, 0) / 1000 + c["P"]
        tc = tau_c(fck, 100 * ast / (b * d))
        vus = v - tc * b * d / 1e3
        s_need = min(0.87 * min(s["fy_stirrup"], 415) * s["stirrup_legs"] * math.pi * dst**2 / 4 / (0.4 * b), 0.75 * d, 300.0)
        if vus > 0:
            s_need = min(s_need, 0.87 * min(s["fy_stirrup"], 415) * s["stirrup_legs"] * math.pi * dst**2 / 4 * d / (vus * 1e3))
        k += 1
        if ec["shear"]["spacing"] > s_need + 1e-6:
            bad.append(f"{name}: the {key} cantilever's stirrups at {ec['shear']['spacing']:.0f}, the shear asks for {s_need:.0f}")
        sd = eng["support"][j]
        fs = 0.58 * fy * max(sd["ast_req"], 1e-9) / ast
        pt = 100 * ast / (b * d)
        den = 0.225 + 0.00322 * fs + 0.625 * math.log10(pt)
        kt = 2.0 if den <= 0.5 else min(2.0, 1 / den)
        kc = min(1.5, 1 + (pc := 100 * sd["asc_prov"] / (b * d)) / (3 + pc)) if sd["doubly"] else 1.0
        near(f"{key} cantilever: allowable span/depth", ec["defl"]["allow"], 7 * kt * kc, 0.03)
        if c["L"] / d > 7 * kt * kc * 1.03 and res["status"] == "ok":
            bad.append(f"{name}: the {key} cantilever fails the span/depth rule by hand but the engine reports OK")

    # extents of the top bars (Cl. 26.2.3.4) and the cut-offs over the supports
    for j in tops:
        sup, lay = reinf["support"][j], reinf["layout"]
        _, tdia, _ = bars(sup["top"])
        for side, i, at_left in [t for t in (("left", j - 1, False), ("right", j, True)) if 0 <= t[1] < n]:
            lc = h.lc[i]
            prof = [(x, h.hog(i, x if at_left else lc - x)) for x in [lc * q / 800 for q in range(801)]]
            x0 = next((x for x, m in prof if m <= 1e-9), lc)
            a = min(max(x0 + max(sup["d"], 12 * tdia, lc / 16), ld(tdia, fck, fy)), lc)
            k += 1
            if abs(eng["ext"][j][side] - a) > lc / 400 + 1:
                bad.append(f"{name}: top bars over support {j + 1} into span {i + 1}: engine {eng['ext'][j][side]:.0f}, hand {a:.0f}")
            # the long bars reach at least that far
            a_lay = lay[i]["a_left" if at_left else "a_right"]
            if a_lay < eng["ext"][j][side] - 0.1:  # the record is rounded to 0.1 mm
                bad.append(f"{name}: top bars over support {j + 1} stop short of their extent in span {i + 1}")
        t = cur["top"][j]
        if not t:
            continue
        cnt, ldia, along = bars(t["long"])
        _, sdia, _ = bars(t["short"])
        d_l = D - (cover + dst + ldia / 2)
        reach = [cur["bottom"][q]["continuing"] if cur["bottom"][q] else reinf["span"][q]["bottom"] for q in (j - 1, j)]
        comp = min(reach, key=lambda g: g["area"])
        _, cdia, casc = bars(comp)
        m_r = resistance(fck, fy, b, d_l, along, casc, cover + dst + cdia / 2)
        back = max(sup["d"], 12 * sdia)
        for side, i, at_left in (("left", j - 1, False), ("right", j, True)):
            lc = h.lc[i]
            x_cut = t["cut"][side]
            xf = x_cut - back
            m = h.hog(i, xf if at_left else lc - xf)
            k += 2
            if m > m_r * 1.01 + 0.5:
                bad.append(f"{name}: support {j + 1} into span {i + 1}: {m:.1f} kN m where the short bars stop (less d or 12 phi), long bars {m_r:.1f}")
            if x_cut < ld(sdia, fck, fy) - 1:
                bad.append(f"{name}: short top bars over support {j + 1} stop within L_d of the face")

    # bottom bars: cut-offs, and the anchorage of Cl. 26.2.3.3(c)
    for i in range(n):
        sp, lc, t = reinf["span"][i], h.lc[i], cur["bottom"][i]
        bf = flange_width(s, h.l[i])
        df = s["flange_thickness_mm"]
        grp = t["continuing"] if t else sp["bottom"]
        _, gdia, garea = bars(grp)
        d = D - (cover + dst + gdia / 2) if t else sp["d"]
        if t:
            _, cutdia, _ = bars(t["curtailed"])
            _, tdia, tasc = bars(sp["top"])
            m_c = resistance(fck, fy, b, d, garea, tasc, cover + dst + tdia / 2, bf, df)
            back = max(sp["d"], 12 * cutdia)
            prof = [(x, h.sag(i, x)) for x in [lc * q / 800 for q in range(801)]]
            peak = max(m for _, m in prof)
            plateau = [x for x, m in prof if m >= 0.995 * peak]
            for xs, toward in ((t["left"], 1), (lc - t["right"], -1)):
                m = h.sag(i, xs + toward * back)
                k += 2
                if m > m_c * 1.01 + 0.5:
                    bad.append(f"{name}: span {i + 1}: {m:.1f} kN m beyond a bottom cut-off by d or 12 phi, continuing bars {m_c:.1f}")
                gap = min(abs(xs - p) for p in plateau)
                if gap < ld(cutdia, fck, fy) - lc / 400 - 1:
                    bad.append(f"{name}: span {i + 1}: curtailed bottom bars stop within L_d of the greatest moment")
        # M_1 of the bars that reach: steel at f_d, no x_u,max limit, a flange where there is one
        tt = 0.87 * fy * garea
        if bf:
            lo_, hi_ = 0.0, d
            for _ in range(200):
                x = (lo_ + hi_) / 2
                if x <= df:
                    c = 0.36 * fck * bf * x
                else:
                    yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
                    c = 0.36 * fck * b * x + 0.45 * fck * (bf - b) * yf
                lo_, hi_ = (x, hi_) if c < tt else (lo_, x)
            x = hi_
            if x <= df:
                m1 = 0.36 * fck * bf * x * (d - 0.42 * x)
            else:
                yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
                m1 = 0.36 * fck * b * x * (d - 0.42 * x) + 0.45 * fck * (bf - b) * yf * (d - yf / 2)
        else:
            m1 = tt * (d - 0.42 * min(tt / (0.36 * fck * b), d))
        L = ld(gdia, fck, fy)
        main = next(it for it in res["bbs"]["items"] if it["description"].startswith("Bottom bars,") and "curtailed" not in it["description"]
                    and i + 1 in names(it["description"], "span"))
        for left in ([True] if i == 0 and 0 not in h.cant else []) + ([False] if i == n - 1 and n not in h.cant else []):
            v = h.shear(i, 0.0 if left else lc)
            r_b = (2 if fy <= 250 else 4) * gdia
            beyond = (h.ws[0] if left else h.ws[n]) / 2 - cover  # past the centre of that end support
            l0 = beyond - (r_b + gdia) + 16 * gdia if "hook" in main["shape"] else beyond - (r_b + gdia) + 8 * gdia if "bend" in main["shape"] else beyond
            k += 1
            if L > 1.3 * m1 / (v * 1e3) + l0 + 1e-6:
                bad.append(f"{name}: span {i + 1}: L_d {L:.0f} exceeds 1.3 M_1/V + L_0 = {1.3 * m1 / (v * 1e3) + l0:.0f} at the end support")
        for left in ([True] if i in tops else []) + ([False] if i + 1 in tops else []):
            prof = [(x, h.sag(i, x if left else lc - x)) for x in [lc * q / 800 for q in range(801)]]
            x = next((x for x, m in prof if m > 1e-9), None)
            if x is None:
                continue
            v = h.shear(i, x if left else lc - x)
            k += 1
            if L > (m1 / (v * 1e3) + max(d, 12 * gdia)) * 1.002:
                bad.append(f"{name}: span {i + 1}: L_d {L:.0f} exceeds M_1/V + max(d, 12 phi) at the point of inflection")

    # the resistance diagram of the bars as detailed covers the design envelope, and so 0.7 of the elastic one (Cl. 37.1.1(b)). A bar counts
    # in full up to the greater of d and 12 phi short of its end (Cl. 26.2.3.1); where the top bars of a span's two supports lap with
    # each other, each set counts in proportion to its embedment beyond the section, up to L_d (Cl. 26.2.1).
    for i in range(n):
        sp, lc, lay_i = reinf["span"][i], h.lc[i], reinf["layout"][i]
        bf, df = flange_width(s, h.l[i]), s["flange_thickness_mm"]
        reach = cur["bottom"][i]["continuing"] if cur["bottom"][i] else sp["bottom"]
        _, rdia, rarea = bars(reach)
        r_y = cover + dst + rdia / 2
        tops = []  # (area, d, counted from, counted to, its end, L_d) in face coordinates of span i
        for j, at_left in ((i, True), (i + 1, False)):
            sup = reinf["support"][j]
            if not sup:
                continue
            t = cur["top"][j]
            lg = t["long"] if t else sup["top"]
            _, ldia, larea = bars(lg)
            a_end = lay_i["a_left" if at_left else "a_right"]
            back = max(sup["d"], 12 * ldia)
            d_l = D - (cover + dst + ldia / 2) if t else sup["d"]
            tops.append((larea, d_l, -math.inf if at_left else lc - a_end + back, a_end - back if at_left else math.inf,
                         a_end if at_left else lc - a_end, ld(ldia, fck, fy), at_left))
            if t:
                _, sdia, sarea = bars(t["short"])
                c = t["cut"]["right" if at_left else "left"]
                back_s = max(sup["d"], 12 * sdia)
                tops.append((sarea, sup["d"], -math.inf if at_left else lc - c + back_s, c - back_s if at_left else math.inf,
                             c if at_left else lc - c, ld(sdia, fck, fy), at_left))
        meet = lay_i["kind"] == "meet"
        x_lap = (lc - lay_i["a_right"], lay_i["a_left"]) if meet else (math.inf, -math.inf)
        worst_h = worst_s = 0.0
        for q in range(201):
            x = lc * q / 200
            m = h.hog(i, x)
            if m > 1e-6:
                if x_lap[0] <= x <= x_lap[1]:
                    parts = [(a * min(1.0, max((end - x) if left else (x - end), 0.0) / L_), d_) for a, d_, _, _, end, L_, left in tops]
                else:
                    parts = [(a, d_) for a, d_, f0, f1, _, _, _ in tops if f0 <= x <= f1]
                area_ = sum(a for a, _ in parts)
                rr = resistance(fck, fy, b, sum(a * d_ for a, d_ in parts) / area_, area_, rarea, r_y) if area_ > 0 else 0.0
                worst_h = max(worst_h, m / max(rr, 1e-9))
            m = h.sag(i, x)
            if m > 1e-6:
                t = cur["bottom"][i]
                area_, d_ = rarea, (D - r_y if t else sp["d"])
                if t:
                    _, cdia, carea = bars(t["curtailed"])
                    back = max(sp["d"], 12 * cdia)
                    if t["left"] + back <= x <= lc - t["right"] - back:
                        area_, d_ = rarea + carea, sp["d"]
                _, tdia, tasc = bars(sp["top"])
                rr = resistance(fck, fy, b, d_, area_, tasc, cover + dst + tdia / 2, bf, df)
                worst_s = max(worst_s, m / max(rr, 1e-9))
        k += 2
        for what, w_ in (("hogging", worst_h), ("sagging", worst_s)):
            if w_ > 1.01:
                bad.append(f"{name}: span {i + 1}: the {what} design envelope exceeds the resistance of the bars there ({w_:.3f})")

    # deflection: continuous, k_t (Fig. 4 closed form), k_c, k_f
    for i in range(n):
        sp, e = reinf["span"][i], eng["span"][i]
        bf = e["bf"]
        bd = bf or b
        _, _, ast = bars(sp["bottom"])
        fs = 0.58 * fy * max(e["ast_req"], 1e-9) / ast
        pt = 100 * ast / (bd * sp["d"])
        den = 0.225 + 0.00322 * fs + 0.625 * math.log10(pt)
        kt = 2.0 if den <= 0.5 else min(2.0, 1 / den)  # Fig. 4 tops out at 2.0
        kc = min(1.5, 1 + (pc := 100 * bars(sp["top"])[2] / (bd * sp["d"])) / (3 + pc)) if e["doubly"] else 1.0
        kf = 1.0
        if bf:
            q = b / bf
            kf = 0.8 if q <= 0.3 else 0.8 + 0.2 * (q - 0.3) / 0.7
        allow = 26 * (10000 / h.l[i] if h.l[i] > 10000 else 1) * kt * kc * kf
        near(f"span {i + 1} deflection allowance", eng["defl"][i]["allow"], allow, 0.03)
        if h.l[i] / sp["d"] > allow * 1.03 and res["status"] == "ok":
            bad.append(f"{name}: span {i + 1} fails the span/depth rule by hand but the engine reports OK")
    return k, bad


def main() -> int:
    bad: list[str] = []
    defaults = ContinuousBeamInput().model_dump()
    expect = dict(BASE, analysis="coefficients")
    if defaults != expect:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), expect.get(k)) for k in set(defaults) | set(expect) if defaults.get(k) != expect.get(k)} }")
    base = design_continuous_beam(ContinuousBeamInput(**BASE))
    n_base = 0
    if base["status"] == "stopped":
        bad.append(f"base: stopped: {base['stop_message']}")
    else:
        n_base, b0 = compare("base", BASE, base)
        bad += b0
        if base["status"] != "ok":
            bad.append("base: engine reports Not OK")
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_continuous_beam(ContinuousBeamInput(**s))
        if res["status"] == "stopped":
            bad.append(f"{name}: stopped unexpectedly: {res['stop_message']}")
            continue
        n, b1 = compare(name, s, res)
        n_cases += n
        bad += b1
        if res["status"] != "ok":
            failed = [i["title"] for sec in res["sheet"]["sections"] for i in sec["items"] if i["kind"] == "check" and not i["ok"]]
            bad.append(f"{name}: engine reports Not OK: {failed}")
    for name, ov, want in STOPS:
        res = design_continuous_beam(ContinuousBeamInput(**dict(BASE, **ov)))
        if res["status"] != "stopped" or not (res["stop_message"] or "").startswith(want):
            bad.append(f"stop '{name}': got {res['status']} / {res['stop_message']}")
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n_base} results agree with the independent hand check; "
          f"{n_cases} values of {len(CASES)} alternative-input cases and {len(STOPS)} stop states correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
