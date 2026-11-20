#!/usr/bin/env python3
"""Independent hand check of the combined footing engine.

From the clauses of IS 456:2000, by a different route where one exists:

  * plan: the resultant by moments about the left end, L = 2 (a + x_r) rounded up; the left end that balances the
    greatest sagging and hogging, by its own scan (engine: ranking with its own statics);
  * statics: each column a point load at its centre, the pressure a trapezoid (its resultant and centroid), the
    greatest hogging where the shear is nil from the quadratic (engine: the load spread over each column, a scan and
    bisection); outside the columns the two must agree;
  * steel areas: the stress block of Cl. 38.1 by bisection (engine: Annex G-1.1(b) closed form);
  * tau_c: the SP 16 closed form (engine: Table 19);
  * punching: each perimeter by cases, two overlapping ones by inclusion and exclusion (engine: strips of the union);
  * bands, one-way shear, development at the stress of each section, bearing: recomputed line by line.

Run:  python tests/handcheck/check_combined_footing.py
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.combined_footing import CombinedFootingInput, design_combined_footing  # noqa: E402

BASE = dict(
    mark="CF1", column1_width_mm=400, column1_depth_mm=400, p1_service_kn=900, column2_width_mm=450, column2_depth_mm=450, p2_service_kn=1200,
    spacing_mm=3600, load_factor=1.5, self_weight_pct=10, sbc_kn_m2=200, left_end_mm=None, length_mm=None, width_mm=None, depth_mm=None,
    fck=25, fy=415, exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20, bar_dia_mm=None,
)

# By hand: x_r = 1200 x 3600 / 2100 = 2057.1 mm from column 1. Balancing the greatest sagging and hogging gives a = 975 mm,
# L = 2 (975 + 2057.1) = 6064.3, rounded up to 6100 mm. A = 2310 / 200 = 11.55 m2, so B = 11.55 / 6.1 = 1.893 m, 1900 mm;
# the 17.9 mm eccentricity from rounding takes q_max to 201.5 kN/m2, so B = 1950 mm.
BASE_EXPECTED = dict(a=975.0, L=6100.0, B=1950.0, cover=50.0, x_r=1200 * 3600 / 2100)

CASES: list[tuple[str, dict]] = [
    ("property line at column 1", dict(left_end_mm=200)),
    ("property line, column 1 heavier but within reach", dict(left_end_mm=500, p1_service_kn=1100, p2_service_kn=1000)),
    ("given length, centred", dict(length_mm=6600)),
    ("given length and left end, eccentric", dict(length_mm=6400, left_end_mm=700)),
    ("given plan and depth", dict(length_mm=6200, width_mm=2200, left_end_mm=1000, depth_mm=1000)),
    ("Fe500 M30", dict(fy=500, fck=30)),
    ("weak soil", dict(sbc_kn_m2=90)),
    ("strong soil", dict(sbc_kn_m2=400)),
    ("columns close, punching zones merge", dict(spacing_mm=1050, p1_service_kn=1500, p2_service_kn=1500, sbc_kn_m2=250)),
    ("oblong columns", dict(column1_width_mm=300, column1_depth_mm=600, column2_width_mm=600, column2_depth_mm=300)),
    ("wide spacing", dict(spacing_mm=6000)),
    ("heavy loads", dict(p1_service_kn=2500, p2_service_kn=3200, column1_width_mm=600, column1_depth_mm=600, column2_width_mm=650,
                         column2_depth_mm=650, sbc_kn_m2=300)),
    ("fixed T16", dict(bar_dia_mm=16)),
    ("mild steel M20", dict(fy=250, fck=20, exposure="mild")),
    ("severe exposure", dict(exposure="severe", fck=30)),
    ("equal loads", dict(p1_service_kn=1000, p2_service_kn=1000, column2_width_mm=400, column2_depth_mm=400)),
    ("heavier left column", dict(p1_service_kn=1500, p2_service_kn=800)),
    ("no own-weight allowance", dict(self_weight_pct=0)),
    # the development of the bars at the stress of each section (Cl. 26.2.1), with end bends where straight bars fall short
    ("bottom bars with end bends", dict(sbc_kn_m2=300, p1_service_kn=2500, p2_service_kn=800, column1_width_mm=450, column1_depth_mm=450,
                                        column2_width_mm=450, column2_depth_mm=450, spacing_mm=2400, fck=30)),
    ("band bars with end bends", dict(sbc_kn_m2=450, p1_service_kn=600, p2_service_kn=800, column1_width_mm=450, column1_depth_mm=450,
                                      column2_width_mm=450, column2_depth_mm=450, spacing_mm=4000, fck=20, exposure="mild")),
    ("widened to develop the bars across", dict(sbc_kn_m2=600, p1_service_kn=600, p2_service_kn=2000, column1_width_mm=450, column1_depth_mm=450,
                                                column2_width_mm=450, column2_depth_mm=450, spacing_mm=4000, fck=20, exposure="mild")),
]

STOPS: list[tuple[str, dict, str]] = [
    ("thin entered depth", dict(length_mm=6100, width_mm=1950, depth_mm=200, p1_service_kn=3000, p2_service_kn=3000),
     "The depth entered needs compression steel"),
]


def steel(m_knm: float, b: float, d: float, fck: float, fy: float) -> float:
    if m_knm <= 0:
        return 0.0
    lo, hi = 0.0, d
    for _ in range(200):
        x = (lo + hi) / 2
        if 0.36 * fck * b * x * (d - 0.42 * x) / 1e6 < m_knm:
            lo = x
        else:
            hi = x
    return 0.36 * fck * b * x / (0.87 * fy)


def tau_c(fck: float, pt: float) -> float:
    pt = min(max(pt, 0.15), 3.0)
    fc = min(fck, 40)
    beta = max(0.8 * fc / (6.89 * pt), 1.0)
    return 0.85 * math.sqrt(0.8 * fc) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)


def l_d(dia: float, fck: float, fy: float) -> float:
    tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[min(int(fck), 40)] * (1.6 if fy >= 415 else 1.0)
    return dia * 0.87 * fy / (4 * tbd)


class Hand:
    """Point loads at the column centres on a trapezoid of factored pressure (kN, m inside)."""

    def __init__(self, s: dict, a: float, L: float, B: float) -> None:
        self.s, self.L, self.B = s, L / 1000, B / 1000
        self.x = [a / 1000, (a + s["spacing_mm"]) / 1000]
        self.p = [s["p1_service_kn"], s["p2_service_kn"]]
        self.pu = [s["load_factor"] * p for p in self.p]
        P = sum(self.pu)
        xr = sum(p * x for p, x in zip(self.pu, self.x, strict=True)) / P
        e = xr - self.L / 2
        self.e = e
        # q at the ends: P/A (1 -/+ 6 e / L)
        self.q_left = P / (self.L * self.B) * (1 - 6 * e / self.L)
        self.q_right = P / (self.L * self.B) * (1 + 6 * e / self.L)

    def q(self, x: float) -> float:
        return self.q_left + (self.q_right - self.q_left) * x / self.L

    def shear(self, x: float) -> float:
        up = self.B * x * (self.q_left + self.q(x)) / 2
        return up - sum(p for p, xc in zip(self.pu, self.x, strict=True) if xc < x)

    def moment(self, x: float) -> float:
        # the trapezoid's resultant B x (q0 + qx)/2 at x (2 q0 + qx) / (3 (q0 + qx)) from the left end
        q0, qx = self.q_left, self.q(x)
        up = self.B * x * x * (2 * q0 + qx) / 6  # resultant times its lever arm about x: B x^2 (q0/2 + (qx - q0)/6)
        return up - sum(p * (x - xc) for p, xc in zip(self.pu, self.x, strict=True) if xc < x)

    def zero_shear(self) -> float:
        # between the columns: B (q0 x + k x^2 / 2) = P_u1
        q0, k = self.q_left, (self.q_right - self.q_left) / self.L
        if abs(k) < 1e-12:
            return self.pu[0] / (self.B * q0)
        return (-q0 + math.sqrt(q0 * q0 + 2 * k * self.pu[0] / self.B)) / k


def faces(s: dict, a: float) -> list[float]:
    d1, d2, sp = s["column1_depth_mm"], s["column2_depth_mm"], s["spacing_mm"]
    return [a - d1 / 2, a + d1 / 2, a + sp - d2 / 2, a + sp + d2 / 2]


def balance(s: dict, a: float) -> float:
    xr = s["spacing_mm"] * s["p2_service_kn"] / (s["p1_service_kn"] + s["p2_service_kn"])
    L = math.ceil(2 * (a + xr) / 50 - 1e-9) * 50
    h = Hand(s, a, L, 1000)
    m_pos = max(max(h.moment(f / 1000) for f in faces(s, a)), 0.0)
    g0, g1 = faces(s, a)[1] / 1000, faces(s, a)[2] / 1000
    xz = h.zero_shear()
    cand = [g0, g1] + ([xz] if g0 < xz < g1 else [])
    m_hog = max(-min(h.moment(x) for x in cand), 0.0)
    return abs(m_hog - m_pos)


def punching(s: dict, h: Hand, d: dict, dp: float) -> list[tuple[tuple[int, ...], float, float]]:
    """(columns, b0, V_p) by cases."""
    L, B = d["L"], d["B"]
    rects = []
    for i, (x, b, D) in enumerate(((d["x1"], s["column1_width_mm"], s["column1_depth_mm"]), (d["x2"], s["column2_width_mm"], s["column2_depth_mm"]))):
        x0, x1 = max(x - D / 2 - dp / 2, 0.0), min(x + D / 2 + dp / 2, L)
        rects.append((i, x0, x1, min(b + dp, B)))

    def load(x0: float, x1: float, hgt: float) -> float:
        return h.q((x0 + x1) / 2000) * (x1 - x0) * hgt / 1e6

    (i1, a0, a1, h1), (i2, b0_, b1, h2) = rects
    if b0_ < a1:  # overlapping: one outline
        inside = load(a0, a1, h1) + load(b0_, b1, h2) - load(b0_, a1, min(h1, h2))
        hmax = max(h1, h2)
        per = (2 * (b1 - a0) if hmax < B else 0.0)
        if hmax < B and min(h1, h2) >= B:
            per = 0.0
        if h1 < B and h2 < B:
            per = 2 * (b1 - a0)
        per += (h1 if a0 > 0 else 0.0) + (h2 if b1 < L else 0.0) + abs(h1 - h2)
        return [((1, 2), per, sum(h.pu) - inside)]
    out = []
    for i, x0, x1, hh in rects:
        per = (2 * (x1 - x0) if hh < B else 0.0) + (hh if x0 > 0 else 0.0) + (hh if x1 < L else 0.0)
        out.append(((i + 1,), per, h.pu[i] - load(x0, x1, hh)))
    return out


def check(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    d = res["data"]
    fck, fy = float(s["fck"]), float(s["fy"])
    bad: list[str] = []
    n = 0

    def same(key: str, engine: float, hand: float, tol: float = 1e-4) -> None:
        nonlocal n
        n += 1
        if abs(engine - hand) > tol * max(abs(hand), 1e-9) + 1e-6:
            bad.append(f"{name}: {key} engine {engine:.6g} hand {hand:.6g}")

    cover = s["clear_cover_mm"] or max(50.0, {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}[s["exposure"]])
    same("cover", d["cover"], cover)
    P = s["p1_service_kn"] + s["p2_service_kn"]
    xr = s["spacing_mm"] * s["p2_service_kn"] / P
    same("x_r", d["x_r"], xr)
    L, B, a, D = d["L"], d["B"], d["a"], d["D"]
    # the plan
    if s["length_mm"] is None:
        same("L", L, math.ceil(2 * (a + xr) / 50 - 1e-9) * 50)
    else:
        same("L", L, s["length_mm"])
        if s["left_end_mm"] is None:
            same("a", a, round((L / 2 - xr) / 25) * 25)
    if s["left_end_mm"] is not None:
        same("a", a, s["left_end_mm"])
    pg = P * (1 + s["self_weight_pct"] / 100)
    if s["left_end_mm"] is None and s["length_mm"] is None:
        a_min = math.ceil(max(s["column1_depth_mm"] / 2, s["spacing_mm"] - 2 * xr + s["column2_depth_mm"] / 2) / 25 - 1e-9) * 25
        side = math.sqrt(pg / s["sbc_kn_m2"]) * 1000
        grid = [g for g in (a_min + 25 * k for k in range(int((s["spacing_mm"] + side) / 25) + 1))
                if math.ceil(2 * (g + xr) / 50 - 1e-9) * 50 - g - s["spacing_mm"] >= s["column2_depth_mm"] / 2]

        def longer(g: float) -> bool:  # the least width the pressure allows is no more than the length
            Lg = math.ceil(2 * (g + xr) / 50 - 1e-9) * 50
            eg = (g + xr) - Lg / 2
            area = pg / s["sbc_kn_m2"]  # m2; the eccentricity adds a little, so test the width that passes
            Bg = max(max(s["column1_width_mm"], s["column2_width_mm"]) + 100, math.ceil(area / (Lg / 1000) * 1000 / 50 - 1e-9) * 50)
            while pg / (Lg / 1000 * Bg / 1000) + 6 * P * abs(eg) / 1000 / (Bg / 1000 * (Lg / 1000) ** 2) > s["sbc_kn_m2"] + 1e-9:
                Bg += 50
            return Bg <= Lg

        pool = [g for g in grid if longer(g)] or grid
        best = min(balance(s, g) for g in pool)
        n += 1
        if (a in pool) != bool(pool) or longer(a) != longer(pool[0]):
            bad.append(f"{name}: left end {a} gives a footing wider than long where a longer one exists")
        n += 1
        if balance(s, a) > best + 1e-6:
            bad.append(f"{name}: left end {a} does not balance the moments ({balance(s, a):.3f} against {best:.3f} kN m)")
    Lm, Bm = L / 1000, B / 1000
    e = (a + xr) - L / 2
    same("e", d["e"], e, 1e-6)
    q_max, q_min = pg / (Lm * Bm) + 6 * P * abs(e) / 1000 / (Bm * Lm * Lm), pg / (Lm * Bm) - 6 * P * abs(e) / 1000 / (Bm * Lm * Lm)
    same("q_max", d["q_max"], q_max)
    same("q_min", d["q_min"], q_min)
    if q_max > s["sbc_kn_m2"] + 1e-6 or q_min < -1e-6:
        bad.append(f"{name}: pressures {q_max:.1f} / {q_min:.1f} outside the limits")
    if s["width_mm"] is None:
        b_min = max(s["column1_width_mm"], s["column2_width_mm"]) + 100
        Bl = (B - 50) / 1000
        q_less = pg / (Lm * Bl) + 6 * P * abs(e) / 1000 / (Bl * Lm * Lm)
        n += 1
        if B - 50 >= b_min and q_less <= s["sbc_kn_m2"] and not any("widened" in i["title"].lower() for sec in res["sheet"]["sections"]
                                                                     for i in sec["items"]):
            bad.append(f"{name}: width {B} is not the least ({B - 50} gives {q_less:.1f} kN/m2)")
    h = Hand(s, a, L, B)
    same("q_u_left", d["q_u_left"], h.q_left)
    same("q_u_right", d["q_u_right"], h.q_right)
    # moments and shears at the faces (outside the columns the point loads give the same as the spread ones)
    for f, me, ve in zip(faces(s, a), d["m_faces"], d["v_faces"], strict=True):
        same(f"M at {f:.0f}", me, h.moment(f / 1000), 1e-6)
        same(f"V at {f:.0f}", ve, h.shear(f / 1000 + (1e-9 if f in (faces(s, a)[1], faces(s, a)[3]) else -1e-9)), 1e-6)
    g0, g1 = faces(s, a)[1] / 1000, faces(s, a)[2] / 1000
    xz = h.zero_shear()
    cand = [g0, g1] + ([xz] if g0 < xz < g1 else [])
    m_hog = max(-min(h.moment(x) for x in cand), 0.0)
    same("m_hog", d["m_hog"], m_hog, 1e-7)
    same("m_pos", d["m_pos"], max(max(h.moment(f / 1000) for f in faces(s, a)), 0.0), 1e-7)
    # flexure along
    dt, db, dtop = d["d_t"], d["d_b"], d["d_top"]
    layer = max(d["dia_across"], d["dia_dist"])
    same("d_t", dt, D - cover - d["dia_across"] / 2)
    same("d_b", db, D - cover - layer - d["dia_bottom"] / 2)
    same("d_top", dtop, D - cover - d["dia_top"] / 2)
    rmin = 0.0015 if fy <= 250 else 0.0012
    for key, m, dd in (("bottom", d["m_pos"], db), ("top", d["m_hog"], dtop)):
        asf = steel(m, B, dd, fck, fy)
        same(f"as_flex_{key}", d[f"as_flex_{key}"], asf, 3e-3)
        req = max(asf, rmin * B * D)
        same(f"as_{key}", d[f"as_{key}"], req, 3e-3)
        dia, n_b, sp = d[f"dia_{key}"], d[f"n_{key}"], d[f"s_{key}"]
        same(f"as_prov_{key}", d[f"as_prov_{key}"], n_b * math.pi * dia * dia / 4, 1e-6)
        if d[f"as_prov_{key}"] < req * (1 - 3e-3):
            bad.append(f"{name}: {key} steel {d[f'as_prov_{key}']:.0f} below {req:.0f}")
        if sp > min(3 * dd, 300) + 1e-9 or sp < 100 - 1e-9 or (n_b - 1) * sp > B - 2 * cover - dia + 1e-6:
            bad.append(f"{name}: {key} bars {n_b} at {sp} do not fit the rules")
    # development along, at the stress of each section
    for x, req, avail in d["anchor_bottom"]:
        m = h.moment(x / 1000)
        want = l_d(d["dia_bottom"], fck, fy) * min(steel(m, B, db, fck, fy) / d["as_prov_bottom"], 1.0)
        same(f"anchor bottom at {x:.0f}", req, want, 3e-3)
        same(f"available at {x:.0f}", avail, min(x, L - x) - cover)
        r_b = (2 if fy <= 250 else 4) * d["dia_bottom"]
        cap = avail - (r_b + d["dia_bottom"]) + 8 * d["dia_bottom"] if d["bent_bottom"] else avail
        if want > cap * (1 + 3e-3):
            bad.append(f"{name}: bottom bars not developed at {x:.0f} ({want:.0f} > {cap:.0f})")
    if d["m_hog"] > 0:
        want = l_d(d["dia_top"], fck, fy) * min(steel(d["m_hog"], B, dtop, fck, fy) / d["as_prov_top"], 1.0)
        same("anchor top", d["anchor_top"][0], want, 3e-3)
        avail = min(d["x_hog"], L - d["x_hog"]) - cover
        if want > avail + 1e-6 and not d["bent_top"]:
            bad.append(f"{name}: top bars not developed")
    # across: the bands
    mid = ((d["x1"] + s["column1_depth_mm"] / 2) + (d["x2"] - s["column2_depth_mm"] / 2)) / 2
    for i, (bd, x, b, Dc, pu) in enumerate(zip(d["bands"], (d["x1"], d["x2"]), (s["column1_width_mm"], s["column2_width_mm"]),
                                             (s["column1_depth_mm"], s["column2_depth_mm"]), h.pu, strict=True), start=1):
        lo, hi = max(x - Dc / 2 - 0.75 * dt, 0.0), min(x + Dc / 2 + 0.75 * dt, L)
        lo, hi = (lo, min(hi, mid)) if i == 1 else (max(lo, mid), hi)
        same(f"band {i} width", bd["w"], hi - lo)
        a_t = (B - b) / 2
        m_t = pu / Bm * (a_t / 1000) ** 2 / 2
        same(f"band {i} moment", bd["m"], m_t)
        asf = steel(m_t, hi - lo, dt, fck, fy)
        same(f"band {i} as_flex", bd["as_flex"], asf, 3e-3)
        req = max(asf, rmin * (hi - lo) * D)
        same(f"band {i} as_req", bd["as_req"], req, 3e-3)
        if bd["as_prov"] < req * (1 - 3e-3) or bd["s"] > min(3 * dt, 300) + 1e-9 or bd["s"] < 100 - 1e-9:
            bad.append(f"{name}: band {i} bars {bd['n']} at {bd['s']} short of the rules")
        want = l_d(d["dia_across"], fck, fy) * min(asf / bd["as_prov"], 1.0)
        same(f"band {i} anchorage", bd["ld_req"], want, 3e-3)
        r_b = (2 if fy <= 250 else 4) * d["dia_across"]
        cap = a_t - cover - (r_b + d["dia_across"]) + 8 * d["dia_across"] if bd["bent"] else a_t - cover
        if want > cap * (1 + 3e-3):
            bad.append(f"{name}: band {i} bars not developed ({want:.0f} > {cap:.0f})")
        if a_t > dt:
            v = pu / Bm * (a_t - dt) / 1000
            same(f"band {i} shear", bd["v"], v)
            tau, tc = v * 1e3 / ((hi - lo) * dt), tau_c(fck, 100 * bd["as_prov"] / ((hi - lo) * dt))
            same(f"band {i} tau_c", bd["tc"], tc, 0.03)
            if not s["depth_mm"] and tau > tc * 1.03:
                bad.append(f"{name}: band {i} one-way shear fails by hand")
    dist_need = rmin * 1000 * D
    if math.pi * d["dia_dist"] ** 2 / 4 * 1000 / d["s_dist"] < dist_need * (1 - 1e-9) or d["s_dist"] > min(3 * (D - cover - d["dia_dist"] / 2), 300):
        bad.append(f"{name}: steel across outside the bands below the minimum")
    # one-way shear along at d from the faces
    f = faces(s, a)
    want_sections = []
    for x, inner in ((f[0] - db, False), (f[1] + dtop, True), (f[2] - dtop, True), (f[3] + db, False)):
        if 0 < x < L and (not inner or f[1] < x < f[2]):
            want_sections.append(x)
    n += 1
    if [round(sc["x"], 1) for sc in d["shear"]] != [round(x, 1) for x in want_sections]:
        bad.append(f"{name}: shear sections {[sc['x'] for sc in d['shear']]} against {want_sections}")
    for sc in d["shear"]:
        x = sc["x"] / 1000
        same(f"V at {sc['x']:.0f}", sc["v"], h.shear(x), 1e-6)
        m = h.moment(x)
        top = m < 0
        dd = dtop if top else db
        tau = abs(h.shear(x)) * 1e3 / (B * dd)
        tc = tau_c(fck, 100 * (d["as_prov_top"] if top else d["as_prov_bottom"]) / (B * dd))
        same(f"tau at {sc['x']:.0f}", sc["tau"], tau)
        same(f"tau_c at {sc['x']:.0f}", sc["tc"], tc, 0.03)
        if not s["depth_mm"] and tau > tc * 1.03:
            bad.append(f"{name}: one-way shear at {sc['x']:.0f} fails by hand ({tau:.3f} > {tc:.3f})")
    # punching
    dp = (dt + db) / 2
    hand_p = punching(s, h, d, dp)
    n += 1
    if [tuple(p["cols"]) for p in d["punching"]] != [c for c, _, _ in hand_p]:
        bad.append(f"{name}: punching groups {[p['cols'] for p in d['punching']]} against {[c for c, _, _ in hand_p]}")
    else:
        for p, (cols, b0, vp) in zip(d["punching"], hand_p, strict=True):
            same(f"b0 {cols}", p["b0"], b0)
            same(f"V_p {cols}", p["vp"], vp)
            dims = [(s["column1_width_mm"], s["column1_depth_mm"]), (s["column2_width_mm"], s["column2_depth_mm"])]
            ks = min(min(0.5 + min(dims[c - 1]) / max(dims[c - 1]), 1.0) for c in cols)
            allow = ks * 0.25 * math.sqrt(fck)
            same(f"allow {cols}", p["allow"], allow)
            if not s["depth_mm"] and vp * 1e3 / (b0 * dp) > allow + 1e-9:
                bad.append(f"{name}: punching {cols} fails by hand")
    # bearing at the column bases
    for i, (bg, x, b, Dc, pu) in enumerate(zip(d["bearing"], (d["x1"], d["x2"]), (s["column1_width_mm"], s["column2_width_mm"]),
                                             (s["column1_depth_mm"], s["column2_depth_mm"]), h.pu, strict=True), start=1):
        along = min(2 * min(x, L - x), Dc + 4 * D) / Dc  # the frustum's base along, within the footing and at 1 in 2
        across = min(B, b + 4 * D) / b
        same(f"bearing ratio {i}", bg["ratio"], min(along, across, 2.0))
        same(f"bearing stress {i}", bg["sigma"], pu * 1e3 / (b * Dc))
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = CombinedFootingInput().model_dump()
    if defaults != BASE:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)} }")
    base = design_combined_footing(CombinedFootingInput(**BASE))
    n_total = 0
    if base["status"] != "ok":
        bad.append(f"base: engine reports {base['status']}")
    else:
        for key, want in BASE_EXPECTED.items():
            n_total += 1
            if abs(base["data"][key] - want) > 1e-6 * max(1, abs(want)):
                bad.append(f"base: {key} engine {base['data'][key]} expected {want}")
        n, b0 = check("base", BASE, base)
        n_total += n
        bad += b0
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_combined_footing(CombinedFootingInput(**s))
        if res["status"] == "stopped":
            bad.append(f"{name}: stopped unexpectedly: {res['stop_message']}")
            continue
        if res["status"] != "ok":
            failed = [i["id"] for sec in res["sheet"]["sections"] for i in sec["items"] if i["kind"] == "check" and not i["ok"]]
            if not (s.get("depth_mm") and all(f.startswith(("shear", "punching")) for f in failed)):
                bad.append(f"{name}: engine reports Not OK: {failed}")
        n, b1 = check(name, s, res)
        n_cases += n
        bad += b1
    for name, ov, want in STOPS:
        res = design_combined_footing(CombinedFootingInput(**dict(BASE, **ov)))
        if res["status"] != "stopped" or not (res["stop_message"] or "").startswith(want):
            bad.append(f"stop '{name}': got {res['status']} / {res['stop_message']}")
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n_total} results of the worked example and {n_cases} values of {len(CASES)} alternative-input cases agree with the "
          f"independent hand check; {len(STOPS)} stop state correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
