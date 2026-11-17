"""Beam engine: the worked example, each branch of the design, stop states and a wide input sweep."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.engineering.rebar import bar_area, bar_unit_weight
from app.modules.structural.domain.beam import BeamInput, design_beam


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def test_worked_example_matches_the_hand_calculation():
    r = design_beam(BeamInput())
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"] == 15
    # self-weight 25 x 0.23 x 0.45 = 2.5875; w = 12 + 2.5875 + 8 = 22.5875; wu = 1.5 w
    assert d["w_factored"] == pytest.approx(33.8812, abs=1e-4)
    # d = 450 - 30 - 8 - 16/2; l = min(4000 + 404, 4000 + 230)
    assert d["d"] == 404.0 and d["l_eff"] == 4230.0
    assert d["mu"] == pytest.approx(33.88125 * 4.23**2 / 8, abs=1e-3)  # 75.78 kN m
    assert d["vu"] == pytest.approx(33.88125 * (2.0 - 0.404), abs=1e-3)  # 54.07 kN at d from the face
    assert d["ast_req"] == pytest.approx(481.3, abs=0.1)
    assert r["reinforcement"]["bottom"]["label"] == "3-T16"
    assert r["reinforcement"]["top"]["label"] == "2-T12"
    # tau_v = 0.582 > tau_c = 0.538 (Table 19 at pt = 0.649 %); Vus is small, so the 300 mm cap governs
    assert d["tau_v"] == pytest.approx(0.582, abs=1e-3) and d["tau_c"] == pytest.approx(0.538, abs=1e-3)
    assert d["sv"] == 300 and d["sv_governing"].startswith("300 mm")
    # allowable span/depth = 20 x kt, fs = 0.58 x 500 x 481.3 / 603.2 = 231.4
    assert d["fs"] == pytest.approx(231.4, abs=0.1)
    assert d["span_depth_allow"] == pytest.approx(20 * d["kt"], abs=1e-3)
    assert d["ld_tension"] == pytest.approx(16 * 0.87 * 500 / (4 * 1.4 * 1.6), abs=0.1)  # 777 mm
    assert r["max_utilisation"] == pytest.approx(0.798, abs=1e-3)


def test_worked_example_bar_schedule_and_quantities():
    r = design_beam(BeamInput())
    a, b, c = r["bbs"]["items"]
    # bottom bars: A = 4000 + 2 x (230 - 30); L_d/3 = 259 > 200 so legs of max(9d, 259 - 200 + 2d) = 144 -> 145
    assert a["dims"] == {"A": 4400, "B": 145} and a["cutting_length_mm"] == 4400 + 2 * 145 - 4 * 16 + 4  # rounded up to 5
    assert b["cutting_length_mm"] == 4400 and b["count"] == 2
    # stirrups: (4000 - 100) / 300 = 13 spaces; 2(170 + 390) + 2 x 80 - 12 x 8 = 1184 -> 1185
    assert c["count"] == 14 and c["cutting_length_mm"] == 1185
    for it in r["bbs"]["items"]:
        assert it["weight_kg"] == pytest.approx(it["count"] * it["cutting_length_mm"] / 1000 * bar_unit_weight(it["dia"]), abs=0.01)
    assert r["bbs"]["total_weight_kg"] == pytest.approx(sum(i["weight_kg"] for i in r["bbs"]["items"]), abs=0.02)
    q = r["quantities"]
    assert q["concrete_m3"] == pytest.approx(0.23 * 0.45 * 4.46, abs=1e-3)
    assert q["formwork_m2"] == pytest.approx((0.23 + 0.9) * 4.0, abs=1e-3)
    assert q["steel_kg"] == pytest.approx(36.3, abs=0.05)


def test_doubly_reinforced_beam():
    r = design_beam(BeamInput(width_mm=300, depth_mm=500, clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=35, live_load_kn_m=22))
    d = r["data"]
    assert d["doubly"] and d["mu"] > d["mu_lim"] and d["asc_req"] > 0
    assert d["asc_prov"] >= d["asc_req"] and d["ast_prov"] >= d["ast_req"]
    assert d["mu_capacity"] >= d["mu"] and d["xu"] <= d["xu_max"] + 1e-6
    assert d["kc"] > 1.0
    assert "asc" in checks(r) and r["status"] == "ok"
    assert "compression" in r["bbs"]["items"][1]["description"]


def test_cantilever_puts_tension_steel_on_top_and_anchors_it():
    r = design_beam(BeamInput(support="cantilever", clear_span_mm=2000, width_mm=300, depth_mm=500, support_width_mm=300,
                              dead_load_kn_m=15, live_load_kn_m=10))
    d = r["data"]
    assert r["reinforcement"]["tension_face"] == "top"
    assert d["l_eff"] == pytest.approx(2000 + d["d"] / 2)  # Cl. 22.2(c)
    wu = 1.5 * (15 + 25 * 0.3 * 0.5 + 10)
    assert d["mu"] == pytest.approx(wu * (d["l_eff"] / 1000) ** 2 / 2, rel=1e-4)
    assert d["vu"] == pytest.approx(wu * 2.0)  # face shear, no reduction
    assert d["span_depth_allow"] == pytest.approx(7 * d["kt"], rel=1e-4)
    top = r["bbs"]["items"][0]
    assert top["shape"] == "L-bend at support" and top["dims"]["B"] >= d["ld_tension"] - 270
    assert any("Check that the leg fits" in f["message"] for f in r["sheet"]["flags"])


def test_torsion_follows_clause_41():
    r = design_beam(BeamInput(mode="forces", mu_knm=120, vu_kn=90, tu_knm=25, width_mm=300, depth_mm=600, clear_span_mm=5000,
                              support_width_mm=300))
    d = r["data"]
    assert d["ve"] == pytest.approx(90 + 1.6 * 25 / 0.3)  # 223.3 kN
    assert d["me1"] == pytest.approx(120 + 25 * (1 + 600 / 300) / 1.7)  # 164.1 kN m
    assert d["me2"] == 0
    b1 = 300 - 2 * (30 + 8 + 8)
    d1 = 600 - 46 - 44
    s_t = 0.87 * 415 * 2 * bar_area(8) / (25e6 / (b1 * d1) + 90e3 / (2.5 * d1))
    assert d["sv_allow"] == pytest.approx(s_t, rel=1e-3) and d["sv"] == 100
    assert r["reinforcement"]["side_face"]["label"] == "1-T12 each face"  # D > 450 with torsion, Cl. 26.5.1.7(b)
    assert r["status"] == "ok"


def test_torsion_larger_than_bending_designs_the_other_face():
    r = design_beam(BeamInput(mode="forces", mu_knm=20, vu_kn=40, tu_knm=30, width_mm=300, depth_mm=600, clear_span_mm=5000))
    d = r["data"]
    assert d["me2"] == pytest.approx(30 * 3 / 1.7 - 20)
    assert d["asc_prov"] >= d["ast2_req"] > 0 and checks(r)["me2"]["ok"]


def test_two_layers_and_four_legged_stirrups():
    r = design_beam(BeamInput(width_mm=400, depth_mm=900, clear_span_mm=9000, support_width_mm=400, dead_load_kn_m=60,
                              live_load_kn_m=40, fck=30, stirrup_legs=4))
    bot = r["reinforcement"]["bottom"]
    assert bot["layers"] == [6, 6] and bot["dia"] == 25
    # centroid of two layers of T25 at 25 mm clear: 30 + 8 + 12.5 + (25 + 25)/2 = 75.5
    assert r["data"]["d"] == pytest.approx(900 - 75.5)
    assert r["reinforcement"]["side_face"] is not None  # D > 750, Cl. 26.5.1.3
    assert [i["description"].split(",")[0] for i in r["bbs"]["items"]][-2:] == ["Stirrups", "Inner stirrups"]
    assert r["reinforcement"]["top"]["count"] >= 4


def test_crack_control_spacing_forces_a_third_bar_in_a_wide_web():
    # 300 wide, Fe 415: two bars would be 300 - 76 - 2 x 16 = 192 mm clear, above the 180 mm of Table 15
    r = design_beam(BeamInput(width_mm=300, depth_mm=500, fy=415, fy_stirrup=415, dead_load_kn_m=4, live_load_kn_m=2, main_bar_dia_mm=16))
    assert r["reinforcement"]["bottom"]["count"] >= 3
    assert checks(r)["spacing_max"]["ok"]


def test_minimum_steel_governs_a_lightly_loaded_beam():
    r = design_beam(BeamInput(width_mm=300, depth_mm=600, dead_load_kn_m=0, live_load_kn_m=1))
    d = r["data"]
    assert d["ast_min"] > d["ast_req"] and d["ast_prov"] >= d["ast_min"]
    assert d["kt"] == 2.0  # low stress, capped


def test_failed_limits_are_reported_not_hidden():
    r = design_beam(BeamInput(width_mm=350, depth_mm=750, clear_span_mm=11000, support_width_mm=400, dead_load_kn_m=15,
                              live_load_kn_m=10, fck=30))
    assert r["status"] == "not_ok" and not checks(r)["deflection"]["ok"]
    assert checks(r)["deflection"]["util"] > 1.0
    r = design_beam(BeamInput(fck=20, exposure="severe"))
    assert r["status"] == "not_ok" and not checks(r)["grade"]["ok"]
    r = design_beam(BeamInput(clear_cover_mm=20, exposure="moderate"))
    assert not checks(r)["cover"]["ok"]


def test_heavy_shear_reports_unworkable_stirrups_and_the_stress_limit():
    base = dict(mode="forces", mu_knm=100, width_mm=230, depth_mm=600, clear_span_mm=3000)
    # tau_v = 380e3 / (230 x 552) = 2.99 < 3.1, but T8 two-legged stirrups would be closer than 75 mm
    r = design_beam(BeamInput(vu_kn=380, **base))
    c = checks(r)
    assert r["status"] == "not_ok" and c["tau_max"]["ok"] and not c["sv_min"]["ok"]
    assert any("four-legged or larger stirrups" in f["message"] for f in r["sheet"]["flags"])
    # tau_v = 600e3 / (230 x 552) = 4.7 > tau_c,max = 3.1 for M25 (Table 20)
    r = design_beam(BeamInput(vu_kn=600, **base))
    assert r["status"] == "not_ok" and not checks(r)["tau_max"]["ok"]


@pytest.mark.parametrize(
    "overrides, message",
    [
        (dict(clear_span_mm=1500, depth_mm=1000, width_mm=300), "deep beam"),
        (dict(depth_mm=300, clear_span_mm=8000, dead_load_kn_m=80, live_load_kn_m=60), "No arrangement"),
    ],
)
def test_stop_states(overrides, message):
    r = design_beam(BeamInput(**overrides))
    assert r["status"] == "stopped" and message in r["stop_message"]
    assert r["bbs"] is None and r["drawing"] is None
    assert r["sheet"]["flags"][-1]["level"] == "error"


@pytest.mark.parametrize(
    "bad",
    [
        dict(width_mm=100),
        dict(depth_mm=5000),
        dict(fck=15),
        dict(fy=600),
        dict(clear_span_mm=0),
        dict(mode="forces"),  # moment and shear missing
        dict(tu_knm=5),  # torsion with load input
        dict(dead_load_kn_m=0, live_load_kn_m=0, include_self_weight=False),
        dict(unknown_field=1),
        dict(dead_load_kn_m=-1),
    ],
)
def test_invalid_input_is_rejected(bad):
    with pytest.raises(ValidationError):
        BeamInput(**bad)


def test_every_step_cites_a_reference_and_result_is_json_safe():
    r = design_beam(BeamInput(mode="forces", mu_knm=300, vu_kn=200, tu_knm=15, width_mm=350, depth_mm=700))
    for s in r["sheet"]["sections"]:
        for i in s["items"]:
            assert i["ref"], i
    text = json.dumps(r, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_drawing_has_two_views_with_the_bars_drawn():
    r = design_beam(BeamInput())
    sec, elev = r["drawing"]["views"]
    assert sec["id"] == "section" and elev["id"] == "elevation"
    bars = [i for i in sec["items"] if i["t"] == "circle"]
    assert len(bars) == 5  # 3-T16 + 2-T12
    assert all(0 < c["cx"] < 230 and 0 < c["cy"] < 450 for c in bars)
    stirrups = [i for i in elev["items"] if i["t"] == "line" and i["layer"] == "stirrup"]
    assert len(stirrups) == r["bbs"]["stirrup_count"] == 14
    xmin, ymin, xmax, ymax = sec["bounds"]
    assert xmin < 0 and xmax > 230 and ymax >= 450


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    grid = itertools.product(
        ("simply_supported", "cantilever"),
        (230, 350, 600),  # b
        (300, 450, 600, 1000),  # D
        (1500, 3500, 6000, 9000),  # clear span
        ((20, 415), (25, 500), (40, 550), (30, 250)),
        ((5, 3), (25, 15), (70, 50)),
    )
    n = n_ok = 0
    for support, b, D, lc, (fck, fy), (dl, ll) in grid:
        if support == "cantilever" and lc > 3500:
            continue
        inp = BeamInput(support=support, width_mm=b, depth_mm=D, clear_span_mm=lc, fck=fck, fy=fy, fy_stirrup=min(fy, 500),
                        dead_load_kn_m=dl, live_load_kn_m=ll, exposure="mild", support_width_mm=300)
        r = design_beam(inp)
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            assert r["stop_message"]
            continue
        d = r["data"]
        ten = r["reinforcement"][r["reinforcement"]["tension_face"]]
        # the iteration on effective depth converged on the bars actually chosen
        if len(ten["layers"]) == 1:
            assert d["d"] == pytest.approx(D - 20 - 8 - ten["dia"] / 2)
        assert d["ast_prov"] >= max(d["ast_req"], d["ast_min"]) - 1e-6
        assert d["asc_prov"] >= d["asc_req"] - 1e-6
        assert d["mu_capacity"] >= d["me1"] - 1e-6
        assert d["xu"] <= d["xu_max"] + 1e-6
        assert 0 < d["sv"] <= d["sv_allow"] + 1e-6 or d["sv"] == 0
        assert all(math.isfinite(v) for v in d.values() if isinstance(v, float))
        if r["status"] == "ok":
            n_ok += 1
            assert r["checks_passed"] == r["checks_total"]
    assert n > 400 and n_ok > 100
