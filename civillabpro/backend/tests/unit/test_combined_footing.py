"""Combined footing engine (STR-020): plan, statics, sections, checks, detailing."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.modules.structural.domain import combined_footing as cf
from app.modules.structural.domain.combined_footing import CombinedFootingInput, design_combined_footing


def _failed(r):
    return [i["id"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "check" and not i["ok"]]


def test_worked_example():
    r = design_combined_footing(CombinedFootingInput())
    d = r["data"]
    assert r["status"] == "ok" and r["key_results"][0]["value"] == "6100 x 1950 x 900"
    assert (d["a"], d["L"], d["B"], d["D"]) == (975, 6100, 1950, 900)
    assert d["x_r"] == pytest.approx(1200 * 3600 / 2100)
    assert d["e"] == pytest.approx(975 + 1200 * 3600 / 2100 - 3050)
    assert d["q_max"] <= 200 and d["q_min"] > 0
    # sagging at the outer faces, hogging between the columns; the greatest of each nearly equal (the plan was chosen so)
    assert d["m_faces"][0] > 0 and d["m_faces"][3] > 0 and d["m_hog"] > 0
    assert abs(d["m_hog"] - d["m_pos"]) < 0.05 * d["m_pos"]
    assert d["faces"][1] < d["x_hog"] < d["faces"][2]
    assert [p["cols"] for p in d["punching"]] == [[1], [2]] and all(p["tau"] <= p["allow"] for p in d["punching"])


def test_statics_close_and_match_point_loads_outside_the_columns():
    inp = CombinedFootingInput()
    for a, L, B in ((975, 6100, 1950), (700, 6400, 2500), (200, 4550, 2600)):
        plan = cf.make_plan(inp, a, L, B)
        st = cf.Statics(plan, 1.5)
        assert st.shear(L) == pytest.approx(0, abs=1e-6) and st.moment(L) == pytest.approx(0, abs=1e-6)
        assert (st.q(0) + st.q(L)) / 2 * L / 1000 * B / 1000 == pytest.approx(sum(st.pu))
        for x in (st.faces()[0] - 1, st.faces()[1] + 1, (st.faces()[1] + st.faces()[2]) / 2, st.faces()[3] + 1):
            point = st.Bm * ((x / 1000) ** 2 / 2 * st.q0 + st.k * (x / 1000) ** 3 / 6) - sum(
                pu * (x - c.x) / 1000 for pu, c in zip(st.pu, plan.cols, strict=True) if c.x < x)
            assert st.moment(x) == pytest.approx(point, abs=1e-9)
        # spread over the columns, shear and moment are continuous
        for x in st.faces():
            assert st.shear(x - 1e-6) == pytest.approx(st.shear(x + 1e-6), abs=1e-3)


def test_property_line_puts_column_1_at_the_end():
    r = design_combined_footing(CombinedFootingInput(left_end_mm=200))
    d = r["data"]
    assert r["status"] == "ok" and d["a"] == 200 and d["L"] == cf.length_centred(200, 1200 * 3600 / 2100)
    assert d["m_faces"][0] == pytest.approx(0, abs=1e-9)  # no overhang, no moment at the outer face
    assert not any(s["where"] == "left of column 1" for s in d["shear"])
    p1 = d["punching"][0]
    dp = p1["d"]
    assert p1["b0"] == pytest.approx(2 * (400 + dp / 2) + (400 + dp))  # three sides: the end of the footing is the fourth
    assert d["bands"][0]["lo"] == 0


def test_validation():
    with pytest.raises(ValidationError, match="300 mm apart"):
        CombinedFootingInput(spacing_mm=650)
    with pytest.raises(ValidationError, match="cannot cut column 1"):
        CombinedFootingInput(left_end_mm=150)
    with pytest.raises(ValidationError, match="strap"):
        CombinedFootingInput(left_end_mm=300, p1_service_kn=2000)
    with pytest.raises(ValidationError, match="does not reach past column 2"):
        CombinedFootingInput(left_end_mm=500, length_mm=4200)
    with pytest.raises(ValidationError, match="would cut a column"):
        CombinedFootingInput(length_mm=3000)
    with pytest.raises(ValidationError, match="wider than both columns"):
        CombinedFootingInput(width_mm=500, column1_width_mm=500)
    # with the length entered as well, the heavier column can sit at the property line: the pressure is then not uniform
    r = design_combined_footing(CombinedFootingInput(left_end_mm=300, p1_service_kn=2000, length_mm=5400, width_mm=3400))
    assert r["data"]["e"] < -100 and r["data"]["q_u_left"] > r["data"]["q_u_right"]


def test_given_length_is_centred_and_given_plan_is_kept():
    r = design_combined_footing(CombinedFootingInput(length_mm=6600))
    assert r["data"]["a"] == cf.left_end_centred(6600, 1200 * 3600 / 2100) and abs(r["data"]["e"]) <= 12.5 + 1e-9
    r = design_combined_footing(CombinedFootingInput(length_mm=6400, left_end_mm=700, width_mm=2500))
    d = r["data"]
    assert (d["L"], d["a"], d["B"]) == (6400, 700, 2500) and d["e"] == pytest.approx(700 + 1200 * 3600 / 2100 - 3200)


def test_least_depth_and_entered_depth():
    inp = CombinedFootingInput()
    r = design_combined_footing(inp)
    d = r["data"]
    plan = cf.make_plan(inp, d["a"], d["L"], d["B"])
    st = cf.Statics(plan, inp.load_factor)
    assert cf.passes(cf.trial(inp, plan, st, d["D"], d["cover"]))
    assert not cf.passes(cf.trial(inp, plan, st, d["D"] - 50, d["cover"]))
    thin = design_combined_footing(CombinedFootingInput(length_mm=6100, width_mm=1950, depth_mm=600))
    assert thin["status"] == "not_ok" and all(f.startswith(("shear", "punching")) for f in _failed(thin))
    assert any("fails a shear check" in f["message"] for f in thin["sheet"]["flags"])
    stop = design_combined_footing(CombinedFootingInput(length_mm=6100, width_mm=1950, depth_mm=200, p1_service_kn=3000, p2_service_kn=3000))
    assert stop["status"] == "stopped" and stop["stop_message"].startswith("The depth entered needs compression steel")


def test_left_end_balances_the_moments_and_keeps_the_footing_longer_than_wide():
    inp = CombinedFootingInput()
    ends = cf.left_ends(inp)
    r = design_combined_footing(inp)
    assert r["data"]["a"] == min(ends, key=lambda a: (cf.balance(inp, a), a))
    close = CombinedFootingInput(spacing_mm=1050, p1_service_kn=1500, p2_service_kn=1500, sbc_kn_m2=250)
    r = design_combined_footing(close)
    d = r["data"]
    assert r["status"] == "ok" and d["L"] >= d["B"]
    assert [p["cols"] for p in d["punching"]] == [[1, 2]]  # the two perimeters overlap: one outline round both
    assert [sc["where"] for sc in d["shear"]] == ["left of column 1", "right of column 2"]  # the gap between them is less than d


def test_merged_punching_outline():
    inp = CombinedFootingInput(spacing_mm=1050, p1_service_kn=1500, p2_service_kn=1500, sbc_kn_m2=250, column2_width_mm=600)
    plan = cf.make_plan(inp, 1300, 3650, 3650)
    st = cf.Statics(plan, 1.5)
    (p,) = cf.punching_zones(plan, st, 700)
    x0, x1 = 1300 - 200 - 350, 1300 + 1050 + 225 + 350
    h1, h2 = 400 + 700, 600 + 700
    assert p.b0 == pytest.approx(2 * (x1 - x0) + h1 + h2 + (h2 - h1))
    overlap = (1300 + 200 + 350) - (1300 + 1050 - 225 - 350)
    area = (400 + 700) * (h1) + (450 + 700) * h2 - overlap * h1
    assert p.vp == pytest.approx(sum(st.pu) - st.q(1825) * area / 1e6, rel=2e-3)  # q nearly uniform here


def test_bends_and_widening():
    bottom = design_combined_footing(CombinedFootingInput(sbc_kn_m2=300, p1_service_kn=2500, p2_service_kn=800, column1_width_mm=450,
                                                          column1_depth_mm=450, column2_width_mm=450, column2_depth_mm=450, spacing_mm=2400, fck=30))
    assert bottom["status"] == "ok" and bottom["data"]["bent_bottom"]
    assert bottom["bbs"]["items"][0]["shape"] == "bent up 90 deg both ends"
    band = design_combined_footing(CombinedFootingInput(sbc_kn_m2=450, p1_service_kn=600, p2_service_kn=800, column1_width_mm=450, column1_depth_mm=450,
                                                        column2_width_mm=450, column2_depth_mm=450, spacing_mm=4000, fck=20, exposure="mild"))
    assert band["status"] == "ok" and all(b["bent"] for b in band["data"]["bands"])
    wide = design_combined_footing(CombinedFootingInput(sbc_kn_m2=600, p1_service_kn=600, p2_service_kn=2000, column1_width_mm=450, column1_depth_mm=450,
                                                        column2_width_mm=450, column2_depth_mm=450, spacing_mm=4000, fck=20, exposure="mild"))
    assert wide["status"] == "ok" and any("so that the bars across can be anchored" in f["message"] for f in wide["sheet"]["flags"])
    narrow = design_combined_footing(CombinedFootingInput(sbc_kn_m2=600, p1_service_kn=600, p2_service_kn=2000, column1_width_mm=450,
                                                          column1_depth_mm=450, column2_width_mm=450, column2_depth_mm=450, spacing_mm=4000, fck=20,
                                                          exposure="mild", left_end_mm=225, width_mm=650))
    assert narrow["status"] == "stopped" and "bars across cannot be developed" in narrow["stop_message"]


def test_schedule_quantities_drawing_and_charts():
    r = design_combined_footing(CombinedFootingInput())
    items = r["bbs"]["items"]
    assert [i["description"].split(",")[0] for i in items] == ["Bars along", "Bars along", "Bars across", "Bars across"]
    rf = r["reinforcement"]
    assert items[2]["count"] == rf["bands"][0]["count"] + rf["bands"][1]["count"]  # same bars in both bands: one row
    assert items[3]["count"] == rf["dist"]["count"] == sum(s["count"] for s in rf["dist"]["segments"])
    assert items[0]["cutting_length_mm"] == 6100 - 100 and items[2]["cutting_length_mm"] == 1950 - 100
    assert r["bbs"]["total_weight_kg"] == pytest.approx(sum(i["weight_kg"] for i in items), abs=0.02)
    assert r["quantities"]["concrete_m3"] == pytest.approx(6.1 * 1.95 * 0.9, abs=1e-3)
    assert [v["id"] for v in r["drawing"]["views"]] == ["plan", "elevation", "section"]
    m = r["charts"][0]["series"][0]["points"]
    assert m[0] == [0.0, 0.0] and m[-1][1] == pytest.approx(0, abs=0.01)
    assert min(y for _, y in m) == pytest.approx(-r["data"]["m_hog"], abs=0.01)
    json.dumps(r, allow_nan=False)


def test_distribution_counts_leave_no_gap_wider_than_the_spacing():
    bands = [{"lo": 0.0, "hi": 900.0}, {"lo": 2500.0, "hi": 3600.0}]
    segs = cf_det().distribution_counts(5000.0, 50.0, bands, 200.0)
    assert [s["count"] for s in segs] == [0, 7, 6]  # nothing beyond a band at the end; 1600 / 200 less one; 1350 / 200 rounded down
    # between the bands: 7 bars leave 8 gaps of 200 over 1600


def cf_det():
    from app.modules.structural.domain import combined_footing_detailing

    return combined_footing_detailing


def test_every_line_cites_a_reference():
    for kw in ({}, dict(left_end_mm=200), dict(length_mm=6400, left_end_mm=700, width_mm=2500)):
        r = design_combined_footing(CombinedFootingInput(**kw))
        for s in r["sheet"]["sections"]:
            for i in s["items"]:
                assert i["ref"], i


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    grid = itertools.product((300, 450), ((600, 1500), (1200, 1200), (2200, 900)), (100, 250, 450), (1800, 4000), ((20, 415), (30, 500)))
    n = n_ok = 0
    for b, (p1, p2), sbc, s, (fck, fy) in grid:
        try:
            inp = CombinedFootingInput(column1_width_mm=b, column1_depth_mm=b, column2_width_mm=b, column2_depth_mm=b, p1_service_kn=p1, p2_service_kn=p2,
                                       sbc_kn_m2=sbc, spacing_mm=s, fck=fck, fy=fy, exposure="mild" if fck == 20 else "moderate")
        except ValidationError:
            continue
        r = design_combined_footing(inp)
        n += 1
        json.dumps(r, allow_nan=False)
        assert r["status"] != "stopped", (b, p1, p2, sbc, s, fck, fy, r["stop_message"])
        d = r["data"]
        if r["status"] == "not_ok":
            assert set(_failed(r)) <= {"bearing1", "bearing2"}, _failed(r)
        assert d["q_max"] <= sbc + 1e-6 and d["q_min"] >= -1e-6 and d["L"] >= d["B"]
        assert d["as_prov_bottom"] >= d["as_bottom"] - 1e-6 and d["as_prov_top"] >= d["as_top"] - 1e-6
        assert all(b_["as_prov"] >= b_["as_req"] - 1e-6 for b_ in d["bands"])
        assert all(sc["tau"] <= sc["tc"] + 1e-9 for sc in d["shear"]) and all(p["tau"] <= p["allow"] + 1e-9 for p in d["punching"])
        assert math.isfinite(d["m_hog"]) and d["D"] >= 300
        n_ok += r["status"] == "ok"
    assert n == 72 and n_ok >= 45
    # what does not pass is the bearing under small, heavily loaded columns (reported with its remedy), never a stop


def test_column_moments_move_the_plan_and_enter_the_statics_as_couples():
    base = design_combined_footing(CombinedFootingInput())["data"]
    inp = CombinedFootingInput(m2_service_knm=150)
    assert inp.resultant_offset() == pytest.approx((1200 * 3600 + 150_000) / 2100)
    r = design_combined_footing(inp)
    d = r["data"]
    assert r["status"] == "ok" and abs(d["e"]) <= 25 + 1e-9  # centred on the loads and the moments
    assert d["a"] + d["x_r"] - d["L"] / 2 == pytest.approx(d["e"])
    assert d["x_r"] > base["x_r"] and d["mu2"] == pytest.approx(225)
    assert any("one load case" in f["message"] for f in r["sheet"]["flags"])
    # on a given plan, a clockwise moment at column 2 bears harder on the right; the statics still close
    fixed = dict(length_mm=6100, width_mm=2100, left_end_mm=975)
    plain = design_combined_footing(CombinedFootingInput(**fixed))["data"]
    turned = design_combined_footing(CombinedFootingInput(**fixed, m2_service_knm=150))["data"]
    assert turned["q_u_right"] > plain["q_u_right"] and turned["q_u_left"] < plain["q_u_left"]
    plan = cf.make_plan(CombinedFootingInput(**fixed, m1_service_knm=-80, m2_service_knm=200), 975, 6100, 2100)
    st = cf.Statics(plan, 1.5)
    assert st.moment(6100) == pytest.approx(0, abs=1e-6) and st.shear(6100) == pytest.approx(0, abs=1e-6)
    # across a column the bending jumps by the couple, beyond what the load alone gives
    c = plan.cols[1]
    load_only = cf.Statics(cf.make_plan(CombinedFootingInput(**fixed), 975, 6100, 2100), 1.5)
    jump = (st.moment(c.hi) - st.moment(c.lo)) - (load_only.moment(c.hi) - load_only.moment(c.lo))
    k_shift = st.k - load_only.k  # the pressure itself changes with the moments: take its share out
    q_part = st.Bm * k_shift * ((c.hi / 1000) ** 3 - (c.lo / 1000) ** 3) / 6 + st.Bm * (st.q0 - load_only.q0) * ((c.hi / 1000) ** 2 - (c.lo / 1000) ** 2) / 2
    assert jump - q_part == pytest.approx(1.5 * 200, rel=1e-9)
