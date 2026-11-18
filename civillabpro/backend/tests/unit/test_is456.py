"""IS 456:2000 rule functions against values printed in the code and in SP 16."""

import math

import pytest

from app.engineering import is456


def test_xu_max_ratio_rounds_to_the_values_in_the_note_to_clause_38_1():
    assert round(is456.xu_max_ratio(250), 2) == 0.53
    assert round(is456.xu_max_ratio(415), 2) == 0.48
    assert round(is456.xu_max_ratio(500), 2) == 0.46
    assert is456.xu_max_ratio(415) == pytest.approx(0.4791, abs=1e-4)
    assert is456.xu_max_ratio(550) == pytest.approx(0.4435, abs=1e-4)
    # at xu,max the tension steel is exactly at its design strength (Cl. 38.1(f))
    for fy in (415, 500, 550):
        k = is456.xu_max_ratio(fy)
        assert is456.steel_design_stress(0.0035 * (1 - k) / k, fy) == pytest.approx(0.87 * fy)


@pytest.mark.parametrize("fy, factor", [(250, 0.149), (415, 0.138), (500, 0.133)])
def test_limiting_moment_factor_matches_sp16_table_e(fy, factor):
    # SP 16, Table E: Mu,lim / (fck b d^2)
    fck, b, d = 20.0, 1000.0, 1000.0
    assert is456.limiting_moment(fck, fy, b, d) / (fck * b * d * d) == pytest.approx(factor, abs=5e-4)


@pytest.mark.parametrize(
    "fy, ratio, expected",
    [
        # SP 16, Table F: stress in compression reinforcement fsc, N/mm2, for d'/d
        (415, 0.05, 355), (415, 0.10, 353), (415, 0.15, 342), (415, 0.20, 329),
        (500, 0.05, 424), (500, 0.10, 412), (500, 0.15, 395), (500, 0.20, 370),
        (250, 0.05, 217), (250, 0.10, 217), (250, 0.15, 217), (250, 0.20, 217),
    ],
)
def test_compression_steel_stress_matches_sp16_table_f(fy, ratio, expected):
    strain = 0.0035 * (1 - ratio / is456.xu_max_ratio(fy))
    assert is456.steel_design_stress(strain, fy) == pytest.approx(expected, abs=2.0)


def test_steel_curve_is_elastic_then_reaches_design_strength():
    assert is456.steel_design_stress(0.001, 415) == pytest.approx(200.0)
    assert is456.steel_design_stress(0.0038, 415) == pytest.approx(0.87 * 415, rel=1e-3)
    assert is456.steel_design_stress(0.01, 500) == pytest.approx(0.87 * 500)
    # monotonic
    prev = 0.0
    for i in range(1, 500):
        s = is456.steel_design_stress(i * 1e-5, 500)
        assert s >= prev
        prev = s


def test_table_19_agrees_with_the_sp16_closed_form():
    # Every printed value must lie within the rounding of the formula it came from.
    for fck in (20, 25, 30, 35, 40):
        for pt in is456._PT:
            assert is456.tau_c(fck, pt) == pytest.approx(is456.tau_c_formula(fck, pt), abs=0.011), (fck, pt)


def test_table_19_values_and_interpolation():
    assert is456.tau_c(20, 0.50) == pytest.approx(0.48)
    assert is456.tau_c(25, 1.00) == pytest.approx(0.64)
    assert is456.tau_c(30, 0.10) == pytest.approx(0.29)  # below 0.15 %: first row
    assert is456.tau_c(20, 5.00) == pytest.approx(0.82)  # above 3 %: last row
    assert is456.tau_c(25, 0.625) == pytest.approx((0.49 + 0.57) / 2)
    assert is456.tau_c(45, 1.0) == is456.tau_c(40, 1.0)  # M40 and above


def test_table_20():
    assert [is456.tau_c_max(g) for g in (20, 25, 30, 35, 40, 50)] == [2.8, 3.1, 3.5, 3.7, 4.0, 4.0]


@pytest.mark.parametrize("fck, fy, multiple", [(20, 415, 47.0), (25, 415, 40.3), (20, 500, 56.6), (30, 500, 45.3), (20, 250, 45.3)])
def test_development_length_multiples(fck, fy, multiple):
    # Cl. 26.2.1: the familiar 47 d for M20 / Fe 415, and so on
    assert is456.development_length(1.0, fck, fy) == pytest.approx(multiple, abs=0.05)


def test_compression_development_length_is_shorter():
    assert is456.development_length(16, 25, 500, compression=True) == pytest.approx(is456.development_length(16, 25, 500) / 1.25)


def test_singly_reinforced_steel_satisfies_annex_g_equation():
    fck, fy, b, d = 25.0, 500.0, 300.0, 550.0
    for mu_knm in (20, 80, 150, 220):
        fl = is456.design_rectangular(mu_knm * 1e6, fck, fy, b, d, 50.0)
        assert not fl.doubly
        back = 0.87 * fy * fl.ast_req * d * (1 - fl.ast_req * fy / (b * d * fck))
        assert back == pytest.approx(mu_knm * 1e6, rel=6e-4)  # 4.6 x 0.87 / 4 = 1.0005
        assert back >= mu_knm * 1e6  # 4.6 in place of 4/0.87 errs on the safe side
        assert fl.xu <= fl.xu_max


def test_balanced_steel_percentage_matches_sp16_table_e():
    # SP 16, Table E: pt,lim = 0.96 % for M20 / Fe 415. SP 16 carries 0.362 and fy/1.15 where the
    # code prints 0.36 and 0.87 fy, hence the 0.6 % tolerance.
    fck, fy, b, d = 20.0, 415.0, 1000.0, 500.0
    fl = is456.design_rectangular(1.001 * is456.limiting_moment(fck, fy, b, d), fck, fy, b, d, 50.0)
    assert 100 * fl.ast_lim / (b * d) == pytest.approx(0.96, abs=0.006)


def test_doubly_reinforced_design_hand_calculation():
    # 300 x 600 (d = 550, d' = 50), M20 / Fe 415, Mu = 400 kN m
    fck, fy, b, d, dc = 20.0, 415.0, 300.0, 550.0, 50.0
    fl = is456.design_rectangular(400e6, fck, fy, b, d, dc)
    xu_max = 0.479107 * 550  # 263.5
    mu_lim = 0.36 * 20 * 300 * xu_max * (550 - 0.42 * xu_max)  # 250.1 kN m
    assert fl.doubly and fl.mu_lim == pytest.approx(mu_lim, rel=1e-5)
    assert fl.mu_lim / 1e6 == pytest.approx(250.1, abs=0.1)
    eps = 0.0035 * (1 - 50 / xu_max)  # 0.002836
    assert fl.eps_sc == pytest.approx(eps, rel=1e-5)
    assert fl.fsc == pytest.approx(352.7, abs=0.5)  # between 0.975 fyd and fyd on Fig. 23A
    asc = (400e6 - mu_lim) / ((fl.fsc - 0.446 * 20) * 500)
    assert fl.asc_req == pytest.approx(asc, rel=1e-5)
    assert fl.asc_req == pytest.approx(870, abs=3)
    ast1 = 0.36 * 20 * 300 * xu_max / (0.87 * 415)
    assert fl.ast_req == pytest.approx(ast1 + asc * (fl.fsc - 8.92) / (0.87 * 415), rel=1e-5)


@pytest.mark.parametrize("fy", [250, 415, 500, 550])
@pytest.mark.parametrize("fck", [20, 30, 40])
def test_capacity_of_the_required_steel_equals_the_design_moment(fck, fy):
    b, d, dc = 300.0, 500.0, 55.0
    mu_lim = is456.limiting_moment(fck, fy, b, d)
    for factor in (0.2, 0.6, 0.95, 1.2, 1.6):
        mu = factor * mu_lim
        fl = is456.design_rectangular(mu, fck, fy, b, d, dc)
        cap = is456.moment_capacity(fck, fy, b, d, fl.ast_req, fl.asc_req, dc)
        if fl.doubly:
            assert cap.mu == pytest.approx(mu, rel=1e-6), (fck, fy, factor)
        else:
            # Annex G-1.1(b) rounds the lever-arm factor 0.42 x 0.87 / 0.36 = 1.015 to 1; the stress
            # block of Cl. 38.1 used for the capacity is therefore lower by up to 0.4 %.
            assert 0.996 * mu <= cap.mu <= 1.0005 * mu, (fck, fy, factor)
        assert cap.xu <= fl.xu_max + 1e-6


def test_capacity_flags_an_over_reinforced_section():
    cap = is456.moment_capacity(20.0, 415.0, 230.0, 400.0, 2500.0, 0.0, 40.0)
    assert cap.limited and cap.xu == pytest.approx(is456.xu_max_ratio(415) * 400)
    assert cap.mu == pytest.approx(is456.limiting_moment(20.0, 415.0, 230.0, 400.0))


def test_minimum_and_maximum_steel():
    assert is456.min_tension_steel(230, 400, 415) == pytest.approx(0.85 * 230 * 400 / 415)
    assert is456.max_steel(230, 450) == pytest.approx(4140)


def test_deflection_modification_factors():
    assert is456.tension_modification_factor(240, 1.0) == pytest.approx(1.0, abs=0.01)  # Fig. 4, fs = 240
    assert is456.tension_modification_factor(240, 0.4) == pytest.approx(1.33, abs=0.02)
    assert is456.tension_modification_factor(120, 0.2) == 2.0  # capped
    assert is456.compression_modification_factor(1.0) == pytest.approx(1.25)  # Fig. 5
    assert is456.compression_modification_factor(3.0) == pytest.approx(1.5)
    assert is456.compression_modification_factor(6.0) == 1.5
    assert is456.service_steel_stress(415, 500, 600) == pytest.approx(0.58 * 415 * 500 / 600)


def test_durability_tables_and_spacing_rules():
    assert [is456.nominal_cover(e) for e in is456.EXPOSURES] == [20, 30, 45, 50, 75]  # Table 16
    assert [is456.min_grade(e) for e in is456.EXPOSURES] == [20, 25, 30, 35, 40]  # Table 5
    assert [is456.max_clear_bar_spacing(fy) for fy in (250, 415, 500, 550)] == [300, 180, 150, 136]  # Table 15
    assert is456.min_clear_bar_spacing_horizontal(16, 20) == 25
    assert is456.min_clear_bar_spacing_horizontal(32, 20) == 32
    assert is456.min_clear_bar_spacing_vertical(12, 20) == 15
    assert is456.min_clear_bar_spacing_vertical(25, 20) == 25
    assert is456.shear_fy(500) == 415 and is456.shear_fy(250) == 250


def test_stirrup_spacing_expressions():
    asv = 2 * math.pi * 8**2 / 4
    assert is456.stirrup_spacing_for_shear(50e3, 415, asv, 400) == pytest.approx(0.87 * 415 * asv * 400 / 50e3)
    assert is456.stirrup_spacing_minimum_steel(415, asv, 230) == pytest.approx(394.5, abs=0.1)


# ------------------------------------------------------------------ flanged sections (Cl. 23.1.2, Annex G-2, Fig. 6)


def test_effective_flange_width_rules_and_cap():
    l0, bw, df = 6000.0, 300.0, 120.0
    assert is456.effective_flange_width("T", l0, bw, df, 5000, False) == pytest.approx(l0 / 6 + bw + 6 * df)
    assert is456.effective_flange_width("L", l0, bw, df, 5000, False) == pytest.approx(l0 / 12 + bw + 3 * df)
    assert is456.effective_flange_width("T", l0, bw, df, 1200, True) == pytest.approx(l0 / (l0 / 1200 + 4) + bw)
    assert is456.effective_flange_width("L", l0, bw, df, 1200, True) == pytest.approx(0.5 * l0 / (l0 / 1200 + 4) + bw)
    assert is456.effective_flange_width("T", l0, bw, df, 1500, False) == 1500  # never more than the width available


def test_flange_depth_yf():
    assert is456.flange_depth_yf(300, 120) == 120  # 120 <= 3/7 x 300
    assert is456.flange_depth_yf(200, 120) == pytest.approx(0.15 * 200 + 0.65 * 120)
    assert is456.flange_depth_yf(7 * 120 / 3, 120) == pytest.approx(120)  # the two rules meet at Df = 3/7 xu


def test_flanged_compression_is_continuous_at_the_flange_underside():
    c_below = is456.flanged_concrete(25, 1500, 300, 120, 500, 120 - 1e-9)[0]
    c_above = is456.flanged_concrete(25, 1500, 300, 120, 500, 120 + 1e-9)[0]
    assert c_above == pytest.approx(c_below, rel=1e-6)  # y_f = 0.8 Df at xu = Df, so 0.45 x 0.8 = 0.36


def test_design_flanged_reduces_to_known_cases():
    # neutral axis in the flange: the rectangle b_f x d of G-1.1(b)
    r = is456.design_flanged(300e6, 25, 415, 1500, 300, 120, 550, 50)
    assert r.na_in_flange and r.ast_req == pytest.approx(is456.design_rectangular(300e6, 25, 415, 1500, 550, 50).ast_req)
    # web as wide as the flange: the stress block of a rectangle (G-1.1(b) differs by its rounding only)
    for mu in (250e6, 400e6):
        a, b = is456.design_flanged(mu, 25, 500, 300, 300, 120, 550, 50), is456.design_rectangular(mu, 25, 500, 300, 550, 50)
        assert a.ast_req == pytest.approx(b.ast_req, rel=5e-3) and a.asc_req == pytest.approx(b.asc_req, rel=5e-3)
    # neutral axis in the web: the steel balances the G-2.2 compression at the x_u that carries M_u
    r = is456.design_flanged(330e6, 25, 500, 750, 250, 100, 450, 50)
    assert not r.na_in_flange and 100 < r.xu < is456.xu_max_ratio(500) * 450
    c, m = is456.flanged_concrete(25, 750, 250, 100, 450, r.xu)
    assert m == pytest.approx(330e6, rel=1e-6) and r.ast_req == pytest.approx(c / (0.87 * 500))
    # above the flanged limiting moment: compression steel for the excess
    r = is456.design_flanged(800e6, 30, 500, 900, 300, 100, 520, 60)
    assert r.doubly and r.asc_req > 0 and r.mu_lim == pytest.approx(is456.limiting_moment_flanged(30, 500, 900, 300, 100, 520))


def test_flanged_capacity_round_trip():
    for mu in (150e6, 330e6):
        r = is456.design_flanged(mu, 25, 500, 750, 250, 100, 450, 50)
        cap = is456.moment_capacity_flanged(25, 500, 750, 250, 100, 450, r.ast_req, 0.0, 50)
        assert not cap.limited and cap.mu == pytest.approx(mu, rel=4e-3)


def test_fig_6_reduction_factor():
    f = is456.flanged_reduction_factor
    assert f(0.1) == 0.8 and f(0.3) == 0.8 and f(1.0) == pytest.approx(1.0)
    assert f(0.65) == pytest.approx(0.9) and f(2.0) == pytest.approx(1.0)
