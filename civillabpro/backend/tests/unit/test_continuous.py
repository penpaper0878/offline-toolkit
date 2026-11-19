"""Elastic analysis of continuous beams against classical results."""

import pytest

from app.engineering import continuous as c


def test_two_equal_spans():
    ms = c.support_moments([5.0, 5.0], [10.0, 10.0])
    assert ms == pytest.approx([0.0, -10 * 25 / 8, 0.0])
    # point of inflection a quarter of the span from the middle support
    left, right = c.hogging_extents([5.0, 5.0], 10.0, 0.0)[0]
    assert left == 0.0 and right == pytest.approx(5.0 / 4)


def test_three_equal_spans_classical_coefficients():
    w, span = 12.0, 4.0
    assert c.support_moments([span] * 3, [w] * 3)[1:3] == pytest.approx([-0.1 * w * span**2] * 2)
    # imposed load on the end spans only, and on the middle span only: both give -0.05 w l^2
    assert c.support_moments([span] * 3, [w, 0, w])[1] == pytest.approx(-0.05 * w * span**2)
    assert c.support_moments([span] * 3, [0, w, 0])[1] == pytest.approx(-0.05 * w * span**2)
    # one end span loaded: -w l^2/15 at the near support, +w l^2/60 at the far one
    ms = c.support_moments([span] * 3, [w, 0, 0])
    assert ms[1] == pytest.approx(-w * span**2 / 15) and ms[2] == pytest.approx(w * span**2 / 60)


def test_unequal_spans_satisfy_the_three_moment_equation():
    spans, w = [4.0, 6.5, 5.0, 3.5], [10.0, 20.0, 15.0, 8.0]
    m = c.support_moments(spans, w)
    for i in range(1, len(spans)):
        lhs = m[i - 1] * spans[i - 1] + 2 * m[i] * (spans[i - 1] + spans[i]) + m[i + 1] * spans[i]
        assert lhs == pytest.approx(-(w[i - 1] * spans[i - 1] ** 3 + w[i] * spans[i] ** 3) / 4)


def test_load_arrangements_of_clause_22_4_1():
    names = [n for n, _ in c.load_arrangements(4)]
    assert names == ["all spans", "odd spans", "even spans", "spans 1 and 2", "spans 2 and 3", "spans 3 and 4"]
    assert dict(c.load_arrangements(4))["odd spans"] == [True, False, True, False]


def test_hogging_throughout_an_unloaded_middle_span():
    # heavy imposed load on the end spans keeps the middle span hogging over its whole length
    ext = c.hogging_extents([5.0] * 3, 10.0, 30.0)
    assert ext[1] == (5.0, 5.0)
    # light imposed load: a sagging region remains
    assert ext[1] != c.hogging_extents([5.0] * 3, 10.0, 1.0)[1] and c.hogging_extents([5.0] * 3, 10.0, 1.0)[1][0] < 2.5


def test_envelope_brackets_every_arrangement():
    spans, wd, wl = [5.0] * 4, 20.0, 15.0
    env = c.envelope(spans, wd, wl, 11)
    for _, loaded in c.load_arrangements(4):
        w = [wd + (wl if x else 0.0) for x in loaded]
        ms = c.support_moments(spans, w)
        for i, rows in enumerate(env):
            for x, lo, hi in rows:
                m = c.moment_at(ms[i], ms[i + 1], w[i], spans[i], x)
                assert lo - 1e-9 <= m <= hi + 1e-9
