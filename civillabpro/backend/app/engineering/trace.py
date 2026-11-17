"""Calculation sheet: the auditable record every engineering engine returns.

A sheet is a list of sections; a section holds steps (one formula line each,
with its code clause) and checks (one limit each, with an OK / Not OK verdict
and a utilisation). Engines build the sheet while they compute, so the report,
the screen and the tests all read the same numbers.

Pure Python: no framework imports are allowed in ``app.engineering``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Op = Literal["<=", ">="]


@dataclass(frozen=True)
class Step:
    """One calculation line."""

    ref: str  # code clause, e.g. "IS 456:2000, Cl. 38.1", or "Input"
    title: str
    eq: str = ""  # symbolic form
    sub: str = ""  # numbers substituted
    value: float | str | None = None
    unit: str = ""
    dp: int = 2
    kind: str = "step"


@dataclass(frozen=True)
class Check:
    """One limit. ``util`` is demand / capacity where that ratio has a meaning."""

    id: str
    ref: str
    title: str
    lhs_label: str
    lhs: float
    op: Op
    rhs_label: str
    rhs: float
    unit: str
    ok: bool
    util: float | None = None
    dp: int = 2
    kind: str = "check"


@dataclass
class Section:
    title: str
    items: list[Step | Check] = field(default_factory=list)


@dataclass
class Flag:
    """Something the engineer must read: doubtful data, an assumption that bites, advice."""

    level: Literal["info", "warning", "error"]
    message: str
    ref: str = ""


class CalcSheet:
    def __init__(self) -> None:
        self.sections: list[Section] = []
        self.flags: list[Flag] = []

    def section(self, title: str) -> Section:
        s = Section(title)
        self.sections.append(s)
        return s

    def step(
        self,
        ref: str,
        title: str,
        eq: str = "",
        sub: str = "",
        value: float | str | None = None,
        unit: str = "",
        dp: int = 2,
    ) -> None:
        self._current().items.append(Step(ref, title, eq, sub, _clean(value), unit, dp))

    def check(
        self,
        id: str,
        ref: str,
        title: str,
        lhs_label: str,
        lhs: float,
        op: Op,
        rhs_label: str,
        rhs: float,
        unit: str = "",
        dp: int = 2,
        ratio: bool = True,
    ) -> bool:
        """Record a limit and return whether it is satisfied.

        A tolerance of 1e-9 (relative) keeps an exact-limit case from failing on
        floating-point noise. ``ratio=False`` marks limits where demand/capacity
        is not meaningful (counts, ranges).
        """
        tol = 1e-9 * max(abs(lhs), abs(rhs), 1.0)
        ok = lhs <= rhs + tol if op == "<=" else lhs >= rhs - tol
        util: float | None = None
        if ratio:
            num, den = (lhs, rhs) if op == "<=" else (rhs, lhs)
            if den > 0 and math.isfinite(num) and math.isfinite(den):
                util = round(num / den, 3)
        self._current().items.append(
            Check(id, ref, title, lhs_label, round(float(lhs), 6), op, rhs_label, round(float(rhs), 6), unit, ok, util, dp)
        )
        return ok

    def flag(self, level: Literal["info", "warning", "error"], message: str, ref: str = "") -> None:
        self.flags.append(Flag(level, message, ref))

    def checks(self) -> list[Check]:
        return [i for s in self.sections for i in s.items if isinstance(i, Check)]

    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks())

    def to_dict(self) -> dict[str, Any]:
        return {
            "sections": [{"title": s.title, "items": [asdict(i) for i in s.items]} for s in self.sections],
            "flags": [asdict(f) for f in self.flags],
        }

    def _current(self) -> Section:
        if not self.sections:
            self.sections.append(Section("Calculation"))
        return self.sections[-1]


def _clean(v: float | str | None) -> float | str | None:
    if isinstance(v, float):
        return round(v, 6) if math.isfinite(v) else None
    return v
