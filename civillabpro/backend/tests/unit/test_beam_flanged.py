"""Flanged beams (T and L): effective width, Annex G-2 flexure, shear on the web, Fig. 6, rib quantities, drawing."""

import itertools
import json

import pytest
from pydantic import ValidationError

from app.engineering import is456
from app.modules.structural.domain.beam import BeamInput, design_beam

# The T-beam worked example of the module note: a floor beam at 3 m centres carrying a 120 mm slab.
T_BEAM = dict(section="t_beam", width_mm=300, depth_mm=550, flange_thickness_mm=120, flange_width_mm=3000,
              clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=30, live_load_kn_m=15)
# An isolated T whose neutral axis falls in the web.
WEB_NA = dict(section="t_beam", width_mm=250, depth_mm=500, flange_thickness_mm=100, flange_width_mm=750, isolated_flange=True,
              clear_span_mm=7000, support_width_mm=300, dead_load_kn_m=20, live_load_kn_m=10)


def checks(res):
    return {i["id"]: i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "check"}


def steps(res):
    return [i for s in res["sheet"]["sections"] for i in s["items"] if i["kind"] == "step"]


def test_t_beam_worked_example():
    r = design_beam(BeamInput(**T_BEAM))
    d = r["data"]
    assert r["status"] == "ok" and r["checks_passed"] == r["checks_total"]
    # effective span 6300 (centre to centre governs), l_0 = l, b_f = 6300/6 + 300 + 6 x 120
    assert d["l_eff"] == 6300 and d["l0"] == 6300 and d["bf"] == pytest.approx(2070)
    # self-weight of the rib below the slab only
    assert d["w_self"] == pytest.approx(25 * 0.300 * 0.430)
    assert d["mu"] == pytest.approx(1.5 * (30 + 15 + 25 * 0.3 * 0.43) * 6.3**2 / 8, rel=1e-6)
    # the neutral axis lies in the flange: a rectangle b_f x d
    assert d["na_in_flange"] and d["xu"] <= 120
    assert d["ast_req"] == pytest.approx(is456.design_rectangular(d["me1"] * 1e6, 25, 500, 2070, d["d"], d["d_c"]).ast_req, rel=1e-4)
    # shear on the web; deflection with p_t on b_f d and Fig. 6
    assert d["tau_v"] == pytest.approx(d["vu"] * 1e3 / (300 * d["d"]), rel=1e-4)
    assert d["pt"] == pytest.approx(100 * d["ast_prov"] / (300 * d["d"]), rel=1e-4)
    assert d["pt_defl"] == pytest.approx(100 * d["ast_prov"] / (2070 * d["d"]), rel=1e-4)
    assert d["kf"] == 0.8
    fs = 0.58 * 500 * d["ast_req"] / d["ast_prov"]
    assert d["span_depth_allow"] == pytest.approx(20 * is456.tension_modification_factor(fs, d["pt_defl"]) * 0.8, rel=1e-4)
    # lateral stability on the flange, the compression face
    assert checks(r)["lateral"]["rhs"] == pytest.approx(min(60 * 2070, 250 * 2070**2 / d["d"]))
    assert any(k["label"] == "Effective flange width" and k["value"] == 2070 for k in r["key_results"])
    assert any("Cl. 23.1.1(b)" in f["ref"] for f in r["sheet"]["flags"])


def test_neutral_axis_in_the_web():
    r = design_beam(BeamInput(**WEB_NA))
    d = r["data"]
    assert r["status"] == "ok" and d["bf"] == 750 and not d["na_in_flange"] and not d["doubly"]
    assert 100 < d["xu"] <= d["xu_max"]
    assert d["mu_capacity"] >= d["me1"]
    # the step reports x_u from the G-2.2 moment, and the steel balances that compression
    xu_step = next(s for s in steps(r) if s["title"].startswith("M_u,f < M_u <= M_u,lim"))
    c, m = is456.flanged_concrete(25, 750, 250, 100, d["d"], xu_step["value"])
    assert m / 1e6 == pytest.approx(d["me1"], rel=1e-4) and c / (0.87 * 500) == pytest.approx(d["ast_req"], rel=1e-4)  # d is stored to 0.01 mm


def test_thick_flange_uses_yf():
    r = design_beam(BeamInput(**dict(WEB_NA, flange_thickness_mm=150, flange_width_mm=600, clear_span_mm=6500, dead_load_kn_m=26,
                                     live_load_kn_m=12)))
    lim = next(s for s in steps(r) if "Limiting moment of the flanged section" in s["title"])
    assert lim["ref"].endswith("G-2.2.2")  # D_f > 3/7 x_u,max: y_f = 0.15 x_u + 0.65 D_f
    assert "y_f = 0.15 x" in lim["sub"]


def test_l_beam_and_isolated_widths():
    r = design_beam(BeamInput(section="l_beam", width_mm=230, depth_mm=500, flange_thickness_mm=125, flange_width_mm=1500,
                              clear_span_mm=5000, dead_load_kn_m=22, live_load_kn_m=10))
    d = r["data"]
    assert r["status"] == "ok" and d["bf"] == pytest.approx(d["l0"] / 12 + 230 + 3 * 125, abs=0.01)
    r = design_beam(BeamInput(section="l_beam", width_mm=300, depth_mm=600, flange_thickness_mm=120, flange_width_mm=900,
                              isolated_flange=True, clear_span_mm=6000, support_width_mm=300, dead_load_kn_m=25, live_load_kn_m=15))
    d = r["data"]
    assert d["bf"] == pytest.approx(0.5 * d["l0"] / (d["l0"] / 900 + 4) + 300, abs=0.01)


def test_entered_l0_and_cap_at_the_width_available():
    r = design_beam(BeamInput(**dict(T_BEAM, l0_mm=4200)))
    assert r["data"]["l0"] == 4200 and r["data"]["bf"] == pytest.approx(4200 / 6 + 300 + 720)
    r = design_beam(BeamInput(**dict(T_BEAM, flange_width_mm=1200)))
    assert r["data"]["bf"] == 1200


def test_cantilever_flange_in_tension_designs_the_web():
    r = design_beam(BeamInput(section="t_beam", support="cantilever", width_mm=300, depth_mm=500, flange_thickness_mm=120,
                              flange_width_mm=2500, clear_span_mm=2000, support_width_mm=300, dead_load_kn_m=20, live_load_kn_m=10))
    d = r["data"]
    assert r["status"] == "ok" and d["na_in_flange"] is None
    assert d["mu_lim"] == pytest.approx(is456.limiting_moment(25, 500, 300, d["d"]) / 1e6, rel=1e-4)
    assert d["pt_defl"] == pytest.approx(d["pt"], rel=1e-6)  # on the web: the flange is in tension
    assert r["reinforcement"]["tension_face"] == "top"
    assert any("flange is in tension" in f["message"] for f in r["sheet"]["flags"])


def test_flange_inputs_do_not_touch_a_rectangular_beam():
    base = design_beam(BeamInput())
    other = design_beam(BeamInput(flange_thickness_mm=200, flange_width_mm=900, isolated_flange=True, l0_mm=3000))
    assert base["data"] == other["data"] and base["bbs"] == other["bbs"]


@pytest.mark.parametrize("bad", [
    dict(section="t_beam", flange_thickness_mm=400),  # not 100 mm thinner than D = 450
    dict(section="l_beam", flange_width_mm=230),  # not wider than the web
    dict(section="hollow"),
])
def test_invalid_flanged_input(bad):
    with pytest.raises(ValidationError):
        BeamInput(**bad)


def test_quantities_measure_the_rib():
    t = design_beam(BeamInput(**T_BEAM))["quantities"]
    assert t["concrete_m3"] == pytest.approx(0.3 * 0.43 * 6.6, abs=1e-3)
    assert t["formwork_m2"] == pytest.approx((0.3 + 2 * 0.43) * 6.0, abs=1e-3)
    lb = design_beam(BeamInput(section="l_beam", width_mm=230, depth_mm=500, flange_thickness_mm=125, flange_width_mm=1500,
                               clear_span_mm=5000))["quantities"]
    assert lb["formwork_m2"] == pytest.approx((0.23 + 0.375 + 0.5) * 5.0, abs=1e-3)  # outer face to the full depth


def test_drawing_shows_the_flange():
    r = design_beam(BeamInput(**T_BEAM))
    sec = r["drawing"]["views"][0]
    outline = next(i for i in sec["items"] if i["t"] == "polyline" and i["layer"] == "concrete")
    xs = [p[0] for p in outline["points"]]
    assert min(xs) < 0 and max(xs) > 300  # outstands on both sides of the web
    assert any(i["t"] == "text" and "Effective flange width b_f = 2070" in i["text"] for i in sec["items"])
    assert r["reinforcement"]["section"] == {"kind": "t_beam", "bw": 300, "D": 550, "df": 120, "bf": 2070.0, "b_actual": 3000}


def test_schema_shows_flange_rows_for_t_and_l_only():
    props = BeamInput.model_json_schema()["properties"]
    assert props["flange_thickness_mm"]["show_if"] == {"section": ["t_beam", "l_beam"]}
    assert props["section"]["labels"]["l_beam"].startswith("L-beam")


def test_sweep_of_flanged_beams():
    grid = itertools.product(("t_beam", "l_beam"), (False, True), (230, 300), (400, 600), (80, 150), (900, 3000), (3000, 7000), ((10, 5), (40, 25)))
    n = n_ok = 0
    for sec, iso, bw, D, df, b_av, lc, (dl, ll) in grid:
        r = design_beam(BeamInput(section=sec, isolated_flange=iso, width_mm=bw, depth_mm=D, flange_thickness_mm=df, flange_width_mm=b_av,
                                  clear_span_mm=lc, dead_load_kn_m=dl, live_load_kn_m=ll, support_width_mm=300))
        n += 1
        json.dumps(r, allow_nan=False)
        if r["status"] == "stopped":
            assert r["stop_message"]
            continue
        d = r["data"]
        assert bw < d["bf"] <= b_av + 1e-9
        assert d["ast_prov"] >= max(d["ast_req"], d["ast_min"]) - 1e-6 and d["asc_prov"] >= d["asc_req"] - 1e-6
        assert d["mu_capacity"] >= d["me1"] - 1e-6 and d["xu"] <= d["xu_max"] + 1e-6
        assert d["na_in_flange"] == (d["xu"] <= df + 1e-6) or d["doubly"]
        n_ok += r["status"] == "ok"
    assert n == 256 and n_ok > 120
