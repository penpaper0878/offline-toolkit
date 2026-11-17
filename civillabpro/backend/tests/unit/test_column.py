"""Column engine: the worked example, each rule, stop states, validation and a sweep of inputs."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.engineering import is456
from app.engineering.rebar import bar_area, bar_unit_weight
from app.modules.structural.domain import column as col
from app.modules.structural.domain.column import ColumnInput, design_column


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def test_worked_example_matches_the_hand_calculation():
    r = design_column(ColumnInput())
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"]
    assert d["cover"] == 32.0  # max(Table 16 30, 40 - 8)
    assert d["ratio_x"] == 8.0 and not d["slender_x"]
    assert d["ratio_y"] == 12.0 and d["slender_y"]  # 12 is not "less than 12"
    assert d["ex_min"] == pytest.approx(22.2) and d["ey_min"] == 20.0
    assert d["mix"] == 90 and d["max"] == 0.0
    assert d["miy"] == pytest.approx(22.0)  # max(0.4 x 10 + 0.6 x 30, 0.4 x 30)
    assert d["may"] == pytest.approx(1200 * 0.3 / 2000 * 144)  # 25.92
    m = r["reinforcement"]["main"]
    assert (m["label"], m["n_b"], m["n_d"]) == ("12-T12", 5, 3)
    asc = 12 * bar_area(12)
    puz = (0.45 * 25 * (300 * 450 - asc) + 0.75 * 500 * asc) / 1000
    assert d["puz"] == pytest.approx(puz, rel=1e-6)
    k = (puz - 1200) / (puz - d["pb_y"])
    assert d["k_y"] == pytest.approx(k, rel=1e-5)
    assert d["case1_mx"] == 90 and d["case1_my"] == pytest.approx(22 + k * 25.92, rel=1e-5)
    assert d["case2_mx"] == 90 and d["case2_my"] == pytest.approx(24 + k * 25.92, rel=1e-5)  # Pu e_y,min = 24 > 22
    assert d["alpha_n"] == pytest.approx(1 + (1200 / puz - 0.2) / 0.6, rel=1e-5)
    assert d["ratio_case2"] > d["ratio_case1"] and d["ratio_case2"] <= 1.0
    assert d["tie_pitch"] == 175 and d["tie_pitch_allow"] == 192  # 16 x 12
    assert d["lap"] == pytest.approx(12 * 0.87 * 500 / (4 * 1.4 * 1.6 * 1.25), abs=0.1)  # 466 > 24 x 12


def test_every_lighter_arrangement_fails():
    inp = ColumnInput()
    cover = col.effective_cover(inp)
    gx, gy = col.axis_geometry(inp, "x"), col.axis_geometry(inp, "y")
    chosen = design_column(inp)["reinforcement"]["main"]
    for arr in col.candidates(inp, cover):
        if (arr.dia, arr.n_b, arr.n_d) == (chosen["dia"], chosen["n_b"], chosen["n_d"]):
            break
        assert not col.evaluate(inp, arr, gx, gy).ok, arr.label()
    else:
        pytest.fail("the chosen arrangement is not among the candidates")


@pytest.mark.parametrize("end, k, sway", [("a", 0.65, False), ("b", 0.80, False), ("c", 1.00, False), ("d", 1.20, True),
                                          ("e", 1.50, True), ("f", 2.00, True), ("g", 2.00, True)])
def test_table_28_factors(end, k, sway):
    g = col.axis_geometry(ColumnInput(end_x=end), "x")
    assert (g.k, g.sway, g.le) == (k, sway, pytest.approx(k * 3600))
    assert g.free_end == (end == "g")


def test_custom_factor_and_separate_length_about_y():
    g = col.axis_geometry(ColumnInput(end_y="custom", k_y=1.75, sway_y=True, unsupported_length_y_mm=2400), "y")
    assert (g.k, g.sway, g.length, g.le) == (1.75, True, 2400, pytest.approx(4200))


def test_minimum_eccentricity_has_a_floor_of_20_mm():
    g = col.axis_geometry(ColumnInput(width_mm=300, unsupported_length_mm=1000), "y")
    assert g.e_min == 20.0  # 2 + 10
    g = col.axis_geometry(ColumnInput(depth_mm=900, width_mm=300, unsupported_length_mm=6000), "x")
    assert g.e_min == pytest.approx(42.0)


def test_initial_moment_rules():
    # braced slender: 0.4 M1 + 0.6 M2, not less than 0.4 M2; M1 negative in double curvature
    g = col.axis_geometry(ColumnInput(muy_knm=50, muy_other_knm=-40), "y")
    assert g.m_initial == pytest.approx(0.4 * 50)  # 0.4(-40) + 30 = 14 < 20
    g = col.axis_geometry(ColumnInput(muy_knm=50, muy_other_knm=40), "y")
    assert g.m_initial == pytest.approx(0.4 * 40 + 0.6 * 50)
    # sway: the larger end moment itself; short: the larger end moment, no additional moment
    g = col.axis_geometry(ColumnInput(end_y="d", muy_knm=50, muy_other_knm=-40), "y")
    assert g.m_initial == 50 and g.ma > 0
    g = col.axis_geometry(ColumnInput(), "x")
    assert g.m_initial == 90 and g.ma == 0.0


def test_total_moment_never_below_the_larger_end_moment():
    inp = ColumnInput(muy_knm=60, muy_other_knm=-60, pu_kn=200)
    gx, gy = col.axis_geometry(inp, "x"), col.axis_geometry(inp, "y")
    c1, c2 = col.design_moments(inp, gx, gy, 1.0, 0.05)
    assert gy.m_initial == pytest.approx(24.0)  # 0.4 x 60
    assert c1.my == 60 and c2.my == 60  # 24 + 0.05 x Ma is below M2


def test_minimum_eccentricity_is_applied_about_one_axis_at_a_time():
    inp = ColumnInput(mux_knm=5, mux_other_knm=0, muy_knm=5, muy_other_knm=0, unsupported_length_mm=3000, width_mm=400, depth_mm=400)
    gx, gy = col.axis_geometry(inp, "x"), col.axis_geometry(inp, "y")
    c1, c2 = col.design_moments(inp, gx, gy, 1.0, 1.0)
    emin = 1200 * 20 / 1000
    assert (c1.mx, c1.my) == (pytest.approx(emin), 5) and (c2.mx, c2.my) == (5, pytest.approx(emin))


@pytest.mark.parametrize("ratio, expected", [(0.0, 1.0), (0.2, 1.0), (0.5, 1.5), (0.8, 2.0), (1.0, 2.0)])
def test_alpha_n(ratio, expected):
    assert col.alpha_n(ratio) == pytest.approx(expected)


def test_reduction_factor_is_one_when_the_load_is_below_balanced():
    r = design_column(ColumnInput(pu_kn=150, mux_knm=60, mux_other_knm=-30, muy_knm=20, muy_other_knm=0))
    assert r["data"]["k_y"] == 1.0 and r["data"]["pb_y"] > 150


def test_axially_loaded_short_column_uses_clause_39_3():
    r = design_column(ColumnInput(pu_kn=1500, mux_knm=0, mux_other_knm=0, muy_knm=0, muy_other_knm=0, unsupported_length_mm=3000, width_mm=400, depth_mm=400))
    d = r["data"]
    assert d["axial_only"] and d["mux1"] is None and r["charts"] == []
    asc = d["asc"]
    assert d["pu_cap_393"] == pytest.approx((0.4 * 25 * (160000 - asc) + 0.67 * 500 * asc) / 1000, rel=1e-6)
    assert "axial" in checks(r) and "biaxial_1" not in checks(r)


def test_axially_loaded_column_with_large_minimum_eccentricity_is_checked_in_bending():
    r = design_column(ColumnInput(pu_kn=900, mux_knm=0, mux_other_knm=0, muy_knm=0, muy_other_knm=0, unsupported_length_mm=3000, width_mm=300, depth_mm=300))
    # e_min = 6 + 10 = 16 -> 20 mm > 0.05 x 300 = 15 mm
    assert not r["data"]["axial_only"] and "biaxial_1" in checks(r)
    assert any("Cl. 39.3" in f["ref"] for f in r["sheet"]["flags"])


def test_cantilever_column_is_checked_against_clause_25_3_2():
    r = design_column(ColumnInput(end_x="g", end_y="g", unsupported_length_mm=3000, width_mm=400, depth_mm=400, pu_kn=300, mux_knm=80,
                                  mux_other_knm=0, muy_knm=40, muy_other_knm=0))
    c = checks(r)
    assert c["l_cantilever_x"]["rhs"] == pytest.approx(100 * 400**2 / 400) and c["l_cantilever_x"]["ok"]


def test_length_limit_failure_is_reported():
    r = design_column(ColumnInput(width_mm=200, depth_mm=200, unsupported_length_mm=12500, pu_kn=40, mux_knm=1, mux_other_knm=0,
                                  muy_knm=1, muy_other_knm=0, max_steel_pct=6.0))
    assert r["status"] in ("not_ok", "stopped")
    if r["status"] == "not_ok":
        assert not checks(r)["l_max"]["ok"]
    else:
        assert not [i for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "check" and i["id"] == "l_max"][0]["ok"]


def test_overloaded_column_stops_with_advice():
    r = design_column(ColumnInput(pu_kn=6000))
    assert r["status"] == "stopped" and "increase the section" in r["stop_message"]
    assert r["bbs"] is None and r["drawing"] is None and r["charts"] == []


@pytest.mark.parametrize("n, s, expected", [(2, 200, []), (3, 120, [1]), (5, 52, [2]), (5, 100, [1, 2, 3]), (6, 60, [2, 4])])
def test_cross_tie_rule(n, s, expected):
    assert col.restrained_bars(n, s) == expected
    if s <= 75:  # every untied bar sits next to a tied one (corners are tied)
        tied = {0, n - 1, *expected}
        assert all(i in tied or (i - 1 in tied and i + 1 in tied) or i - 1 in tied or i + 1 in tied for i in range(n))


def test_tie_rules():
    r = design_column(ColumnInput(main_bar_dia_mm=25, pu_kn=2000))
    assert r["data"]["tie_pitch_allow"] == 300 and r["reinforcement"]["ties"]["spacing"] == 300  # least of 300, 400, 300
    assert checks(r)["tie_dia"]["rhs"] == pytest.approx(25 / 4)
    r = design_column(ColumnInput(main_bar_dia_mm=32, tie_dia_mm=8, pu_kn=2600, width_mm=400, depth_mm=500))
    assert checks(r)["tie_dia"]["ok"]  # 32 / 4 = 8


def test_cover_rules():
    r = design_column(ColumnInput(clear_cover_mm=25, tie_dia_mm=8))
    c = checks(r)
    assert not c["cover"]["ok"] and not c["cover_bar"]["ok"] and r["status"] == "not_ok"
    assert col.min_longitudinal_cover(ColumnInput(width_mm=200, depth_mm=200), 12) == 25.0
    assert col.min_longitudinal_cover(ColumnInput(), 12) == 40.0
    assert col.min_longitudinal_cover(ColumnInput(), 45) == 45.0


@pytest.mark.parametrize(
    "bad",
    [
        dict(width_mm=200, depth_mm=900),  # a wall
        dict(mux_other_knm=-120),
        dict(muy_other_knm=31),
        dict(pu_kn=0),
        dict(fck=15),
        dict(end_x="z"),
        dict(k_x=4.0),
        dict(max_steel_pct=7),
        dict(unknown=1),
    ],
)
def test_invalid_input_is_rejected(bad):
    with pytest.raises(ValidationError):
        ColumnInput(**bad)


def test_schedule_quantities_and_drawing():
    r = design_column(ColumnInput())
    items = {i["mark"]: i for i in r["bbs"]["items"]}
    lap = r["reinforcement"]["lap"]
    assert items["a"]["count"] == 12 and items["a"]["cutting_length_mm"] == math.ceil((3600 + 450 + lap) / 5) * 5
    assert items["b"]["count"] == 21  # floor((3600 - 100) / 175) + 1
    a, b = 300 - 64, 450 - 64
    assert items["b"]["dims"] == {"A": a, "B": b, "hook": 80} and items["b"]["cutting_length_mm"] == math.ceil((2 * (a + b) + 160 - 96) / 5) * 5
    for it in r["bbs"]["items"]:
        assert it["weight_kg"] == pytest.approx(it["count"] * it["cutting_length_mm"] / 1000 * bar_unit_weight(it["dia"]), abs=0.01)
    q = r["quantities"]
    assert q["concrete_m3"] == pytest.approx(0.3 * 0.45 * 3.6) and q["formwork_m2"] == pytest.approx(2 * 0.75 * 3.6)
    sec, elev = r["drawing"]["views"]
    assert len([i for i in sec["items"] if i["t"] == "circle"]) == 12
    assert all(0 < c["cx"] < 300 and 0 < c["cy"] < 450 for c in sec["items"] if c["t"] == "circle")
    assert len([i for i in elev["items"] if i["t"] == "line" and i["layer"] == "stirrup"]) == 21


def test_charts_show_capacity_and_design_forces():
    r = design_column(ColumnInput())
    cx, cy = r["charts"]
    assert (cx["id"], cy["id"]) == ("interaction_x", "interaction_y")
    curve = cx["series"][0]["points"]
    assert [p for _, p in curve] == sorted(p for _, p in curve) and curve[0][1] == 0
    # about x both cases give 90 kN m: one point; about y they differ: two points
    assert cx["series"][1] == {"name": "Design forces", "kind": "point", "points": [[90.0, 1200.0]], "labels": ["Cases 1 and 2"]}
    assert len(cy["series"][1]["points"]) == 2 and cy["series"][1]["labels"] == ["Case 1", "Case 2"]
    # the capacity curve passes through the solved capacity at Pu
    mux1 = r["data"]["mux1"]
    above = next(i for i, (_, p) in enumerate(curve) if p >= 1200)
    (m0, p0), (m1, p1) = curve[above - 1], curve[above]
    assert m0 + (m1 - m0) * (1200 - p0) / (p1 - p0) == pytest.approx(mux1, rel=0.03)


def test_every_line_cites_a_reference_and_the_result_is_json_safe():
    r = design_column(ColumnInput(end_x="d", end_y="d", unsupported_length_mm=4500, width_mm=350, pu_kn=1500, mux_knm=120, mux_other_knm=-100))
    for s in r["sheet"]["sections"]:
        for i in s["items"]:
            assert i["ref"], i
    text = json.dumps(r, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    grid = itertools.product(
        ((230, 230), (300, 450), (450, 300), (400, 600)),
        (2500, 4500, 8000),
        ("c", "d"),
        ((20, 415), (25, 500), (40, 550)),
        ((300, 20, 10), (1500, 80, 40), (3000, 150, 120)),
    )
    n = n_ok = 0
    for (b, D), lu, end, (fck, fy), (pu, mx, my) in grid:
        inp = ColumnInput(width_mm=b, depth_mm=D, unsupported_length_mm=lu, end_x=end, end_y=end, fck=fck, fy=fy, exposure="mild",
                          pu_kn=pu, mux_knm=mx, mux_other_knm=-mx / 2, muy_knm=my, muy_other_knm=my / 2)
        r = design_column(inp)
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            assert r["stop_message"]
            continue
        d = r["data"]
        assert 0.8 - 1e-9 <= d["p_pct"] <= 4.0 + 1e-9
        assert d["puz"] > pu
        if not d["axial_only"]:
            assert max(d["ratio_case1"], d["ratio_case2"]) <= 1.0 + 1e-9
            assert 1.0 <= d["alpha_n"] <= 2.0 and 0.0 <= d["k_x"] <= 1.0 and 0.0 <= d["k_y"] <= 1.0
            for case in ("case1", "case2"):
                assert d[f"{case}_mx"] >= mx - 1e-9 and d[f"{case}_my"] >= my - 1e-9
        assert d["tie_pitch"] <= min(b, D, 16 * r["reinforcement"]["main"]["dia"], 300)
        assert r["reinforcement"]["main"]["dia"] / 4 <= r["reinforcement"]["ties"]["dia"]
        if r["status"] == "ok":
            n_ok += 1
            assert r["checks_passed"] == r["checks_total"]
    assert n == 216 and n_ok > 90


def test_development_length_used_for_laps_is_the_compression_value():
    inp = ColumnInput(main_bar_dia_mm=20)
    r = design_column(inp)
    assert r["reinforcement"]["lap"] == round(max(is456.development_length(20, 25, 500, compression=True), 24 * 20))
