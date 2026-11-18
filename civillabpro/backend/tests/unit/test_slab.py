"""Slab engine: the worked example, panel types, each rule, stop states, validation and a sweep."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.engineering import is456
from app.engineering import is456_slabs as sl
from app.engineering.rebar import bar_area, bar_unit_weight
from app.modules.structural.domain.slab import SlabInput, design_slab, spacing_for


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def test_worked_example_matches_the_hand_calculation():
    r = design_slab(SlabInput())
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"]
    assert (d["dia"], d["d_x"], d["d_y"]) == (8, 116.0, 108.0)
    assert (d["lx"], d["ly"]) == (3416.0, 4608.0)  # min(clear + d, clear + support)
    assert (d["table"], d["case"], d["one_way"]) == ("26", 4, False)
    r_ = 4608 / 3416
    ax = sl.interpolate(sl.RATIOS_26, sl.TABLE_26[4].pos_x, r_)
    assert d["coefficients"]["pos_x"] == pytest.approx(ax) and d["coefficients"]["pos_y"] == 0.035
    assert d["wu"] == pytest.approx(1.5 * (1.5 + 3.75 + 3.0))
    assert d["moments"]["bottom_x"] == pytest.approx(ax * 12.375 * 3.416**2, rel=1e-6)
    assert d["moments"]["top_y_cont"] == pytest.approx(0.047 * 12.375 * 3.416**2, rel=1e-6)
    # Cl. 24.1 note 2 applies: l_x <= 3.5 m, imposed 3 kN/m2, Fe 415, continuous: 40 x 0.8
    assert (d["defl_method"], d["defl_allow"]) == ("24.1 note 2", 32.0) and d["defl_ratio"] == pytest.approx(3416 / 150)
    assert d["k"] == 1.30 and d["tau_v"] < d["k"] * d["tau_c"]
    # torsion steel: three-quarters of the steel for the mid-span moment
    assert d["torsion_as"] == pytest.approx(0.75 * d["as_flex"]["bottom_x"])
    corners = {c["name"]: c["factor"] for c in r["reinforcement"]["torsion"]["corners"]}
    assert corners == {"L1-S1": 1.0, "L1-S2": 0.5, "L2-S1": 0.5}  # no steel where both edges are continuous (D-1.10)


@pytest.mark.parametrize(
    "edges, case",
    [
        (("continuous", "continuous", "continuous", "continuous"), 1),
        (("continuous", "continuous", "discontinuous", "continuous"), 2),
        (("discontinuous", "continuous", "continuous", "continuous"), 3),
        (("discontinuous", "continuous", "discontinuous", "continuous"), 4),
        (("continuous", "continuous", "discontinuous", "discontinuous"), 5),
        (("discontinuous", "discontinuous", "continuous", "continuous"), 6),
        (("discontinuous", "continuous", "discontinuous", "discontinuous"), 7),
        (("discontinuous", "discontinuous", "discontinuous", "continuous"), 8),
        (("discontinuous", "discontinuous", "discontinuous", "discontinuous"), 9),
    ],
)
def test_edges_select_the_table_26_case(edges, case):
    l1, l2, s1, s2 = edges
    r = design_slab(SlabInput(long_edge_1=l1, long_edge_2=l2, short_edge_1=s1, short_edge_2=s2))
    assert r["data"]["case"] == case
    present = set(r["data"]["moments"])
    assert ("top_x_cont" in present) == (l1 == "continuous" or l2 == "continuous")
    assert ("top_y_cont" in present) == (s1 == "continuous" or s2 == "continuous")
    assert ("top_x_disc" in present) == (l1 == "discontinuous" or l2 == "discontinuous")
    assert ("torsion" in present) == (case != 1)


def test_table_27_only_for_a_simply_supported_panel_with_free_corners():
    free = dict(long_edge_2="discontinuous", short_edge_2="discontinuous", corners_held_down=False)
    r = design_slab(SlabInput(**free))
    assert r["data"]["table"] == "27" and r["data"]["torsion_as"] is None
    assert any("Annex D-2" in f["ref"] for f in r["sheet"]["flags"])
    # with a continuous edge the flag is irrelevant: Table 26
    assert design_slab(SlabInput(corners_held_down=False))["data"]["table"] == "26"
    held = design_slab(SlabInput(long_edge_2="discontinuous", short_edge_2="discontinuous"))
    assert held["data"]["moments"]["bottom_x"] < r["data"]["moments"]["bottom_x"]  # restrained corners attract less moment


def test_one_way_above_a_ratio_of_two():
    r = design_slab(SlabInput(span_x_mm=3000, span_y_mm=5800))
    assert not r["data"]["one_way"] and r["data"]["ratio"] <= 2.0
    r = design_slab(SlabInput(span_x_mm=3000, span_y_mm=7000))
    assert r["data"]["one_way"] and r["data"]["ratio"] > 2.0


def test_one_way_coefficients():
    wd, wl = 1.5 * (1.5 + 3.75), 1.5 * 3.0
    base = dict(span_x_mm=3000, span_y_mm=7000)
    ss = design_slab(SlabInput(**base, long_edge_2="discontinuous"))["data"]
    L = ss["lx"] / 1000
    assert ss["moments"]["bottom_x"] == pytest.approx((wd + wl) * L * L / 8, rel=1e-6) and "top_x_cont" not in ss["moments"]
    end = design_slab(SlabInput(**base))["data"]
    assert end["moments"]["bottom_x"] == pytest.approx((wd / 12 + wl / 10) * L * L, rel=1e-6)
    assert end["moments"]["top_x_cont"] == pytest.approx((wd / 10 + wl / 9) * L * L, rel=1e-6)
    assert end["vu"] == pytest.approx((0.6 * wd + 0.6 * wl) * L, rel=1e-6)
    interior = design_slab(SlabInput(**base, long_edge_1="continuous"))["data"]
    assert interior["moments"]["bottom_x"] == pytest.approx((wd / 16 + wl / 12) * L * L, rel=1e-6)
    assert interior["vu"] == pytest.approx((0.55 * wd + 0.6 * wl) * L, rel=1e-6)
    flags = design_slab(SlabInput(**base))["sheet"]["flags"]
    assert any("Cl. 22.5.1" in f["ref"] for f in flags)


def test_minimum_steel_and_one_bar_size():
    r = design_slab(SlabInput(long_edge_1="continuous", short_edge_1="continuous", live_load_kn_m2=1.5))
    d = r["data"]
    assert d["as_req"]["bottom_x"] == pytest.approx(d["as_min"]) == pytest.approx(0.0012 * 1000 * 150)
    assert set(r["bbs"]["summary"][i]["dia"] for i in range(len(r["bbs"]["summary"]))) == {8}


def test_bar_size_rises_when_8_mm_would_be_too_close():
    r = design_slab(SlabInput(span_x_mm=5000, span_y_mm=6000, thickness_mm=180, live_load_kn_m2=5))
    assert r["data"]["dia"] >= 10 and min(r["data"]["spacing"].values()) >= 100
    fixed = design_slab(SlabInput(bar_dia_mm=12))
    assert fixed["data"]["dia"] == 12


def test_spacing_rounding():
    b = spacing_for(300.0, 10, 348.0)
    assert b.spacing == 260 and b.area == pytest.approx(1000 * bar_area(10) / 260)  # 261.8 -> 260
    assert spacing_for(50.0, 8, 348.0).spacing == 340  # capped by 3d, in 10 mm steps


def test_deflection_method_selection():
    assert design_slab(SlabInput(fy=500))["data"]["defl_method"] == "23.2.1"
    assert design_slab(SlabInput(live_load_kn_m2=4.0))["data"]["defl_method"] == "23.2.1"
    assert design_slab(SlabInput(span_x_mm=3500, span_y_mm=4500))["data"]["defl_method"] == "23.2.1"  # l_x above 3.5 m
    mild = design_slab(SlabInput(fy=250, fck=20, exposure="mild"))["data"]
    assert mild["defl_allow"] == 40.0  # continuous, mild steel
    ss = design_slab(SlabInput(long_edge_2="discontinuous", short_edge_2="discontinuous"))["data"]
    assert ss["defl_allow"] == pytest.approx(28.0)  # 35 x 0.8


def test_shear_checks_and_slab_factor():
    r = design_slab(SlabInput(thickness_mm=250, span_x_mm=5000, span_y_mm=6000, live_load_kn_m2=5))
    c = checks(r)
    assert r["data"]["k"] == pytest.approx(1.10)
    assert c["shear"]["rhs"] == pytest.approx(1.10 * r["data"]["tau_c"], rel=1e-5)
    assert c["shear_max"]["rhs"] == pytest.approx(is456.tau_c_max(25) / 2)


def test_failed_limits_are_reported():
    r = design_slab(SlabInput(clear_cover_mm=20))  # moderate exposure needs 30
    assert r["status"] == "not_ok" and not checks(r)["cover"]["ok"]
    r = design_slab(SlabInput(fck=20))  # moderate exposure needs M25
    assert not checks(r)["grade"]["ok"]


def test_stop_state():
    r = design_slab(SlabInput(span_x_mm=6000, span_y_mm=7000, thickness_mm=100))
    assert r["status"] == "stopped" and "increase the thickness" in r["stop_message"]
    assert r["bbs"] is None and r["drawing"] is None


@pytest.mark.parametrize("bad", [dict(span_x_mm=5000, span_y_mm=4000), dict(thickness_mm=60), dict(finishes_kn_m2=0, live_load_kn_m2=0, include_self_weight=False),
                                 dict(bar_dia_mm=20), dict(long_edge_1="fixed"), dict(extra=1)])
def test_invalid_input_is_rejected(bad):
    with pytest.raises(ValidationError):
        SlabInput(**bad)


def test_schedule_quantities_and_drawing():
    r = design_slab(SlabInput())
    items = {i["description"].split(", T")[0]: i for i in r["bbs"]["items"]}
    sp = r["data"]["spacing"]
    a = items["Short span bottom, middle strip"]
    assert a["cutting_length_mm"] == 3300 + 2 * (230 - 30) and a["count"] == math.floor(0.75 * 4500 / sp["bottom_x"]) + 1
    top = items["Top bars over continuous long edges"]
    assert top["dims"]["A"] == round(2 * 0.3 * 3416 + 230)
    disc = items["Top bars at discontinuous long edges"]
    assert disc["shape"].startswith("L-bar") and disc["dims"]["B"] == 150 - 60
    for it in r["bbs"]["items"]:
        assert it["weight_kg"] == pytest.approx(it["count"] * it["cutting_length_mm"] / 1000 * bar_unit_weight(it["dia"]), abs=0.01)
    lengths = {i["dims"]["A"] for i in r["bbs"]["items"] if i["description"].startswith("Distribution")}
    assert lengths == {4500, 3300}  # one item per edge direction, each as long as its edge
    q = r["quantities"]
    assert q["concrete_m3"] == pytest.approx(3.3 * 4.5 * 0.15, abs=1e-3) and q["formwork_m2"] == pytest.approx(3.3 * 4.5, abs=1e-3)  # reported to 3 dp
    plan, sec = r["drawing"]["views"]
    assert plan["id"] == "plan" and sec["id"] == "elevation"
    mats = [i for i in plan["items"] if i["t"] == "line" and i["layer"] == "stirrup"]
    assert len(mats) >= 3 * 10  # three corners with a 5 x 5 grid of lines each
    text = json.dumps(r, allow_nan=False)
    assert "NaN" not in text


def test_every_line_cites_a_reference():
    for kw in ({}, dict(span_x_mm=3000, span_y_mm=7000), dict(long_edge_2="discontinuous", short_edge_2="discontinuous", corners_held_down=False)):
        r = design_slab(SlabInput(**kw))
        for s in r["sheet"]["sections"]:
            for i in s["items"]:
                assert i["ref"], i


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    edge_sets = [("continuous",) * 4, ("discontinuous", "continuous", "discontinuous", "continuous"), ("discontinuous",) * 4]
    grid = itertools.product(((2500, 3000), (3000, 4500), (4000, 4000), (3000, 7000), (5000, 6500)), (110, 150, 200), edge_sets,
                             ((20, 250), (25, 415), (30, 500)), (1.5, 4.0, 10.0))
    n = n_ok = 0
    for (lx, ly), D, edges, (fck, fy), q in grid:
        l1, l2, s1, s2 = edges
        r = design_slab(SlabInput(span_x_mm=lx, span_y_mm=ly, thickness_mm=D, long_edge_1=l1, long_edge_2=l2, short_edge_1=s1, short_edge_2=s2,
                                  fck=fck, fy=fy, exposure="mild", live_load_kn_m2=q))
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            continue
        d = r["data"]
        area = 1000 * bar_area(d["dia"])
        for key, s in d["spacing"].items():
            assert area / s >= d["as_req"][key] - 1e-6, (key, lx, ly, D)
            assert s >= 75
        assert d["dia"] <= D / 8
        if r["status"] == "ok":
            n_ok += 1
    assert n == 405 and n_ok > 150


def test_corners_free_with_a_continuous_edge_is_designed_as_held_down_and_says_so():
    r = design_slab(SlabInput(corners_held_down=False))
    assert r["data"]["table"] == "26"
    assert any("only to a panel discontinuous on all four edges" in f["message"] for f in r["sheet"]["flags"])
