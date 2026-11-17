"""Strain-compatibility section kernel (IS 456:2000, Cl. 39.1) against closed-form values."""

import math

import pytest

from app.engineering import is456
from app.engineering import rc_section as rc

B, D, FCK, FY = 300.0, 450.0, 25.0, 500.0
A3T16 = 3 * math.pi * 16**2 / 4
SYM = [rc.Layer(50.0, A3T16), rc.Layer(D - 50.0, A3T16)]


def test_concrete_stress_follows_fig_21():
    fcd = 0.67 * FCK / 1.5
    assert rc.concrete_stress(-0.001, FCK) == 0.0
    assert rc.concrete_stress(0.001, FCK) == pytest.approx(fcd * 0.75)  # 2(0.5) - 0.5^2
    assert rc.concrete_stress(0.002, FCK) == pytest.approx(fcd)
    assert rc.concrete_stress(0.0035, FCK) == pytest.approx(fcd)


@pytest.mark.parametrize("xu", [20.0, 150.0, 449.9])
def test_stress_block_constants_with_the_neutral_axis_in_the_section(xu):
    # The rounded values of Cl. 38.1 are 0.36 and 0.42: these are the exact ones they come from.
    force, yc = rc.concrete_resultant(B, D, xu, FCK)
    assert force / (FCK * B * xu) == pytest.approx(0.67 / 1.5 * (1 - 4 / 21), rel=1e-12)  # 0.36159
    assert yc / xu == pytest.approx(0.41597, abs=1e-5)


def test_strain_profile_is_continuous_at_xu_equal_to_d_and_tends_to_uniform():
    below = rc.concrete_resultant(B, D, D * (1 - 1e-10), FCK)
    above = rc.concrete_resultant(B, D, D * (1 + 1e-10), FCK)
    assert below[0] == pytest.approx(above[0], rel=1e-8) and below[1] == pytest.approx(above[1], rel=1e-7)
    # Cl. 39.1(b): edge strain = 0.0035 - 0.75 x strain at the least compressed edge
    for xu in (1.2 * D, 2 * D, 10 * D):
        top = rc.strain_at(0.0, xu, D)
        bottom = rc.strain_at(D, xu, D)
        assert top == pytest.approx(0.0035 - 0.75 * bottom, rel=1e-12)
    force, yc = rc.concrete_resultant(B, D, math.inf, FCK)
    assert force == pytest.approx(0.67 / 1.5 * FCK * B * D) and yc == D / 2
    far = rc.concrete_resultant(B, D, 1e4 * D, FCK)
    assert far[0] == pytest.approx(force, rel=1e-6)


def test_displaced_concrete_is_deducted_only_in_compression():
    assert rc.bar_stress(0.003, FCK, FY) == pytest.approx(is456.steel_design_stress(0.003, FY) - rc.concrete_stress(0.003, FCK))
    assert rc.bar_stress(-0.003, FCK, FY) == pytest.approx(-is456.steel_design_stress(0.003, FY))


def test_pure_bending_matches_the_beam_capacity():
    s = rc.at_axial_load(B, D, SYM, FCK, FY, 0.0)
    beam = is456.moment_capacity(FCK, FY, B, D - 50.0, A3T16, A3T16, 50.0)
    # The beam formula uses the rounded 0.36 / 0.42 block: within half a percent.
    assert s.m == pytest.approx(beam.mu, rel=5e-3)
    assert abs(s.p) < 1e-3


def test_axial_load_rises_with_the_neutral_axis_depth():
    prev = -math.inf
    for i in range(300):
        p = rc.state(B, D, SYM, FCK, FY, D * 0.01 * 1e5 ** (i / 299)).p
        assert p >= prev - 1e-6
        prev = p


@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.4, 0.8, 0.99])
def test_solving_for_an_axial_load_returns_that_load(fraction):
    p0 = rc.squash_load(B, D, SYM, FCK, FY)
    s = rc.at_axial_load(B, D, SYM, FCK, FY, fraction * p0)
    assert s.p == pytest.approx(fraction * p0, abs=1e-3 * max(fraction * p0, 1.0))
    assert s.m > 0 or fraction > 0.98


def test_loads_outside_the_section_capacity_have_no_moment():
    p0 = rc.squash_load(B, D, SYM, FCK, FY)
    assert rc.at_axial_load(B, D, SYM, FCK, FY, 1.01 * p0) is None
    assert rc.at_axial_load(B, D, SYM, FCK, FY, -1e9) is None
    assert rc.at_axial_load(B, D, SYM, FCK, FY, p0).xu == math.inf


def test_squash_load_uses_the_stresses_at_strain_0_002():
    fcd = 0.67 / 1.5 * FCK
    fs = is456.steel_design_stress(0.002, FY)
    expected = fcd * (B * D - 2 * A3T16) + fs * 2 * A3T16
    assert rc.squash_load(B, D, SYM, FCK, FY) == pytest.approx(expected)


def test_balanced_state_uses_the_limiting_neutral_axis():
    s = rc.balanced(B, D, SYM, FCK, FY)
    assert s.xu == pytest.approx(is456.xu_max_ratio(FY) * (D - 50.0))
    # the extreme tension row is exactly at its design strength
    e = rc.strain_at(D - 50.0, s.xu, D)
    assert is456.steel_design_stress(e, FY) == pytest.approx(0.87 * FY)


def test_interaction_curve_runs_from_pure_bending_to_the_squash_load():
    curve = rc.interaction_curve(B, D, SYM, FCK, FY)
    ps = [p for _, p in curve]
    assert ps == sorted(ps)
    assert ps[0] == 0.0 and curve[0][0] > 0
    assert ps[-1] == pytest.approx(rc.squash_load(B, D, SYM, FCK, FY))
    assert abs(curve[-1][0]) < 1e-6  # symmetric bars: no moment at uniform strain
    assert max(m for m, _ in curve) > curve[0][0]  # the familiar nose above pure bending
