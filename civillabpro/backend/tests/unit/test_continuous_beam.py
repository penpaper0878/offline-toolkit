"""Continuous beam engine: the worked example, each rule, the layout of the bars, stops, validation and a sweep."""

import itertools
import json
import math

import pytest
from pydantic import ValidationError

from app.engineering import is456
from app.engineering.rebar import bar_unit_weight
from app.modules.structural.domain.continuous_beam import ContinuousBeamInput, design_continuous_beam, effective_spans


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def items(res, start):
    return [i for i in res["bbs"]["items"] if i["description"].startswith(start)]


def count(res, *starts):
    """Bars of a group, continuing and curtailed together."""
    return sum(i["count"] for i in res["bbs"]["items"] if i["description"].startswith(starts))


def test_worked_example():
    r = design_continuous_beam(ContinuousBeamInput())
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"]
    wd, wl = 1.5 * (25 + 25 * 0.3 * 0.5), 1.5 * 15
    assert (d["wd"], d["wl"]) == pytest.approx((wd, wl))
    assert d["rule"] == "a" and d["l_end"] == d["l_int"] == 5300  # 300 mm supports are narrow: centre to centre governs
    assert d["m_end"] == pytest.approx((wd / 12 + wl / 10) * 5.3**2, abs=1e-3)
    assert d["m_int"] == pytest.approx((wd / 16 + wl / 12) * 5.3**2, abs=1e-3)
    assert d["m_b"] == pytest.approx((wd / 10 + wl / 9) * 5.3**2, abs=1e-3)
    assert d["m_c"] == pytest.approx((wd / 12 + wl / 9) * 5.3**2, abs=1e-3)
    assert d["v_a"] == pytest.approx((0.40 * wd + 0.45 * wl) * 5.3, abs=1e-3)
    assert d["v_b1"] == pytest.approx(0.60 * (wd + wl) * 5.3, abs=1e-3)
    assert d["v_b2"] == pytest.approx((0.55 * wd + 0.60 * wl) * 5.3, abs=1e-3)
    assert d["v_c"] == pytest.approx((0.50 * wd + 0.60 * wl) * 5.3, abs=1e-3)
    reinf = r["reinforcement"]
    assert reinf["end"]["bottom"]["label"] == "5-T16" and reinf["interior"]["bottom"]["label"] == "4-T16"
    assert reinf["support_b"]["top"]["label"] == "6-T16" and reinf["support_c"]["top"]["label"] == "10-T12 (6+4)"
    for key, m in (("end", d["m_end"]), ("interior", d["m_int"]), ("support_b", d["m_b"]), ("support_c", d["m_c"])):
        assert d[key]["capacity"] >= m and d[key]["xu"] <= d[key]["xu_max"]
        assert d[key]["ast_prov"] >= max(d[key]["ast_req"], d[key]["min_steel"])


def test_three_spans_have_no_c_support():
    r = design_continuous_beam(ContinuousBeamInput(spans=3))
    assert r["status"] == "ok" and r["reinforcement"]["support_c"] is None and "support_c" not in r["data"] and r["data"]["m_c"] == 0
    assert not items(r, "Top bars over interior supports")
    eb, ib = r["reinforcement"]["end"]["bottom"], r["reinforcement"]["interior"]["bottom"]
    assert count(r, "Bottom bars, end spans") == 2 * eb["count"]
    assert count(r, "Bottom bars, interior spans") == ib["count"]


def test_effective_span_rules():
    narrow = ContinuousBeamInput(support_width_mm=300)
    assert effective_spans(narrow, 450) == (5300, 5300, "a")  # min(5000 + 450, 5000 + 300)
    assert effective_spans(narrow, 250) == (5250, 5250, "a")
    wide = ContinuousBeamInput(support_width_mm=600, clear_span_mm=6000)  # 600 > min(6000/12, 600)
    assert effective_spans(wide, 500) == (6250, 6000, "b")  # end span: l_c + min(d/2, w_s/2); interior: l_c


def test_support_uses_the_bottom_bars_as_compression_steel():
    r = design_continuous_beam(ContinuousBeamInput(live_load_kn_m=40))
    d, reinf = r["data"], r["reinforcement"]
    assert d["support_b"]["doubly"] and 0 < d["support_b"]["asc_req"] <= d["support_b"]["asc_prov"]
    assert checks(r)["asc_b"]["ok"]
    assert any("compression steel" in f["message"] for f in r["sheet"]["flags"])
    # the bottom bars continue past the far face of the support by the development length in compression
    eb = reinf["end"]["bottom"]
    ext = max(0.0, is456.development_length(eb["dia"], 25, 500, compression=True) - (300 - reinf["cover"]))
    assert items(r, "Bottom bars, end spans")[0]["dims"]["A"] == pytest.approx(5000 + 2 * (300 - reinf["cover"]) + ext, abs=1)


def test_top_bar_extents_follow_clause_26_2_3_4():
    r = design_continuous_beam(ContinuousBeamInput())
    d, reinf = r["data"], r["reinforcement"]
    sb = reinf["support_b"]
    d_b, phi = d["support_b"]["d"], sb["top"]["dia"]
    need = max(d["hog"]["B_end"] + max(d_b, 12 * phi, 5000 / 16), is456.development_length(phi, 25, 500))
    assert d["ext"]["B_end"] == pytest.approx(min(need, 5000), abs=0.1)
    assert 0 < d["hog"]["B_end"] < d["hog"]["B_int"] < 5000  # the end span's hogging zone is the shorter one


def test_support_bars_that_meet_lap_at_mid_span():
    r = design_continuous_beam(ContinuousBeamInput())
    lay = r["reinforcement"]["layout"]
    span = lay["interior"][0]
    assert span["meet"] and span["hanger"] == 0 and span["a_left"] == span["a_right"] == pytest.approx((5000 + span["lap"]) / 2)
    assert span["lap"] >= max(is456.development_length(16, 25, 500), 30 * 16) - 1e-9
    c = checks(r)["lap_hogging_0"]
    assert c["ok"] and c["lhs"] > 0  # hogging at mid-span under the alternate arrangement, carried by the lapped bars
    top_b = items(r, "Top bars over supports next to the ends")[0]
    assert top_b["dims"]["A"] == pytest.approx(300 + lay["end"]["a_b"] + lay["b_into_interior"], abs=1)


def test_hangers_lap_with_the_support_bars_in_the_end_span():
    r = design_continuous_beam(ContinuousBeamInput())
    lay, cover = r["reinforcement"]["layout"], r["reinforcement"]["cover"]
    h = items(r, "Top hangers, end spans")[0]
    assert h["dims"]["A"] == pytest.approx((300 - cover) + (5000 - lay["end"]["a_b"]) + lay["end"]["lap"], abs=1)
    assert lay["end"]["lap"] == pytest.approx(max(is456.development_length(12, 25, 500, compression=True), 24 * 12))


def test_schedule_counts_cover_the_whole_beam():
    for n in (3, 4, 7):
        r = design_continuous_beam(ContinuousBeamInput(spans=n))
        reinf = r["reinforcement"]
        assert count(r, "Bottom bars, end spans") == 2 * reinf["end"]["bottom"]["count"]
        assert count(r, "Bottom bars, interior spans") == (n - 2) * reinf["interior"]["bottom"]["count"]
        assert count(r, "Top bars over supports next to the ends", "Top bars over B") == 2 * reinf["support_b"]["top"]["count"]
        if n >= 4:
            assert count(r, "Top bars over interior supports", "Top bars over C") == (n - 3) * reinf["support_c"]["top"]["count"]
        per = r["bbs"]["stirrups_per_span"]
        assert items(r, "Stirrups, end spans")[0]["count"] == 2 * per["end"]
        assert items(r, "Stirrups, interior spans")[0]["count"] == (n - 2) * per["interior"]
        for it in r["bbs"]["items"]:
            assert it["weight_kg"] == pytest.approx(it["count"] * it["cutting_length_mm"] / 1000 * bar_unit_weight(it["dia"]), abs=0.01)
        q = r["quantities"]
        assert q["concrete_m3"] == pytest.approx(0.3 * 0.5 * (n * 5.0 + (n + 1) * 0.3), abs=1e-3)


def test_t_beam_uses_0_7_l_and_designs_supports_on_the_web():
    r = design_continuous_beam(ContinuousBeamInput(section="t_beam", width_mm=300, depth_mm=500, flange_thickness_mm=125, flange_width_mm=3000,
                                                   dead_load_kn_m=35, live_load_kn_m=20, clear_span_mm=6000))
    d = r["data"]
    assert r["status"] == "ok"
    assert d["end"]["bf"] == pytest.approx(min(0.7 * d["l_end"] / 6 + 300 + 6 * 125, 3000), abs=0.01)
    assert d["support_b"]["mu_lim"] == pytest.approx(is456.limiting_moment(25, 500, 300, d["support_b"]["d"]) / 1e6, rel=1e-4)
    assert d["w_self"] == pytest.approx(25 * 0.3 * 0.375)
    assert any("Cl. 23.1.1(b)" in f["ref"] for f in r["sheet"]["flags"])


def test_drawing_views():
    r = design_continuous_beam(ContinuousBeamInput())
    elev, secs = r["drawing"]["views"]
    assert elev["id"] == "elevation" and secs["id"] == "sections"
    texts = [i["text"] for i in secs["items"] if i["t"] == "text"]
    assert "A-A: mid-span of the end span" in texts and "B-B: at the support next to the end" in texts
    assert any("past the break" in i.get("text", "") for i in elev["items"] if i["t"] == "dim")
    assert "NaN" not in json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("bad", [dict(spans=2), dict(section="t_beam", flange_thickness_mm=450), dict(dead_load_kn_m=0, live_load_kn_m=0,
                                                                                                        include_self_weight=False), dict(unknown=1)])
def test_invalid_input(bad):
    with pytest.raises(ValidationError):
        ContinuousBeamInput(**bad)


@pytest.mark.parametrize("ov, message", [
    (dict(clear_span_mm=1000, depth_mm=600), "The effective span is less than 2.5 times"),
    (dict(depth_mm=300, width_mm=200, dead_load_kn_m=80, live_load_kn_m=60, clear_span_mm=7000), "No arrangement"),
])
def test_stops(ov, message):
    r = design_continuous_beam(ContinuousBeamInput(**ov))
    assert r["status"] == "stopped" and r["stop_message"].startswith(message) and r["bbs"] is None


def test_every_line_cites_a_reference():
    for kw in ({}, dict(spans=3), dict(section="l_beam", width_mm=250, depth_mm=450, flange_width_mm=1200)):
        r = design_continuous_beam(ContinuousBeamInput(**kw))
        for s in r["sheet"]["sections"]:
            for i in s["items"]:
                assert i["ref"], i


def test_sweep():
    grid = itertools.product((3, 4, 7), (3000, 6000, 9000), (400, 650), ((10, 5), (30, 20), (60, 40)), ("rectangular", "t_beam"))
    n = n_ok = 0
    for spans, lc, D, (dl, ll), sec in grid:
        r = design_continuous_beam(ContinuousBeamInput(spans=spans, clear_span_mm=lc, depth_mm=D, dead_load_kn_m=dl, live_load_kn_m=ll,
                                                       section=sec, width_mm=300, flange_width_mm=2500))
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            assert r["stop_message"]
            continue
        d = r["data"]
        for key, m in (("end", d["m_end"]), ("interior", d["m_int"]), ("support_b", d["m_b"])) + ((("support_c", d["m_c"]),) if spans >= 4 else ()):
            assert d[key]["capacity"] >= m - 1e-6 and d[key]["xu"] <= d[key]["xu_max"] + 1e-6
            assert d[key]["ast_prov"] >= max(d[key]["ast_req"], d[key]["min_steel"]) - 1e-6
        lay = r["reinforcement"]["layout"]
        for s in lay["interior"]:
            assert s["hanger"] > 0 or s["meet"]
            assert math.isfinite(s["a_left"]) and 0 < s["a_left"] <= lc
        n_ok += r["status"] == "ok"
    assert n == 108 and n_ok > 50


def test_curtailment_of_the_continuous_beam():
    r = design_continuous_beam(ContinuousBeamInput())
    cur, reinf = r["data"]["curtailment"], r["reinforcement"]
    assert r["status"] == "ok"
    tb = cur["top"]["b"]
    # a third of the top steel (3 of 6 T16) runs to the point of inflection; the rest stops where those suffice
    assert tb["long"] == "3-T16" and tb["short"] == "3-T16"
    ld = is456.development_length(16, 25, 500)
    assert ld <= tb["cut"]["end"] < reinf["layout"]["end"]["a_b"] and ld <= tb["cut"]["interior"] < reinf["layout"]["b_into_interior"]
    assert all(c["condition"] in ("a", "b", "c") for c in tb["conditions"])
    bi = cur["bottom"]["interior"]
    assert bi["continuing"] == "2-T16" and bi["left"] == bi["right"] >= r["data"]["interior"]["d"]
    # the stirrups: designed spacing near the supports, wider between, and the schedule counts the positions
    z = cur["zones"]["interior"]
    assert z["applied"] and z["s_end"] < z["s_mid"] and count(r, "Stirrups, interior spans") == 2 * z["count"]
    # every gap between stirrups is within the spacing that applies there
    pos = reinf["curtailment"]["zones"]["interior"]["positions"]
    assert max(b - a for a, b in zip(pos, pos[1:], strict=False)) <= z["s_mid"] + 1e-6
    assert r["quantities"]["steel_kg"] < 388.6  # the same beam before curtailment


def test_heavy_imposed_load_curtails_both_faces_where_anchorage_allows():
    r = design_continuous_beam(ContinuousBeamInput(live_load_kn_m=40))
    cur = r["data"]["curtailment"]
    assert cur["bottom"]["end"] and cur["top"]["b"] and cur["top"]["c"]
    be = cur["bottom"]["end"]
    assert be["left"] != be["right"]  # the end span's diagram is not symmetric
    # two of the three T25 alone could not develop at the point of inflection (Cl. 26.2.3.3(c)), so all three run through
    assert cur["bottom"]["interior"] is None
    steps = [i["title"] for s in r["sheet"]["sections"] for i in s["items"]]
    assert any(t.startswith("Interior span bottom bars: the continuing bars alone could not be anchored") for t in steps)
    assert r["checks_passed"] == r["checks_total"]


def test_anchorage_at_the_end_supports_and_points_of_inflection():
    r = design_continuous_beam(ContinuousBeamInput())
    c = checks(r)
    end, infl_e, infl_i = c["anchorage_end"], c["anchorage_inflection_end"], c["anchorage_inflection_interior"]
    assert end["ok"] and infl_e["ok"] and infl_i["ok"]
    # at the end support the bars are confined by the reaction (1.3 M_1/V); at a point of inflection L_0 = max(d, 12 phi), no 1.3
    assert "1.3" in end["rhs_label"] and "1.3" not in infl_i["rhs_label"]
    t = 0.87 * 500 * 5 * math.pi * 16**2 / 4  # all five T16 reach the end supports (the end span is not curtailed)
    d = r["data"]["end"]["d"]
    m1 = t * (d - 0.42 * t / (0.36 * 25 * 300))
    l0 = 300 / 2 - r["reinforcement"]["cover"]
    assert end["rhs"] == pytest.approx(1.3 * m1 / (r["data"]["v_a"] * 1e3) + l0, rel=1e-4)


def test_bar_selection_respects_anchorage():
    # 3-T32 carry the end span's moment but cannot develop at the end supports; a fourth bar raises M_1 enough (Cl. 26.2.3.3(c))
    kw = dict(support_width_mm=150, clear_span_mm=3000, depth_mm=450, dead_load_kn_m=60, live_load_kn_m=40, main_bar_dia_mm=32)
    r = design_continuous_beam(ContinuousBeamInput(**kw))
    assert r["reinforcement"]["end"]["bottom"]["label"] == "4-T32"
    c = checks(r)
    assert c["anchorage_end"]["ok"] and c["anchorage_inflection_end"]["ok"]
    # where no arrangement can be anchored, the stop says so
    r = design_continuous_beam(ContinuousBeamInput(**dict(kw, clear_span_mm=4500)))
    assert r["status"] == "stopped" and "too large to be anchored" in r["stop_message"]


def test_u_hooks_at_the_end_supports():
    # narrow end supports: a 90 degree bend's 8 phi do not develop T20, a standard U-hook's 16 phi do (Cl. 26.2.2.1(b))
    r = design_continuous_beam(ContinuousBeamInput(support_width_mm=150, clear_span_mm=2500, depth_mm=450, dead_load_kn_m=80,
                                                   live_load_kn_m=48, main_bar_dia_mm=20))
    assert r["status"] == "ok" and r["reinforcement"]["curtailment"]["end_detail"] == "hook"
    c = checks(r)["anchorage_end"]
    cover = r["reinforcement"]["cover"]
    assert c["ok"]
    steps = [i["title"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "step"]
    assert any("start of the hook" in t for t in steps) and any("U-hook, worth 16 diameters" in t for t in steps)
    # L_0: straight from the centre of the support to the start of the hook (r = 4 phi), plus 16 phi
    l0 = 150 / 2 - cover - (4 * 20 + 20) + 16 * 20
    assert c["rhs"] - l0 > 0 and c["lhs"] == pytest.approx(is456.development_length(20, 25, 500))
    main = items(r, "Bottom bars, end spans")[0]
    assert main["shape"] == "U-hook at the end support" and main["cutting_length_mm"] == main["dims"]["A"] + main["dims"]["hook"]
    elev = next(v for v in r["drawing"]["views"] if v["id"] == "elevation")
    assert any(e["t"] == "polyline" and e["layer"] == "rebar" for e in elev["items"])
