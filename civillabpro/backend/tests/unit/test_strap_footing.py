"""Strap footing engine (STR-044): reactions, plan, the strap, pad 1, pad 2 by the isolated footing, outputs."""

import itertools
import json

import pytest
from pydantic import ValidationError

from app.modules.structural.domain import footing as iso
from app.modules.structural.domain import strap_footing as sf
from app.modules.structural.domain.strap_footing import StrapFootingInput, design_strap_footing


def _failed(r):
    return [i["id"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "check" and not i["ok"]]


def test_worked_example():
    r = design_strap_footing(StrapFootingInput())
    d = r["data"]
    assert r["status"] == "ok" and _failed(r) == []
    assert (d["L1"], d["B1"], d["e"]) == (1600, 3200, 600)
    assert d["R1"] == pytest.approx(800 * 4500 / 3900) and d["R1"] + d["R2"] == pytest.approx(2000)
    assert d["strap"]["m_hog"] == pytest.approx(592.0, abs=0.1) and d["strap"]["x_hog"] == pytest.approx(1200 / (1.5 * 800 * 4500 / 3900 / 1.6) * 1000)
    assert d["pad2"]["L"] == 2450 and d["gap"] > 0


def test_statics_close_at_column_2():
    inp = StrapFootingInput()
    for L1 in (1400, 1600, 2000):
        st = sf.StrapStatics(inp, L1, 1.5)
        assert st.moment(st.x2) == pytest.approx(0, abs=1e-6)
        e, r1, r2 = sf.reactions(inp, L1)
        assert st.shear(st.x2) == pytest.approx(1.5 * (r1 - 800))  # the strap pulls column 2 down by R_1 - P_1
        assert r1 * (inp.spacing_mm - e) == pytest.approx(800 * inp.spacing_mm)


def test_pad1_is_the_shortest_no_wider_than_twice_its_length():
    inp = StrapFootingInput()
    L1, B1 = sf.pad1_plan(inp)
    assert B1 <= 2 * L1
    _, r1, _ = sf.reactions(inp, L1 - 50)
    import math
    shorter_b = max(700, math.ceil(r1 * 1.1 / 200 * 1e6 / (L1 - 50) / 50 - 1e-9) * 50)
    assert shorter_b > 2 * (L1 - 50)


def test_pad2_is_the_isolated_footing_for_r2_and_bearing_takes_the_whole_load():
    r = design_strap_footing(StrapFootingInput())
    d = r["data"]
    alone = iso.design_footing(sf._pad2_input(StrapFootingInput(), d["R2"]))
    assert {k: d["pad2"][k] for k in ("L", "B", "D", "as_prov_l", "tau_p")} == {k: alone["data"][k] for k in ("L", "B", "D", "as_prov_l", "tau_p")}
    assert d["bearing"][1]["sigma"] == pytest.approx(1.5 * 1200 * 1e3 / (450 * 450))  # P_u2, not R_u2
    assert any(i["id"].startswith("pad2_") for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "check")
    assert not any("Bearing" in f["message"] for f in r["sheet"]["flags"] if "pad 2" in f["message"].lower())


def test_strap_shear_zones_and_stirrups():
    d = design_strap_footing(StrapFootingInput())["data"]["strap"]
    z1, z2 = d["zones"]
    assert z1["name"] == "over pad 1" and z1["vus"] > 0 and z1["s"] <= z1["s_max"]
    assert z2["name"] == "free span" and z2["v"] == pytest.approx(1.5 * (800 * 4500 / 3900 - 800))
    assert d["tau_face"] <= 3.1 and d["side_per_face"] > 0  # 800 deep: side-face bars


def test_setback_column_sags_and_bent_top_bars():
    r = design_strap_footing(StrapFootingInput(left_end_mm=450))
    assert r["status"] == "ok" and r["data"]["strap"]["m_sag"] > 0
    bent = design_strap_footing(StrapFootingInput(fy=500, fck=30))
    assert bent["data"]["strap"]["bent"] and bent["bbs"]["items"][0]["shape"] == "L-bend at one end"


def test_validation_and_stops():
    with pytest.raises(ValidationError, match="cannot cut column 1"):
        StrapFootingInput(left_end_mm=150)
    with pytest.raises(ValidationError, match="both the length and the width of pad 1"):
        StrapFootingInput(pad1_width_mm=3000)
    with pytest.raises(ValidationError, match="past the inner face of column 1"):
        StrapFootingInput(pad1_length_mm=350, pad1_width_mm=3000)
    with pytest.raises(ValidationError, match="at least as wide as column 1"):
        StrapFootingInput(strap_width_mm=300, column1_width_mm=400)
    light = design_strap_footing(StrapFootingInput(p1_service_kn=1500, p2_service_kn=250))
    assert light["status"] == "stopped" and "too light" in light["stop_message"]
    meet = design_strap_footing(StrapFootingInput(spacing_mm=3000, p1_service_kn=400, p2_service_kn=3500, sbc_kn_m2=150))
    assert meet["status"] == "stopped" and "combined footing" in meet["stop_message"]


def test_outputs():
    r = design_strap_footing(StrapFootingInput())
    items = r["bbs"]["items"]
    assert [i["description"].split(",")[0] for i in items[:5]] == ["Strap", "Strap", "Strap", "Strap", "Pad 1"]
    assert items[-1]["description"].startswith("Pad 2")
    assert r["bbs"]["total_weight_kg"] == pytest.approx(sum(i["weight_kg"] for i in items), abs=0.05)
    st = r["reinforcement"]["strap"]
    assert sum(z["count"] for z in st["zones"]) == next(i["count"] for i in items if "stirrups" in i["description"])
    assert [v["id"] for v in r["drawing"]["views"]] == ["plan", "elevation", "section"]
    m = r["charts"][0]["series"][0]["points"]
    assert min(y for _, y in m) == pytest.approx(-592.0, abs=0.5) and m[-1][1] == pytest.approx(0, abs=0.01)
    q = r["quantities"]
    assert q["concrete_m3"] > (1.6 * 3.2 * 0.7 + 2.45 * 2.45 * 0.5)
    json.dumps(r, allow_nan=False)
    for s in r["sheet"]["sections"]:
        for i in s["items"]:
            assert i["ref"], i


def test_sweep_never_breaks_and_ok_results_are_self_consistent():
    grid = itertools.product(((300, 300), (400, 400), (500, 600)), (500, 1000, 1600), (900, 1800), (120, 250), (3500, 6000), ((20, 415), (30, 500)))
    n = n_ok = 0
    for (b, dcol), p1, p2, sbc, s, (fck, fy) in grid:
        inp = StrapFootingInput(column1_width_mm=b, column1_depth_mm=dcol, column2_width_mm=b, column2_depth_mm=dcol, p1_service_kn=p1,
                                p2_service_kn=p2, sbc_kn_m2=sbc, spacing_mm=s, fck=fck, fy=fy, exposure="mild" if fck == 20 else "moderate")
        r = design_strap_footing(inp)
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            assert any(k in r["stop_message"] for k in ("too light", "would meet", "No pad under column 1")), r["stop_message"]
            continue
        d = r["data"]
        if r["status"] == "not_ok":
            assert set(_failed(r)) <= {"bearing1", "bearing2"}, _failed(r)
        assert d["q1"] <= sbc + 1e-6 and d["R2"] > 0 and d["gap"] >= 100
        st = d["strap"]
        assert st["area"] >= st["as_req"] - 1e-6 and st["D"] >= max(d["pad1"]["D"], d["pad2"]["D"])
        assert all(z["s"] <= z["s_max"] + 1e-9 for z in st["zones"])
        n_ok += r["status"] == "ok"
    assert n == 144 and n_ok >= 60
    # what does not pass is the bearing under small, heavily loaded columns (with its remedy), and the two stops above


def test_a_strap_too_narrow_for_any_depth_is_widened_to_the_least_section():
    inp = StrapFootingInput(column1_width_mm=300, column1_depth_mm=300, p1_service_kn=1600, p2_service_kn=1800, sbc_kn_m2=100, spacing_mm=6000)
    r = design_strap_footing(inp)
    d = r["data"]
    st_ = sf.StrapStatics(inp, d["L1"], 1.5)
    x_end = min(d["x2"] + 150 + 300, d["x2"] + d["L2"] / 2)
    assert sf.select_strap(inp, st_, 300, d["pad2"]["D"], 50, x_end) is None  # column 1's width suits no depth
    b = d["strap"]["b"]
    assert b > 300 and any("widened" in i["title"] for s in r["sheet"]["sections"] for i in s["items"])
    areas = {}
    for w in range(350, int(d["B1"] - 200) + 1, 50):
        t = sf.select_strap(inp, st_, w, d["pad2"]["D"], 50, x_end)
        if t is not None:
            areas[w] = w * t.D
    assert b == min(areas, key=lambda w: (areas[w], w))
    assert d["strap"]["D"] <= 4 * b  # a proportionate section, not the narrowest and deepest

