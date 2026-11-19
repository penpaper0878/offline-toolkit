"""Continuous beam by elastic analysis with redistribution (STR-036): the analysis kernel and the engine."""

import json
import random

import pytest
from pydantic import ValidationError

from app.engineering import continuous as an
from app.modules.structural.domain.continuous_beam import ContinuousBeamInput, design_continuous_beam


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def elastic(**kw):
    return design_continuous_beam(ContinuousBeamInput(analysis="elastic", **kw))


def spans(*c, dl=25.0, ll=15.0):
    return [dict(clear_span_mm=x, dead_load_kn_m=dl, live_load_kn_m=ll) for x in c]


# ----------------------------------------------------------------------------- kernel


def test_three_moment_equation_with_point_loads_against_closed_forms():
    # two equal spans, P at the middle of each: M_B = -3 P L / 16
    ms = an.support_moments_loads([6.0, 6.0], [an.SpanLoad(0, ((3.0, 100.0),)), an.SpanLoad(0, ((3.0, 100.0),))])
    assert ms[1] == pytest.approx(-3 * 100 * 6 / 16)
    # P at a in one span only: M_B = -P a b (l + a) / (4 l^2)
    P, a, s = 50.0, 2.0, 6.0
    assert an.support_moments_loads([s, s], [an.SpanLoad(0, ((a, P),)), an.SpanLoad()])[1] == pytest.approx(-P * a * (s - a) * (s + a) / (4 * s * s))
    # uniform loads: the same as the routine of the coefficient method
    assert an.support_moments_loads([5.0, 6.0, 4.0], [an.SpanLoad(10), an.SpanLoad(12), an.SpanLoad(8)]) == pytest.approx(
        an.support_moments([5.0, 6.0, 4.0], [10, 12, 8]))


def test_free_diagrams_and_statics():
    load = an.SpanLoad(10.0, ((2.0, 30.0),))
    # the shear drops by P across the load, and the moment is the integral of the shear
    assert an.free_shear(load, 6.0, 2.0 - 1e-9) - an.free_shear(load, 6.0, 2.0 + 1e-9) == pytest.approx(30.0)
    assert an.free_moment(load, 6.0, 2.0) == pytest.approx(10 * 2 * 4 / 2 + 30 * 4 * 2 / 6)
    assert an.moment_in(-20.0, -10.0, load, 6.0, 0.0) == pytest.approx(-20.0)
    assert an.moment_in(-20.0, -10.0, load, 6.0, 6.0) == pytest.approx(-10.0)


def test_redistribution_holds_each_support_to_its_cap():
    cases = [[0.0, -100.0, -60.0, 0.0], [0.0, -80.0, -90.0, 0.0]]
    out, caps = an.redistribute(cases, 0.15)
    assert caps == pytest.approx([0.0, 85.0, 76.5, 0.0])
    assert out == [[0.0, -85.0, -60.0, 0.0], [0.0, -80.0, -76.5, 0.0]]  # only moments above the cap fall, and only to it


def test_envelopes_have_stations_either_side_of_a_point_load():
    loads = [an.SpanLoad(20.0), an.SpanLoad(20.0, ((2.5, 80.0),))]
    envs, hog_e, caps = an.envelopes([5.0, 5.0], [loads], 0.0, 50)
    xs = envs[1].x
    below = max(k for k, x in enumerate(xs) if x < 2.5)
    above = min(k for k, x in enumerate(xs) if x > 2.5)
    assert 2.5 - xs[below] < 1e-4 and xs[above] - 2.5 < 1e-4
    assert envs[1].shear[below] + envs[1].shear[above] > 70.0  # the jump in shear is caught
    assert hog_e[1] == pytest.approx(caps[1])


# ----------------------------------------------------------------------------- engine


def test_worked_example():
    r = elastic()
    d, ch = r["data"], checks(r)
    assert r["status"] == "ok" and r["engine_version"] == "1.5.0"
    # support moments: 15 percent below the elastic greatest, not below 70 percent of it (Cl. 37.1.1)
    for j in (1, 2):
        assert d["m_sup"][j] == pytest.approx(0.85 * d["m_sup_elastic"][j], rel=1e-6)
        assert ch[f"redistribution_{j + 1}"]["ok"]
    # equilibrium: the span moments rise where the support moments fell (span 2 carries the point load)
    assert d["m_span"][1] > d["m_span_elastic"][1]
    assert all(m >= 0.7 * e - 1e-9 for m, e in zip(d["m_span"], d["m_span_elastic"], strict=True))
    assert [g for g in r["drawing"]["views"] if g["id"].startswith("elevation")] and len(r["drawing"]["views"]) == 4  # 3 spans and the sections
    assert {c["id"] for c in r["charts"]} == {"moments", "shear"}
    hog = next(s for s in r["charts"][0]["series"] if s["name"] == "Greatest hogging")
    assert min(y for _, y in hog["points"]) < -200
    json.dumps(r, allow_nan=False)


def test_condition_d_limits_the_neutral_axis_where_moments_fell():
    r = elastic(redistribution_pct=30.0, depth_mm=550)
    d, ch = r["data"], checks(r)
    for j in (1, 2):
        sup = d["support"][j]
        key = f"xu_redistribution_s{j + 1}"
        if sup["capacity"] < d["m_sup_elastic"][j]:
            assert ch[key]["ok"] and ch[key]["lhs"] == pytest.approx(sup["xu"] / sup["d"] + 0.30, rel=1e-4)
            assert sup["xu"] / sup["d"] <= 0.30 + 1e-9
        else:
            assert key not in ch


def test_no_redistribution_designs_for_the_elastic_envelope():
    r = elastic(redistribution_pct=0.0, depth_mm=550)
    d = r["data"]
    assert d["m_sup"] == pytest.approx(d["m_sup_elastic"]) and d["m_span"] == pytest.approx(d["m_span_elastic"])
    assert not any(k.startswith("xu_redistribution") for k in checks(r))


def test_two_spans_and_a_symmetric_schedule():
    r = elastic(span_table=spans(5000, 5000), point_loads=[])
    assert r["status"] == "ok"
    assert r["data"]["m_span"][0] == pytest.approx(r["data"]["m_span"][1], rel=1e-4)
    # alike rows of the two spans are merged
    assert any(", spans 1 and 2" in i["description"] for i in r["bbs"]["items"])
    z = r["reinforcement"]["curtailment"]["zones"]
    assert [(round(5000 - b, 1), round(5000 - a, 1), s) for a, b, s in reversed(z[0]["bands"])] == z[1]["bands"]  # mirror images


def test_short_middle_span_laps_the_support_bars_and_checks_the_lap():
    r = elastic(span_table=spans(7000, 3000, 7000), point_loads=[], depth_mm=600)
    lay = r["reinforcement"]["layout"]
    assert lay[1]["kind"] == "meet" and lay[1]["a_left"] + lay[1]["a_right"] - 3000 >= lay[1]["lap"] - 1e-6
    assert checks(r)["lap_hogging_2"]["ok"]


def test_point_load_within_d_takes_the_shear_at_the_face():
    r = elastic(point_loads=[dict(span=1, distance_mm=200.0, dead_kn=60.0, live_kn=40.0)])
    steps = [i["title"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "step"]
    assert any(t.startswith("Span 1, left end: shear at the face (a point load lies within d)") for t in steps)


def test_stops_and_input_errors():
    assert elastic(span_table=spans(1000, 1200), point_loads=[], depth_mm=600)["status"] == "stopped"
    with pytest.raises(ValidationError, match="on span 4, but the beam has 3 spans"):
        ContinuousBeamInput(analysis="elastic", point_loads=[dict(span=4, distance_mm=100.0, dead_kn=10.0, live_kn=0.0)])
    with pytest.raises(ValidationError, match="beyond the clear span of span 1"):
        ContinuousBeamInput(analysis="elastic", point_loads=[dict(span=1, distance_mm=5500.0, dead_kn=10.0, live_kn=0.0)])
    with pytest.raises(ValidationError):
        ContinuousBeamInput(analysis="elastic", span_table=spans(5000))  # one span is a simple beam
    # the coefficient method keeps its own rule of three or more spans
    with pytest.raises(ValidationError):
        ContinuousBeamInput(spans=2)


def test_coefficient_method_is_the_default_and_unchanged():
    r = design_continuous_beam(ContinuousBeamInput())
    assert "method" not in r["data"] and r["key_results"][2]["value"] == "5-T16"


def test_sweep_is_json_safe_and_never_raises():
    rnd = random.Random(11)
    statuses = set()
    for _ in range(40):
        n = rnd.randint(2, 6)
        rows = spans(*[rnd.choice([3000, 4500, 6000, 7500]) for _ in range(n)], dl=rnd.choice([10, 25, 40]), ll=rnd.choice([0, 10, 20]))
        pls = [dict(span=(sp := rnd.randint(1, n)), distance_mm=rnd.uniform(0, rows[sp - 1]["clear_span_mm"]), dead_kn=rnd.choice([0, 30]),
                    live_kn=rnd.choice([0, 50])) for _ in range(rnd.randint(0, 2))]
        r = elastic(span_table=rows, point_loads=pls, redistribution_pct=rnd.choice([0, 15, 30]), depth_mm=rnd.choice([450, 600, 750]),
                    width_mm=rnd.choice([230, 300]), section=rnd.choice(["rectangular", "t_beam"]))
        json.dumps(r, allow_nan=False)
        statuses.add(r["status"])
        if r["status"] != "stopped":
            assert len(r["reinforcement"]["span"]) == n and len(r["reinforcement"]["curtailment"]["zones"]) == n
    assert "ok" in statuses


def test_redistribution_steps_down_where_condition_d_allows_no_more():
    r = elastic(redistribution_pct=30.0)  # 500 deep: support 3 cannot keep x_u/d within 0.3
    fr = r["data"]["redistribution_applied"]
    assert r["status"] == "ok" and fr[0] == fr[-1] == 0.0 and fr[1] == pytest.approx(0.30) and fr[2] < 0.30
    d = r["data"]
    assert d["m_sup"][2] == pytest.approx((1 - fr[2]) * d["m_sup_elastic"][2], rel=1e-6)
    steps = [i["title"] for s in r["sheet"]["sections"] for i in s["items"] if i["kind"] == "step"]
    assert any(t.startswith("Support 3: no arrangement of top bars meets x_u/d + dM/100 <= 0.6") for t in steps)
    assert r["key_results"][2]["label"] == "Redistribution, least at a support" and r["key_results"][2]["value"] == pytest.approx(100 * fr[2])
