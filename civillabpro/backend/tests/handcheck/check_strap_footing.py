#!/usr/bin/env python3
"""Independent hand check of the strap footing engine.

From the clauses of IS 456:2000, by a different route where one exists:

  * reactions: R_2 = P_2 - P_1 e / (s - e) by moments about pad 1's centre, then R_1 = P_1 + P_2 - R_2 (engine: R_1 by moments about
    column 2);
  * the strap: column 1 a point load at its centre, the greatest hogging where the shear is nil in closed form, x_0 = P_u1 / w
    (engine: the load spread over the column and a bisection); outside the column the two must agree;
  * steel areas by bisection of the stress block (engine: Annex G closed form); tau_c by the SP 16 formula (engine: Table 19);
  * stirrup spacings from Cl. 40.4(a) and 26.5.1.6 recomputed;
  * pad 2 by the isolated footing's own hand check (check_footing.py), written independently of the isolated footing engine;
  * pad 1, bearing and development recomputed line by line.

Run:  python tests/handcheck/check_strap_footing.py
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from app.modules.structural.domain.strap_footing import StrapFootingInput, design_strap_footing  # noqa: E402

_spec = importlib.util.spec_from_file_location("check_footing", HERE / "check_footing.py")
iso = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(iso)  # type: ignore[union-attr]

BASE = dict(
    mark="SF1", column1_width_mm=400, column1_depth_mm=400, p1_service_kn=800, column2_width_mm=450, column2_depth_mm=450, p2_service_kn=1200,
    spacing_mm=4500, left_end_mm=None, load_factor=1.5, self_weight_pct=10, sbc_kn_m2=200, pad1_length_mm=None, pad1_width_mm=None,
    pad1_depth_mm=None, pad2_length_mm=None, pad2_width_mm=None, pad2_depth_mm=None, strap_width_mm=None, strap_depth_mm=None, fck=25, fy=415,
    exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20, bar_dia_mm=None,
)

# By hand: with L_1 = 1600, e = 800 - 200 = 600 mm; R_2 = 1200 - 800 x 600 / 3900 = 1076.9 kN, R_1 = 923.1 kN; A_1 = 923.1 x 1.1 / 200 =
# 5.077 m2, B_1 = 3.173 m, 3200 mm = 2 L_1 (1550 would need 3300 > 3100). w = 1.5 x 923.1 / 1.6 = 865.4 kN/m; x_0 = 1200 / 865.4 = 1.387 m;
# M = 865.4 x 1.387^2 / 2 - 1200 x (1.387 - 0.2) = -592.0 kN m.
BASE_EXPECTED = {"L1": 1600.0, "B1": 3200.0, "R1": 800 * 4500 / 3900, "m_hog": 592.0}

CASES: list[tuple[str, dict]] = [
    ("column 1 set back from the line, sagging under it", dict(left_end_mm=450)),
    ("given pad 1", dict(pad1_length_mm=1800, pad1_width_mm=2900)),
    ("given strap", dict(strap_width_mm=450, strap_depth_mm=900)),
    ("Fe500 M30", dict(fy=500, fck=30)),
    ("weak soil", dict(sbc_kn_m2=120)),
    ("strong soil", dict(sbc_kn_m2=400)),
    ("heavy columns", dict(p1_service_kn=1500, p2_service_kn=2200, column1_width_mm=500, column1_depth_mm=500, column2_width_mm=550,
                           column2_depth_mm=550, sbc_kn_m2=250)),
    ("long spacing", dict(spacing_mm=7000)),
    ("short spacing", dict(spacing_mm=3200, p1_service_kn=600)),
    ("mild steel M20", dict(fy=250, fck=20, exposure="mild")),
    ("pads in T16", dict(bar_dia_mm=16)),
    ("severe exposure", dict(exposure="severe", fck=30)),
    ("oblong columns", dict(column1_width_mm=300, column1_depth_mm=600, column2_width_mm=600, column2_depth_mm=300)),
    ("strap widened beyond column 1", dict(column1_width_mm=300, column1_depth_mm=300, p1_service_kn=1600, p2_service_kn=1800, sbc_kn_m2=100,
                                           spacing_mm=6000)),
]

STOPS: list[tuple[str, dict, str]] = [
    ("light interior column", dict(p1_service_kn=1500, p2_service_kn=250), "Column 2 is too light"),
    ("pads meet", dict(spacing_mm=3000, p1_service_kn=400, p2_service_kn=3500, sbc_kn_m2=150), "The two pads would meet"),
    ("spacing too short for pad 1", dict(spacing_mm=1800, p2_service_kn=2500), "No pad under column 1"),
    ("thin entered strap", dict(strap_depth_mm=300), "The strap depth entered is too shallow"),
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


def l_d(dia: float, fck: float, fy: float) -> float:
    tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[min(int(fck), 40)] * (1.6 if fy >= 415 else 1.0)
    return dia * 0.87 * fy / (4 * tbd)


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
    a = s["left_end_mm"] if s["left_end_mm"] is not None else s["column1_depth_mm"] / 2
    sp, P1, P2 = s["spacing_mm"], s["p1_service_kn"], s["p2_service_kn"]
    alpha = 1 + s["self_weight_pct"] / 100
    b_s = d["strap"]["b"]
    if s["strap_width_mm"] is not None:
        same("strap width", b_s, s["strap_width_mm"])
    elif b_s < max(s["column1_width_mm"], 300):
        bad.append(f"{name}: strap {b_s} narrower than column 1 or 300 mm")

    def reactions(L1: float) -> tuple[float, float, float]:
        e = L1 / 2 - a
        r2 = P2 - P1 * e / (sp - e)  # moments about pad 1's centre
        return e, P1 + P2 - r2, r2

    # pad 1's plan
    L1, B1 = d["L1"], d["B1"]
    if s["pad1_length_mm"] is None:
        b_min = max(s["column1_width_mm"], b_s) + 200
        want = None
        Lt = math.ceil((a + s["column1_depth_mm"] / 2 + 100) / 50 - 1e-9) * 50
        while Lt < sp:
            _, r1t, _ = reactions(Lt)
            Bt = max(b_min, math.ceil(r1t * alpha / s["sbc_kn_m2"] * 1e6 / Lt / 50 - 1e-9) * 50)
            if Bt <= 2 * Lt:
                want = (Lt, Bt)
                break
            Lt += 50
        n += 1
        if want != (L1, B1):
            bad.append(f"{name}: pad 1 {L1} x {B1}, by hand {want}")
    e, r1, r2 = reactions(L1)
    same("e", d["e"], e)
    same("R1", d["R1"], r1, 1e-9)
    same("R2", d["R2"], r2, 1e-9)
    q1 = r1 * alpha / (L1 / 1000 * B1 / 1000)
    same("q1", d["q1"], q1)
    if q1 > s["sbc_kn_m2"] + 1e-6:
        bad.append(f"{name}: pad 1 pressure {q1:.1f} above the safe bearing pressure")

    # pad 2 by the isolated footing's hand check
    f2 = dict(iso.BASE, mark=f"{s['mark']} pad 2", column_width_mm=s["column2_width_mm"], column_depth_mm=s["column2_depth_mm"], p_service_kn=r2,
              load_factor=s["load_factor"], self_weight_pct=s["self_weight_pct"], sbc_kn_m2=s["sbc_kn_m2"], length_mm=s["pad2_length_mm"],
              width_mm=s["pad2_width_mm"], depth_mm=s["pad2_depth_mm"], fck=s["fck"], fy=s["fy"], exposure=s["exposure"],
              clear_cover_mm=s["clear_cover_mm"], max_aggregate_mm=s["max_aggregate_mm"], bar_dia_mm=s["bar_dia_mm"])
    n2, bad2 = iso.compare(f"{name}, pad 2", f2, {"data": d["pad2"]})
    n += n2
    bad += bad2
    L2, B2 = d["L2"], d["B2"]
    x2 = a + sp
    same("gap", d["gap"], x2 - L2 / 2 - L1)

    # the strap: column 1 a point load at its centre
    g = s["load_factor"]
    p1u, r1u = g * P1, g * r1
    w = r1u / (L1 / 1000)
    same("w", d["w"], w)
    hi1 = a + s["column1_depth_mm"] / 2
    x0 = p1u / w * 1000  # mm, where w x = P_u1
    st = d["strap"]
    if hi1 < x0 < L1:
        same("x_hog", st["x_hog"], x0, 1e-6)
        m_hog = -(w * (x0 / 1000) ** 2 / 2 - p1u * (x0 - a) / 1000)
    else:
        m_hog = -(w * (L1 / 1000) ** 2 / 2 - p1u * (L1 - a) / 1000)
    same("m_hog", st["m_hog"], m_hog, 1e-7)
    v_face = abs(w * hi1 / 1000 - p1u)
    same("v_face", st["v_face"], v_face, 1e-9)
    b, D, dd, dia = st["b"], st["D"], st["d"], st["dia"]
    same("strap d", dd, D - cover - 12 - dia / 2)
    asf = steel(m_hog, b, dd, fck, fy)
    # the engine's Annex G-1.1(b) formula and the stress block part by up to about 0.5 percent close to M_u,lim, where a strap often is
    same("strap as_flex", st["as_flex"], asf, 6e-3)
    req = max(asf, 0.85 * b * dd / fy)
    same("strap as_req", st["as_req"], req, 6e-3)
    if st["area"] < req * (1 - 3e-3) or st["n"] * math.pi * dia * dia / 4 != st["area"] and abs(st["n"] * math.pi * dia * dia / 4 - st["area"]) > 1e-3:
        bad.append(f"{name}: strap top steel {st['area']:.0f} against {req:.0f}")
    clear = (b - 2 * cover - 24 - st["n"] * dia) / (st["n"] - 1)
    if clear < max(dia, s["max_aggregate_mm"] + 5) - 1e-9:
        bad.append(f"{name}: strap top bars do not fit ({clear:.0f} mm clear)")
    xu = (0.53 if fy <= 250 else 0.48 if fy <= 415 else 0.46) * dd  # Cl. 38.1(f), x_u,max/d (0.46 for Fe 500; Fe 550 lower still)
    if fy <= 500 and 0.36 * fck * b * xu * (dd - 0.42 * xu) / 1e6 < m_hog * (1 - 1e-6):
        bad.append(f"{name}: the strap needs compression steel by hand")
    ld = l_d(dia, fck, fy) * min(asf / st["area"], 1.0)
    same("strap anchorage", st["ld_req"], ld, 6e-3)
    avail = st["x_hog"] - cover
    r_b = (2 if fy <= 250 else 4) * dia
    cap = avail - (r_b + dia) + 8 * dia if st["bent"] else avail
    if ld > cap * (1 + 6e-3):
        bad.append(f"{name}: strap top bars not developed toward the property line")
    if st["x_end"] - cover - x2 < max(dd, 12 * dia) - 1e-6:
        bad.append(f"{name}: strap top bars stop short past column 2")
    tcmax = {20: 2.8, 25: 3.1, 30: 3.5, 35: 3.7, 40: 4.0}[int(fck)]
    if v_face * 1e3 / (b * dd) > tcmax + 1e-9:
        bad.append(f"{name}: tau at the face of column 1 above tau_c,max by hand")
    tc = iso.tau_c(fck, 100 * st["area"] / (b * dd))
    fys = min(fy, 415)
    for z, v in zip(st["zones"], (abs(w * min(hi1 + dd, L1) / 1000 - p1u), abs(r1u - p1u)), strict=True):
        same(f"V {z['name']}", z["v"], v, 1e-9)
        same(f"tau_c {z['name']}", z["tc"], tc, 0.03)
        asv = 2 * math.pi * z["dia"] ** 2 / 4
        s_max = min(0.87 * fys * asv / (0.4 * b), 0.75 * dd, 300)
        same(f"s_max {z['name']}", z["s_max"], s_max)
        vus = max(v * 1e3 - z["tc"] * b * dd, 0)
        s_need = s_max if vus <= 0 else min(0.87 * fys * asv * dd / vus, s_max)
        n += 1
        if z["s"] > s_need + 1e-6 or z["s"] < 100 or z["s"] < s_need - 10 - 1e-6:
            bad.append(f"{name}: stirrups {z['name']} at {z['s']} against {s_need:.1f} by hand")
    if D > 750 and not st["side_per_face"]:
        bad.append(f"{name}: no side-face bars on a strap deeper than 750 mm")
    if D < max(d["pad1"]["D"], d["pad2"]["D"]) - 1e-9:
        bad.append(f"{name}: strap shallower than a pad")

    # pad 1
    p = d["pad1"]
    q = r1u / (L1 / 1000 * B1 / 1000)
    same("pad 1 q", p["q"], q)
    a_t = (B1 - b_s) / 2
    m = q * L1 / 1000 * (a_t / 1000) ** 2 / 2
    same("pad 1 m", p["m"], m)
    same("pad 1 d", p["d"], p["D"] - cover - p["dia"] / 2)
    asf1 = steel(m, L1, p["d"], fck, fy)
    same("pad 1 as_flex", p["as_flex"], asf1, 3e-3)
    rmin = 0.0015 if fy <= 250 else 0.0012
    req1 = max(asf1, rmin * L1 * p["D"])
    same("pad 1 as_req", p["as_req"], req1, 3e-3)
    if p["area"] < req1 * (1 - 3e-3) or p["s"] > min(3 * p["d"], 300) or p["s"] < 100:
        bad.append(f"{name}: pad 1 bars across short of the rules")
    v1 = q * L1 / 1000 * max(a_t - p["d"], 0) / 1000
    same("pad 1 V", p["v"], v1)
    tau1, tc1 = v1 * 1e3 / (L1 * p["d"]), iso.tau_c(fck, 100 * p["area"] / (L1 * p["d"]))
    same("pad 1 tau_c", p["tc"], tc1, 0.03)
    if not s["pad1_depth_mm"] and tau1 > tc1 * 1.03:
        bad.append(f"{name}: pad 1 shear fails by hand")
    ld1 = l_d(p["dia"], fck, fy) * min(asf1 / p["area"], 1.0)
    same("pad 1 anchorage", p["ld_req"], ld1, 3e-3)
    cap1 = a_t - cover - ((2 if fy <= 250 else 4) * p["dia"] + p["dia"]) + 8 * p["dia"] if p["bent"] else a_t - cover
    if ld1 > cap1 * (1 + 3e-3):
        bad.append(f"{name}: pad 1 bars not developed")
    if p["area_along"] < rmin * B1 * p["D"] * (1 - 1e-9):
        bad.append(f"{name}: pad 1 bars along below the minimum")

    # bearing at the columns, each with its whole load
    for i, (bg, bc, dc, pu, ratio) in enumerate(zip(
            d["bearing"], (s["column1_width_mm"], s["column2_width_mm"]), (s["column1_depth_mm"], s["column2_depth_mm"]), (p1u, g * P2),
            (max(min(2 * a / s["column1_depth_mm"], b_s / s["column1_width_mm"], (max(s["column1_width_mm"], s["column1_depth_mm"]) + 4 * D)
                     / max(s["column1_width_mm"], s["column1_depth_mm"]), 2.0), 1.0),
             max(min(L2 / s["column2_depth_mm"], B2 / s["column2_width_mm"], (max(s["column2_width_mm"], s["column2_depth_mm"]) + 4 * d["pad2"]["D"])
                     / max(s["column2_width_mm"], s["column2_depth_mm"]), 2.0), 1.0)), strict=True), start=1):
        same(f"bearing ratio {i}", bg["ratio"], ratio)
        same(f"bearing stress {i}", bg["sigma"], pu * 1e3 / (bc * dc))
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = StrapFootingInput().model_dump()
    if defaults != BASE:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)} }")
    base = design_strap_footing(StrapFootingInput(**BASE))
    n_total = 0
    if base["status"] != "ok":
        bad.append(f"base: engine reports {base['status']} {base['stop_message']}")
    else:
        got = {"L1": base["data"]["L1"], "B1": base["data"]["B1"], "R1": base["data"]["R1"], "m_hog": base["data"]["strap"]["m_hog"]}
        for key, want in BASE_EXPECTED.items():
            n_total += 1
            if abs(got[key] - want) > 1e-3 * max(1, abs(want)):
                bad.append(f"base: {key} engine {got[key]} expected {want}")
        n, b0 = check("base", BASE, base)
        n_total += n
        bad += b0
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_strap_footing(StrapFootingInput(**s))
        if res["status"] == "stopped":
            bad.append(f"{name}: stopped unexpectedly: {res['stop_message']}")
            continue
        if res["status"] != "ok":
            failed = [i["id"] for sec in res["sheet"]["sections"] for i in sec["items"] if i["kind"] == "check" and not i["ok"]]
            if not set(failed) <= {"bearing1", "bearing2"}:
                bad.append(f"{name}: engine reports Not OK: {failed}")
        n, b1 = check(name, s, res)
        n_cases += n
        bad += b1
    for name, ov, want in STOPS:
        res = design_strap_footing(StrapFootingInput(**dict(BASE, **ov)))
        if res["status"] != "stopped" or not (res["stop_message"] or "").startswith(want):
            bad.append(f"stop '{name}': got {res['status']} / {res['stop_message']}")
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n_total} results of the worked example and {n_cases} values of {len(CASES)} alternative-input cases agree with the independent "
          f"hand check; {len(STOPS)} stop states correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
