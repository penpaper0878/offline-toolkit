#!/usr/bin/env python3
"""Independent hand check of the slab engine.

Written from the clauses of IS 456:2000, not from the engine, and by a different route where one exists:

  * steel areas: the stress block of Cl. 38.1 solved by bisection (engine: Annex G-1.1(b) closed form);
  * Table 27: the unrounded Rankine-Grashoff expressions (engine: the rounded table);
  * tau_c: the SP 16 closed form behind Table 19 (engine: interpolation in Table 19);
  * Table 26: typed again here, separately from the engine (double entry), with its own case mapping
    and interpolation, so a transcription slip in either copy shows up;
  * spans, loads, Tables 12 and 13, shear, the slab factor k, deflection and corner torsion steel:
    recomputed line by line.

Run:  python tests/handcheck/check_slab.py
"""

from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.structural.domain.slab import SlabInput, design_slab  # noqa: E402

BASE = dict(
    mark="S1", span_x_mm=3300, span_y_mm=4500, support_width_mm=230, thickness_mm=150,
    long_edge_1="discontinuous", long_edge_2="continuous", short_edge_1="discontinuous", short_edge_2="continuous", corners_held_down=True,
    fck=25, fy=415, exposure="moderate", clear_cover_mm=None, max_aggregate_mm=20,
    finishes_kn_m2=1.5, live_load_kn_m2=3.0, include_self_weight=True, unit_weight_kn_m3=25, load_factor=1.5, bar_dia_mm=None,
)

# Worked by hand: T8 bars; d_x = 150 - 30 - 4 = 116, d_y = 108; l_x = min(3300 + 116, 3300 + 230) = 3416,
# l_y = min(4500 + 108, 4730) = 4608; r = 1.349 (Table 26 case 4, two adjacent edges discontinuous);
# w_u = 1.5 (1.5 + 3.75 + 3.0) = 12.375 kN/m2.
BASE_EXPECTED = dict(d_x=116.0, d_y=108.0, lx=3416.0, ly=4608.0, wu=12.375)

CASES: list[tuple[str, dict]] = [
    ("interior panel", dict(long_edge_1="continuous", short_edge_1="continuous")),
    ("one short edge discontinuous", dict(long_edge_1="continuous")),
    ("one long edge discontinuous", dict(short_edge_1="continuous")),
    ("two short edges discontinuous", dict(long_edge_1="continuous", short_edge_2="discontinuous")),
    ("two long edges discontinuous", dict(long_edge_2="discontinuous", short_edge_1="continuous")),
    ("three discontinuous, long continuous", dict(short_edge_2="discontinuous")),
    ("three discontinuous, short continuous", dict(long_edge_2="discontinuous")),
    ("four discontinuous, held down", dict(long_edge_2="discontinuous", short_edge_2="discontinuous")),
    ("four discontinuous, free corners", dict(long_edge_2="discontinuous", short_edge_2="discontinuous", corners_held_down=False)),
    ("square panel", dict(span_x_mm=4000, span_y_mm=4000, thickness_mm=160)),
    ("ratio near 2", dict(span_x_mm=3000, span_y_mm=5800)),
    ("one-way simply supported", dict(span_x_mm=3000, span_y_mm=7000, long_edge_2="discontinuous")),
    ("one-way end span", dict(span_x_mm=3000, span_y_mm=7000)),
    ("one-way interior span", dict(span_x_mm=3000, span_y_mm=7000, long_edge_1="continuous")),
    ("mild steel M20, large panel", dict(span_x_mm=5000, span_y_mm=6000, thickness_mm=180, fck=20, fy=250, exposure="mild", live_load_kn_m2=4)),
    ("Fe500, Cl. 23.2.1 deflection", dict(fy=500)),
    ("heavy load, T10 fixed", dict(live_load_kn_m2=7.5, finishes_kn_m2=2.0, bar_dia_mm=10, thickness_mm=170)),
    ("no self-weight, user cover", dict(include_self_weight=False, finishes_kn_m2=5.0, clear_cover_mm=25, exposure="mild")),
]

STOPS: list[tuple[str, dict, str]] = [
    ("too thin for the span", dict(span_x_mm=6000, span_y_mm=7000, thickness_mm=100), "No bar size"),
]

COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}

# Table 26, typed here a second time: case -> (neg_x row, pos_x row, neg_y, pos_y)
T26 = {
    1: ([.032, .037, .043, .047, .051, .053, .060, .065], [.024, .028, .032, .036, .039, .041, .045, .049], .032, .024),
    2: ([.037, .043, .048, .051, .055, .057, .064, .068], [.028, .032, .036, .039, .041, .044, .048, .052], .037, .028),
    3: ([.037, .044, .052, .057, .063, .067, .077, .085], [.028, .033, .039, .044, .047, .051, .059, .065], .037, .028),
    4: ([.047, .053, .060, .065, .071, .075, .084, .091], [.035, .040, .045, .049, .053, .056, .063, .069], .047, .035),
    5: ([.045, .049, .052, .056, .059, .060, .065, .069], [.035, .037, .040, .043, .044, .045, .049, .052], None, .035),
    6: (None, [.035, .043, .051, .057, .063, .068, .080, .088], .045, .035),
    7: ([.057, .064, .071, .076, .080, .084, .091, .097], [.043, .048, .053, .057, .060, .064, .069, .073], None, .043),
    8: (None, [.043, .051, .059, .065, .071, .076, .087, .096], .057, .043),
    9: (None, [.056, .064, .072, .079, .085, .089, .100, .107], None, .056),
}
R26 = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0]


def interp(xs: list[float], ys: list[float], x: float) -> float:
    x = min(max(x, xs[0]), xs[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            return ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[-1]


def which_case(long_disc: int, short_disc: int) -> int:
    if long_disc == 2 and short_disc == 2:
        return 9
    if long_disc + short_disc == 3:
        return 7 if long_disc == 1 else 8
    if long_disc == 2:
        return 6
    if short_disc == 2:
        return 5
    if long_disc == 1 and short_disc == 1:
        return 4
    if long_disc == 1:
        return 3
    if short_disc == 1:
        return 2
    return 1


def steel_by_stress_block(m_knm: float, d: float, fck: float, fy: float) -> float:
    """A_s per metre for M by bisection on the neutral axis of the 0.36 / 0.42 block."""
    lo, hi = 0.0, d
    for _ in range(200):
        x = (lo + hi) / 2
        if 0.36 * fck * 1000 * x * (d - 0.42 * x) / 1e6 < m_knm:
            lo = x
        else:
            hi = x
    return 0.36 * fck * 1000 * x / (0.87 * fy)


def tau_c_closed(fck: float, pt: float) -> float:
    pt = min(max(pt, 0.15), 3.0)
    fc = min(fck, 40)
    beta = max(0.8 * fc / (6.89 * pt), 1.0)
    return 0.85 * math.sqrt(0.8 * fc) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)


def k_slab(D: float) -> float:
    return interp([150, 175, 200, 225, 250, 275, 300], [1.30, 1.25, 1.20, 1.15, 1.10, 1.05, 1.00], D)


def kt(fs: float, pt: float) -> float:
    den = 0.225 + 0.00322 * fs - 0.625 * math.log10(1 / pt)
    return 2.0 if den <= 0.5 else min(2.0, 1 / den)


def hand(s: dict, dia: int, spacing: dict[str, float]) -> dict:
    """Recompute the results for the bar size the engine chose."""
    D, fck, fy = s["thickness_mm"], float(s["fck"]), float(s["fy"])
    lxc, lyc, sw = s["span_x_mm"], s["span_y_mm"], s["support_width_mm"]
    c = s["clear_cover_mm"] if s["clear_cover_mm"] is not None else COVER[s["exposure"]]
    d_x, d_y = D - c - dia / 2, D - c - 1.5 * dia
    lx, ly = min(lxc + d_x, lxc + sw), min(lyc + d_y, lyc + sw)
    r = ly / lx
    gk = s["finishes_kn_m2"] + (s["unit_weight_kn_m3"] * D / 1000 if s["include_self_weight"] else 0)
    wd, wl = s["load_factor"] * gk, s["load_factor"] * s["live_load_kn_m2"]
    wu = wd + wl
    long_disc = [s["long_edge_1"], s["long_edge_2"]].count("discontinuous")
    short_disc = [s["short_edge_1"], s["short_edge_2"]].count("discontinuous")
    asmin = (0.0015 if fy <= 250 else 0.0012) * 1000 * D
    L = lx / 1000
    out = dict(d_x=d_x, d_y=d_y, lx=lx, ly=ly, ratio=r, wu=wu, as_min=asmin, one_way=r > 2)
    mom: dict[str, float] = {}
    if r > 2:
        if long_disc == 2:
            mom["bottom_x"] = wu * L * L / 8
            vu = wu * (lxc / 2000 - d_x / 1000)
        else:
            cd, cl = (1 / 12, 1 / 10) if long_disc == 1 else (1 / 16, 1 / 12)
            mom["bottom_x"] = (cd * wd + cl * wl) * L * L
            mom["top_x_cont"] = (wd / 10 + wl / 9) * L * L
            vu = (0.6 * wd + 0.6 * wl) * L if long_disc == 1 else (0.55 * wd + 0.6 * wl) * L
    else:
        if long_disc == 2 and short_disc == 2 and not s["corners_held_down"]:
            r4 = r**4
            ax, ay, nx, ny = r4 / (8 * (1 + r4)), r * r / (8 * (1 + r4)), None, None
        else:
            neg, pos, ny, ay = T26[which_case(long_disc, short_disc)]
            ax = interp(R26, pos, r)
            nx = interp(R26, neg, r) if neg else None
        mom["bottom_x"] = ax * wu * L * L
        mom["bottom_y"] = ay * wu * L * L
        if nx is not None:
            mom["top_x_cont"] = nx * wu * L * L
        if ny is not None:
            mom["top_y_cont"] = ny * wu * L * L
        vu = wu * (lxc / 2000 - d_x / 1000)
    out["moments"] = mom
    depth = {"bottom_x": d_x, "bottom_y": d_y, "top_x_cont": d_x, "top_y_cont": d_y}
    out["as_flex"] = {k: steel_by_stress_block(m, depth[k], fck, fy) for k, m in mom.items()}
    out["vu"] = vu
    as_x = 1000 * math.pi * dia * dia / 4 / spacing["bottom_x"]
    pt = 100 * as_x / (1000 * d_x)
    out["tau_v"] = vu * 1e3 / (1000 * d_x)
    out["tau_c"] = tau_c_closed(fck, pt)
    out["k"] = k_slab(D)
    if r <= 2 and lx <= 3500 and s["live_load_kn_m2"] <= 3 and fy <= 415:
        out["defl_ratio"] = lx / D
        out["defl_allow"] = (35 if (long_disc == 2 and short_disc == 2) else 40) * (0.8 if fy > 250 else 1.0)
    else:
        as_req_x = max(steel_by_stress_block(mom["bottom_x"], d_x, fck, fy), asmin)
        fs = 0.58 * fy * as_req_x / as_x
        basic = 20 if long_disc == 2 else 26
        out["defl_ratio"] = lx / d_x
        out["defl_allow"] = basic * (10000 / lx if lx > 10000 else 1) * kt(fs, pt)
    if r <= 2 and not (long_disc == 2 and short_disc == 2 and not s["corners_held_down"]) and (long_disc or short_disc):
        out["torsion_as"] = 0.75 * steel_by_stress_block(mom["bottom_x"], d_x, fck, fy)
    return out


TOL = {"as_flex": 3e-3, "tau_c": 0.03, "defl_allow": 6e-3, "torsion_as": 3e-3, "moments": 1e-4}


def close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(abs(b), 1e-9) + 1e-6


def compare(name: str, s: dict, res: dict) -> tuple[int, list[str]]:
    d = res["data"]
    h = hand(s, d["dia"], d["spacing"])
    bad, n = [], 0
    for key in ("d_x", "d_y", "lx", "ly", "ratio", "wu", "as_min", "vu", "tau_v", "k", "defl_ratio"):
        n += 1
        if not close(d[key], h[key], 1e-4):
            bad.append(f"{name}: {key} engine {d[key]} hand {h[key]:.6g}")
    n += 1
    if d["one_way"] != h["one_way"]:
        bad.append(f"{name}: one_way engine {d['one_way']} hand {h['one_way']}")
    # Table 27 rounded against the exact expression; Table 26 the same values: a looser tolerance only for Table 27
    mtol = 6e-3 if d["table"] == "27" else TOL["moments"]
    for key, hv in h["moments"].items():
        n += 1
        if not close(d["moments"][key], hv, mtol):
            bad.append(f"{name}: moment {key} engine {d['moments'][key]} hand {hv:.6g}")
        n += 1
        if not close(d["as_flex"][key], h["as_flex"][key], TOL["as_flex"] + (mtol if d["table"] == "27" else 0)):
            bad.append(f"{name}: steel {key} engine {d['as_flex'][key]} hand {h['as_flex'][key]:.6g}")
    for key in ("tau_c", "defl_allow"):
        n += 1
        if not close(d[key], h[key], TOL[key]):
            bad.append(f"{name}: {key} engine {d[key]} hand {h[key]:.6g}")
    if "torsion_as" in h:
        n += 1
        if d["torsion_as"] is None or not close(d["torsion_as"], h["torsion_as"], TOL["torsion_as"]):
            bad.append(f"{name}: torsion engine {d['torsion_as']} hand {h['torsion_as']:.6g}")
    # the bars provided satisfy the hand requirements and the spacing rules
    area = 1000 * math.pi * d["dia"] ** 2 / 4
    for key, s_ in d["spacing"].items():
        need = h["as_flex"].get(key, 0.0)
        if key.startswith("bottom"):
            need = max(need, h["as_min"])
        if area / s_ < need * (1 - TOL["as_flex"]):
            bad.append(f"{name}: {key} provides {area / s_:.0f} below the hand requirement {need:.0f}")
        if s_ > min(3 * h["d_x"], 300) + 1e-9 and key not in ("bottom_y",):
            bad.append(f"{name}: {key} spacing {s_} above 3d / 300")
    return n, bad


def main() -> int:
    bad: list[str] = []
    defaults = SlabInput().model_dump()
    if defaults != BASE:
        bad.append(f"engine defaults differ from BASE: { {k: (defaults.get(k), BASE.get(k)) for k in set(defaults) | set(BASE) if defaults.get(k) != BASE.get(k)} }")
    base = design_slab(SlabInput(**BASE))
    for key, want in BASE_EXPECTED.items():
        if not close(base["data"][key], want, 1e-9):
            bad.append(f"base: {key} engine {base['data'][key]} expected {want}")
    if (base["data"]["table"], base["data"]["case"]) != ("26", 4):
        bad.append(f"base: expected Table 26 case 4, engine {base['data']['table']} case {base['data']['case']}")
    n_base, b0 = compare("base", BASE, base)
    bad += b0
    n_cases = 0
    for name, ov in CASES:
        s = dict(BASE, **ov)
        res = design_slab(SlabInput(**s))
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
        res = design_slab(SlabInput(**dict(BASE, **ov)))
        if res["status"] != "stopped" or not (res["stop_message"] or "").startswith(want):
            bad.append(f"stop '{name}': got {res['status']} / {res['stop_message']}")
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n_base + len(BASE_EXPECTED) + 1} results agree with the independent hand check; "
          f"{n_cases} values of {len(CASES)} alternative-input cases and {len(STOPS)} stop states correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
