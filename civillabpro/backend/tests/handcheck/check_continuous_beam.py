#!/usr/bin/env python3
"""Independent hand check of the continuous beam engine.

From the clauses of IS 456:2000 and SP 16, by a different route wherever one exists:

  * Tables 12 and 13 typed again here (double entry) and applied to the spans of Cl. 22.2(b);
  * flexure: the neutral axis by bisection on the stress block of Cl. 38.1, a rectangle b_f wide while it is
    in the flange, and the G-2.2 web case by the closed-form root of its quadratic (engine: Annex G-1.1(b)
    and bisection on G-2.2); compression steel stress from SP 16 Table A;
  * tau_c by the SP 16 closed form (engine: Table 19);
  * points of inflection by Hardy Cross moment distribution of every load arrangement of Cl. 22.4.1 and a
    scan with bisection for the first zero (engine: three-moment equation and a closed-form root).

Run:  python tests/handcheck/check_continuous_beam.py
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.continuous_beam import ContinuousBeamInput, design_continuous_beam  # noqa: E402

BASE = dict(
    mark="CB1", spans=4, clear_span_mm=5000, support_width_mm=300, section="rectangular", width_mm=300, depth_mm=500,
    flange_thickness_mm=120, flange_width_mm=3000, isolated_flange=False, l0_mm=None, fck=25, fy=500, fy_stirrup=500,
    exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20, dead_load_kn_m=25, live_load_kn_m=15, include_self_weight=True,
    unit_weight_kn_m3=25, load_factor=1.5, main_bar_dia_mm=None, hanger_bar_dia_mm=12, stirrup_dia_mm=8, stirrup_legs=2,
)

# By hand for BASE: w_d = 1.5 (25 + 25 x 0.3 x 0.5) = 43.125, w_l = 22.5 kN/m; supports 300 < 5000/12, so
# l = min(5000 + d, 5300) = 5300 for both span types; M_1 = (43.125/12 + 22.5/10) 5.3^2 = 164.15 kN m,
# M_B = (43.125/10 + 22.5/9) 5.3^2 = 191.36 kN m.
BASE_EXPECTED = dict(wd=43.125, wl=22.5, l_end=5300.0, l_int=5300.0, m_end=164.1509, m_b=191.3631)

CASES: list[tuple[str, dict]] = [
    ("three spans", dict(spans=3)),
    ("five spans", dict(spans=5)),
    ("twelve spans", dict(spans=12, clear_span_mm=4000)),
    ("wide supports (Cl. 22.2(b))", dict(spans=6, support_width_mm=600, clear_span_mm=6000)),
    ("heavy imposed load, compression steel", dict(live_load_kn_m=40)),
    ("Fe 415 M20 mild", dict(fy=415, fy_stirrup=415, fck=20, exposure="mild")),
    ("T-beam floor", dict(section="t_beam", width_mm=300, depth_mm=500, flange_thickness_mm=125, flange_width_mm=3000, dead_load_kn_m=35,
                          live_load_kn_m=20, clear_span_mm=6000)),
    ("L-beam, l_0 entered", dict(section="l_beam", width_mm=250, depth_mm=450, flange_thickness_mm=120, flange_width_mm=1200, l0_mm=3500,
                                 dead_load_kn_m=20, live_load_kn_m=10)),
    ("no self-weight", dict(include_self_weight=False, dead_load_kn_m=30)),
    ("deep, side face bars, four legs", dict(width_mm=400, depth_mm=900, clear_span_mm=9000, dead_load_kn_m=60, live_load_kn_m=30, fck=30,
                                             support_width_mm=450, stirrup_legs=4, stirrup_dia_mm=10)),
    ("fixed bar size", dict(main_bar_dia_mm=20)),
    ("light load", dict(dead_load_kn_m=6, live_load_kn_m=3)),
]

STOPS: list[tuple[str, dict, str]] = [
    ("continuous deep beam", dict(clear_span_mm=1000, depth_mm=600), "The effective span is less than 2.5 times"),
    ("section too small", dict(depth_mm=300, width_mm=200, dead_load_kn_m=80, live_load_kn_m=60, clear_span_mm=7000), "No arrangement"),
]

# Tables 12 and 13 of IS 456, typed again: (dead load, imposed load).
T12 = {"end_span": (1 / 12, 1 / 10), "next_to_end_support": (-1 / 10, -1 / 9), "interior_span": (1 / 16, 1 / 12), "interior_support": (-1 / 12, -1 / 9)}
T13 = {"end": (0.40, 0.45), "next_outer": (0.60, 0.60), "next_inner": (0.55, 0.60), "interior": (0.50, 0.60)}
SP16_TABLE_A = {
    415: [(0.00144, 288.7), (0.00163, 306.7), (0.00192, 324.8), (0.00241, 342.8), (0.00276, 351.8), (0.00380, 360.9)],
    500: [(0.00174, 347.8), (0.00195, 369.6), (0.00226, 391.3), (0.00277, 413.0), (0.00312, 423.9), (0.00417, 434.8)],
}


def fsc(strain: float, fy: int) -> float:
    if fy == 250:
        return min(2e5 * strain, 217.5)
    pts = SP16_TABLE_A[fy]
    if strain <= pts[0][0]:
        return 2e5 * strain
    for (e0, s0), (e1, s1) in zip(pts, pts[1:], strict=False):
        if strain <= e1:
            return s0 + (s1 - s0) * (strain - e0) / (e1 - e0)
    return pts[-1][1]


def steel(m_knm: float, b: float, d: float, fck: float, fy: float, dc: float, bf: float | None = None, df: float = 0.0) -> tuple[float, float]:
    """(A_st, A_sc) for a moment; a flange of width bf and depth df in compression if given."""
    xmax = 0.0035 / (0.0055 + 0.87 * fy / 2e5) * d

    def comp(x: float) -> tuple[float, float]:
        if bf is None or x <= df:
            w = bf if bf is not None else b
            return 0.36 * fck * w * x, 0.36 * fck * w * x * (d - 0.42 * x) / 1e6
        yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
        return (0.36 * fck * b * x + 0.45 * fck * (bf - b) * yf,
                (0.36 * fck * b * x * (d - 0.42 * x) + 0.45 * fck * (bf - b) * yf * (d - yf / 2)) / 1e6)

    mlim = comp(xmax)[1]
    if m_knm > mlim:
        f = fsc(0.0035 * (1 - dc / xmax), int(fy)) - 0.446 * fck
        asc = (m_knm - mlim) * 1e6 / (f * (d - dc))
        return (comp(xmax)[0] + asc * f) / (0.87 * fy), asc
    if bf is not None and m_knm > comp(df)[1] and df < xmax:  # web: closed-form root when y_f = D_f
        mw = m_knm * 1e6 - 0.45 * fck * (bf - b) * df * (d - df / 2)
        a2, a1 = 0.1512 * fck * b, 0.36 * fck * b * d
        x = (a1 - math.sqrt(max(a1 * a1 - 4 * a2 * mw, 0.0))) / (2 * a2)
        if x >= 7 * df / 3:
            return comp(x)[0] / (0.87 * fy), 0.0
    lo, hi = 0.0, xmax
    for _ in range(200):
        x = (lo + hi) / 2
        lo, hi = (x, hi) if comp(x)[1] < m_knm else (lo, x)
    return comp(hi)[0] / (0.87 * fy), 0.0


def tau_c(fck: float, pt: float) -> float:
    ptc = min(max(pt, 0.15), 3.0)
    beta = max(0.8 * min(fck, 40) / (6.89 * ptc), 1.0)
    return 0.85 * math.sqrt(0.8 * min(fck, 40)) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)


def hardy_cross(spans: list[float], w: list[float]) -> list[float]:
    """Bending moments at the supports (sagging positive) by moment distribution; end supports pinned."""
    n = len(spans)
    # member end moments, clockwise positive: (left end, right end) of each span
    k = [3 / s if i in (0, n - 1) else 4 / s for i, s in enumerate(spans)]  # end spans: far end pinned
    mem = []
    for i, (s, q) in enumerate(zip(spans, w, strict=True)):
        if i == 0:
            mem.append([0.0, q * s * s / 8])
        elif i == n - 1:
            mem.append([-q * s * s / 8, 0.0])
        else:
            mem.append([-q * s * s / 12, q * s * s / 12])
    for _ in range(2000):
        worst = 0.0
        for j in range(1, n):  # joint j: right end of span j-1, left end of span j
            unb = mem[j - 1][1] + mem[j][0]
            worst = max(worst, abs(unb))
            kl, kr = k[j - 1], k[j]
            dl, dr = -unb * kl / (kl + kr), -unb * kr / (kl + kr)
            mem[j - 1][1] += dl
            mem[j][0] += dr
            if j - 1 not in (0, n - 1):
                mem[j - 1][0] += dl / 2  # carry over to the far end of an interior span
            if j not in (0, n - 1):
                mem[j][1] += dr / 2
        if worst < 1e-12:
            break
    return [0.0] + [mem[j][0] for j in range(1, n)] + [0.0]


def first_zero(ml: float, mr: float, q: float, s: float) -> float:
    if ml >= 0:
        return 0.0
    f = lambda x: ml * (1 - x / s) + mr * x / s + q * x * (s - x) / 2  # noqa: E731
    steps = 4000
    for i in range(1, steps + 1):
        x = s * i / steps
        if f(x) >= 0:
            lo, hi = s * (i - 1) / steps, x
            for _ in range(80):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
            return (lo + hi) / 2
    return s


def extents(spans: list[float], wd: float, wl: float) -> list[tuple[float, float]]:
    n = len(spans)
    pats = [[True] * n, [i % 2 == 0 for i in range(n)], [i % 2 == 1 for i in range(n)]] + [[j in (i, i + 1) for j in range(n)] for i in range(n - 1)]
    out = [[0.0, 0.0] for _ in range(n)]
    for p in pats:
        w = [wd + (wl if p[i] else 0.0) for i in range(n)]
        m = hardy_cross(spans, w)
        for i in range(n):
            out[i][0] = max(out[i][0], first_zero(m[i], m[i + 1], w[i], spans[i]))
            out[i][1] = max(out[i][1], first_zero(m[i + 1], m[i], w[i], spans[i]))
    return [(a, b) for a, b in out]


def hand(s: dict, res: dict) -> dict:
    eng, reinf = res["data"], res["reinforcement"]
    b, D, lc, sw, n = s["width_mm"], s["depth_mm"], s["clear_span_mm"], s["support_width_mm"], s["spans"]
    fck, fy = s["fck"], s["fy"]
    cover = s["clear_cover_mm"] or {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}[s["exposure"]]
    dst = s["stirrup_dia_mm"]
    flanged = s["section"] != "rectangular"
    df = s["flange_thickness_mm"]
    out: dict = {}
    rib = D - df if flanged else D
    w_self = s["unit_weight_kn_m3"] * b * rib / 1e6 if s["include_self_weight"] else 0.0
    wd, wl = s["load_factor"] * (s["dead_load_kn_m"] + w_self), s["load_factor"] * s["live_load_kn_m"]
    out.update(w_self=w_self, wd=wd, wl=wl)

    def ybar(g: dict) -> float:  # centroid of a group from its face
        y1 = cover + dst + g["dia"] / 2
        if len(g["layers"]) == 1:
            return y1
        y2 = y1 + g["dia"] + max(g["dia"], 2 * s["max_aggregate_mm"] / 3, 15)
        return (g["layers"][0] * y1 + g["layers"][1] * y2) / g["count"]

    def area(g: dict) -> float:
        return g["count"] * math.pi * g["dia"] ** 2 / 4

    d1, d2 = D - ybar(reinf["end"]["bottom"]), D - ybar(reinf["interior"]["bottom"])

    def span_of(d: float, end: bool) -> float:  # Cl. 22.2(b)
        if sw <= min(lc / 12, 600):
            return min(lc + d, lc + sw)
        return lc + min(d / 2, sw / 2) if end else lc

    l1, l2 = span_of(d1, True), span_of(d2, False)
    out.update(l_end=l1, l_int=l2)
    co = lambda key, span: (T12[key][0] * wd + T12[key][1] * wl) * (span / 1000) ** 2  # noqa: E731
    out["m_end"], out["m_int"] = co("end_span", l1), co("interior_span", l2)
    out["m_b"] = -(co("next_to_end_support", l1) + co("next_to_end_support", l2)) / 2
    out["m_c"] = -co("interior_support", l2) if n >= 4 else 0.0
    sh = lambda key, span: (T13[key][0] * wd + T13[key][1] * wl) * span / 1000  # noqa: E731
    out.update(v_a=sh("end", l1), v_b1=sh("next_outer", l1), v_b2=sh("next_inner", l2), v_c=sh("interior", l2) if n >= 4 else 0.0)

    # mid-span sections (bottom in tension; a flange in compression if there is one)
    for key, d, span, m in (("end", d1, l1, out["m_end"]), ("interior", d2, l2, out["m_int"])):
        bf = None
        if flanged:
            l0 = s["l0_mm"] or 0.7 * span
            bact = s["flange_width_mm"]
            if s["isolated_flange"]:
                bf = (1 if s["section"] == "t_beam" else 0.5) * l0 / (l0 / bact + 4) + b
            else:
                bf = l0 / 6 + b + 6 * df if s["section"] == "t_beam" else l0 / 12 + b + 3 * df
            bf = min(bf, bact)
        dc = ybar(reinf[key]["top"])
        ast, asc = steel(m, b, d, fck, fy, dc, bf, df)
        out[f"{key}.ast_req"], out[f"{key}.asc_req"] = ast, asc
        out[f"{key}.d"] = d
    # supports (top in tension, the web as a rectangle, the lighter bottom bars as compression)
    comp_b = reinf["end"]["bottom"] if area(reinf["end"]["bottom"]) <= area(reinf["interior"]["bottom"]) else reinf["interior"]["bottom"]
    sups = [("support_b", reinf["support_b"], out["m_b"], comp_b)]
    if n >= 4:
        sups.append(("support_c", reinf["support_c"], out["m_c"], reinf["interior"]["bottom"]))
    for key, sup, m, comp in sups:
        d = D - ybar(sup["top"])
        ast, asc = steel(m, b, d, fck, fy, ybar(comp))
        out[f"{key}.ast_req"], out[f"{key}.asc_req"], out[f"{key}.d"] = ast, asc, d

    # stirrups: required spacing at each end of each span type
    fyv = min(s["fy_stirrup"], 415)
    asv = s["stirrup_legs"] * math.pi * dst**2 / 4
    w = wd + wl
    db = out["support_b.d"]
    ends = {"end": [(out["v_a"], area(reinf["end"]["bottom"]), d1), (out["v_b1"], area(reinf["support_b"]["top"]), db)],
            "interior": [(out["v_b2"], area(reinf["support_b"]["top"]), db)]}
    if n >= 4:
        ends["interior"].append((out["v_c"], area(reinf["support_c"]["top"]), out["support_c.d"]))
    for kind, rows in ends.items():
        lims = [0.87 * fyv * asv / (0.4 * b), 300.0]
        for v, ast, d in rows:
            vu = max(v - w * d / 1000, 0.0)
            vus = vu - tau_c(fck, 100 * ast / (b * d)) * b * d / 1e3
            if vus > 0:
                lims.append(0.87 * fyv * asv * d / (vus * 1e3))
            lims.append(0.75 * d)
        out[f"stirrups.{kind}.allow"] = min(lims)

    # deflection: continuous, k_t, k_c, Fig. 6
    for key, d, span in (("end", d1, l1), ("interior", d2, l2)):
        bf = eng[key]["bf"]
        bd = bf if bf else b
        ast_p = area(reinf[key]["bottom"])
        fs = 0.58 * fy * eng[key]["ast_req"] / ast_p
        pt = 100 * ast_p / (bd * d)
        kt = min(2.0, 1 / (0.225 + 0.00322 * fs - 0.625 * math.log10(1 / pt)))
        kc = min(1.5, 1 + (pc := 100 * area(reinf[key]["top"]) / (bd * d)) / (3 + pc)) if eng[key]["doubly"] else 1.0
        kf = 1.0
        if bf:
            r = b / bf
            kf = 0.8 if r <= 0.3 else 0.8 + 0.2 * (r - 0.3) / 0.7
        out[f"defl.{key}.allow"] = 26 * (10000 / span if span > 10000 else 1) * kt * kc * kf

    # points of inflection, measured from the faces of the supports
    sp = [l1 / 1000] + [l2 / 1000] * (n - 2) + [l1 / 1000]
    ex = extents(sp, wd, wl)
    face = lambda x, span: min(max(x * 1000 - (span - lc) / 2, 0.0), lc)  # noqa: E731
    out["hog.B_end"], out["hog.B_int"] = face(ex[0][1], l1), face(ex[1][0], l2)
    if n >= 4:
        out["hog.C_int"] = face(max([ex[1][1]] + [x for i in range(2, n - 2) for x in ex[i]]), l2)
    return out


TOL = {".ast_req": 6e-3, ".asc_req": 1e-2, "allow": 0.03, "hog.": 2e-3}


def get(eng: dict, key: str) -> float:
    cur: object = eng
    for part in key.split("."):
        cur = cur[part]  # type: ignore[index]
    return float(cur)  # type: ignore[arg-type]


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    h = hand(s, res)
    eng = res["data"]
    bad, n = [], 0
    for key, hv in h.items():
        if key == "w_self":
            continue
        ev = get(eng, key)
        tol = next((t for k, t in TOL.items() if k in key), 1e-4)
        n += 1
        if abs(ev - hv) > tol * max(abs(hv), 1.0) + 0.05:
            bad.append(f"{name}: {key} engine {ev:.6g} hand {hv:.6g}")
    # what was provided meets the hand requirement
    reinf = res["reinforcement"]
    for key, grp in (("end", reinf["end"]["bottom"]), ("interior", reinf["interior"]["bottom"]), ("support_b", reinf["support_b"]["top"]),
                     *((("support_c", reinf["support_c"]["top"]),) if reinf["support_c"] else ())):
        prov = grp["count"] * math.pi * grp["dia"] ** 2 / 4
        if prov < h[f"{key}.ast_req"] * (1 - 6e-3):
            bad.append(f"{name}: {key} steel {prov:.0f} below the hand requirement {h[key + '.ast_req']:.0f}")
    for kind in ("end", "interior"):
        if eng["stirrups"][kind]["spacing"] > h[f"stirrups.{kind}.allow"] * 1.03:
            bad.append(f"{name}: {kind} stirrups at {eng['stirrups'][kind]['spacing']} above the hand limit {h[f'stirrups.{kind}.allow']:.0f}")
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = ContinuousBeamInput().model_dump()
    if defaults != BASE:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)} }")
    base = design_continuous_beam(ContinuousBeamInput(**BASE))
    for key, want in BASE_EXPECTED.items():
        if abs(base["data"][key] - want) > 1e-3 * max(1, abs(want)):
            bad.append(f"base: {key} engine {base['data'][key]} expected {want}")
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
    print(f"OK: {n_base + len(BASE_EXPECTED)} results agree with the independent hand check; "
          f"{n_cases} values of {len(CASES)} alternative-input cases and {len(STOPS)} stop states correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
