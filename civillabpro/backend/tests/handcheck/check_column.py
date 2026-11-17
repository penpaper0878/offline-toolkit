#!/usr/bin/env python3
"""Independent hand check of the column engine.

Written from the clauses of IS 456:2000 and the tables of SP 16, not from the engine, and by a
different route for every capacity:

  * concrete: the Fig. 21 stress block integrated numerically over 4000 strips
    (engine: closed-form integrals of the parabola-rectangle);
  * steel: stresses read from the points printed in SP 16, Table A for Fe 415 and Fe 500,
    elastic-plastic for Fe 250, and for Fe 550 the Fig. 23A points computed here from their
    definition (engine: its own interpolation of Fig. 23);
  * neutral axis at P_u: a scan over a logarithmic grid, then bisection on this file's own
    force function (engine: bisection on its own);
  * effective length, slenderness, minimum eccentricity, initial and additional moments, P_uz,
    P_b, k, alpha_n and both load cases of Cl. 25.4: recomputed line by line.

Run:  python tests/handcheck/check_column.py
Last line on success:  OK: n results agree ... (exit code 0)
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.column import ColumnInput, design_column  # noqa: E402

BASE = dict(
    mark="C1", width_mm=300, depth_mm=450, unsupported_length_mm=3600, unsupported_length_y_mm=None,
    end_x="c", k_x=1.0, sway_x=False, end_y="c", k_y=1.0, sway_y=False,
    fck=25, fy=500, exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20,
    pu_kn=1200, mux_knm=90, mux_other_knm=-45, muy_knm=30, muy_other_knm=10,
    main_bar_dia_mm=None, tie_dia_mm=8, max_steel_pct=4.0, beam_depth_mm=450,
)

# Worked by hand from the clauses (module docstring of column.py).
BASE_EXPECTED = dict(
    ratio_x=8.0,  # 3600 / 450
    ratio_y=12.0,  # 3600 / 300: slender (Cl. 25.1.2 needs less than 12 for short)
    ex_min=22.2,  # 3600/500 + 450/30
    ey_min=20.0,  # 3600/500 + 300/30 = 17.2, not less than 20
    miy=22.0,  # max(0.4 x 10 + 0.6 x 30, 0.4 x 30)
    may=25.92,  # 1200 x 0.3 / 2000 x 12^2
    cover=32.0,  # max(30, 40 - 8)
)

TABLE_28 = {"a": (0.65, False), "b": (0.80, False), "c": (1.00, False), "d": (1.20, True), "e": (1.50, True), "f": (2.00, True), "g": (2.00, True)}
COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}

CASES: list[tuple[str, dict]] = [
    ("M20 Fe415 mild", dict(fck=20, fy=415, exposure="mild")),
    ("Fe550 M40", dict(fy=550, fck=40, exposure="severe", pu_kn=2600, width_mm=400, depth_mm=500)),
    ("Fe250 M20", dict(fy=250, fck=20, exposure="mild")),
    ("axial only, Cl. 39.3", dict(pu_kn=1500, mux_knm=0, mux_other_knm=0, muy_knm=0, muy_other_knm=0, unsupported_length_mm=3000, width_mm=400, depth_mm=400)),
    ("axial only, e_min > 0.05 D", dict(pu_kn=900, mux_knm=0, mux_other_knm=0, muy_knm=0, muy_other_knm=0, unsupported_length_mm=3000, width_mm=230, depth_mm=300)),
    ("sway both axes", dict(end_x="d", end_y="d", unsupported_length_mm=4500, width_mm=350, depth_mm=450, pu_kn=1500, mux_knm=120, mux_other_knm=-100,
                            muy_knm=60, muy_other_knm=-40)),
    ("heavy biaxial", dict(fck=30, fy=415, width_mm=450, depth_mm=600, pu_kn=2500, mux_knm=320, mux_other_knm=150, muy_knm=180, muy_other_knm=-90)),
    ("cantilever (free end)", dict(end_x="g", end_y="g", unsupported_length_mm=3000, width_mm=400, depth_mm=400, pu_kn=300, mux_knm=80, mux_other_knm=0,
                                   muy_knm=40, muy_other_knm=0)),
    ("small 230 x 230", dict(width_mm=230, depth_mm=230, pu_kn=600, mux_knm=15, mux_other_knm=0, muy_knm=10, muy_other_knm=0, unsupported_length_mm=3000)),
    ("fixed T20", dict(main_bar_dia_mm=20)),
    ("custom factor, sway", dict(end_x="custom", k_x=1.6, sway_x=True, end_y="custom", k_y=1.3, sway_y=True)),
    ("tall slender", dict(unsupported_length_mm=9000, pu_kn=800, mux_knm=40, mux_other_knm=20, muy_knm=20, muy_other_knm=10)),
    ("different lengths", dict(unsupported_length_y_mm=2400, end_x="b", end_y="a")),
    ("braced single curvature", dict(unsupported_length_mm=6000, mux_knm=80, mux_other_knm=60, muy_knm=30, muy_other_knm=30)),
    ("wide section (b > D)", dict(width_mm=450, depth_mm=300, mux_knm=40, mux_other_knm=-20, muy_knm=70, muy_other_knm=35)),
    ("low axial load", dict(pu_kn=150, mux_knm=110, mux_other_knm=-60, muy_knm=40, muy_other_knm=0)),
    ("user cover, T10 ties", dict(clear_cover_mm=40, tie_dia_mm=10, pu_kn=1600)),
]

STOPS: list[tuple[str, dict, str]] = [
    ("overloaded", dict(pu_kn=6000), "No arrangement of bars"),
    ("too slender for the section", dict(width_mm=200, depth_mm=200, unsupported_length_mm=7000, pu_kn=900, mux_knm=30, mux_other_knm=-30,
                                         muy_knm=30, muy_other_knm=-30), "No arrangement of bars"),
]

# SP 16, Table A: (strain, design stress N/mm2) at 0.80 ... 1.0 of 0.87 fy, as printed.
SP16_TABLE_A = {
    415: [(0.00144, 288.7), (0.00163, 306.7), (0.00192, 324.8), (0.00241, 342.8), (0.00276, 351.8), (0.00380, 360.9)],
    500: [(0.00174, 347.8), (0.00195, 369.6), (0.00226, 391.3), (0.00277, 413.0), (0.00312, 423.9), (0.00417, 434.8)],
}


def fig23a_points(fy: float) -> list[tuple[float, float]]:
    """Fig. 23A from its definition: stress levels 0.80 ... 1.0 of 0.87 fy with their inelastic strains."""
    fyd = 0.87 * fy
    return [(k * fyd / 2e5 + inel, k * fyd) for k, inel in ((0.80, 0), (0.85, 0.0001), (0.90, 0.0003), (0.95, 0.0007), (0.975, 0.0010), (1.0, 0.0020))]


def steel(strain: float, fy: float) -> float:
    e = abs(strain)
    if fy <= 250:
        s = min(2e5 * e, 0.87 * fy)
    else:
        pts = SP16_TABLE_A.get(int(fy)) or fig23a_points(fy)
        if e <= pts[0][0]:
            s = 2e5 * e
        else:
            s = pts[-1][1]
            for (e0, s0), (e1, s1) in zip(pts, pts[1:], strict=False):
                if e <= e1:
                    s = s0 + (s1 - s0) * (e - e0) / (e1 - e0)
                    break
    return math.copysign(s, strain)


def concrete(strain: float, fck: float) -> float:
    if strain <= 0:
        return 0.0
    f = 0.67 * fck / 1.5
    return f if strain >= 0.002 else f * (2 * strain / 0.002 - (strain / 0.002) ** 2)


def strain(y: float, xu: float, depth: float) -> float:
    """Cl. 39.1: 0.0035 at the compression edge, or the pivot of 0.002 at 3D/7 when the whole section is compressed."""
    if xu <= depth:
        return 0.0035 * (xu - y) / xu
    return 0.002 * (xu - y) / (xu - 3 * depth / 7)


N_STRIPS = 4000


def forces(width: float, depth: float, rows: list[tuple[float, float]], fck: float, fy: float, xu: float) -> tuple[float, float]:
    """(P in N, M about mid-depth in N mm) by strip integration and row-by-row steel."""
    h = depth / N_STRIPS
    p = m = 0.0
    for i in range(N_STRIPS):
        y = (i + 0.5) * h
        f = concrete(strain(y, xu, depth), fck) * width * h
        p += f
        m += f * (depth / 2 - y)
    for y, a in rows:
        e = strain(y, xu, depth)
        f = a * (steel(e, fy) - (concrete(e, fck) if e > 0 else 0.0))
        p += f
        m += f * (depth / 2 - y)
    return p, m


def moment_at(width: float, depth: float, rows: list[tuple[float, float]], fck: float, fy: float, p_target: float) -> float:
    grid = [depth * 0.02 * (1.12**i) for i in range(120)]  # 0.02 D to about 17 000 D
    prev = None
    for xu in grid:
        p, _ = forces(width, depth, rows, fck, fy, xu)
        if p >= p_target:
            lo, hi = (prev if prev is not None else xu * 0.5), xu
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if forces(width, depth, rows, fck, fy, mid)[0] < p_target:
                    lo = mid
                else:
                    hi = mid
            return forces(width, depth, rows, fck, fy, 0.5 * (lo + hi))[1]
        prev = xu
    return 0.0


def rows_for(axis: str, b: float, D: float, n_b: int, n_d: int, dia: float, edge: float) -> tuple[float, float, list[tuple[float, float]]]:
    """(width, depth, rows) for bending about ``axis``: rows of bars measured from the compression face."""
    a1 = math.pi * dia * dia / 4
    if axis == "x":
        width, depth, outer, inner = b, D, n_b, n_d - 2
    else:
        width, depth, outer, inner = D, b, n_d, n_b - 2
    rows = [(edge, outer * a1), (depth - edge, outer * a1)]
    rows += [(edge + i * (depth - 2 * edge) / (inner + 1), 2 * a1) for i in range(1, inner + 1)]
    return width, depth, rows


def hand(s: dict, main: dict) -> dict:
    b, D, fck, fy, pu = s["width_mm"], s["depth_mm"], s["fck"], s["fy"], s["pu_kn"]
    lx = s["unsupported_length_mm"]
    ly = s["unsupported_length_y_mm"] or lx
    out: dict = {}
    out["cover"] = s["clear_cover_mm"] if s["clear_cover_mm"] is not None else max(COVER[s["exposure"]], 40 - s["tie_dia_mm"])

    axes = {}
    for ax, dim, length, end, kc, swc, m2, m1 in (("x", D, lx, s["end_x"], s["k_x"], s["sway_x"], s["mux_knm"], s["mux_other_knm"]),
                                                   ("y", b, ly, s["end_y"], s["k_y"], s["sway_y"], s["muy_knm"], s["muy_other_knm"])):
        k, sway = (kc, swc) if end == "custom" else TABLE_28[end]
        ratio = k * length / dim
        slender = not ratio < 12
        e_min = max(length / 500 + dim / 30, 20)
        mi = max(0.4 * m1 + 0.6 * m2, 0.4 * m2) if (slender and not sway) else m2
        ma = pu * dim / 1000 / 2000 * ratio**2 if slender else 0.0
        axes[ax] = dict(ratio=ratio, slender=slender, e_min=e_min, mi=mi, ma=ma, m2=m2)
    out.update(ratio_x=axes["x"]["ratio"], ratio_y=axes["y"]["ratio"], ex_min=axes["x"]["e_min"], ey_min=axes["y"]["e_min"],
               mix=axes["x"]["mi"], miy=axes["y"]["mi"], max=axes["x"]["ma"], may=axes["y"]["ma"])

    n_b, n_d, dia, edge = main["n_b"], main["n_d"], main["dia"], main["edge"]
    asc = (2 * n_b + 2 * (n_d - 2)) * math.pi * dia * dia / 4
    ac = b * D - asc
    out["asc"] = asc
    out["puz"] = (0.45 * fck * ac + 0.75 * fy * asc) / 1000
    out["pu_cap_393"] = (0.4 * fck * ac + 0.67 * fy * asc) / 1000

    kxu = 0.0035 / (0.0055 + 0.87 * fy / 2e5)
    pb, kf, mu1 = {}, {}, {}
    for ax in ("x", "y"):
        width, depth, rows = rows_for(ax, b, D, n_b, n_d, dia, edge)
        dt = max(y for y, _ in rows)
        pb[ax] = forces(width, depth, rows, fck, fy, kxu * dt)[0] / 1000
        g = axes[ax]
        kf[ax] = 1.0 if (not g["slender"] or out["puz"] <= pb[ax]) else min(max((out["puz"] - pu) / (out["puz"] - pb[ax]), 0.0), 1.0)
        mu1[ax] = moment_at(width, depth, rows, fck, fy, pu * 1000) / 1e6
    out.update(pb_x=pb["x"], pb_y=pb["y"], k_x=kf["x"], k_y=kf["y"])

    def total(ax: str, emin: bool) -> float:
        g = axes[ax]
        init = max(g["mi"], pu * g["e_min"] / 1000) if emin else g["mi"]
        return max(init + kf[ax] * g["ma"], g["m2"])

    out.update(case1_mx=total("x", True), case1_my=total("y", False), case2_mx=total("x", False), case2_my=total("y", True))
    axial_only = (not axes["x"]["slender"] and not axes["y"]["slender"] and s["mux_knm"] == 0 and s["muy_knm"] == 0
                  and axes["x"]["e_min"] <= 0.05 * D and axes["y"]["e_min"] <= 0.05 * b)
    out["axial_only"] = axial_only
    if not axial_only:
        r = pu / out["puz"]
        an = 1.0 + (min(max(r, 0.2), 0.8) - 0.2) / 0.6
        out.update(mux1=mu1["x"], muy1=mu1["y"], alpha_n=an,
                   ratio_case1=(out["case1_mx"] / mu1["x"]) ** an + (out["case1_my"] / mu1["y"]) ** an,
                   ratio_case2=(out["case2_mx"] / mu1["x"]) ** an + (out["case2_my"] / mu1["y"]) ** an)
    pitch_allow = min(min(b, D), 16 * dia, 300)
    out["tie_pitch_allow"] = pitch_allow
    out["p_pct"] = 100 * asc / (b * D)
    return out


# relative tolerances: exact arithmetic unless the route differs from the engine's
TOL = {
    # P_b is a small difference of large forces (in a 230 x 230 column, 173 + 115 - 175 - 109 = 4 kN), so its
    # difference is measured against the force scale: 5 % of P_uz when P_b itself is smaller (see SCALE below).
    # The route difference there is entirely the rounding of SP 16 Table A, which the engine reproduces exactly
    # when given Table A's stresses.
    "pb_x": 4e-3, "pb_y": 4e-3,
    "k_x": 6e-3, "k_y": 6e-3,
    "mux1": 4e-3, "muy1": 4e-3,
    "ratio_case1": 1.2e-2, "ratio_case2": 1.2e-2,  # alpha_n powers amplify the capacity difference
    "case1_mx": 6e-3, "case1_my": 6e-3, "case2_mx": 6e-3, "case2_my": 6e-3,  # through k
}


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    h = hand(s, res["reinforcement"]["main"])
    eng = res["data"]
    bad, n = [], 0
    for key, hv in h.items():
        ev = eng[key]
        n += 1
        if isinstance(hv, bool):
            if ev != hv:
                bad.append(f"{name}: {key} engine {ev} hand {hv}")
            continue
        tol = TOL.get(key, 1e-4)
        scale = max(abs(hv), 0.05 * h["puz"]) if key in ("pb_x", "pb_y") else max(abs(hv), 1e-9)
        if abs(ev - hv) > tol * scale + 1e-6:
            bad.append(f"{name}: {key} engine {ev:.6g} hand {hv:.6g} (tolerance {tol:g})")
    # the bars provided must satisfy the hand interaction check, with the tolerance of the route
    if not h["axial_only"]:
        worst = max(h["ratio_case1"], h["ratio_case2"])
        if worst > 1.0 + TOL["ratio_case1"]:
            bad.append(f"{name}: hand interaction ratio {worst:.4f} exceeds 1 for the bars selected")
    elif s["pu_kn"] > h["pu_cap_393"] * (1 + 1e-9):
        bad.append(f"{name}: hand axial capacity {h['pu_cap_393']:.1f} below P_u")
    if not 0.8 - 1e-9 <= h["p_pct"] <= s["max_steel_pct"] + 1e-9:
        bad.append(f"{name}: steel {h['p_pct']:.2f} % outside the limits")
    if eng["tie_pitch"] > h["tie_pitch_allow"] + 1e-9:
        bad.append(f"{name}: tie pitch {eng['tie_pitch']} above {h['tie_pitch_allow']}")
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = ColumnInput().model_dump()
    if defaults != BASE:
        diff = {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)}
        bad.append(f"engine defaults differ from BASE: {diff}")
    base = design_column(ColumnInput(**BASE))
    for key, want in BASE_EXPECTED.items():
        got = base["data"][key]
        if abs(got - want) > 1e-9 * max(1.0, abs(want)) + 1e-6:
            bad.append(f"base: {key} engine {got} expected {want}")
    n_base, b0 = compare("base", BASE, base)
    bad += b0
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_column(ColumnInput(**s))
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
        res = design_column(ColumnInput(**dict(BASE, **ov)))
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
