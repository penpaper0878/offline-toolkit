#!/usr/bin/env python3
"""Independent hand check of the footing engine.

From the clauses of IS 456:2000, by a different route where one exists:

  * plan size: the required area solved as a quadratic for equal projections, then rounded up
    (engine: stepping the projection);
  * steel areas: the stress block of Cl. 38.1 by bisection (engine: Annex G-1.1(b) closed form);
  * tau_c: the SP 16 closed form (engine: Table 19);
  * pressures, moments at the faces, one-way and punching shear, k_s, bearing and development
    length: recomputed line by line;
  * plans enlarged to anchor the bars: the development length of a T10 bar against the projection
    (engine: a search over depths and bar sizes at growing plans).

Run:  python tests/handcheck/check_footing.py
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.footing import FootingInput, design_footing  # noqa: E402

BASE = dict(
    mark="F1", column_width_mm=300, column_depth_mm=450, p_service_kn=800, m_l_service_knm=0, m_b_service_knm=0, load_factor=1.5,
    self_weight_pct=10, sbc_kn_m2=200, length_mm=None, width_mm=None, depth_mm=None, fck=25, fy=415, exposure="moderate",
    clear_cover_mm=None, max_aggregate_mm=20, bar_dia_mm=None,
)

# By hand: A = 880 / 200 = 4.40 m2; (0.45 + 2a)(0.30 + 2a) = 4.40 gives a = 0.862 m, so L = 2.174 m and
# B = 2.024 m, rounded up to 2200 x 2050 mm. q_u = 1200 / (2.2 x 2.05) = 266.08 kN/m2.
BASE_EXPECTED = dict(L=2200.0, B=2050.0, qu=1200 / (2.2 * 2.05), cover=50.0)

CASES: list[tuple[str, dict]] = [
    ("moments both ways", dict(m_l_service_knm=80, m_b_service_knm=30)),
    ("square column, heavy", dict(column_width_mm=400, column_depth_mm=400, p_service_kn=1800, sbc_kn_m2=250)),
    ("long footing, outer bars", dict(length_mm=4000, width_mm=2000, column_depth_mm=600, p_service_kn=1200)),
    ("Fe500 M30", dict(fy=500, fck=30)),
    ("weak soil", dict(sbc_kn_m2=80)),
    ("strong soil", dict(sbc_kn_m2=450)),
    ("large moment", dict(m_l_service_knm=300)),
    ("fixed T16", dict(bar_dia_mm=16)),
    ("given size and depth", dict(length_mm=2600, width_mm=2400, depth_mm=600)),
    ("mild steel M20", dict(fy=250, fck=20, exposure="mild")),
    ("severe exposure", dict(exposure="severe", fck=30)),
    ("no own-weight allowance", dict(self_weight_pct=0)),
    ("small column big load", dict(column_width_mm=230, column_depth_mm=230, p_service_kn=1000, fck=35)),
    ("long pier, bearing area limited by the depth", dict(column_width_mm=500, column_depth_mm=2000, p_service_kn=1200, sbc_kn_m2=100)),
]

# Light loads on strong soil: the bearing plan leaves projections too short to develop even a 10 mm bar with a
# 90 degree bend (L_d = 0.87 f_y phi / (4 tau_bd) against the projection less cover, less the r + phi the bend takes from
# the straight part (IS 2502: r = 2 phi mild, 4 phi deformed), plus 8 phi, Cl. 26.2.1 and 26.2.2.1(b)), so the plan grows. By hand: the engine's plan anchors T10, and 50 mm less does not.
ENLARGED: list[tuple[str, dict]] = [
    ("light load, strong soil, M20 Fe415", dict(column_width_mm=230, column_depth_mm=230, p_service_kn=300, sbc_kn_m2=400, fck=20, exposure="mild")),
    ("light load, wide column, M30 Fe550", dict(column_width_mm=450, column_depth_mm=600, p_service_kn=300, sbc_kn_m2=200, fck=30, fy=550)),
]

STOPS: list[tuple[str, dict, str]] = [
    ("entered plan too small to anchor", dict(column_width_mm=230, column_depth_mm=230, p_service_kn=300, sbc_kn_m2=400, fck=20, exposure="mild",
                                              length_mm=950, width_mm=950), "The projections beyond the column are too short"),
    ("thin entered depth", dict(length_mm=4000, width_mm=4000, depth_mm=200, p_service_kn=3000, sbc_kn_m2=300), "The depth entered needs compression steel"),
]


def steel(m_knm: float, b: float, d: float, fck: float, fy: float) -> float:
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


def hand(s: dict, d: dict) -> dict:
    fck, fy = float(s["fck"]), float(s["fy"])
    bc, dc = s["column_width_mm"], s["column_depth_mm"]
    out: dict = {"cover": s["clear_cover_mm"] or max(50.0, {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}[s["exposure"]])}
    p = s["p_service_kn"] * (1 + s["self_weight_pct"] / 100)
    if s["length_mm"] is None:
        if s["m_l_service_knm"] == 0 and s["m_b_service_knm"] == 0:
            area = p / s["sbc_kn_m2"] * 1e6
            # (dc + 2a)(bc + 2a) = area
            a = (-(bc + dc) + math.sqrt((bc + dc) ** 2 - 4 * (bc * dc - area))) / 4
            out["L"] = math.ceil((dc + 2 * a) / 50 - 1e-9) * 50
            out["B"] = math.ceil((bc + 2 * a) / 50 - 1e-9) * 50
            # the engine steps the projection by 25 mm: its plan may differ by a step; confirm it is no smaller
            L, B = d["L"], d["B"]
        else:
            L, B = d["L"], d["B"]
    else:
        L, B = s["length_mm"], s["width_mm"]
    Lm, Bm = L / 1000, B / 1000
    var = 6 * s["m_l_service_knm"] / (Bm * Lm * Lm) + 6 * s["m_b_service_knm"] / (Lm * Bm * Bm)
    out["q_max"], out["q_min"] = p / (Lm * Bm) + var, p / (Lm * Bm) - var
    f = s["load_factor"]
    qu = f * s["p_service_kn"] / (Lm * Bm) + f * var
    out["qu"] = qu
    D, dia, c = d["D"], d["dia"], out["cover"]
    dl, db = D - c - dia / 2, D - c - 1.5 * dia
    al, ab = (L - dc) / 2, (B - bc) / 2
    out["m_l"] = qu * Bm * (al / 1000) ** 2 / 2
    out["m_b"] = qu * Lm * (ab / 1000) ** 2 / 2
    out["as_flex_l"] = steel(out["m_l"], B, dl, fck, fy)
    out["as_flex_b"] = steel(out["m_b"], L, db, fck, fy)
    rmin = 0.0015 if fy <= 250 else 0.0012
    out["as_l"] = max(out["as_flex_l"], rmin * B * D)
    out["as_b"] = max(out["as_flex_b"], rmin * L * D)
    out["v1_l"] = qu * Bm * max(al - dl, 0) / 1000
    out["v1_b"] = qu * Lm * max(ab - db, 0) / 1000
    out["tau1_l"] = out["v1_l"] * 1e3 / (B * dl)
    out["tau1_b"] = out["v1_b"] * 1e3 / (L * db)
    out["tc_l"] = tau_c(fck, 100 * d["as_prov_l"] / (B * dl))
    out["tc_b"] = tau_c(fck, 100 * d["as_prov_b"] / (L * db))
    da = (dl + db) / 2
    out["b0"] = 2 * ((bc + da) + (dc + da))
    out["vp"] = qu * (Lm * Bm - (bc + da) * (dc + da) / 1e6)
    out["tau_p"] = out["vp"] * 1e3 / (out["b0"] * da)
    out["ks"] = min(0.5 + min(bc, dc) / max(bc, dc), 1.0)
    out["tau_p_allow"] = out["ks"] * 0.25 * math.sqrt(fck)
    tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[min(int(fck), 40)] * (1.6 if fy >= 415 else 1.0)
    out["ld"] = dia * 0.87 * fy / (4 * tbd)
    out["bearing"] = f * s["p_service_kn"] * 1e3 / (bc * dc)
    # Cl. 34.4: the similar area grows by 2 D on each side at most (frustum at 1 in 2), so sqrt(A1/A2) is that scale
    a1_l, a1_b = min(L, dc + 4 * D), min(B, bc + 4 * D)
    out["bearing_allow"] = 0.45 * fck * min(a1_l / dc, a1_b / bc, 2.0)  # similar to the column: the smaller scale governs
    return out


TOL = {"as_flex_l": 3e-3, "as_flex_b": 3e-3, "as_l": 3e-3, "as_b": 3e-3, "tc_l": 0.03, "tc_b": 0.03}


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    d = res["data"]
    h = hand(s, d)
    bad, n = [], 0
    for key, hv in h.items():
        if key in ("L", "B") and s["length_mm"] is None:
            continue  # checked separately against the quadratic
        n += 1
        tol = TOL.get(key, 1e-4)
        if abs(d[key] - hv) > tol * max(abs(hv), 1e-9) + 1e-6:
            bad.append(f"{name}: {key} engine {d[key]} hand {hv:.6g}")
    # the engine's result must satisfy the hand checks
    if h["q_max"] > s["sbc_kn_m2"] + 1e-6 or h["q_min"] < -1e-6:
        bad.append(f"{name}: hand pressures {h['q_max']:.1f} / {h['q_min']:.1f} outside the limits")
    if d["as_prov_l"] < h["as_l"] * (1 - 3e-3) or d["as_prov_b"] < h["as_b"] * (1 - 3e-3):
        bad.append(f"{name}: steel provided below the hand requirement")
    if not s.get("depth_mm"):
        if h["tau1_l"] > h["tc_l"] * 1.03 or h["tau1_b"] > h["tc_b"] * 1.03 or h["tau_p"] > h["tau_p_allow"] + 1e-9:
            bad.append(f"{name}: a hand shear check fails for the depth the engine chose")
        avail = min((d["L"] - s["column_depth_mm"]) / 2, (d["B"] - s["column_width_mm"]) / 2) - h["cover"]
        if d["bent_ends"]:
            # Cl. 26.2.2.1(b): a 90 degree bend is worth 8 diameters, the straight part stopping where the bend starts;
            # bends are used only when straight bars cannot develop
            r_b = (2 if s["fy"] <= 250 else 4) * d["dia"]
            if not (avail < h["ld"] <= avail - (r_b + d["dia"]) + 8 * d["dia"] + 1e-9):
                bad.append(f"{name}: bent ends reported but L_d {h['ld']:.0f} against straight {avail:.0f}")
        elif h["ld"] > avail + 1e-9:
            bad.append(f"{name}: development length {h['ld']:.0f} does not fit the projection")
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = FootingInput().model_dump()
    if defaults != BASE:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)} }")
    base = design_footing(FootingInput(**BASE))
    for key, want in BASE_EXPECTED.items():
        if abs(base["data"][key] - want) > 1e-6 * max(1, abs(want)):
            bad.append(f"base: {key} engine {base['data'][key]} expected {want}")
    h = hand(BASE, base["data"])
    if (h["L"], h["B"]) != (base["data"]["L"], base["data"]["B"]):
        bad.append(f"base: plan by the quadratic {h['L']} x {h['B']}, engine {base['data']['L']} x {base['data']['B']}")
    n_base, b0 = compare("base", BASE, base)
    bad += b0
    if base["status"] != "ok":
        bad.append("base: engine reports Not OK")
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_footing(FootingInput(**s))
        if res["status"] == "stopped":
            bad.append(f"{name}: stopped unexpectedly: {res['stop_message']}")
            continue
        n, b1 = compare(name, s, res)
        n_cases += n
        bad += b1
        if res["status"] != "ok":
            failed = [i["title"] for sec in res["sheet"]["sections"] for i in sec["items"] if i["kind"] == "check" and not i["ok"]]
            bad.append(f"{name}: engine reports Not OK: {failed}")
    n_enlarged = 0
    for name, ov in ENLARGED:
        s = dict(BASE, **ov)
        res = design_footing(FootingInput(**s))
        if res["status"] != "ok":
            bad.append(f"{name}: engine reports {res['status']}")
            continue
        n, b1 = compare(name, s, res)
        n_cases += n
        bad += b1
        d = res["data"]
        fck, fy = float(s["fck"]), float(s["fy"])
        tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[int(fck)] * (1.6 if fy >= 415 else 1.0)
        ld10 = 10 * 0.87 * fy / (4 * tbd)
        area = s["p_service_kn"] * (1 + s["self_weight_pct"] / 100) / s["sbc_kn_m2"] * 1e6
        bc, dc = s["column_width_mm"], s["column_depth_mm"]
        a_bearing = (-(bc + dc) + math.sqrt((bc + dc) ** 2 - 4 * (bc * dc - area))) / 4
        a_engine = min((d["L"] - dc) / 2, (d["B"] - bc) / 2)
        if a_engine <= a_bearing:
            bad.append(f"{name}: the plan was not enlarged ({d['L']} x {d['B']})")
        # compare() has confirmed that the chosen bar develops at the engine's plan
        a_less = a_engine - 25  # 50 mm less on L and B
        bent10 = a_less - 50 - ((2 if s["fy"] <= 250 else 4) * 10 + 10) + 80  # cover 50 (mild), straight to the bend, plus 8 phi
        if bent10 >= ld10:
            bad.append(f"{name}: T10 would already develop with 50 mm less ({bent10:.0f} >= {ld10:.0f}): plan not the least")
        n_enlarged += 1
    for name, ov, want in STOPS:
        res = design_footing(FootingInput(**dict(BASE, **ov)))
        if res["status"] != "stopped" or not (res["stop_message"] or "").startswith(want):
            bad.append(f"stop '{name}': got {res['status']} / {res['stop_message']}")
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n_base + len(BASE_EXPECTED) + 1} results agree with the independent hand check; "
          f"{n_cases} values of {len(CASES) + n_enlarged} alternative-input cases (including {n_enlarged} enlarged plans) "
          f"and {len(STOPS)} stop states correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
