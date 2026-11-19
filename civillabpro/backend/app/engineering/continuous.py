"""Elastic analysis of a continuous beam on knife-edge supports.

Under uniform load on equal spans it places the points of inflection for the coefficient method (Table 12
gives the design moments there), under the arrangements of imposed load of IS 456:2000, Cl. 22.4.1: dead
load on every span with the imposed load (a) on two adjacent spans, or (b) on alternate spans. Under any
spans, uniform and point loads it is the analysis of the elastic method, with the redistribution of moments
of Cl. 37.1.1 (allowed by Cl. 22.7 with an elastic analysis).

Units: spans in m, loads in kN/m, moments in kN m; sagging positive. Pure Python, no framework imports.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


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


# ----------------------------------------------------------------------------- any spans, uniform and point loads
#
# Used by the elastic method of the continuous beam (STR-036). A span carries a uniform load over its length and any
# number of point loads. Spans in m, loads in kN/m and kN, moments in kN m, sagging positive, as above.


@dataclass(frozen=True)
class SpanLoad:
    """Loads on one span: a uniform load, and point loads as (distance from the left support, m; load, kN)."""

    udl: float = 0.0
    points: tuple[tuple[float, float], ...] = ()

    def __add__(self, other: SpanLoad) -> SpanLoad:
        return SpanLoad(self.udl + other.udl, self.points + other.points)


def load_terms(load: SpanLoad, span: float) -> tuple[float, float]:
    """6 A x / l of the span's free (simply supported) moment diagram, with x from the left end and from the right end, kN m2.

    Uniform load: w l^3 / 4 both ways. Point load P at a from the left (b = l - a): P a b (l + a) / l from the left end,
    P a b (l + b) / l from the right end.
    """
    left = right = load.udl * span**3 / 4.0
    for a, p in load.points:
        b = span - a
        left += p * a * b * (span + a) / span
        right += p * a * b * (span + b) / span
    return left, right


def support_moments_loads(spans: list[float], loads: list[SpanLoad]) -> list[float]:
    """Moments at the n + 1 supports under any loads, by the three-moment equation, the end supports free to rotate.

    At support j: M_(j-1) l_(j-1) + 2 M_j (l_(j-1) + l_j) + M_(j+1) l_j = -(6 A x / l of span j-1, x from its left end)
    - (6 A x / l of span j, x from its right end); solved by the tridiagonal (Thomas) algorithm.
    """
    n = len(spans)
    if n < 2:
        return [0.0] * (n + 1)
    m = n - 1
    terms = [load_terms(ld, s) for ld, s in zip(loads, spans, strict=True)]
    a = [spans[i] for i in range(m)]
    bdiag = [2.0 * (spans[i] + spans[i + 1]) for i in range(m)]
    c = [spans[i + 1] for i in range(m)]
    rhs = [-(terms[i][0] + terms[i + 1][1]) for i in range(m)]
    cp, dp = [0.0] * m, [0.0] * m
    for i in range(m):
        den = bdiag[i] - (a[i] * cp[i - 1] if i else 0.0)
        cp[i] = c[i] / den if i < m - 1 else 0.0
        dp[i] = (rhs[i] - (a[i] * dp[i - 1] if i else 0.0)) / den
    x = [0.0] * m
    for i in range(m - 1, -1, -1):
        x[i] = dp[i] - (cp[i] * x[i + 1] if i < m - 1 else 0.0)
    return [0.0, *x, 0.0]


def free_moment(load: SpanLoad, span: float, x: float) -> float:
    """Moment at x of the span simply supported, kN m."""
    m = load.udl * x * (span - x) / 2.0
    for a, p in load.points:
        m += p * (span - a) * x / span if x <= a else p * a * (span - x) / span
    return m


def free_shear(load: SpanLoad, span: float, x: float) -> float:
    """Shear just to the right of x of the span simply supported, kN (positive upward on the left of the section)."""
    v = load.udl * (span / 2.0 - x)
    for a, p in load.points:
        v += p * (span - a) / span if x < a else -p * a / span
    return v


def moment_in(m_left: float, m_right: float, load: SpanLoad, span: float, x: float) -> float:
    return m_left * (1.0 - x / span) + m_right * x / span + free_moment(load, span, x)


def shear_in(m_left: float, m_right: float, load: SpanLoad, span: float, x: float) -> float:
    return (m_right - m_left) / span + free_shear(load, span, x)


def arrangements(dead: list[SpanLoad], imposed: list[SpanLoad]) -> list[tuple[str, list[SpanLoad]]]:
    """Cl. 22.4.1 with any loads: the dead load on every span, the imposed load as ``load_arrangements`` places it."""
    n = len(dead)
    return [(name, [dead[i] + imposed[i] if on[i] else dead[i] for i in range(n)]) for name, on in load_arrangements(n)]


def redistribute(moments: list[list[float]], fraction: float | list[float]) -> tuple[list[list[float]], list[float]]:
    """Cl. 37.1.1: in every arrangement, the hogging moment at each support is held to (1 - fraction) of the greatest hogging there
    over all arrangements (one fraction, or one per support); span moments then follow from statics, so equilibrium holds. Returns
    the modified support moments of every arrangement and the caps (kN m, as magnitudes)."""
    fr = fraction if isinstance(fraction, list) else [fraction] * len(moments[0])
    caps = [(1.0 - fr[j]) * max(max(-ms[j], 0.0) for ms in moments) for j in range(len(moments[0]))]
    out = [[-min(-m, caps[j]) if m < 0.0 else m for j, m in enumerate(ms)] for ms in moments]
    return out, caps


@dataclass(frozen=True)
class SpanEnvelope:
    """Envelopes along one span, at stations x (m from the left support; both sides of every point load)."""

    x: tuple[float, ...]
    sag_elastic: tuple[float, ...]  # greatest sagging, >= 0
    hog_elastic: tuple[float, ...]  # greatest hogging as a magnitude, >= 0
    sag: tuple[float, ...]  # after redistribution
    hog: tuple[float, ...]
    shear: tuple[float, ...]  # greatest |V| after redistribution


def stations(span: float, load_points: list[float], steps: int = 200) -> list[float]:
    """Evenly spaced stations, and a station just either side of every point load."""
    eps = 1e-6 * span
    xs = {span * k / steps for k in range(steps + 1)}
    for a in load_points:
        xs.update(x for x in (a - eps, a + eps) if 0.0 <= x <= span)
    return sorted(xs)


def envelopes(spans: list[float], cases: list[list[SpanLoad]], fraction: float | list[float], steps: int = 200
              ) -> tuple[list[SpanEnvelope], list[float], list[float]]:
    """Moment and shear envelopes of every span over the arrangements, elastic and after redistribution of ``fraction`` (one, or one
    per support).

    Returns the envelopes, the greatest elastic hogging at each support and the redistributed one (magnitudes, kN m).
    """
    elastic = [support_moments_loads(spans, loads) for loads in cases]
    modified, caps = redistribute(elastic, fraction)
    hog_e = [max(max(-ms[j], 0.0) for ms in elastic) for j in range(len(spans) + 1)]
    out = []
    for i, span in enumerate(spans):
        pts = sorted({a for loads in cases for a, _ in loads[i].points})
        xs = stations(span, pts, steps)
        se, he, sr, hr, vr = [], [], [], [], []
        for x in xs:
            me = [moment_in(ms[i], ms[i + 1], loads[i], span, x) for ms, loads in zip(elastic, cases, strict=True)]
            mr = [moment_in(ms[i], ms[i + 1], loads[i], span, x) for ms, loads in zip(modified, cases, strict=True)]
            v = [abs(shear_in(ms[i], ms[i + 1], loads[i], span, x)) for ms, loads in zip(modified, cases, strict=True)]
            se.append(max(max(me), 0.0))
            he.append(max(-min(me), 0.0))
            sr.append(max(max(mr), 0.0))
            hr.append(max(-min(mr), 0.0))
            vr.append(max(v))
        out.append(SpanEnvelope(tuple(xs), tuple(se), tuple(he), tuple(sr), tuple(hr), tuple(vr)))
    return out, hog_e, caps
