"""Elastic analysis of a continuous beam on knife-edge supports under uniform load on each span.

Used for the extent of the hogging regions (where top bars must run) under the arrangements of imposed load
of IS 456:2000, Cl. 22.4.1: dead load on every span with the imposed load (a) on two adjacent spans, or
(b) on alternate spans. The design moments themselves come from Table 12; this only places the points of
inflection.

Units: spans in m, loads in kN/m, moments in kN m; sagging positive. Pure Python, no framework imports.
"""

from __future__ import annotations

import math


def support_moments(spans: list[float], loads: list[float]) -> list[float]:
    """Moments at the n + 1 supports by the three-moment equation (Clapeyron), the end supports free to rotate.

    M_(i-1) l_i + 2 M_i (l_i + l_(i+1)) + M_(i+1) l_(i+1) = -(w_i l_i^3 + w_(i+1) l_(i+1)^3) / 4, solved by the
    tridiagonal (Thomas) algorithm.
    """
    n = len(spans)
    if n < 2:
        return [0.0] * (n + 1)
    m = n - 1  # unknown interior moments
    a = [spans[i] for i in range(m)]  # sub-diagonal (coefficient of M_(i-1)), a[0] unused
    bdiag = [2.0 * (spans[i] + spans[i + 1]) for i in range(m)]
    c = [spans[i + 1] for i in range(m)]  # super-diagonal, c[-1] unused
    rhs = [-(loads[i] * spans[i] ** 3 + loads[i + 1] * spans[i + 1] ** 3) / 4.0 for i in range(m)]
    cp, dp = [0.0] * m, [0.0] * m
    for i in range(m):
        den = bdiag[i] - (a[i] * cp[i - 1] if i else 0.0)
        cp[i] = c[i] / den if i < m - 1 else 0.0
        dp[i] = (rhs[i] - (a[i] * dp[i - 1] if i else 0.0)) / den
    x = [0.0] * m
    for i in range(m - 1, -1, -1):
        x[i] = dp[i] - (cp[i] * x[i + 1] if i < m - 1 else 0.0)
    return [0.0, *x, 0.0]


def load_arrangements(n: int) -> list[tuple[str, list[bool]]]:
    """Cl. 22.4.1: imposed load on every span, on alternate spans (both sets), and on each pair of adjacent spans."""
    out = [("all spans", [True] * n), ("odd spans", [i % 2 == 0 for i in range(n)]), ("even spans", [i % 2 == 1 for i in range(n)])]
    out += [(f"spans {i + 1} and {i + 2}", [j in (i, i + 1) for j in range(n)]) for i in range(n - 1)]
    return out


def moment_at(m_left: float, m_right: float, w: float, span: float, x: float) -> float:
    """Moment at x from the left support of a span with end moments and a uniform load, kN m (sagging positive)."""
    return m_left * (1.0 - x / span) + m_right * x / span + w * x * (span - x) / 2.0


def _first_zero(m0: float, m1: float, w: float, span: float) -> float:
    """Distance from the end with moment m0 to the first point where the moment reaches zero (span if never)."""
    if m0 >= 0:
        return 0.0
    # M(x) = (w/2)(-x^2) + (w span/2 + (m1 - m0)/span) x + m0 ; find the first root of -a x^2 + b x + m0 = 0
    a, b = w / 2.0, w * span / 2.0 + (m1 - m0) / span
    if a <= 0:
        return min(span, -m0 / b) if b > 0 else span
    disc = b * b + 4.0 * a * m0
    if disc < 0:
        return span
    x = (b - math.sqrt(disc)) / (2.0 * a)
    return x if 0.0 < x < span else span


def hogging_extents(spans: list[float], wd: float, wl: float) -> list[tuple[float, float]]:
    """For each span, the greatest distance from its left and from its right support over which the top is in
    tension, over the arrangements of Cl. 22.4.1, m."""
    n = len(spans)
    out = [[0.0, 0.0] for _ in range(n)]
    for _, loaded in load_arrangements(n):
        w = [wd + (wl if loaded[i] else 0.0) for i in range(n)]
        ms = support_moments(spans, w)
        for i in range(n):
            out[i][0] = max(out[i][0], _first_zero(ms[i], ms[i + 1], w[i], spans[i]))
            out[i][1] = max(out[i][1], _first_zero(ms[i + 1], ms[i], w[i], spans[i]))
    return [(a, b) for a, b in out]


def envelope(spans: list[float], wd: float, wl: float, points: int = 41) -> list[list[tuple[float, float, float]]]:
    """Moment envelope in each span: (x, least moment, greatest moment) at ``points`` stations, kN m."""
    n = len(spans)
    cases = []
    for _, loaded in load_arrangements(n):
        w = [wd + (wl if loaded[i] else 0.0) for i in range(n)]
        cases.append((w, support_moments(spans, w)))
    out = []
    for i, span in enumerate(spans):
        rows = []
        for k in range(points):
            x = span * k / (points - 1)
            vals = [moment_at(ms[i], ms[i + 1], w[i], span, x) for w, ms in cases]
            rows.append((x, min(vals), max(vals)))
        out.append(rows)
    return out


def shear_at(m_left: float, m_right: float, w: float, span: float, x: float) -> float:
    """Shear at x from the left support of a span with end moments and a uniform load, kN (positive upward on the left)."""
    return (m_right - m_left) / span + w * (span / 2.0 - x)


def shear_envelope(spans: list[float], wd: float, wl: float, points: int = 41) -> list[list[tuple[float, float]]]:
    """Greatest shear (absolute) in each span over the arrangements of Cl. 22.4.1: (x, |V|max) at ``points`` stations, kN."""
    n = len(spans)
    cases = []
    for _, loaded in load_arrangements(n):
        w = [wd + (wl if loaded[i] else 0.0) for i in range(n)]
        cases.append((w, support_moments(spans, w)))
    out = []
    for i, span in enumerate(spans):
        rows = []
        for k in range(points):
            x = span * k / (points - 1)
            rows.append((x, max(abs(shear_at(ms[i], ms[i + 1], w[i], span, x)) for w, ms in cases)))
        out.append(rows)
    return out
