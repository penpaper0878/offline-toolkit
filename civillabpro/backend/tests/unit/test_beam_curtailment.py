"""Curtailment of the tension bars (Cl. 26.2.3) and stirrup zones in the simple beam."""

import itertools
import json
import math

import pytest

from app.engineering import is456
from app.engineering.rebar import BarGroup
from app.modules.structural.domain.beam import BeamInput, design_beam, split_for_curtailment, stirrup_positions

HEAVY = dict(width_mm=300, depth_mm=500, clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=35, live_load_kn_m=22)


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def test_split_rule():
    assert split_for_curtailment(BarGroup(16, (2,))) is None  # two bars: nothing to stop
    cont, cut = split_for_curtailment(BarGroup(16, (3,)))
    assert (cont.count, cut.count) == (2, 1)
    cont, cut = split_for_curtailment(BarGroup(20, (5,)))
    assert (cont.count, cut.count) == (3, 2)
    cont, cut = split_for_curtailment(BarGroup(20, (5, 4)))  # the second layer stops
    assert cont.layers == (5,) and cut.layers == (4,) and cont.area >= (cont.area + cut.area) / 3


def test_stirrup_positions():
    # one spacing: as many as before, symmetric
    pos = stirrup_positions(4000, 30, False, 300, [])
    assert len(pos) == 14 and pos[0] == 50 and pos[-1] == 3950
    assert all(b - a <= 300 + 1e-9 for a, b in zip(pos, pos[1:], strict=False))
    assert pos == tuple(sorted(4000 - x for x in pos))
    # a closer end zone and a closer band along stopped bars
    pos = stirrup_positions(6000, 30, False, 300, [(0, 1000, 125), (1500, 1900, 90)])
    gaps = [(a, b - a) for a, b in zip(pos, pos[1:], strict=False)]
    assert all(g <= 125 + 1e-9 for a, g in gaps if a < 1000)
    assert all(g <= 90 + 1e-9 for a, g in gaps if 1500 - 90 <= a <= 1900)
    assert max(g for _, g in gaps) <= 300 + 1e-9
    # cantilever: from the support to the free end less cover
    pos = stirrup_positions(2000, 30, True, 300, [])
    assert pos[0] == 50 and pos[-1] <= 1970 and len(pos) == 7


def test_worked_example_stops_the_middle_bar():
    r = design_beam(BeamInput())
    c = r["data"]["curtailment"]
    assert c["applied"] and c["condition"] == "a"
    # 2-T16 resist 65.26 kN m; M(x) reaches it 1212 mm from the face; less d = 404, in 50 mm steps
    assert c["m_cont"] == pytest.approx(65.26, abs=0.01) and c["x_cut"] == 800
    assert checks(r)["curtail_shear"]["ok"] and checks(r)["curtail_third"]["ok"]
    assert r["reinforcement"]["curtailment"]["curtailed"]["label"] == "1-T16"


def test_condition_b_adds_closer_stirrups_along_the_stopped_bars():
    r = design_beam(BeamInput(section="t_beam", width_mm=300, depth_mm=550, flange_thickness_mm=120, flange_width_mm=3000,
                              clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=30, live_load_kn_m=15))
    c, st = r["data"]["curtailment"], r["reinforcement"]["stirrups"]
    assert c["applied"] and c["condition"] == "b" and st["cutoff"]["spacing"] == c["s_b"]
    beta_b = 3 / 9  # 3 of 9 T16 stop
    assert c["s_b"] <= c["d_cont"] / (8 * beta_b)
    assert st["cutoff"]["from"] == c["x_cut"] and st["cutoff"]["to"] == pytest.approx(c["x_cut"] + 0.75 * c["d_cont"], abs=0.1)
    ch = checks(r)
    assert ch["curtail_shear"]["ok"] and ch["curtail_excess"]["ok"]
    assert any("Cl. 26.2.3.2(b)" in n for n in r["drawing"]["notes"])


def test_no_curtailment_cases_say_why():
    near = design_beam(BeamInput(width_mm=600, depth_mm=300, clear_span_mm=3000, dead_load_kn_m=20, live_load_kn_m=15))
    assert not near["data"]["curtailment"]["applied"] and "within d" in near["data"]["curtailment"]["reason"]
    assert any("run the full length" in f["message"] for f in near["sheet"]["flags"])
    two = design_beam(BeamInput(support="cantilever", clear_span_mm=1200, depth_mm=400, dead_load_kn_m=10, live_load_kn_m=6))
    assert not two["data"]["curtailment"]["applied"] and "too few bars" in two["data"]["curtailment"]["reason"]
    forces = design_beam(BeamInput(mode="forces", mu_knm=140, vu_kn=110, width_mm=300, depth_mm=550, clear_span_mm=5000))
    assert forces["data"]["curtailment"] is None and forces["reinforcement"]["curtailment"] is None
    assert any("no moment or shear diagram" in f["message"] for f in forces["sheet"]["flags"])


def test_cantilever_curtailment():
    r = design_beam(BeamInput(support="cantilever", clear_span_mm=2000, width_mm=300, depth_mm=500, support_width_mm=300,
                              dead_load_kn_m=15, live_load_kn_m=10))
    c = r["data"]["curtailment"]
    ld = is456.development_length(16, 25, 500)
    assert c["applied"] and c["x_cut"] >= max(c["x_theory"] + max(r["data"]["d"], 12 * 16), ld) and c["x_cut"] % 50 == 0
    cut = next(i for i in r["bbs"]["items"] if "curtailed" in i["description"])
    assert cut["dims"]["A"] == pytest.approx(300 - r["reinforcement"]["cover"] + c["x_cut"])


def test_stirrup_zones_follow_the_shear_diagram():
    r = design_beam(BeamInput(**HEAVY))
    z, st, d = r["data"]["zones"], r["reinforcement"]["stirrups"], r["data"]
    assert z["applied"] and z["s_end"] < z["s_mid"] == 300
    assert checks(r)["zone_shear"]["ok"]
    pos = st["positions"]
    assert len(pos) == z["count"] == next(i for i in r["bbs"]["items"] if i["description"].startswith("Stirrups"))["count"]
    # fewer stirrups than one close spacing throughout
    assert z["count"] < math.floor((6000 - 100) / z["s_end"]) + 1
    assert d["sv"] == z["s_end"]


def test_sweep_cut_offs_are_safe():
    grid = itertools.product(("simply_supported", "cantilever"), (230, 300), (450, 600), (3000, 6000), ((10, 5), (30, 20), (60, 40)))
    n = n_cut = 0
    for support, b, D, lc, (dl, ll) in grid:
        if support == "cantilever" and lc > 3000:
            continue
        r = design_beam(BeamInput(support=support, width_mm=b, depth_mm=D, clear_span_mm=lc, dead_load_kn_m=dl, live_load_kn_m=ll,
                                  support_width_mm=300))
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            continue
        d, c = r["data"], r["data"]["curtailment"]
        pos = r["reinforcement"]["stirrups"]["positions"]
        assert max(b2 - a2 for a2, b2 in zip(pos, pos[1:], strict=False)) <= max(d["zones"]["s_mid"], d["sv"]) + 1e-6
        if not c["applied"]:
            continue
        n_cut += 1
        wu, le = d["w_factored"], d["l_eff"]
        # beyond the cut-off (towards the maximum moment) by max(d, 12 phi), the continuing bars suffice
        if support == "cantilever":
            x = c["x_cut"] - max(d["d"], 12 * r["reinforcement"]["curtailment"]["curtailed"]["dia"])
            m = wu * max(le - x, 0) ** 2 / 2e6
        else:
            x = c["x_cut"] + max(d["d"], 12 * r["reinforcement"]["curtailment"]["curtailed"]["dia"]) + (le - lc) / 2
            m = wu * x * (le - x) / 2e6
        assert m <= c["m_cont"] + 1e-6
    assert n == 36 and n_cut >= 10



# ------------------------------------------------------------------ Cl. 26.2.3.3(c): anchorage at simple supports (STR-017)


def test_anchorage_check_at_the_supports():
    r = design_beam(BeamInput())
    c = checks(r)["anchorage"]
    # 2-T16 reach the supports: M_1 with the steel at f_d, V at the face, L_0 = 230/2 - 30, bars bent for Cl. 26.2.3.3(a)
    t = 0.87 * 500 * 2 * math.pi * 16**2 / 4
    m1 = t * (404 - 0.42 * t / (0.36 * 25 * 230))
    l0 = 230 / 2 - 30 + 8 * 16
    assert c["ok"] and c["lhs"] == pytest.approx(is456.development_length(16, 25, 500))
    assert c["rhs"] == pytest.approx(1.3 * m1 / (r["data"]["vu_face"] * 1e3) + l0, rel=1e-6)


def test_m1_has_no_neutral_axis_limit():
    # the clause assumes the steel at f_d: over-reinforced sections are not capped at x_u,max
    t = 0.87 * 500 * 2199
    assert is456.moment_at_design_stress(25, 500, 250, 520, 2199) == pytest.approx(t * (520 - 0.42 * t / (0.36 * 25 * 250)))
    assert is456.moment_at_design_stress(25, 500, 250, 520, 2199) > is456.moment_capacity(25, 500, 250, 520, 2199, 0, 50).mu


def test_a_bend_is_added_where_straight_bars_fail():
    # a heavily loaded short beam on narrow supports: straight T20 cannot develop; the bend's 8 phi makes up the difference
    r = design_beam(BeamInput(width_mm=250, depth_mm=600, clear_span_mm=3000, dead_load_kn_m=120, live_load_kn_m=80, stirrup_dia_mm=10))
    main = next(i for i in r["bbs"]["items"] if i["description"].startswith("Bottom bars (tension)"))
    assert r["status"] == "ok" and "bend" in main["shape"] and checks(r)["anchorage"]["ok"]


def test_bars_too_large_to_anchor_stop_with_the_right_message():
    r = design_beam(BeamInput(width_mm=250, depth_mm=600, clear_span_mm=2500, support_width_mm=150, dead_load_kn_m=200, live_load_kn_m=150,
                              main_bar_dia_mm=32, stirrup_dia_mm=10, fck=30))
    assert r["status"] == "stopped" and "anchored at the supports (Cl. 26.2.3.3(c))" in r["stop_message"]
