"""Footing engine: the worked example, each rule, stop states, validation and a sweep."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.engineering import is456
from app.engineering.rebar import bar_area, bar_unit_weight
from app.modules.structural.domain import footing as ft
from app.modules.structural.domain.footing import FootingInput, design_footing


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def test_worked_example():
    r = design_footing(FootingInput())
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"]
    assert (d["L"], d["B"]) == (2200.0, 2050.0) and d["cover"] == 50.0
    assert d["q_max"] == pytest.approx(880 / (2.2 * 2.05))
    assert d["qu"] == pytest.approx(1200 / (2.2 * 2.05))
    a_l = (2200 - 450) / 2
    assert d["m_l"] == pytest.approx(d["qu"] * 2.05 * (a_l / 1000) ** 2 / 2, rel=1e-9)
    assert d["D"] == 450.0 and d["dia"] == 20
    # the depth is the least with straight bars: 50 mm less has no straight-bar design (bent ends are the fallback)
    assert not d["bent_ends"]
    for dia in ft.FOOTING_BAR_DIAMETERS:
        t = ft.trial(FootingInput(), 2200, 2050, 400.0, dia, 50.0, d["qu"])
        assert not (t.ok_flexure and t.ok_spacing and t.ok_shear and t.ok_anchorage and not t.bent_ends)
    assert d["ks"] == 1.0  # 0.5 + 300/450 = 1.17, not more than 1
    assert d["tau_p_allow"] == pytest.approx(1.0 * 0.25 * 5)


def test_plan_sizing_with_moments_keeps_contact_and_bearing():
    inp = FootingInput(m_l_service_knm=150, m_b_service_knm=40)
    r = design_footing(inp)
    d = r["data"]
    assert d["q_max"] <= 200 + 1e-6 and d["q_min"] >= -1e-6
    # one step smaller fails one of the two limits
    L, B = d["L"] - 50, d["B"] - 50
    pr = ft.service_pressures(inp, L / 1000, B / 1000)
    assert pr.q_max > 200 or pr.q_min < 0
    assert any("safe side with moments" in f["message"] for f in r["sheet"]["flags"])


def test_central_band_rule():
    r = design_footing(FootingInput(length_mm=4000, width_mm=2000, column_depth_mm=600, p_service_kn=1200))
    d = r["data"]
    beta = 2.0
    band_req = d["as_b"] * 2 / (beta + 1)
    assert d["n_b_outer"] > 0
    assert d["n_b_band"] * bar_area(d["dia"]) >= band_req - 1e-6
    assert checks(r)["band"]["ok"]
    items = [i for i in r["bbs"]["items"] if "outer" in i["description"]]
    assert items and items[0]["count"] == 2 * d["n_b_outer"]


def test_nearly_square_footing_spreads_the_short_bars_uniformly():
    n_band, s_band, n_out, s_out, area = ft.bars_short_direction(2000.0, 2200.0, 2050.0, 16, 300.0, 50.0)
    assert s_band == s_out  # one uniform spacing over the length
    assert n_band * bar_area(16) >= 2000 * 2 / (2200 / 2050 + 1) - 1e-6
    assert area >= 2000


def test_entered_depth_is_checked_as_it_is():
    r = design_footing(FootingInput(length_mm=2200, width_mm=2050, depth_mm=350))
    c = checks(r)
    assert r["status"] == "not_ok" and r["data"]["D"] == 350
    assert not c["punching"]["ok"]
    assert any("depth entered fails a shear check" in f["message"] for f in r["sheet"]["flags"])


def test_bearing_failure_is_reported_with_the_remedy():
    r = design_footing(FootingInput(column_width_mm=230, column_depth_mm=230, p_service_kn=1000, fck=30))
    c = checks(r)
    assert not c["bearing"]["ok"] and r["status"] == "not_ok"
    assert c["bearing"]["rhs"] == pytest.approx(0.45 * 30 * 2)  # sqrt(A1/A2) capped at 2
    assert any("dowels" in f["message"] for f in r["sheet"]["flags"])


def test_bearing_area_stays_within_a_one_in_two_frustum():
    r = design_footing(FootingInput(column_width_mm=500, column_depth_mm=2000, p_service_kn=1200, sbc_kn_m2=100))
    d, c = r["data"], checks(r)
    assert r["status"] == "ok" and (d["L"], d["B"], d["D"]) == (4500, 3000, 350)
    by_plan = min(d["L"] / 2000, d["B"] / 500, 2.0)  # 2.0: the plan alone would allow the full increase
    by_depth = 1 + 4 * d["D"] / 2000  # 1.7: the frustum reaches only 2 D beyond each face
    assert by_depth < by_plan and c["bearing"]["rhs"] == pytest.approx(0.45 * 25 * by_depth)


def test_anchorage_drives_the_bar_size():
    r = design_footing(FootingInput())
    d = r["data"]
    avail = min((2200 - 450) / 2, (2050 - 300) / 2) - 50
    assert d["ld"] <= avail and d["ld"] == pytest.approx(is456.development_length(d["dia"], 25, 415))
    assert is456.development_length(25, 25, 415) > avail  # T25 would not fit the projection


def test_cover_rules():
    assert ft.effective_cover(FootingInput()) == 50.0
    assert ft.effective_cover(FootingInput(exposure="severe", fck=30)) == 50.0
    assert ft.effective_cover(FootingInput(exposure="extreme", fck=40)) == 75.0
    r = design_footing(FootingInput(clear_cover_mm=40))
    assert not checks(r)["cover"]["ok"]


def test_stop_and_validation():
    r = design_footing(FootingInput(length_mm=4000, width_mm=4000, depth_mm=200, p_service_kn=3000, sbc_kn_m2=300))
    assert r["status"] == "stopped" and r["bbs"] is None
    for bad in (dict(length_mm=2000), dict(length_mm=400, width_mm=2000), dict(length_mm=2000, width_mm=250), dict(p_service_kn=0),
                dict(fck=45), dict(clear_cover_mm=30), dict(unknown=1)):
        with pytest.raises(ValidationError):
            FootingInput(**bad)


def test_schedule_quantities_and_drawing():
    r = design_footing(FootingInput())
    d = r["data"]
    items = r["bbs"]["items"]
    assert items[0]["count"] == d["n_l"] and items[0]["cutting_length_mm"] == 2200 - 100
    assert items[1]["cutting_length_mm"] == 2050 - 100
    for it in items:
        assert it["weight_kg"] == pytest.approx(it["count"] * it["cutting_length_mm"] / 1000 * bar_unit_weight(it["dia"]), abs=0.01)
    q = r["quantities"]
    assert q["concrete_m3"] == pytest.approx(2.2 * 2.05 * 0.45, abs=1e-3) and q["formwork_m2"] == pytest.approx(2 * (2.2 + 2.05) * 0.45, abs=1e-3)
    plan, sec = r["drawing"]["views"]
    assert plan["id"] == "plan" and sec["id"] == "elevation"
    assert "NaN" not in json.dumps(r, allow_nan=False)


def test_every_line_cites_a_reference():
    for kw in ({}, dict(m_l_service_knm=80), dict(length_mm=4000, width_mm=2000, column_depth_mm=600)):
        r = design_footing(FootingInput(**kw))
        for s in r["sheet"]["sections"]:
            for i in s["items"]:
                assert i["ref"], i


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    grid = itertools.product(((230, 230), (300, 450), (450, 600)), (300, 900, 2500), (0, 60), (100, 200, 400), ((20, 415), (25, 500), (30, 550)))
    n = n_ok = 0
    for (bc, dc), p, m, sbc, (fck, fy) in grid:
        exposure = "mild" if fck == 20 else "moderate"
        r = design_footing(FootingInput(column_width_mm=bc, column_depth_mm=dc, p_service_kn=p, m_l_service_knm=m, sbc_kn_m2=sbc, fck=fck, fy=fy,
                                        exposure=exposure))
        n += 1
        json.dumps(r, allow_nan=False)
        assert r["status"] != "stopped", ((bc, dc), p, m, sbc, fck, fy, r["stop_message"])
        d = r["data"]
        if r["status"] == "not_ok":
            assert [i["id"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "check" and not i["ok"]] == ["bearing"]
        assert d["q_max"] <= sbc + 1e-6 and d["q_min"] >= -1e-6
        assert d["as_prov_l"] >= d["as_l"] - 1e-6 and d["as_prov_b"] >= d["as_b"] - 1e-6
        assert d["tau_p"] <= d["tau_p_allow"] + 1e-9 and d["tau1_l"] <= d["tc_l"] + 1e-9 and d["tau1_b"] <= d["tc_b"] + 1e-9
        assert d["D"] >= 150 and math.isfinite(d["m_l"])
        if r["status"] == "ok":
            n_ok += 1
    assert n == 162 and n_ok > 100
    # what does not pass is the bearing under small, heavily loaded columns (reported with its remedy), never a stop


def test_short_projections_use_bent_ends():
    r = design_footing(FootingInput(column_width_mm=230, column_depth_mm=230, p_service_kn=300, fy=500))
    d = r["data"]
    assert r["status"] == "ok" and d["bent_ends"]
    avail = min((d["L"] - 230) / 2, (d["B"] - 230) / 2) - 50
    assert avail < d["ld"] <= avail - (4 * d["dia"] + d["dia"]) + 8 * d["dia"]  # straight to the start of the bend (r = 4 phi), plus 8 phi
    item = r["bbs"]["items"][0]
    assert item["shape"] == "bent up 90 deg both ends" and item["dims"]["B"] == 12 * d["dia"]
    assert item["cutting_length_mm"] == math.ceil((d["L"] - 100 + 24 * d["dia"] - 4 * d["dia"]) / 5 - 1e-9) * 5


def test_plan_grows_until_the_bars_can_be_anchored():
    small = dict(column_width_mm=230, column_depth_mm=230, p_service_kn=300, sbc_kn_m2=400, fck=20, exposure="mild")
    inp = FootingInput(**small)
    r = design_footing(inp)
    d = r["data"]
    assert r["status"] == "ok"
    L0, B0 = ft.size_plan(inp)
    assert (L0, B0) == (950.0, 950.0) and d["L"] > L0
    assert any("larger than the 950 x 950 mm" in f["message"] for f in r["sheet"]["flags"])
    # the bars develop at this plan, and the next smaller plan has no design at all
    avail = (d["L"] - 230) / 2 - 50
    assert d["ld"] <= avail - 5 * d["dia"] + 8 * d["dia"]
    smaller = d["L"] - 50
    t, blocked = ft.select_section(inp, smaller, smaller, 50.0, ft.factored_pressure(inp, smaller / 1000, smaller / 1000))
    assert t is None and blocked
    # an entered plan is never changed: too small a one stops with the remedy
    s = design_footing(FootingInput(**small, length_mm=950, width_mm=950))
    assert s["status"] == "stopped" and "too short to develop" in s["stop_message"] and "larger length and width" in s["stop_message"]


def test_enlarge_plan_keeps_equal_projections_and_never_shrinks():
    assert ft.enlarge_plan(950, 950, 230, 230) == (1000, 1000)
    L, B = ft.enlarge_plan(1350, 1200, 300, 450)
    assert (L, B) == (1400, 1250) and (L - 450) / 2 == (B - 300) / 2
