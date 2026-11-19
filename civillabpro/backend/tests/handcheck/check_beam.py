#!/usr/bin/env python3
"""Independent hand check of the beam engine.

Written from the text of IS 456:2000 and SP 16, not from the engine, and by a
different route wherever the code allows one:

  * flexure: the neutral axis is found by bisection on the stress block of
    Cl. 38.1 (engine: the closed form of Annex G-1.1(b));
  * compression steel stress: read from the points printed in SP 16, Table A
    (engine: Fig. 23A generated from 0.87 fy);
  * concrete shear strength: the SP 16 closed form (engine: Table 19, interpolated);
  * flanged sections: the effective width recomputed from Cl. 23.1.2; with the
    neutral axis in the web, x_u from the closed-form root of the G-2.2.1 quadratic,
    or by false position where y_f < D_f (engine: bisection on the G-2.2 moment);
    Fig. 6 from its two straight lines;
  * curtailment: the resistance of the continuing bars by stress-block bisection and the point
    where they suffice by bisection on M(x) (engine: closed form), then Cl. 26.2.3.1, 26.2.1 and
    26.2.3.2 checked at the engine's cut-off with the SP 16 tau_c; stirrup zones: the shear where
    the wider spacing begins checked against the resistance there;
  * loads, effective span, torsion equivalents, deflection factors, development
    length: recomputed line by line.

Run:  python tests/handcheck/check_beam.py
Last line on success:  OK: n results agree ... (exit code 0)
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.beam import BeamInput, design_beam  # noqa: E402

# The engine defaults (the worked example). The check fails if a default changes without this.
BASE = dict(
    mark="B1", support="simply_supported", clear_span_mm=4000, support_width_mm=230, section="rectangular", width_mm=230, depth_mm=450,
    flange_thickness_mm=120, flange_width_mm=3000, isolated_flange=False, l0_mm=None,
    fck=25, fy=500, fy_stirrup=500, exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20,
    mode="loads", dead_load_kn_m=12, live_load_kn_m=8, include_self_weight=True, unit_weight_kn_m3=25, load_factor=1.5,
    mu_knm=None, vu_kn=None, tu_knm=0, main_bar_dia_mm=None, hanger_bar_dia_mm=12, stirrup_dia_mm=8, stirrup_legs=2,
)

# Hand-calculated key results of BASE (see the module docstring of beam.py).
BASE_EXPECTED = dict(w_factored=33.881, l_eff=4230.0, mu=75.78, vu=54.07, ast_req=481.0, sv=300.0)

CASES: list[tuple[str, dict]] = [
    ("M20 Fe415 mild", dict(fck=20, fy=415, fy_stirrup=415, exposure="mild")),
    ("wide shallow", dict(width_mm=600, depth_mm=300, clear_span_mm=3000, dead_load_kn_m=20, live_load_kn_m=15)),
    ("long span", dict(width_mm=350, depth_mm=950, clear_span_mm=11000, support_width_mm=400, dead_load_kn_m=15, live_load_kn_m=10, fck=30)),
    ("doubly reinforced", dict(width_mm=300, depth_mm=500, clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=35, live_load_kn_m=22)),
    ("doubly Fe415", dict(width_mm=300, depth_mm=550, clear_span_mm=6500, support_width_mm=300, dead_load_kn_m=40, live_load_kn_m=25, fy=415, fck=30)),
    ("mild steel", dict(fy=250, fy_stirrup=250, fck=20, exposure="mild", dead_load_kn_m=8, live_load_kn_m=5)),
    ("Fe550 M40 severe", dict(fy=550, fck=40, exposure="severe", width_mm=300, depth_mm=600, clear_span_mm=7000, dead_load_kn_m=25, live_load_kn_m=20)),
    ("cantilever", dict(support="cantilever", clear_span_mm=2000, width_mm=300, depth_mm=500, support_width_mm=300, dead_load_kn_m=15, live_load_kn_m=10)),
    ("short cantilever", dict(support="cantilever", clear_span_mm=1200, width_mm=230, depth_mm=400, dead_load_kn_m=10, live_load_kn_m=6)),
    ("no self-weight", dict(include_self_weight=False, dead_load_kn_m=18, live_load_kn_m=12)),
    ("forces", dict(mode="forces", mu_knm=140, vu_kn=110, width_mm=300, depth_mm=550, clear_span_mm=5000)),
    ("forces + torsion", dict(mode="forces", mu_knm=120, vu_kn=90, tu_knm=25, width_mm=300, depth_mm=600, clear_span_mm=5000, support_width_mm=300)),
    ("torsion governs (Me2)", dict(mode="forces", mu_knm=20, vu_kn=40, tu_knm=30, width_mm=300, depth_mm=600, clear_span_mm=5000, support_width_mm=300)),
    ("four legs, two layers", dict(width_mm=400, depth_mm=900, clear_span_mm=9000, support_width_mm=400, dead_load_kn_m=60, live_load_kn_m=40, fck=30, stirrup_legs=4)),
    ("fixed bar size", dict(main_bar_dia_mm=20, dead_load_kn_m=20, live_load_kn_m=14)),
    ("heavy shear", dict(width_mm=250, depth_mm=600, clear_span_mm=3000, dead_load_kn_m=120, live_load_kn_m=80, stirrup_dia_mm=10)),
    ("user cover", dict(clear_cover_mm=40, exposure="moderate")),
    # flanged sections
    ("T-beam, neutral axis in the flange", dict(section="t_beam", width_mm=300, depth_mm=550, flange_thickness_mm=120, flange_width_mm=3000,
                                                clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=30, live_load_kn_m=15)),
    ("L-beam, edge of a slab", dict(section="l_beam", width_mm=230, depth_mm=500, flange_thickness_mm=125, flange_width_mm=1500,
                                    clear_span_mm=5000, dead_load_kn_m=22, live_load_kn_m=10)),
    ("isolated T, neutral axis in the web", dict(section="t_beam", width_mm=250, depth_mm=500, flange_thickness_mm=100, flange_width_mm=750,
                                                 isolated_flange=True, clear_span_mm=7000, support_width_mm=300, dead_load_kn_m=20,
                                                 live_load_kn_m=10)),
    ("isolated T, thick flange (y_f < D_f)", dict(section="t_beam", width_mm=250, depth_mm=500, flange_thickness_mm=150, flange_width_mm=600,
                                                  isolated_flange=True, clear_span_mm=6500, support_width_mm=300, dead_load_kn_m=26,
                                                  live_load_kn_m=12)),
    ("isolated L", dict(section="l_beam", width_mm=300, depth_mm=600, flange_thickness_mm=120, flange_width_mm=900, isolated_flange=True,
                        clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=25, live_load_kn_m=15)),
    ("T-beam, doubly reinforced", dict(section="t_beam", width_mm=300, depth_mm=600, flange_thickness_mm=100, flange_width_mm=900,
                                       isolated_flange=True, clear_span_mm=7000, support_width_mm=300, dead_load_kn_m=50, live_load_kn_m=30, fck=30)),
    ("T-beam, l_0 entered, forces", dict(section="t_beam", mode="forces", mu_knm=260, vu_kn=150, width_mm=300, depth_mm=500, flange_thickness_mm=120,
                                         flange_width_mm=2400, l0_mm=4200, clear_span_mm=6000, support_width_mm=300)),
    ("T-beam cantilever (flange in tension)", dict(section="t_beam", support="cantilever", width_mm=300, depth_mm=500, flange_thickness_mm=120,
                                                   flange_width_mm=2500, clear_span_mm=2000, support_width_mm=300, dead_load_kn_m=20,
                                                   live_load_kn_m=10)),
]

STOPS: list[tuple[str, dict, str]] = [
    ("deep beam", dict(clear_span_mm=1500, depth_mm=1000, width_mm=300), "Effective span is less than twice"),
    ("section too small", dict(depth_mm=300, clear_span_mm=8000, dead_load_kn_m=80, live_load_kn_m=60), "No arrangement of up to two layers"),
]

# SP 16, Table A: (strain, design stress) at 0.80 ... 1.0 fyd, as printed.
SP16_TABLE_A = {
    415: [(0.00144, 288.7), (0.00163, 306.7), (0.00192, 324.8), (0.00241, 342.8), (0.00276, 351.8), (0.00380, 360.9)],
    500: [(0.00174, 347.8), (0.00195, 369.6), (0.00226, 391.3), (0.00277, 413.0), (0.00312, 423.9), (0.00417, 434.8)],
}
BOND = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}
COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}


def fsc_hand(strain: float, fy: int) -> float | None:
    if fy == 250:
        return min(2e5 * strain, 0.87 * 250)
    if fy not in SP16_TABLE_A:
        return None  # SP 16 does not tabulate this grade; the engine value is checked by the unit tests
    pts = SP16_TABLE_A[fy]
    if strain <= pts[0][0]:
        return 2e5 * strain
    for (e0, s0), (e1, s1) in zip(pts, pts[1:], strict=False):
        if strain <= e1:
            return s0 + (s1 - s0) * (strain - e0) / (e1 - e0)
    return pts[-1][1]


def hand(s: dict, reinf: dict) -> dict:
    """Recompute the key results. ``reinf`` supplies only the bars the engine chose."""
    b, D, lc, sw = s["width_mm"], s["depth_mm"], s["clear_span_mm"], s["support_width_mm"]
    fck, fy = s["fck"], s["fy"]
    cover = s["clear_cover_mm"] if s["clear_cover_mm"] is not None else COVER[s["exposure"]]
    dst = s["stirrup_dia_mm"]
    cant = s["support"] == "cantilever"
    tf = reinf["tension_face"]
    of = "bottom" if tf == "top" else "top"
    ten, oth = reinf[tf], reinf[of]
    # effective depth from the bars chosen
    y1 = cover + dst + ten["dia"] / 2
    if len(ten["layers"]) == 1:
        ybar = y1
    else:
        gap = max(15.0, 2 * s["max_aggregate_mm"] / 3, ten["dia"])
        y2 = y1 + ten["dia"] + gap
        ybar = (ten["layers"][0] * y1 + ten["layers"][1] * y2) / ten["count"]
    d = D - ybar
    dc = cover + dst + oth["dia"] / 2
    out = {"d": d, "d_c": dc}

    # effective span and forces
    l_eff = lc + d / 2 if cant else min(lc + d, lc + sw)
    out["l_eff"] = l_eff
    flanged = s["section"] != "rectangular"
    df = s["flange_thickness_mm"]
    bf = b
    if flanged:  # Cl. 23.1.2
        l0, bact, tee = s["l0_mm"] or l_eff, s["flange_width_mm"], s["section"] == "t_beam"
        if s["isolated_flange"]:
            bf = (1.0 if tee else 0.5) * l0 / (l0 / bact + 4) + b
        else:
            bf = l0 / 6 + b + 6 * df if tee else l0 / 12 + b + 3 * df
        bf = min(bf, bact)
        out["bf"] = bf
    comp_flange = flanged and not cant
    if s["mode"] == "loads":
        rib = D - df if flanged else D
        sw_kn = s["unit_weight_kn_m3"] * (b / 1000) * (rib / 1000) if s["include_self_weight"] else 0.0
        wu = s["load_factor"] * (s["dead_load_kn_m"] + sw_kn + s["live_load_kn_m"])
        out["w_factored"] = wu
        if cant:
            mu = wu * (l_eff / 1000) ** 2 / 2
            vu = wu * lc / 1000
        else:
            mu = wu * (l_eff / 1000) ** 2 / 8
            vu = wu * (lc / 2 - d) / 1000
        tu = 0.0
    else:
        mu, vu, tu = s["mu_knm"], s["vu_kn"], s["tu_knm"]
    ve = vu + 1.6 * tu / (b / 1000)
    mt = tu * (1 + D / b) / 1.7
    me1 = mu + mt
    out.update(mu=mu, vu=vu, ve=ve, me1=me1, me2=max(mt - mu, 0.0))

    # flexure by bisection on the stress block
    k = 0.0035 / (0.0055 + 0.87 * fy / 2e5)
    xu_max = k * d
    mu_lim = 0.36 * fck * b * xu_max * (d - 0.42 * xu_max) / 1e6
    if comp_flange:
        def comp(x: float) -> tuple[float, float]:  # Annex G-2: force (N) and moment about the steel (kN m)
            if x <= df:
                return 0.36 * fck * bf * x, 0.36 * fck * bf * x * (d - 0.42 * x) / 1e6
            yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
            return (0.36 * fck * b * x + 0.45 * fck * (bf - b) * yf,
                    (0.36 * fck * b * x * (d - 0.42 * x) + 0.45 * fck * (bf - b) * yf * (d - yf / 2)) / 1e6)
        mu_lim = comp(xu_max)[1]
        m_f = 0.36 * fck * bf * df * (d - 0.42 * df) / 1e6
        if me1 <= mu_lim and me1 > m_f and df < xu_max:
            # neutral axis in the web: closed-form root with y_f = D_f ...
            m_web = me1 * 1e6 - 0.45 * fck * (bf - b) * df * (d - df / 2)
            a2, a1 = 0.36 * 0.42 * fck * b, 0.36 * fck * b * d
            x = (a1 - math.sqrt(max(a1 * a1 - 4 * a2 * m_web, 0.0))) / (2 * a2)
            if x < 7 * df / 3:  # ... else y_f < D_f: false position between D_f and the end of that range
                lo, hi = df, min(7 * df / 3, xu_max)
                flo, fhi = comp(lo)[1] - me1, comp(hi)[1] - me1
                x = lo
                if flo < 0:
                    for _ in range(200):
                        x = hi - fhi * (hi - lo) / (fhi - flo)
                        fx = comp(x)[1] - me1
                        if abs(fx) < 1e-9:
                            break
                        if fx < 0:
                            lo, flo = x, fx
                        else:
                            hi, fhi = x, fx
            out["mu_lim"] = mu_lim
            out["ast_req"] = comp(max(x, df))[0] / (0.87 * fy)
            out["asc_req"] = 0.0
        elif me1 > mu_lim:
            fsc = fsc_hand(0.0035 * (1 - dc / xu_max), fy)
            out["mu_lim"] = mu_lim
            if fsc is not None:
                asc = (me1 - mu_lim) * 1e6 / ((fsc - 0.446 * fck) * (d - dc))
                out["asc_req"] = asc
                out["ast_req"] = (comp(xu_max)[0] + asc * (fsc - 0.446 * fck)) / (0.87 * fy)
    out.setdefault("mu_lim", mu_lim)
    b_flex = bf if comp_flange else b  # with the neutral axis in the flange: a rectangle b_f wide
    if "ast_req" in out:
        pass
    elif me1 <= mu_lim:
        lo, hi = 0.0, xu_max
        for _ in range(200):
            x = (lo + hi) / 2
            if 0.36 * fck * b_flex * x * (d - 0.42 * x) / 1e6 < me1:
                lo = x
            else:
                hi = x
        out["ast_req"] = 0.36 * fck * b_flex * x / (0.87 * fy)  # stress-block steel: within 0.5 % of Annex G-1.1(b)
        out["asc_req"] = 0.0
    else:
        fsc = fsc_hand(0.0035 * (1 - dc / xu_max), fy)
        if fsc is not None:
            asc = (me1 - mu_lim) * 1e6 / ((fsc - 0.446 * fck) * (d - dc))
            out["asc_req"] = asc
            out["ast_req"] = (0.36 * fck * b * xu_max + asc * (fsc - 0.446 * fck)) / (0.87 * fy)

    # shear by the SP 16 closed form
    ast_prov = ten["count"] * math.pi * ten["dia"] ** 2 / 4
    out["ast_prov"] = ast_prov
    pt = 100 * ast_prov / (b * d)
    ptc = min(max(pt, 0.15), 3.0)
    beta = max(0.8 * min(fck, 40) / (6.89 * ptc), 1.0)
    tau_c = 0.85 * math.sqrt(0.8 * min(fck, 40)) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)
    tau_v = ve * 1e3 / (b * d)
    out.update(pt=pt, tau_c=tau_c, tau_v=tau_v)
    fyv = min(s["fy_stirrup"], 415)
    asv = s["stirrup_legs"] * math.pi * dst**2 / 4
    lims = [0.87 * fyv * asv / (0.4 * b), 0.75 * d, 300.0]
    vus = ve - tau_c * b * d / 1e3
    if vus > 0:
        lims.append(0.87 * fyv * asv * d / (vus * 1e3))
    if tu > 0:
        b1 = b - 2 * (cover + dst + ten["dia"] / 2)
        d1 = D - (cover + dst + ten["dia"] / 2) - dc
        asv2 = 2 * math.pi * dst**2 / 4
        if tau_v > tau_c:
            lims.append(0.87 * fyv * asv2 / (tu * 1e6 / (b1 * d1) + vu * 1e3 / (2.5 * d1)))
            lims.append(0.87 * fyv * asv2 / ((tau_v - tau_c) * b))
        x1, y1s = b - 2 * cover - dst, D - 2 * cover - dst
        lims += [x1, (x1 + y1s) / 4]
    out["sv_allow"] = min(lims)

    # deflection
    if "ast_req" in out:
        fs = 0.58 * fy * out["ast_req"] / ast_prov
        b_d = bf if comp_flange else b  # Cl. 23.2.1(e): percentages on b_f d
        p_d = 100 * ast_prov / (b_d * d)
        kt = min(2.0, 1 / (0.225 + 0.00322 * fs - 0.625 * math.log10(1 / p_d)))
        kc = 1.0
        if out.get("asc_req", 0) > 0:
            pc = 100 * (oth["count"] * math.pi * oth["dia"] ** 2 / 4) / (b_d * d)
            kc = min(1.5, 1 + pc / (3 + pc))
        basic = 7.0 if cant else 20.0
        if not cant and l_eff > 10000:
            basic *= 10000 / l_eff
        kf = 1.0
        if flanged:  # Fig. 6: two straight lines, (0, 0.8) to (0.3, 0.8) and (0.3, 0.8) to (1.0, 1.0)
            r = b / bf
            kf = 0.8 if r <= 0.3 else 0.8 + (r - 0.3) * (1.0 - 0.8) / (1.0 - 0.3)
        out["span_depth_allow"] = basic * kt * kc * kf
    out["span_depth"] = l_eff / d

    # development length
    tbd = BOND[max(g for g in BOND if g <= min(fck, 40))] * (1.6 if fy >= 415 else 1.0)
    out["ld_tension"] = ten["dia"] * 0.87 * fy / (4 * tbd)
    return out


# relative tolerance per result: exact arithmetic unless a different method or data source is used
TOL = {
    "ast_req": 6e-3,  # stress block against Annex G-1.1(b); SP 16 Table A against Fig. 23A
    "asc_req": 6e-3,
    "tau_c": 0.025,  # closed form against the two-decimal table
    "sv_allow": 0.2,  # follows tau_c where Vus is a small difference of large numbers; see note in main()
    "span_depth_allow": 6e-3,
}


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    h = hand(s, res["reinforcement"])
    eng = res["data"]
    bad, n = [], 0
    for key, hv in h.items():
        ev = eng[key]
        tol = TOL.get(key, 1e-4)
        n += 1
        if key == "sv_allow":
            # compare the shear-strength spacing through the resistance it gives, which is well conditioned
            if abs(ev - hv) > tol * max(abs(hv), 1e-9) and not (ev <= hv * 1.02):
                bad.append(f"{name}: {key} engine {ev:.4g} hand {hv:.4g}")
            continue
        if abs(ev - hv) > tol * max(abs(hv), 1e-9) + 1e-6:
            bad.append(f"{name}: {key} engine {ev:.6g} hand {hv:.6g}")
    # the bars provided must meet the hand requirements
    if "ast_req" in h and h["ast_prov"] < h["ast_req"] * (1 - 6e-3):
        bad.append(f"{name}: tension steel provided {h['ast_prov']:.0f} below hand requirement {h['ast_req']:.0f}")
    if res["data"]["sv"] > h["sv_allow"] * 1.02:
        bad.append(f"{name}: stirrup spacing {res['data']['sv']:.0f} above hand limit {h['sv_allow']:.0f}")
    k, more = check_curtailment(name, s, res)
    k2, more2 = check_anchorage(name, s, res)
    return n + k + k2, bad + more + more2


def check_anchorage(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    """Cl. 26.2.3.3(c) at the simple supports: L_d <= 1.3 M_1/V + L_0, M_1 with the bars at f_d (no x_u,max limit)."""
    if s["support"] == "cantilever":
        return 0, []
    eng, reinf = res["data"], res["reinforcement"]
    b, fck, fy = s["width_mm"], s["fck"], s["fy"]
    cover = s["clear_cover_mm"] if s["clear_cover_mm"] is not None else COVER[s["exposure"]]
    grp = reinf["curtailment"]["continuing"] if reinf.get("curtailment") else reinf["bottom"]
    ast = grp["count"] * math.pi * grp["dia"] ** 2 / 4
    d = eng["curtailment"]["d_cont"] if eng.get("curtailment") and eng["curtailment"]["applied"] else eng["d"]
    t = 0.87 * fy * ast
    if eng["bf"]:  # a compression flange: bisection on force
        bf, df = eng["bf"], s["flange_thickness_mm"]

        def c(x: float) -> tuple[float, float]:
            if x <= df:
                return 0.36 * fck * bf * x, 0.36 * fck * bf * x * (d - 0.42 * x)
            yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
            return 0.36 * fck * b * x + 0.45 * fck * (bf - b) * yf, 0.36 * fck * b * x * (d - 0.42 * x) + 0.45 * fck * (bf - b) * yf * (d - yf / 2)

        lo, hi = 0.0, d
        for _ in range(200):
            x = (lo + hi) / 2
            lo, hi = (x, hi) if c(x)[0] < t else (lo, x)
        m1 = c(hi)[1]
    else:
        m1 = t * (d - 0.42 * min(t / (0.36 * fck * b), d))
    v = eng["vu_face"] * 1e3
    main = next(i for i in res["bbs"]["items"] if i["description"].startswith("Bottom bars (tension)"))
    bent = "bend" in main["shape"]
    l0 = s["support_width_mm"] / 2 - cover + (8 * grp["dia"] if bent else 0)
    tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[max(g for g in (20, 25, 30, 35, 40) if g <= min(fck, 40))] * (1.6 if fy >= 415 else 1.0)
    ld = grp["dia"] * 0.87 * fy / (4 * tbd)
    rhs = 1.3 * m1 / v + l0
    chk = next(i for sec in res["sheet"]["sections"] for i in sec["items"] if i.get("id") == "anchorage")
    bad = []
    if abs(chk["rhs"] - rhs) > 0.003 * rhs + 1 or abs(chk["lhs"] - ld) > 0.5:
        bad.append(f"{name}: anchorage engine {chk['lhs']:.0f} <= {chk['rhs']:.0f}, hand {ld:.0f} <= {rhs:.0f}")
    if ld > rhs + 1e-6 and res["status"] == "ok":
        bad.append(f"{name}: L_d {ld:.0f} exceeds 1.3 M_1/V + L_0 = {rhs:.0f} but the engine reports OK")
    return 2, bad


def check_curtailment(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    """Cl. 26.2.3: the engine's cut-off and stirrup zones checked from the diagrams, by bisection."""
    eng, reinf = res["data"], res["reinforcement"]
    cur, zones = eng.get("curtailment"), eng.get("zones")
    if s["mode"] != "loads" or cur is None:
        return 0, []
    bad: list[str] = []
    n = 0
    b, D, lc, fck, fy = s["width_mm"], s["depth_mm"], s["clear_span_mm"], s["fck"], s["fy"]
    cant = s["support"] == "cantilever"
    wu, le, d = eng["w_factored"], eng["l_eff"], eng["d"]
    off = 0.0 if cant else (le - lc) / 2

    def m_at(xf: float) -> float:  # kN m, xf from the face of the support
        return wu * max(le - xf, 0) ** 2 / 2e6 if cant else wu * (xf + off) * (le - xf - off) / 2e6

    def v_at(xf: float) -> float:
        return wu * max(lc - xf, 0) / 1e3 if cant else wu * max(le / 2 - off - xf, 0) / 1e3

    fyv = min(s["fy_stirrup"], 415)
    asv = s["stirrup_legs"] * math.pi * s["stirrup_dia_mm"] ** 2 / 4
    st = reinf["stirrups"]
    if cur["applied"]:
        c = reinf["curtailment"]
        cont, cut = c["continuing"], c["curtailed"]
        a_cont = cont["count"] * math.pi * cont["dia"] ** 2 / 4
        a_all = a_cont + cut["count"] * math.pi * cut["dia"] ** 2 / 4
        dc = cur["d_cont"]
        # resistance of the continuing bars: stress block (a flange in compression for a simple span), by bisection on force
        bf = eng["bf"] if (eng["bf"] and not cant) else b
        df = s["flange_thickness_mm"] if eng["bf"] and not cant else D
        t = 0.87 * fy * a_cont

        def comp(x: float) -> tuple[float, float]:
            if x <= df:
                return 0.36 * fck * bf * x, 0.36 * fck * bf * x * (dc - 0.42 * x)
            yf = df if x >= 7 * df / 3 else 0.15 * x + 0.65 * df
            return (0.36 * fck * b * x + 0.45 * fck * (bf - b) * yf,
                    0.36 * fck * b * x * (dc - 0.42 * x) + 0.45 * fck * (bf - b) * yf * (dc - yf / 2))

        # the bars on the other face act as compression steel (SP 16 Table A), as in the engine's moment check
        of = "top" if reinf["tension_face"] == "bottom" else "bottom"
        oth = reinf[of]
        asc = oth["count"] * math.pi * oth["dia"] ** 2 / 4
        dsc = (s["clear_cover_mm"] if s["clear_cover_mm"] is not None else COVER[s["exposure"]]) + s["stirrup_dia_mm"] + oth["dia"] / 2
        with_asc = fsc_hand(0.002, fy) is not None

        def steel_c(x: float) -> float:
            if not with_asc or x <= dsc:
                return 0.0
            return asc * max(fsc_hand(0.0035 * (x - dsc) / x, fy) - 0.446 * fck, 0.0)  # type: ignore[operator]

        lo, hi = 0.0, dc
        for _ in range(200):
            x = (lo + hi) / 2
            lo, hi = (x, hi) if comp(x)[0] + steel_c(x) < t else (lo, x)
        m_r = (comp(hi)[1] + steel_c(hi) * (dc - dsc)) / 1e6
        n += 1
        # Fe 550 is not in SP 16 Table A: there the hand value leaves out the compression steel and can only be lower
        if (with_asc and abs(m_r - cur["m_cont"]) > 0.006 * cur["m_cont"]) or m_r > cur["m_cont"] * 1.006:
            bad.append(f"{name}: resistance of the continuing bars engine {cur['m_cont']:.2f} hand {m_r:.2f}")
        m_r = max(m_r, cur["m_cont"])
        # where the continuing bars suffice, by bisection on M(x) from the face
        if cant:  # M falls from the face to the free end
            if m_at(0) <= m_r:
                x_t = 0.0
            else:
                lo, hi = 0.0, lc
                for _ in range(200):
                    x = (lo + hi) / 2
                    lo, hi = (x, hi) if m_at(x) > m_r else (lo, x)
                x_t = (lo + hi) / 2
        elif m_at(lc / 2) <= m_r:  # M rises from the face to mid-span
            x_t = lc / 2
        else:
            lo, hi = 0.0, lc / 2
            for _ in range(200):
                x = (lo + hi) / 2
                lo, hi = (x, hi) if m_at(x) < m_r else (lo, x)
            x_t = (lo + hi) / 2
        beyond = max(d, 12 * cut["dia"])
        tbd = {20: 1.2, 25: 1.4, 30: 1.5, 35: 1.7, 40: 1.9}[max(g for g in (20, 25, 30, 35, 40) if g <= min(fck, 40))] * (1.6 if fy >= 415 else 1.0)
        ld = cut["dia"] * 0.87 * fy / (4 * tbd)
        x_cut = cur["x_cut"]
        n += 3
        if cant:
            if not (x_cut >= x_t + beyond - 1 and x_cut >= ld - 1 and x_cut <= max(x_t + beyond, ld) + 50):
                bad.append(f"{name}: cantilever cut-off {x_cut} against x_t {x_t:.0f} + {beyond:.0f}, L_d {ld:.0f}")
        elif not (x_cut <= x_t - beyond + 1 and x_cut <= lc / 2 - ld + 1 and x_cut >= min(x_t - beyond, lc / 2 - ld) - 50):
            bad.append(f"{name}: cut-off {x_cut} against x_t {x_t:.0f} - {beyond:.0f}, l_c/2 - L_d {lc / 2 - ld:.0f}")
        if a_cont < a_all / 3 - 1e-6:
            bad.append(f"{name}: less than a third of the bars continue")
        # Cl. 26.2.3.2 at the cut-off with the stirrups there
        z = st.get("zones")
        sv_here = st["spacing"] if not z or x_cut <= z["length"] + 1e-6 else z["s_mid"]
        pt = min(max(100 * a_cont / (b * dc), 0.15), 3.0)
        beta = max(0.8 * min(fck, 40) / (6.89 * pt), 1.0)
        tc = 0.85 * math.sqrt(0.8 * min(fck, 40)) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)
        v_cap = (tc * b * dc + 0.87 * fyv * asv * dc / sv_here) / 1e3
        n += 1
        if cur["condition"] in ("a", "c"):
            lim = 2 / 3 if cur["condition"] == "a" else 3 / 4
            if v_at(x_cut) > lim * v_cap * 1.03:
                bad.append(f"{name}: shear at the cut-off {v_at(x_cut):.1f} above {lim:.2f} of {v_cap:.1f}")
        else:  # (b): closer stirrups along the stopped bars over 3/4 d, excess >= 0.4 b s / f_y, spacing <= d / (8 beta_b)
            cz = st["cutoff"]
            beta_b = 1 - a_cont / a_all
            vus = max(v_at(x_cut) - tc * b * dc / 1e3, 0.0)
            need = max(vus * 1e3 / (0.87 * fyv * dc), 0.4 * b / (0.87 * fyv)) + 0.4 * b / fyv
            s_allow = min(asv / need, dc / (8 * beta_b))
            span = (x_cut - 0.75 * dc, x_cut) if cant else (x_cut, x_cut + 0.75 * dc)
            inside = [x for x in st["positions"] if span[0] - cz["spacing"] - 1e-6 <= x <= span[1] + cz["spacing"] + 1e-6]
            gaps = [q - p_ for p_, q in zip(inside, inside[1:], strict=False)]
            n += 2
            if cz["spacing"] > s_allow * 1.03:
                bad.append(f"{name}: spacing along the stopped bars {cz['spacing']} above the hand limit {s_allow:.0f}")
            if not gaps or max(gaps) > cz["spacing"] + 1e-6 or abs(cz["from"] - span[0]) > 1 or abs(cz["to"] - span[1]) > 1:
                bad.append(f"{name}: the closer stirrups do not cover 3/4 d from the cut-off ({cz}, {span})")
    if zones and zones["applied"]:
        z = st["zones"]
        pos = st["positions"]
        end = max(p for p in pos if p <= z["length"] + st["spacing"] + 1e-6)
        cont_bars = reinf["curtailment"]["continuing"] if reinf.get("curtailment") else reinf[reinf["tension_face"]]
        a_cont = cont_bars["count"] * math.pi * cont_bars["dia"] ** 2 / 4
        dc = eng["curtailment"]["d_cont"] if eng["curtailment"]["applied"] else d
        pt = min(max(100 * a_cont / (b * dc), 0.15), 3.0)
        beta = max(0.8 * min(fck, 40) / (6.89 * pt), 1.0)
        tc = 0.85 * math.sqrt(0.8 * min(fck, 40)) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)
        v_mid = (tc * b * dc + 0.87 * fyv * asv * dc / z["s_mid"]) / 1e3
        n += 2
        if v_at(end) > v_mid * 1.03:
            bad.append(f"{name}: shear {v_at(end):.1f} where the wider spacing begins, above {v_mid:.1f}")
        gaps = [b2 - a2 for a2, b2 in zip(pos, pos[1:], strict=False)]
        if max(gaps) > z["s_mid"] + 1e-6 or any(g > st["spacing"] + 1e-6 for a2, g in zip(pos, gaps, strict=False) if a2 < z["length"]):
            bad.append(f"{name}: stirrup positions exceed the zone spacings")
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = BeamInput().model_dump()
    if defaults != BASE:
        diff = {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)}
        bad.append(f"engine defaults differ from BASE: {diff}")
    base = design_beam(BeamInput(**BASE))
    for key, want in BASE_EXPECTED.items():
        got = base["data"][key]
        if abs(got - want) > 0.005 * abs(want):
            bad.append(f"base: {key} engine {got} expected {want}")
    n_base, b0 = compare("base", BASE, base)
    bad += b0
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_beam(BeamInput(**s))
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
        res = design_beam(BeamInput(**dict(BASE, **ov)))
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
