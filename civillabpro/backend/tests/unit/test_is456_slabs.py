"""Slab tables and rules of IS 456:2000 (Tables 12, 13, 26, 27; Cl. 24.1, 26.3.3, 26.5.2, 40.2.1.1)."""

import pytest

from app.engineering import is456_slabs as sl

# Table 27 as printed (ly/lx 1.0 ... 2.0). The engine generates it from Rankine-Grashoff;
# agreement here confirms both the formula and the transcription.
PRINTED_27_X = (0.062, 0.074, 0.084, 0.093, 0.099, 0.104, 0.113, 0.118)
PRINTED_27_Y = (0.062, 0.061, 0.059, 0.055, 0.051, 0.046, 0.037, 0.029)


def test_table_27_generated_from_rankine_grashoff_matches_the_printed_values():
    assert sl.TABLE_27_X == PRINTED_27_X
    assert sl.TABLE_27_Y == PRINTED_27_Y


def test_table_27_interpolation():
    c = sl.coefficients_27(1.15)
    assert c.pos_x == pytest.approx((0.074 + 0.084) / 2) and c.pos_y == pytest.approx((0.061 + 0.059) / 2)
    assert c.neg_x is None and c.neg_y is None


# Rows confirmed against published reproductions of the printed table (see the code register).
CORROBORATED = {
    (1, "neg_x"): (0.032, 0.037, 0.043, 0.047, 0.051, 0.053, 0.060, 0.065),
    (1, "pos_x"): (0.024, 0.028, 0.032, 0.036, 0.039, 0.041, 0.045, 0.049),
    (2, "neg_x"): (0.037, 0.043, 0.048, 0.051, 0.055, 0.057, 0.064, 0.068),
    (7, "pos_x"): (0.043, 0.048, 0.053, 0.057, 0.060, 0.064, 0.069, 0.073),
    (9, "pos_x"): (0.056, 0.064, 0.072, 0.079, 0.085, 0.089, 0.100, 0.107),
}


@pytest.mark.parametrize("key, row", CORROBORATED.items())
def test_table_26_corroborated_rows(key, row):
    case, field = key
    assert getattr(sl.TABLE_26[case], field) == row


def test_table_26_partly_corroborated_rows():
    assert sl.TABLE_26[5].pos_x[:4] == (0.035, 0.037, 0.040, 0.043)
    assert sl.TABLE_26[6].pos_x[:6] == (0.035, 0.043, 0.051, 0.057, 0.063, 0.068)


@pytest.mark.parametrize("case", range(1, 10))
def test_table_26_structure(case):
    c = sl.TABLE_26[case]
    # coefficients rise with ly/lx
    for row in (c.neg_x, c.pos_x):
        if row:
            assert len(row) == 8 and all(b >= a for a, b in zip(row, row[1:], strict=False))
    # negative moments are 4/3 of positive within the rounding of three decimals
    if c.neg_x:
        for n, p in zip(c.neg_x, c.pos_x, strict=True):
            assert 1.27 <= n / p <= 1.40, (case, n, p)
    if c.neg_y:
        assert 1.27 <= c.neg_y / c.pos_y <= 1.40
    # negative coefficients exist exactly where there is a continuous edge
    long_cont = {1: 2, 2: 2, 3: 1, 4: 1, 5: 2, 6: 0, 7: 1, 8: 0, 9: 0}[case]
    short_cont = {1: 2, 2: 1, 3: 2, 4: 1, 5: 0, 6: 2, 7: 0, 8: 1, 9: 0}[case]
    assert (c.neg_x is not None) == (long_cont > 0)
    assert (c.neg_y is not None) == (short_cont > 0)
    assert sl.case_26(2 - long_cont, 2 - short_cont) == case


def test_more_discontinuity_never_reduces_the_mid_span_moments():
    order = [(1, 2), (1, 3), (2, 4), (3, 4), (2, 5), (3, 6), (4, 7), (4, 8), (7, 9), (8, 9)]
    for less, more in order:
        assert all(b >= a for a, b in zip(sl.TABLE_26[less].pos_x, sl.TABLE_26[more].pos_x, strict=True)), (less, more)
        assert sl.TABLE_26[more].pos_y >= sl.TABLE_26[less].pos_y


def test_table_26_interpolation_and_limits():
    c = sl.coefficients_26(1, 1.625)
    assert c.pos_x == pytest.approx((0.041 + 0.045) / 2)
    assert sl.coefficients_26(1, 2.4).pos_x == 0.049  # end value beyond the table
    assert sl.coefficients_26(9, 1.3).neg_x is None


def test_tables_12_and_13():
    assert sl.TABLE_12["end_span_middle"] == (1 / 12, 1 / 10)
    assert sl.TABLE_12["support_next_to_end"] == (1 / 10, 1 / 9)
    assert sl.TABLE_12["interior_span_middle"] == (1 / 16, 1 / 12)
    assert sl.TABLE_12["interior_support"] == (1 / 12, 1 / 9)
    assert sl.TABLE_13["end_support"] == (0.40, 0.45) and sl.TABLE_13["next_to_end_inner"] == (0.55, 0.60)


@pytest.mark.parametrize("D, k", [(100, 1.30), (150, 1.30), (162.5, 1.275), (200, 1.20), (275, 1.05), (300, 1.00), (450, 1.00)])
def test_slab_shear_factor(D, k):
    assert sl.shear_factor_k(D) == pytest.approx(k)


def test_slab_detailing_rules():
    assert sl.min_steel(1000, 150, 415) == pytest.approx(180)  # 0.12 %
    assert sl.min_steel(1000, 150, 250) == pytest.approx(225)  # 0.15 %
    assert sl.max_bar_diameter(150) == 18.75
    assert sl.max_spacing_main(120) == 300 and sl.max_spacing_main(90) == 270
    assert sl.max_spacing_distribution(120) == 450 and sl.max_spacing_distribution(80) == 400
    assert sl.two_way_span_depth_note2(415, simply_supported=True) == pytest.approx(28.0)
    assert sl.two_way_span_depth_note2(250, simply_supported=False) == 40.0
