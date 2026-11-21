#!/usr/bin/env python3
"""Independent hand check of the estimation arithmetic (measurements, analysis of rates, abstract of cost).

By exact fractions and a rounding of their own (half up, to the paisa), against the engine's decimals:

  * measurements: the product of the count and the dimensions given, each line to 0.01, deductions subtracted;
  * analysis of rates: the lines' amounts to the paisa, water on their cost, overheads and profit on the cost with water, the rate
    per unit of output to the paisa;
  * abstract: each amount to the paisa, the additions on the sub-total, the total rounded to the rupee.

The figures of the worked examples are illustrative, not taken from any published schedule.

Run:  python tests/handcheck/check_estimate.py
"""

from __future__ import annotations

import pathlib
import random
import sys
from fractions import Fraction as F

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from app.modules.estimation.domain.abstract import Addition, abstract, amount  # noqa: E402
from app.modules.estimation.domain.measure import MeasureLine, item_quantity, line_quantity  # noqa: E402
from app.modules.estimation.domain.rates import AnalysisLine, analyse  # noqa: E402


def half_up(x: F, places: int = 2) -> F:
    q = F(10) ** places
    n = x * q
    whole = n.numerator // n.denominator  # floor
    frac = n - whole
    if frac >= F(1, 2):
        whole += 1
    return F(whole) / q


def f(x: float) -> F:
    return F(repr(x))


# a rate analysis of 1 m3 of reinforced concrete work, constituents and rates illustrative
LINES = [
    ("material", "Stone aggregate 20 mm", "m3", 0.67, 1860.0), ("material", "Stone aggregate 10 mm", "m3", 0.22, 1910.0),
    ("material", "Coarse sand", "m3", 0.445, 2150.0), ("material", "Cement", "t", 0.384, 7100.0),
    ("labour", "Mason", "day", 0.17, 941.0), ("labour", "Beldar", "day", 2.0, 707.0), ("labour", "Bhisti", "day", 0.7, 765.0),
    ("plant", "Concrete mixer with hopper", "day", 0.07, 1350.0), ("plant", "Vibrator", "day", 0.07, 520.0),
    ("sundries", "Sundries", "LS", 1.0, 112.5),
]


def hand_analysis(lines: list[tuple[str, str, str, float, float]], out: float, water: float, op: float) -> dict[str, F]:
    amounts = [half_up(f(q) * f(r)) for _, _, _, q, r in lines]
    cost = sum(amounts, F(0))
    w = half_up(cost * f(water) / 100)
    o = half_up((cost + w) * f(op) / 100)
    return {"cost": cost, "water": w, "op": o, "total": cost + w + o, "rate": half_up((cost + w + o) / f(out))}


def main() -> int:
    bad: list[str] = []
    n = 0

    def same(name: str, engine: object, hand: F) -> None:
        nonlocal n
        n += 1
        if F(str(engine)) != hand:
            bad.append(f"{name}: engine {engine} hand {float(hand)}")

    # analysis of rates: the worked example and random ones
    cases = [(LINES, 1.0, 1.0, 15.0), (LINES, 2.5, 1.0, 15.0), (LINES[:4], 1.0, 0.0, 10.0)]
    rng = random.Random(456)
    for _ in range(60):
        k = rng.randint(1, 8)
        lines = [(rng.choice(["material", "labour", "plant", "sundries"]), f"line {i}", "u", round(rng.uniform(0.01, 50), 3), round(rng.uniform(1, 9000), 2))
                 for i in range(k)]
        cases.append((lines, round(rng.uniform(0.1, 20), 2), rng.choice([0.0, 1.0, 1.5]), rng.choice([10.0, 15.0, 17.5])))
    for i, (lines, out, w, op) in enumerate(cases):
        e = analyse([AnalysisLine(k, d, u, q, r) for k, d, u, q, r in lines], out, w, op)  # type: ignore[arg-type]
        h = hand_analysis(lines, out, w, op)
        for key, val in (("cost", e.cost), ("water", e.water), ("op", e.overheads_profit), ("total", e.total), ("rate", e.rate)):
            same(f"analysis {i} {key}", val, h[key])
    base = analyse([AnalysisLine(k, d, u, q, r) for k, d, u, q, r in LINES], 1.0)  # type: ignore[arg-type]
    # by hand, line by line: 1246.20 + 420.20 + 956.75 + 2726.40 + 159.97 + 1414.00 + 535.50 + 94.50 + 36.40 + 112.50 = 7702.42;
    # water 1 % = 77.02; overheads and profit 15 % of 7779.44 = 1166.92; rate 8946.36
    same("worked example cost", base.cost, F("7702.42"))
    same("worked example water (1 %)", base.water, F("77.02"))
    same("worked example overheads and profit (15 % of 7779.44)", base.overheads_profit, F("1166.92"))
    same("worked example rate", base.rate, F("8946.36"))

    # measurements
    rng = random.Random(1200)
    for i in range(200):
        dims = [None if rng.random() < 0.3 else round(rng.uniform(0.05, 30), 2) for _ in range(3)]
        nos = rng.choice([1, 2, 3, 4, 6, 12, 0.5])
        deduct = rng.random() < 0.2
        ln = MeasureLine("", nos, *dims, deduct)  # type: ignore[arg-type]
        prod = f(float(nos))
        for d in dims:
            if d is not None:
                prod *= f(d)
        want = half_up(prod)
        same(f"measurement line {i}", line_quantity(ln), -want if deduct else want)
    lines = [MeasureLine("footing", 4, 2.2, 2.05, 0.45), MeasureLine("column stub", 4, 0.3, 0.45, 1.2), MeasureLine("pipe sleeve", 2, 0.5, 0.5, 0.45, True)]
    # by hand: 4 x 2.2 x 2.05 x 0.45 = 8.118 -> 8.12; 4 x 0.3 x 0.45 x 1.2 = 0.648 -> 0.65; less 2 x 0.5 x 0.5 x 0.45 = 0.225 -> 0.23; 8.54
    same("worked measurement", item_quantity(lines), F("8.54"))

    # abstract
    rng = random.Random(2024)
    for i in range(40):
        rows = [(round(rng.uniform(0.01, 500), 2), round(rng.uniform(1, 20000), 2)) for _ in range(rng.randint(1, 15))]
        adds = [Addition(f"add {k}", rng.choice([1.0, 2.0, 3.0, 12.5, 18.0])) for k in range(rng.randint(0, 3))]
        amts = [amount(q, r) for q, r in rows]
        res = abstract(amts, adds)
        hand_amts = [half_up(f(q) * f(r)) for q, r in rows]
        sub = sum(hand_amts, F(0))
        same(f"abstract {i} subtotal", res.subtotal, sub)
        tot = sub
        for (label, _pct, val), a in zip(res.additions, adds, strict=True):
            want = half_up(sub * f(a.pct) / 100)
            same(f"abstract {i} {label}", val, want)
            tot += want
        same(f"abstract {i} total", res.total, tot)
        same(f"abstract {i} rounded", res.rounded, half_up(tot, 0))
    for line in bad:
        print("BAD", line)
    if bad:
        return 1
    print(f"OK: {n} values of measurements, analyses of rates and abstracts agree with the independent hand check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
