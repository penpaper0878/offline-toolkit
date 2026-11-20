"""Rectangular combined footing of uniform depth under two rectangular columns, to IS 456:2000.

The columns stand on the footing's long axis, column 1 to the left. The plan is centred on the resultant of the
column loads, so the pressure is uniform but for the 50 mm rounding of the length; the left end may be fixed (a
property line). Along the length the footing is a beam on the soil pressure, hogging between the columns and sagging
under them and in the overhangs. Across, each column's load is carried in a band of steel under it.

Design, with the factored net pressure from the column loads (own weight acts against its own reaction):

* bending along the length at the faces of the columns and at the greatest hogging between them (Cl. 34.2.3.2);
  bottom bars and top bars over the whole width, at least the minimum of Cl. 26.5.2.1;
* bending across under each column: the column's load spread over the width, moment at the face of the column, in a
  band the column's length plus 0.75 d each side (interpretation 96), minimum steel elsewhere;
* one-way shear at d from the faces of the columns, along and across (Cl. 34.2.4.1(a)), and punching at d/2 around
  each column (Cl. 31.6, 34.2.4.1(b)), the perimeter cut by the footing's ends or merged where two of them overlap;
* development of every bar group beyond its critical sections at the stress there (Cl. 26.2.1, 34.2.4.3), with
  90 degree end bends where straight bars fall short (Cl. 26.2.2.1(b));
* bearing at the base of each column (Cl. 34.4), edge thickness (Cl. 34.1.2), cover (Cl. 26.4.2.2).

Worked example (the defaults): columns 400 x 400 (900 kN) and 450 x 450 (1200 kN) at 3.6 m, safe bearing pressure
200 kN/m2, 10 percent for own weight, M25 / Fe 415. tests/handcheck/check_combined_footing.py reproduces it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engineering import is456
from app.engineering import is456_slabs as sl
from app.engineering.rebar import bar_area, bend_radius
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.footing import FOOTING_BAR_DIAMETERS, FOOTING_MIN_COVER, PRACTICAL_MIN_SPACING, bars_across, bent_value

ELEMENT_TYPE = "combined_footing"
ENGINE_VERSION = "1.0.0"
CODE_BASIS = ("IS 456:2000", "IS 2502:1963")
REF = is456.CODE

EDGE_MIN = 150.0  # Cl. 34.1.2, footings on soil
STEP = 50.0  # plan and depth in 50 mm steps
GRID = 25.0  # the left end is set out in 25 mm steps
MIN_GAP = 300.0  # clear distance between the columns
BAND_SPREAD = 0.75  # the band under a column reaches 0.75 d beyond each face (interpretation 96)
MAX_SIZE = 20000.0


def _f(default: Any, title: str, group: str, unit: str = "", labels: dict[str, str] | None = None, **kw: Any) -> Any:
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


class CombinedFootingInput(BaseModel):
    """Everything the combined footing engine reads. Lengths in mm, loads in kN, pressures in kN/m2."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("CF1", "Footing mark", "Member", min_length=1, max_length=40)
    column1_width_mm: float = _f(400, "Column 1 width b_1", "Column 1 (left)", "mm", ge=150, le=2000, description="Across the footing")
    column1_depth_mm: float = _f(400, "Column 1 depth D_1", "Column 1 (left)", "mm", ge=150, le=3000, description="Along the footing")
    p1_service_kn: float = _f(900, "Column 1 service load", "Column 1 (left)", "kN", gt=0, le=1e5, description="Dead + imposed, unfactored")
    column2_width_mm: float = _f(450, "Column 2 width b_2", "Column 2 (right)", "mm", ge=150, le=2000, description="Across the footing")
    column2_depth_mm: float = _f(450, "Column 2 depth D_2", "Column 2 (right)", "mm", ge=150, le=3000, description="Along the footing")
    p2_service_kn: float = _f(1200, "Column 2 service load", "Column 2 (right)", "kN", gt=0, le=1e5, description="Dead + imposed, unfactored")
    spacing_mm: float = _f(3600, "Column spacing", "Columns", "mm", ge=600, le=15000, description="Centre to centre, along the footing")

    load_factor: float = _f(1.5, "Load factor", "Loading", "", ge=1.0, le=2.0, description="For design of the concrete, Table 18")
    self_weight_pct: float = _f(10, "Allowance for own weight", "Loading", "%", ge=0, le=40, description="Footing and backfill, for sizing only")
    sbc_kn_m2: float = _f(200, "Safe bearing pressure", "Soil", "kN/m2", gt=0, le=5000, description="Net, from the soil investigation")

    left_end_mm: float | None = _f(None, "Left end to column 1", "Size", "mm", ge=75, le=10000,
                                   description="From the left end to the centre of column 1, e.g. at a property line. Blank: chosen by the engine")
    length_mm: float | None = _f(None, "Length L", "Size", "mm", ge=1000, le=MAX_SIZE, description="Blank: centred on the resultant of the loads")
    width_mm: float | None = _f(None, "Width B", "Size", "mm", ge=500, le=MAX_SIZE, description="Blank: the least the bearing pressure allows")
    depth_mm: float | None = _f(None, "Depth D", "Size", "mm", ge=200, le=3000, description="Blank: the least depth that passes")

    fck: Literal[20, 25, 30, 35, 40] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in (20, 25, 30, 35, 40)})
    fy: Literal[250, 415, 500, 550] = _f(415, "Steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Clear cover", "Materials", "mm", ge=40, le=100, description="Blank: 50 mm or Table 16, whichever is more")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)
    bar_dia_mm: Literal[10, 12, 16, 20, 25] | None = _f(None, "Bar size", "Reinforcement", "mm", description="Blank lets the engine choose for each set")

    def resultant_offset(self) -> float:
        """Distance from the centre of column 1 to the resultant of the service loads, mm."""
        return self.spacing_mm * self.p2_service_kn / (self.p1_service_kn + self.p2_service_kn)

    @model_validator(mode="after")
    def _consistent(self) -> CombinedFootingInput:
        s, d1, d2 = self.spacing_mm, self.column1_depth_mm, self.column2_depth_mm
        if s - (d1 + d2) / 2 < MIN_GAP - 1e-9:
            raise ValueError(f"The columns must stand at least {MIN_GAP:.0f} mm apart, face to face: increase the spacing.")
        er = self.resultant_offset()
        a = self.left_end_mm
        if a is not None and a < d1 / 2:
            raise ValueError("The left end cannot cut column 1: the distance to its centre must be at least half its depth.")
        if self.length_mm is not None:
            if a is not None and self.length_mm - a - s < d2 / 2 - 1e-9:
                raise ValueError("The length entered does not reach past column 2.")
            if a is None:
                a = left_end_centred(self.length_mm, er)
                if a < d1 / 2 or self.length_mm - a - s < d2 / 2 - 1e-9:
                    raise ValueError("Centred on the loads, this length would cut a column: enter a longer length, or the left end as well.")
        elif a is not None and length_centred(a, er) - a - s < d2 / 2 - 1e-9:
            raise ValueError("With the left end this close to column 1, no rectangle centred on the loads reaches past column 2: the heavier "
                             "load is at the restricted end. Enter the length as well (the pressure is then not uniform), or use a "
                             "trapezoidal or strap footing.")
        if self.width_mm is not None and self.width_mm <= max(self.column1_width_mm, self.column2_width_mm):
            raise ValueError("The footing must be wider than both columns.")
        return self


def length_centred(a: float, er: float) -> float:
    """The length that puts the footing's centre on the resultant, rounded up to 50 mm."""
    return math.ceil(2.0 * (a + er) / STEP - 1e-9) * STEP


def left_end_centred(L: float, er: float) -> float:
    """The left end that puts the centre of a given length on the resultant, to the nearest 25 mm."""
    return round((L / 2.0 - er) / GRID) * GRID


@dataclass(frozen=True)
class Col:
    x: float  # centre, from the left end, mm
    b: float  # across, mm
    D: float  # along, mm
    p: float  # service load, kN

    @property
    def lo(self) -> float:
        return self.x - self.D / 2.0

    @property
    def hi(self) -> float:
        return self.x + self.D / 2.0


@dataclass(frozen=True)
class Plan:
    L: float
    B: float
    a: float
    cols: tuple[Col, Col]


def make_plan(inp: CombinedFootingInput, a: float, L: float, B: float) -> Plan:
    c1 = Col(a, inp.column1_width_mm, inp.column1_depth_mm, inp.p1_service_kn)
    c2 = Col(a + inp.spacing_mm, inp.column2_width_mm, inp.column2_depth_mm, inp.p2_service_kn)
    return Plan(L, B, a, (c1, c2))


def eccentricity(plan: Plan) -> float:
    """Resultant of the column loads less the footing's centre, mm (positive: to the right)."""
    p = sum(c.p for c in plan.cols)
    return sum(c.p * c.x for c in plan.cols) / p - plan.L / 2.0


def service_pressures(inp: CombinedFootingInput, plan: Plan) -> tuple[float, float]:
    """Greatest and least gross service pressure, kN/m2: the own-weight allowance at the centre, the column loads at their resultant."""
    p = inp.p1_service_kn + inp.p2_service_kn
    Lm, Bm = plan.L / 1000.0, plan.B / 1000.0
    mean = p * (1 + inp.self_weight_pct / 100.0) / (Lm * Bm)
    var = 6.0 * p * abs(eccentricity(plan)) / 1000.0 / (Bm * Lm * Lm)
    return mean + var, mean - var


class Statics:
    """Factored net pressure q(x) = q0 + k x (kN/m2, x in m) balancing the factored column loads, and the shear and bending
    along the footing (kN, kN m; sagging, tension at the bottom, positive). Each column's load is spread over its depth."""

    def __init__(self, plan: Plan, gamma: float) -> None:
        self.plan = plan
        self.pu = [gamma * c.p for c in plan.cols]
        total = sum(self.pu)
        Lm, Bm = plan.L / 1000.0, plan.B / 1000.0
        e = eccentricity(plan) / 1000.0
        self.k = 12.0 * total * e / (Bm * Lm ** 3)
        self.q0 = total / (Lm * Bm) - self.k * Lm / 2.0
        self.Bm = Bm
        self._hog: tuple[float, float] | None = None

    def q(self, x: float) -> float:
        return self.q0 + self.k * x / 1000.0

    def shear(self, x: float) -> float:
        t = x / 1000.0
        v = self.Bm * (self.q0 * t + self.k * t * t / 2.0)
        for c, pu in zip(self.plan.cols, self.pu, strict=True):
            v -= pu * min(max((x - c.lo) / c.D, 0.0), 1.0)
        return v

    def moment(self, x: float) -> float:
        t = x / 1000.0
        m = self.Bm * (self.q0 * t * t / 2.0 + self.k * t ** 3 / 6.0)
        for c, pu in zip(self.plan.cols, self.pu, strict=True):
            if x >= c.hi:
                m -= pu * (x - c.x) / 1000.0
            elif x > c.lo:
                m -= pu * (x - c.lo) ** 2 / (2.0 * c.D) / 1000.0
        return m

    def faces(self) -> list[float]:
        c1, c2 = self.plan.cols
        return [c1.lo, c1.hi, c2.lo, c2.hi]

    def greatest_hogging(self) -> tuple[float, float]:
        """(x, M) of the least moment between the inner faces: where the shear changes sign, or a face."""
        if self._hog is None:
            self._hog = self._hogging()
        return self._hog

    def _hogging(self) -> tuple[float, float]:
        g0, g1 = self.plan.cols[0].hi, self.plan.cols[1].lo
        n = 200
        xs = [g0 + (g1 - g0) * i / n for i in range(n + 1)]
        best = min(xs, key=self.moment)
        for i in range(n):
            a, b = xs[i], xs[i + 1]
            if self.shear(a) <= 0.0 <= self.shear(b):
                for _ in range(60):
                    m = (a + b) / 2.0
                    if self.shear(m) <= 0.0:
                        a = m
                    else:
                        b = m
                x = (a + b) / 2.0
                if self.moment(x) < self.moment(best):
                    best = x
        return best, self.moment(best)


@dataclass
class Group:
    """One set of parallel bars."""

    dia: int
    n: int
    s: float
    area: float
    bent: bool = False


@dataclass
class Band:
    lo: float
    hi: float
    a_t: float  # projection across beyond the column face, mm
    m: float  # kN m, at the face of the column
    as_flex: float
    as_req: float
    bars: Group | None = None
    ld_req: float = 0.0
    avail: float = 0.0
    v: float = 0.0
    tau: float = 0.0
    tc: float = 0.0

    @property
    def w(self) -> float:
        return self.hi - self.lo


@dataclass
class ShearSection:
    x: float
    where: str
    v: float
    m: float
    steel: str  # "bottom" or "top"
    d: float
    tau: float
    tc: float


@dataclass
class Punch:
    cols: tuple[int, ...]
    b0: float
    vp: float
    tau: float
    ks: float
    allow: float
    d: float


@dataclass
class Trial:
    D: float
    d_t: float
    d_lb: float
    d_top: float
    bands: list[Band]
    dist: Group | None
    m_pos: float
    x_pos: float
    m_hog: float
    x_hog: float
    as_flex_bottom: float
    as_bottom: float
    as_flex_top: float
    as_top: float
    bottom: Group | None
    top: Group | None
    anchor_bottom: list[tuple[float, float, float]] = field(default_factory=list)  # (x, required, available)
    anchor_top: tuple[float, float] = (0.0, 0.0)
    shear: list[ShearSection] = field(default_factory=list)
    punching: list[Punch] = field(default_factory=list)
    ok_flexure: bool = True
    ok_bars: bool = True
    ok_shear: bool = True
    anchorage_blocked: bool = False  # the bars across cannot be developed: a wider footing helps
    along_blocked: bool = False  # the bars along cannot be developed within the overhangs


def effective_cover(inp: CombinedFootingInput) -> float:
    if inp.clear_cover_mm is not None:
        return inp.clear_cover_mm
    return max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure))


def _as_flex(m_knm: float, fck: float, fy: float, b: float, d: float) -> float:
    return is456.design_rectangular(m_knm * 1e6, fck, fy, b, d, 0).ast_req if m_knm > 0 else 0.0


def _spacing_ok(s: float, dia: int, agg: float) -> bool:
    return s >= PRACTICAL_MIN_SPACING - 1e-9 and s - dia >= is456.min_clear_bar_spacing_horizontal(dia, agg) - 1e-9


def _anchor(req: float, avail: float, dia: int, fy: float) -> tuple[bool, bool]:
    """(develops straight, develops with a 90 degree bend at the end)."""
    return req <= avail + 1e-9, req <= bent_value(avail, dia, fy) + 1e-9


def band_bars(as_req: float, w: float, dia: int, s_max: float) -> Group:
    """Bars at one spacing across a band of width w, each bar serving a strip s wide; spacing in 10 mm steps."""
    a1 = bar_area(dia)
    s = max(math.floor(min(s_max, a1 * w / as_req if as_req > 0 else s_max) / 10.0 + 1e-9) * 10.0, 10.0)  # below 100 fails the spacing check
    n = max(math.ceil(w / s - 1e-9), 2)
    return Group(dia, n, s, n * a1)


def band_limits(plan: Plan, d_t: float) -> list[tuple[float, float]]:
    """The band under each column: its depth plus 0.75 d each side, within the footing and not past the middle of the gap."""
    c1, c2 = plan.cols
    mid = (c1.hi + c2.lo) / 2.0
    out = []
    for i, c in enumerate(plan.cols):
        lo, hi = c.lo - BAND_SPREAD * d_t, c.hi + BAND_SPREAD * d_t
        lo, hi = max(lo, 0.0), min(hi, plan.L)
        if i == 0:
            hi = min(hi, mid)
        else:
            lo = max(lo, mid)
        out.append((lo, hi))
    return out


def punching_zones(plan: Plan, st: Statics, d: float) -> list[Punch]:
    """Punching at d/2 from the faces of each column (Cl. 31.6.1), the perimeter cut where it would leave the footing.
    Where the two perimeters overlap, the columns are checked together on the outline of the union."""
    rects = []
    for i, c in enumerate(plan.cols):
        rects.append((i, max(c.lo - d / 2, 0.0), min(c.hi + d / 2, plan.L), min(c.b + d, plan.B)))
    groups: list[list[tuple[int, float, float, float]]] = []
    for r in sorted(rects, key=lambda r: r[1]):
        if groups and r[1] < groups[-1][-1][2] - 1e-9:
            groups[-1].append(r)
        else:
            groups.append([r])
    out = []
    for g in groups:
        xs = sorted({x for r in g for x in (r[1], r[2])})

        def height(lo: float, hi: float, g: list[tuple[int, float, float, float]] = g) -> float:
            mid = (lo + hi) / 2
            return max((r[3] for r in g if r[1] - 1e-9 <= mid <= r[2] + 1e-9), default=0.0)

        heights = [height(xs[i], xs[i + 1]) for i in range(len(xs) - 1)]
        b0 = 0.0
        inside = 0.0  # kN of soil pressure within the outline
        for i in range(len(xs) - 1):
            h, ln = heights[i], xs[i + 1] - xs[i]
            if h < plan.B - 1e-9:
                b0 += 2.0 * ln  # the two long sides, unless on the footing's edges
            inside += st.q((xs[i] + xs[i + 1]) / 2) * ln * h / 1e6
        for j, x in enumerate(xs):  # the ends and the steps between rectangles of different widths
            left = heights[j - 1] if j > 0 else 0.0
            right = heights[j] if j < len(heights) else 0.0
            if 1e-9 < x < plan.L - 1e-9:
                b0 += abs(left - right)
        cols = tuple(r[0] for r in g)
        vp = sum(st.pu[i] for i in cols) - inside
        cs = [plan.cols[i] for i in cols]
        ks = min(min(0.5 + min(c.b, c.D) / max(c.b, c.D), 1.0) for c in cs)
        out.append(Punch(cols, b0, vp, vp * 1e3 / (b0 * d) if b0 > 0 else math.inf, ks, 0.0, d))
    return out


def trial(inp: CombinedFootingInput, plan: Plan, st: Statics, D: float, cover: float) -> Trial:
    """Every bar set and check at one depth, each set with the smallest bar that fits and develops (straight before bent)."""
    fck, fy, agg = float(inp.fck), float(inp.fy), inp.max_aggregate_mm
    dias = [inp.bar_dia_mm] if inp.bar_dia_mm else list(FOOTING_BAR_DIAMETERS)
    L, B = plan.L, plan.B
    tr_faces = st.faces()
    m_faces = [st.moment(x) for x in tr_faces]
    i_pos = max(range(4), key=lambda i: m_faces[i])
    m_pos, x_pos = max(m_faces[i_pos], 0.0), tr_faces[i_pos]
    x_hog, m_h = st.greatest_hogging()
    m_hog = max(-m_h, 0.0)
    blocked = False

    # ------------------------------------------------------------------ across, under each column (outer layer)
    chosen_t: tuple[int, float, list[Band]] | None = None
    for allow_bent in (False, True):
        for dia in dias:
            d_t = D - cover - dia / 2.0
            s_max = sl.max_spacing_main(d_t)
            bands = []
            ok = True
            for (lo, hi), c, pu in zip(band_limits(plan, d_t), plan.cols, st.pu, strict=True):
                a_t = (B - c.b) / 2.0
                m = pu / (B / 1000.0) * (a_t / 1000.0) ** 2 / 2.0
                w = hi - lo
                if m * 1e6 > is456.limiting_moment(fck, fy, w, d_t):
                    return _failed(D, plan, m_pos, x_pos, m_hog, x_hog, blocked)
                asf = _as_flex(m, fck, fy, w, d_t)
                asr = max(asf, sl.min_steel(w, D, fy))
                g = band_bars(asr, w, dia, s_max)
                avail = a_t - cover
                req = is456.development_length(dia, fck, fy) * min(asf / g.area, 1.0)
                straight, bent = _anchor(req, avail, dia, fy)
                g.bent = not straight
                band = Band(lo, hi, a_t, m, asf, asr, g, req, avail)
                bands.append(band)
                if not _spacing_ok(g.s, dia, agg):
                    ok = False
                if not (straight or (allow_bent and bent)):
                    ok = False
                    if _spacing_ok(g.s, dia, agg) and not bent:
                        blocked = True
            if ok:
                chosen_t = (dia, d_t, bands)
                break
        if chosen_t:
            break
    if chosen_t is None:
        t = _failed(D, plan, m_pos, x_pos, m_hog, x_hog, blocked)
        t.ok_flexure = True
        return t
    dia_t, d_t, bands = chosen_t

    # distribution across, outside the bands: the minimum steel, the smallest bar at a practical spacing
    dist = None
    for dia in FOOTING_BAR_DIAMETERS if not inp.bar_dia_mm else dias:
        need = sl.min_steel(1000.0, D, fy)
        s = math.floor(min(sl.max_spacing_main(D - cover - dia / 2.0), bar_area(dia) * 1000.0 / need) / 10.0 + 1e-9) * 10.0
        if _spacing_ok(s, dia, agg):
            dist = Group(dia, 0, s, bar_area(dia) * 1000.0 / s)
            break
    layer = max(dia_t, dist.dia if dist else dia_t)

    # ------------------------------------------------------------------ along, bottom (inner layer) and top
    def along(m: float, d_of: Any, sections: Any) -> tuple[Group, float, float, Any] | str:
        """The smallest bar that fits and develops (straight before bent), or why none does: "flexure" or "bars"."""
        for allow_bent in (False, True):
            for dia in dias:
                d = d_of(dia)
                if m * 1e6 > is456.limiting_moment(fck, fy, B, d):
                    return "flexure"
                asf = _as_flex(m, fck, fy, B, d)
                asr = max(asf, sl.min_steel(B, D, fy))
                s, n, ap = bars_across(asr, B, dia, sl.max_spacing_main(d), cover)
                g = Group(dia, n, s, ap)
                if not _spacing_ok(s, dia, agg):
                    continue
                anchors = sections(g, d)
                straight = all(_anchor(r, av, dia, fy)[0] for _, r, av in anchors)
                bent = all(_anchor(r, av, dia, fy)[1] for _, r, av in anchors)
                if straight or (allow_bent and bent):
                    g.bent = not straight
                    return g, asf, asr, anchors
        return "bars"

    def bottom_sections(g: Group, d: float) -> list[tuple[float, float, float]]:
        out = []
        for x in tr_faces:
            m = st.moment(x)
            if m <= 1e-9:
                continue  # no sagging there: nothing to develop
            req = is456.development_length(g.dia, fck, fy) * min(_as_flex(m, fck, fy, B, d) / g.area, 1.0)
            out.append((x, req, min(x, L - x) - cover))
        return out

    def top_sections(g: Group, d: float) -> list[tuple[float, float, float]]:
        if m_hog <= 1e-9:
            return []
        req = is456.development_length(g.dia, fck, fy) * min(_as_flex(m_hog, fck, fy, B, d) / g.area, 1.0)
        return [(x_hog, req, min(x_hog, L - x_hog) - cover)]

    bot = along(m_pos, lambda dia: D - cover - layer - dia / 2.0, bottom_sections)
    top = along(m_hog, lambda dia: D - cover - dia / 2.0, top_sections)
    if isinstance(bot, str) or isinstance(top, str):
        t = _failed(D, plan, m_pos, x_pos, m_hog, x_hog, blocked)
        t.ok_flexure = "flexure" not in (bot, top)
        t.along_blocked = t.ok_flexure
        return t
    g_b, asf_b, asr_b, anc_b = bot
    g_t, asf_t, asr_t, anc_t = top
    d_lb = D - cover - layer - g_b.dia / 2.0
    d_top = D - cover - g_t.dia / 2.0

    # ------------------------------------------------------------------ shear along, at d from each face (Cl. 34.2.4.1(a))
    shear: list[ShearSection] = []
    c1, c2 = plan.cols
    for x, where, inner in ((c1.lo - d_lb, "left of column 1", False), (c1.hi + d_top, "right of column 1", True),
                            (c2.lo - d_top, "left of column 2", True), (c2.hi + d_lb, "right of column 2", False)):
        if x <= 0.0 or x >= L or (inner and not (c1.hi < x < c2.lo)):
            continue  # the face is within d of the end, or of the other column
        m, v = st.moment(x), st.shear(x)
        steel = "top" if m < 0 else "bottom"
        g, d = (g_t, d_top) if steel == "top" else (g_b, d_lb)
        tau = abs(v) * 1e3 / (B * d)
        shear.append(ShearSection(x, where, v, m, steel, d, tau, is456.tau_c(fck, 100.0 * g.area / (B * d))))
    # across, in each band, at d from the face of the column
    for band, pu in zip(bands, st.pu, strict=True):
        assert band.bars is not None
        band.v = pu / (B / 1000.0) * max(band.a_t - d_t, 0.0) / 1000.0
        band.tau = band.v * 1e3 / (band.w * d_t)
        band.tc = is456.tau_c(fck, 100.0 * band.bars.area / (band.w * d_t))
    d_p = (d_t + d_lb) / 2.0
    punch = punching_zones(plan, st, d_p)
    for p in punch:
        p.allow = p.ks * 0.25 * math.sqrt(fck)
    ok_shear = all(s.tau <= s.tc + 1e-12 for s in shear) and all(b.tau <= b.tc + 1e-12 for b in bands) and \
        all(p.tau <= p.allow + 1e-12 for p in punch)
    return Trial(D, d_t, d_lb, d_top, bands, dist, m_pos, x_pos, m_hog, x_hog, asf_b, asr_b, asf_t, asr_t, g_b, g_t,
                 anc_b, (anc_t[0][1], anc_t[0][2]) if anc_t else (0.0, 0.0), shear, punch, True, dist is not None, ok_shear, blocked)


def _failed(D: float, plan: Plan, m_pos: float, x_pos: float, m_hog: float, x_hog: float, blocked: bool) -> Trial:
    nan = math.nan
    return Trial(D, nan, nan, nan, [], None, m_pos, x_pos, m_hog, x_hog, nan, nan, nan, nan, None, None, ok_flexure=False, ok_bars=False,
                 ok_shear=False, anchorage_blocked=blocked)


def passes(t: Trial) -> bool:
    return t.ok_flexure and t.ok_bars and t.ok_shear and t.bottom is not None and t.top is not None and bool(t.bands)


@dataclass
class Blocked:
    """Why no depth passed, where the bars' development was the reason."""

    across: bool = False  # a wider footing helps
    along: bool = False  # longer overhangs would help


def select_depth(inp: CombinedFootingInput, plan: Plan, st: Statics, cover: float) -> tuple[Trial | None, Blocked]:
    """The least depth in 50 mm steps that passes (an entered depth as it is, unless it needs compression steel)."""
    why = Blocked()
    depths = [float(inp.depth_mm)] if inp.depth_mm else [float(d) for d in range(300, 3001, int(STEP))]
    for D in depths:
        t = trial(inp, plan, st, D, cover)
        why.across = why.across or t.anchorage_blocked
        why.along = why.along or t.along_blocked
        if passes(t):
            return t, why
        if inp.depth_mm and t.ok_flexure and t.bottom is not None and t.top is not None and t.bands:
            return t, why
    return None, why


def least_width(inp: CombinedFootingInput, L: float, a: float) -> float:
    """The least width in 50 mm steps, 50 mm wider than the wider column each side, that keeps the pressure within limits."""
    b_min = max(inp.column1_width_mm, inp.column2_width_mm) + 2 * STEP
    p = (inp.p1_service_kn + inp.p2_service_kn) * (1 + inp.self_weight_pct / 100.0)
    B = max(b_min, math.ceil(p / inp.sbc_kn_m2 / (L / 1000.0) * 1000.0 / STEP - 1e-9) * STEP)
    while B <= MAX_SIZE:
        q_max, q_min = service_pressures(inp, make_plan(inp, a, L, B))
        if q_max <= inp.sbc_kn_m2 + 1e-9 and q_min >= -1e-9:
            return B
        B += STEP
    return math.inf


@dataclass
class Outcome:
    plan: Plan
    trial: Trial
    B_bearing: float  # the width the bearing pressure needs
    candidates: int


def design_plan(inp: CombinedFootingInput, a: float, L: float, cover: float) -> tuple[Outcome | None, Blocked]:
    """Design at one length and left end: the entered width, or the least the pressure allows, widened in 50 mm steps
    where the bars across cannot be developed within the projections."""
    if inp.width_mm is not None:
        plan = make_plan(inp, a, L, float(inp.width_mm))
        t, why = select_depth(inp, plan, Statics(plan, inp.load_factor), cover)
        return (Outcome(plan, t, plan.B, 1) if t else None), why
    B0 = least_width(inp, L, a)
    if math.isinf(B0):
        return None, Blocked()
    B = B0
    seen = Blocked()
    while B <= B0 + 3000.0:
        plan = make_plan(inp, a, L, B)
        t, why = select_depth(inp, plan, Statics(plan, inp.load_factor), cover)
        seen.along = seen.along or why.along
        if t is not None:
            return Outcome(plan, t, B0, 1), seen
        if not why.across:
            return None, seen
        seen.across = True
        B += STEP
    return None, seen


def balance(inp: CombinedFootingInput, a: float) -> float:
    """|greatest hogging - greatest sagging| along the footing for a left end a, centred on the resultant, kN m. The moments
    along do not depend on the width (the load per metre is the column loads over the length) or on the depth."""
    L = length_centred(a, inp.resultant_offset())
    st = Statics(make_plan(inp, a, L, 1000.0), inp.load_factor)
    m_pos = max(max(st.moment(x) for x in st.faces()), 0.0)
    m_hog = max(-st.greatest_hogging()[1], 0.0)
    return abs(m_hog - m_pos)


def left_ends(inp: CombinedFootingInput) -> list[float]:
    """Left ends on the 25 mm grid, from the least that keeps column 2 on a centred footing, over one spacing and the side of
    a square of the area needed (so that close columns can still have a footing longer than it is wide)."""
    er, d1, d2, s = inp.resultant_offset(), inp.column1_depth_mm, inp.column2_depth_mm, inp.spacing_mm
    a_min = math.ceil(max(d1 / 2.0, s - 2.0 * er + d2 / 2.0) / GRID - 1e-9) * GRID
    side = math.sqrt((inp.p1_service_kn + inp.p2_service_kn) * (1 + inp.self_weight_pct / 100.0) / inp.sbc_kn_m2) * 1000.0
    out = []
    a = a_min
    while a <= a_min + s + side + 1e-9:
        if length_centred(a, er) - a - s >= d2 / 2.0 - 1e-9:
            out.append(a)
        a += GRID
    return out


def choose_plan(inp: CombinedFootingInput, cover: float) -> tuple[Outcome | None, Blocked]:
    """The plan: as entered, centred on the resultant, or (left end and length both blank) the centred plan, no wider than it
    is long where one can be, whose greatest hogging and sagging along are nearest equal (the classic economy of a combined
    footing); should that plan not design, the next nearest."""
    er = inp.resultant_offset()
    if inp.length_mm is not None:
        L = float(inp.length_mm)
        a = float(inp.left_end_mm) if inp.left_end_mm is not None else left_end_centred(L, er)
        return design_plan(inp, a, L, cover)
    if inp.left_end_mm is not None:
        a = float(inp.left_end_mm)
        return design_plan(inp, a, length_centred(a, er), cover)
    ends = left_ends(inp)

    def rank(a: float) -> tuple[bool, float, float]:
        L = length_centred(a, er)
        return (least_width(inp, L, a) > L, round(balance(inp, a), 6), a)  # a footing longer than it is wide first

    ranked = sorted(ends, key=rank)
    seen = Blocked()
    for a in ranked[:12]:
        out, why = design_plan(inp, a, length_centred(a, er), cover)
        seen.across = seen.across or why.across
        seen.along = seen.along or why.along
        if out is not None and passes(out.trial):
            out.candidates = len(ends)
            return out, seen
    return None, seen


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def design_combined_footing(inp: CombinedFootingInput) -> dict[str, Any]:
    from app.modules.structural.domain import combined_footing_detailing as det

    sheet = CalcSheet()
    fck, fy = float(inp.fck), float(inp.fy)
    cover = effective_cover(inp)
    gamma = inp.load_factor

    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.step(f"{REF}, Cl. 26.4.2.2 and Table 16" if inp.clear_cover_mm is None else "Input",
               "Clear cover: 50 mm for footings, and not less than Table 16", "c", "", cover, "mm", 0)
    sheet.check("cover", f"{REF}, Cl. 26.4.2.2", "Cover in a footing", "c", cover, ">=", "c_min",
                max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure)), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ plan
    sheet.section("2. Plan size")
    p = inp.p1_service_kn + inp.p2_service_kn
    er = inp.resultant_offset()
    sheet.step("Statics", "Resultant of the service loads, from the centre of column 1", "x_r = P_2 s / (P_1 + P_2)",
               f"{_n(inp.p2_service_kn, 1)} x {_n(inp.spacing_mm, 0)} / {_n(p, 1)}", er, "mm", 0)
    p_gross = p * (1 + inp.self_weight_pct / 100.0)
    sheet.step("Input", "Service loads and own-weight allowance", "(P_1 + P_2)(1 + alpha)", f"{_n(p, 1)} x (1 + {_n(inp.self_weight_pct, 0)}/100)",
               p_gross, "kN", 1)
    sheet.step("Statics", "Area needed", "A_req = (P_1 + P_2)(1 + alpha) / q_safe", f"{_n(p_gross, 1)} / {_n(inp.sbc_kn_m2, 0)}",
               p_gross / inp.sbc_kn_m2, "m2", 3)
    out, why = choose_plan(inp, cover)
    if out is None:
        if inp.depth_mm:
            msg = "The depth entered needs compression steel: increase it or leave it blank."
        elif why.across:
            msg = ("The bars across cannot be developed beyond the column faces, even with end bends (Cl. 26.2.1): enter a larger width, "
                   "or leave it blank.")
        elif why.along:
            msg = ("The bottom bars along cannot be developed beyond the column faces within the overhangs, even with end bends (Cl. 26.2.1): "
                   "lengthen the overhangs, or leave the left end and the length blank.")
        else:
            msg = "No footing up to 20 m wide and 3 m deep carries these loads within the bearing pressure: check the loads and the soil."
        return _stopped(sheet, msg)
    plan, t = out.plan, out.trial
    L, B, a = plan.L, plan.B, plan.a
    c1, c2 = plan.cols
    if inp.length_mm is None and inp.left_end_mm is None:
        sheet.step("Selected", f"Centred on the resultant, L = 2 (a + x_r) in 50 mm steps; of {out.candidates} left ends a in 25 mm steps, the "
                   "one, no wider than it is long, whose greatest sagging and hogging along are nearest equal", "a, L", "", f"{_n(a, 0)}, {_n(L, 0)}", "mm")
    elif inp.length_mm is None:
        sheet.step("Input", "Left end to the centre of column 1", "a", "", a, "mm", 0)
        sheet.step("Statics", "Length centred on the resultant, in 50 mm steps", "L = 2 (a + x_r)", f"2 x ({_n(a, 0)} + {_n(er, 0)})", L, "mm", 0)
    elif inp.left_end_mm is None:
        sheet.step("Input", "Length", "L", "", L, "mm", 0)
        sheet.step("Statics", "Left end centring the length on the resultant, in 25 mm steps", "a = L/2 - x_r", f"{_n(L, 0)}/2 - {_n(er, 0)}",
                   a, "mm", 0)
    else:
        sheet.step("Input", "Length and left end to the centre of column 1", "L, a", "", f"{_n(L, 0)}, {_n(a, 0)}", "mm")
    sheet.step("Geometry", "Overhangs beyond the outer faces of the columns", "a - D_1/2, L - a - s - D_2/2", "",
               f"{_n(c1.lo, 0)}, {_n(L - c2.hi, 0)}", "mm")
    if inp.width_mm is None:
        sheet.step("Selected", "Width: least in 50 mm steps, at least 50 mm beyond the wider column each side, that keeps the pressure within "
                   "limits", "B", "", out.B_bearing, "mm", 0)
        if B > out.B_bearing:
            sheet.step(f"{REF}, Cl. 26.2.1, 34.2.4.3", "Widened in 50 mm steps until the bars across can be developed beyond the column faces",
                       "B", f"from {_n(out.B_bearing, 0)}", B, "mm", 0)
            sheet.flag("info", f"The footing is {_n(B, 0)} mm wide, more than the {_n(out.B_bearing, 0)} mm the bearing pressure needs, so that "
                               "the bars across can be anchored.")
    else:
        sheet.step("Input", "Width", "B", "", B, "mm", 0)
    e = eccentricity(plan)
    q_max, q_min = service_pressures(inp, plan)
    sheet.step("Statics", "Eccentricity of the loads from the centre of the footing", "e = a + x_r - L/2", f"{_n(a, 0)} + {_n(er, 1)} - {_n(L / 2, 0)}",
               e, "mm", 1)
    sheet.step("Statics", "Service pressures", "q = (P_1 + P_2)(1 + alpha)/(L B) +/- 6 (P_1 + P_2) e/(B L^2)",
               f"L x B = {_n(L / 1000, 3)} x {_n(B / 1000, 3)} m", f"{_n(q_max, 1)}, {_n(q_min, 1)}", "kN/m2")
    sheet.check("bearing_soil", "Soil", "Largest pressure within the safe bearing pressure", "q_max", q_max, "<=", "q_safe", inp.sbc_kn_m2, "kN/m2", 1)
    sheet.check("contact", "Soil", "No loss of contact (smallest pressure not negative)", "q_min", q_min, ">=", "0", 0.0, "kN/m2", 1, ratio=False)

    # ------------------------------------------------------------------ along
    st = Statics(plan, gamma)
    sheet.section("3. Bending along the footing")
    sheet.step(f"{REF}, Table 18", "Factored column loads", "P_u1, P_u2 = gamma_f P", f"gamma_f = {_n(gamma)}", f"{_n(st.pu[0], 1)}, {_n(st.pu[1], 1)}", "kN")
    sheet.step("Statics", "Factored net pressure at the left and right ends, varying linearly, from the column loads only",
               "q_u = (P_u1 + P_u2)/(L B) -/+ 6 (P_u1 + P_u2) e/(B L^2)", "", f"{_n(st.q(0), 2)}, {_n(st.q(L), 2)}", "kN/m2")
    sheet.step(f"{REF}, Cl. 34.2.3.2", "Moments at the column faces (sagging positive, tension at the bottom)", "M_x = int q_u B (x - t) dt - P_u (x - x_c)",
               f"x = {', '.join(_n(x, 0) for x in st.faces())} mm", ", ".join(_n(st.moment(x), 1) for x in st.faces()), "kN m")
    sheet.step("Statics", "Greatest hogging between the columns, where the shear is nil", "M_hog at V = 0", f"x = {_n(t.x_hog, 0)} mm", -t.m_hog, "kN m", 1)
    sheet.step("Selected" if not inp.depth_mm else "Input",
               "Depth: the least in 50 mm steps that needs no compression steel and no shear steel" if not inp.depth_mm else "Depth", "D", "", t.D, "mm", 0)
    sheet.check("edge", f"{REF}, Cl. 34.1.2", "Thickness at the edge of a footing on soil", "D", t.D, ">=", "D_edge,min", EDGE_MIN, "mm", 0, ratio=False)
    assert t.bottom is not None and t.top is not None
    gb, gt = t.bottom, t.top
    dia_t = t.bands[0].bars.dia if t.bands[0].bars else 0
    sheet.step("Geometry", f"Effective depths: bars across (bottom, outer, T{dia_t}), along (bottom, inner, T{gb.dia}), along (top, T{gt.dia})",
               "d_t, d_b, d_top", f"D = {_n(t.D, 0)}, c = {_n(cover, 0)}", f"{_n(t.d_t, 1)}, {_n(t.d_lb, 1)}, {_n(t.d_top, 1)}", "mm")
    ld_cache: dict[int, float] = {}

    def ld(dia: int) -> float:
        ld_cache.setdefault(dia, is456.development_length(dia, fck, fy))
        return ld_cache[dia]

    for name, m, d, asf, asr, g in (("bottom", t.m_pos, t.d_lb, t.as_flex_bottom, t.as_bottom, gb), ("top", t.m_hog, t.d_top, t.as_flex_top, t.as_top, gt)):
        mu_lim = is456.limiting_moment(fck, fy, B, d) / 1e6
        what = "greatest sagging, at a column face" if name == "bottom" else "greatest hogging, between the columns"
        sheet.check(f"mulim_{name}", f"{REF}, Annex G-1.1(c)", f"Bars along, {name}: no compression steel for the {what}", "M", m, "<=", "M_u,lim",
                    mu_lim, "kN m", 2)
        sheet.step(f"{REF}, Annex G-1.1(b)", f"Bars along, {name}: steel for the moment over the width B", "A_s", f"d = {_n(d, 1)}", asf, "mm2", 0)
        sheet.step(f"{REF}, Cl. 26.5.2.1", f"Bars along, {name}: steel required, not less than {'0.15' if fy <= 250 else '0.12'} percent", "A_s,req", "",
                   asr, "mm2", 0)
        sheet.step("Selected", f"Bars along, {name}: {g.n} T{g.dia} at {g.s:.0f}, the full length", "A_s,prov", "", g.area, "mm2", 0)
        sheet.check(f"as_{name}", f"{REF}, Cl. 26.5.2.1", f"Bars along, {name}: steel provided", "A_s,req", asr, "<=", "A_s,prov", g.area, "mm2", 0)
        sheet.check(f"spacing_{name}", f"{REF}, Cl. 26.3.3(b)", f"Bars along, {name}: spacing", "s", g.s, "<=", "s_max", sl.max_spacing_main(d), "mm", 0)
    sheet.step(f"{REF}, Cl. 26.2.1", "Development lengths at the full design stress", "L_d = phi 0.87 f_y / (4 tau_bd)",
               ", ".join(f"T{dd}" for dd in sorted({gb.dia, gt.dia})), ", ".join(_n(ld(dd), 0) for dd in sorted({gb.dia, gt.dia})), "mm", 0)
    for x, req, avail in t.anchor_bottom:
        bent = gb.bent
        sheet.check(f"anchor_bottom_{x:.0f}", f"{REF}, Cl. 26.2.1" + (", 26.2.2.1(b)" if bent else ""),
                    f"Bottom bars along developed beyond the face at x = {x:.0f}, at the stress there" + (", with end bends" if bent else ""),
                    "L_d sigma_s/(0.87 f_y)", req, "<=", "available", bent_value(avail, gb.dia, fy) if bent else avail, "mm", 0)
    if t.m_hog > 1e-9:
        req, avail = t.anchor_top
        sheet.check("anchor_top", f"{REF}, Cl. 26.2.1" + (", 26.2.2.1(b)" if gt.bent else ""),
                    "Top bars developed each side of the greatest hogging, at the stress there" + (", with end bends" if gt.bent else ""),
                    "L_d sigma_s/(0.87 f_y)", req, "<=", "available", bent_value(avail, gt.dia, fy) if gt.bent else avail, "mm", 0)

    # ------------------------------------------------------------------ across
    sheet.section("4. Bending across, under each column")
    for i, (band, c, pu) in enumerate(zip(t.bands, plan.cols, st.pu, strict=True), start=1):
        g = band.bars
        assert g is not None
        sheet.step("Interpretation 96", f"Band under column {i}: its depth plus 0.75 d_t each side, within the footing and the gap", "w",
                   f"{_n(c.D, 0)} + 1.5 x {_n(t.d_t, 1)}, from x = {_n(band.lo, 0)} to {_n(band.hi, 0)}", band.w, "mm", 0)
        sheet.step(f"{REF}, Cl. 34.2.3.2", f"Column {i}: moment at its face, its load spread across the width", "M_t = (P_u / B) a_t^2 / 2",
                   f"{_n(pu, 1)} / {_n(B / 1000, 3)} x {_n(band.a_t / 1000, 3)}^2 / 2", band.m, "kN m", 2)
        sheet.check(f"mulim_band{i}", f"{REF}, Annex G-1.1(c)", f"Band {i}: no compression steel", "M_t", band.m, "<=", "M_u,lim",
                    is456.limiting_moment(fck, fy, band.w, t.d_t) / 1e6, "kN m", 2)
        sheet.step(f"{REF}, Annex G-1.1(b), Cl. 26.5.2.1", f"Band {i}: steel for the moment, not less than the minimum", "A_s,req",
                   f"A_s = {_n(band.as_flex, 0)}", band.as_req, "mm2", 0)
        sheet.check(f"as_band{i}", f"{REF}, Cl. 26.5.2.1", f"Band {i}: {g.n} T{g.dia} at {g.s:.0f}", "A_s,req", band.as_req, "<=", "A_s,prov", g.area, "mm2", 0)
        sheet.check(f"spacing_band{i}", f"{REF}, Cl. 26.3.3(b)", f"Band {i}: spacing", "s", g.s, "<=", "s_max", sl.max_spacing_main(t.d_t), "mm", 0)
        if g.bent:
            r_b = bend_radius(g.dia, fy)
            sheet.check(f"anchor_band{i}", f"{REF}, Cl. 26.2.1, 26.2.2.1(b)", f"Band {i}: bars developed beyond the column face, with end bends "
                        f"(straight part to the start of the bend, r = {r_b:.0f})", "L_d sigma_s/(0.87 f_y)", band.ld_req, "<=",
                        "a_t - c - (r + phi) + 8 phi", bent_value(band.avail, g.dia, fy), "mm", 0)
        else:
            sheet.check(f"anchor_band{i}", f"{REF}, Cl. 26.2.1, 34.2.4.3", f"Band {i}: bars developed beyond the column face, at the stress there",
                        "L_d sigma_s/(0.87 f_y)", band.ld_req, "<=", "a_t - c", band.avail, "mm", 0)
    assert t.dist is not None
    sheet.step(f"{REF}, Cl. 26.5.2.1, 26.3.3(b)", f"Across, outside the bands: the minimum steel, T{t.dist.dia} at {t.dist.s:.0f}", "A_s,min",
               f"{'0.15' if fy <= 250 else '0.12'} percent of 1000 x {_n(t.D, 0)}", sl.min_steel(1000.0, t.D, fy), "mm2/m", 0)

    # ------------------------------------------------------------------ shear
    sheet.section("5. Shear")
    for sc in t.shear:
        sheet.step(f"{REF}, Cl. 34.2.4.1(a)", f"One-way shear along, at d from the face, {sc.where}, x = {sc.x:.0f} ({sc.steel} bars in tension)",
                   "V_u", f"M = {_n(sc.m, 1)} kN m", abs(sc.v), "kN", 1)
        sheet.check(f"shear_{sc.x:.0f}", f"{REF}, Cl. 34.2.4.1(a), Table 19", f"One-way shear, {sc.where}", "tau_v = V_u/(B d)", sc.tau, "<=", "tau_c",
                    sc.tc, "N/mm2", 3)
    for i, band in enumerate(t.bands, start=1):
        if band.a_t > t.d_t:
            sheet.check(f"shear_band{i}", f"{REF}, Cl. 34.2.4.1(a), Table 19", f"One-way shear across, band {i}, at d from the column face",
                        "tau_v = (P_u/B)(a_t - d)/(w d)", band.tau, "<=", "tau_c", band.tc, "N/mm2", 3)
    for pz in t.punching:
        who = " and ".join(f"column {i + 1}" for i in pz.cols)
        sheet.step(f"{REF}, Cl. 31.6.1", f"Punching around {who}: perimeter at d/2 from the faces, within the footing", "b_0",
                   f"d = {_n(pz.d, 1)}", pz.b0, "mm", 0)
        sheet.step(f"{REF}, Cl. 31.6.1", f"Punching shear around {who}: the load less the pressure within the perimeter", "V_p", "", pz.vp, "kN", 1)
        sheet.check(f"punching_{'_'.join(str(i + 1) for i in pz.cols)}", f"{REF}, Cl. 31.6.3", f"Punching shear around {who}", "tau_v", pz.tau, "<=",
                    "k_s 0.25 sqrt(f_ck)", pz.allow, "N/mm2", 3)

    # ------------------------------------------------------------------ bearing
    sheet.section("6. Transfer of load at the base of the columns")
    bearing = []
    for i, (c, pu) in enumerate(zip(plan.cols, st.pu, strict=True), start=1):
        ratio = min(2.0 * min(c.x, L - c.x) / c.D, B / c.b, 1.0 + 4.0 * t.D / max(c.b, c.D), 2.0)
        allow = 0.45 * fck * ratio
        sigma = pu * 1e3 / (c.b * c.D)
        bearing.append((sigma, allow, ratio))
        sheet.step(f"{REF}, Cl. 34.4", f"Column {i}: allowable bearing, A_1 within the footing at 1 in 2, sqrt(A_1/A_2) not more than 2",
                   "0.45 f_ck sqrt(A_1/A_2)", f"sqrt(A_1/A_2) = min(2 min(x, L - x)/D, B/b, 1 + 4 D/max(b, D), 2) = {_n(ratio, 3)}", allow, "N/mm2", 2)
        sheet.check(f"bearing{i}", f"{REF}, Cl. 34.4", f"Bearing at the base of column {i}", "sigma = P_u/(b D)", sigma, "<=", "sigma_allow", allow, "N/mm2", 2)
        if sigma > allow:
            sheet.flag("warning", f"Bearing under column {i} exceeds the allowable by {(sigma - allow) * c.b * c.D / 1e3:.0f} kN: carry the excess on "
                                  "column bars or dowels continued into the footing, or raise the concrete grade.", f"{REF}, Cl. 34.4")
        sheet.step(f"{REF}, Cl. 34.4.3", f"Column {i}: bars or dowels continued into the footing, at least 0.5 percent of the column", "A_s,dowel,min",
                   "", 0.005 * c.b * c.D, "mm2", 0)

    # ------------------------------------------------------------------ flags and outputs
    sheet.flag("info", "The footing is taken as rigid: the soil pressure varies linearly along it and is uniform across it.")
    sheet.flag("info", "One-way shear uses tau_c of Table 19 without the enhancement for slabs, which is on the safe side.")
    if inp.depth_mm and not t.ok_shear:
        sheet.flag("warning", "The depth entered fails a shear check: increase it, or leave it blank for the engine to choose.")
    if abs(e) > 1.0:
        sheet.flag("info", f"The resultant is {abs(e):.0f} mm from the centre of the footing, so the pressure varies along it; the design uses that "
                           "variation.")
    reinforcement = det.reinforcement(inp, plan, t, cover)
    bbs = det.bar_schedule(inp, reinforcement)
    quantities = det.quantities(inp, reinforcement, bbs)
    drawing = det.drawing(inp, reinforcement)
    charts = _charts(st)

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    p_ratio = max(pz.tau / pz.allow for pz in t.punching)
    key_results = [
        {"label": "Size L x B x D", "sym": "", "value": f"{L:.0f} x {B:.0f} x {t.D:.0f}", "unit": "mm", "dp": 0},
        {"label": "Left end to column 1", "sym": "a", "value": a, "unit": "mm", "dp": 0},
        {"label": "Largest pressure", "sym": "q_max", "value": round(q_max, 1), "unit": "kN/m2", "dp": 1},
        {"label": "Bottom bars along", "sym": "", "value": reinforcement["bottom"]["label"], "unit": "", "dp": 0},
        {"label": "Top bars along", "sym": "", "value": reinforcement["top"]["label"], "unit": "", "dp": 0},
        {"label": "Bars across, bands", "sym": "", "value": " / ".join(b["label"] for b in reinforcement["bands"]), "unit": "", "dp": 0},
        {"label": "Punching ratio", "sym": "", "value": round(p_ratio, 3), "unit": "", "dp": 3},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
        {"label": "Concrete", "sym": "", "value": quantities["concrete_m3"], "unit": "m3", "dp": 3},
    ]
    data = {
        "cover": cover, "L": L, "B": B, "a": a, "D": t.D, "x1": c1.x, "x2": c2.x, "e": round(e, 6), "x_r": round(er, 6),
        "q_max": round(q_max, 6), "q_min": round(q_min, 6), "q_u_left": round(st.q(0), 6), "q_u_right": round(st.q(L), 6),
        "pu1": round(st.pu[0], 6), "pu2": round(st.pu[1], 6),
        "faces": st.faces(), "m_faces": [round(st.moment(x), 6) for x in st.faces()], "v_faces": [round(st.shear(x), 6) for x in st.faces()],
        "m_pos": round(t.m_pos, 6), "x_pos": t.x_pos, "m_hog": round(t.m_hog, 6), "x_hog": round(t.x_hog, 3),
        "d_t": round(t.d_t, 3), "d_b": round(t.d_lb, 3), "d_top": round(t.d_top, 3),
        "dia_bottom": gb.dia, "dia_top": gt.dia, "dia_across": dia_t, "dia_dist": t.dist.dia,
        "as_flex_bottom": round(t.as_flex_bottom, 4), "as_bottom": round(t.as_bottom, 4), "as_prov_bottom": round(gb.area, 4),
        "n_bottom": gb.n, "s_bottom": gb.s, "bent_bottom": gb.bent,
        "as_flex_top": round(t.as_flex_top, 4), "as_top": round(t.as_top, 4), "as_prov_top": round(gt.area, 4), "n_top": gt.n, "s_top": gt.s,
        "bent_top": gt.bent,
        "anchor_bottom": [[x, round(r, 3), round(av, 3)] for x, r, av in t.anchor_bottom],
        "anchor_top": [round(t.anchor_top[0], 3), round(t.anchor_top[1], 3)],
        "bands": [{"lo": round(b.lo, 3), "hi": round(b.hi, 3), "w": round(b.w, 3), "a_t": b.a_t, "m": round(b.m, 6), "as_flex": round(b.as_flex, 4),
                   "as_req": round(b.as_req, 4), "as_prov": round(b.bars.area, 4) if b.bars else 0, "n": b.bars.n if b.bars else 0,
                   "s": b.bars.s if b.bars else 0, "bent": b.bars.bent if b.bars else False, "ld_req": round(b.ld_req, 3),
                   "avail": round(b.avail, 3), "v": round(b.v, 6), "tau": round(b.tau, 6), "tc": round(b.tc, 6)} for b in t.bands],
        "s_dist": t.dist.s,
        "shear": [{"x": round(s.x, 3), "where": s.where, "v": round(s.v, 6), "m": round(s.m, 6), "steel": s.steel, "d": round(s.d, 3),
                   "tau": round(s.tau, 6), "tc": round(s.tc, 6)} for s in t.shear],
        "punching": [{"cols": [i + 1 for i in pz.cols], "b0": round(pz.b0, 3), "vp": round(pz.vp, 6), "tau": round(pz.tau, 6), "ks": round(pz.ks, 6),
                      "allow": round(pz.allow, 6), "d": round(pz.d, 3)} for pz in t.punching],
        "bearing": [{"sigma": round(s, 6), "allow": round(al, 6), "ratio": round(r, 6)} for s, al, r in bearing],
    }
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok", "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok), "checks_total": len(checks), "max_utilisation": max(utils) if utils else None,
        "key_results": key_results, "data": data, "reinforcement": reinforcement, "sheet": sheet.to_dict(), "bbs": bbs,
        "quantities": quantities, "drawing": drawing, "charts": charts,
    }


def _charts(st: Statics) -> list[dict[str, Any]]:
    L = st.plan.L
    xs = sorted({*(L * i / 120.0 for i in range(121)), *st.faces(), st.greatest_hogging()[0]})
    m = [[round(x / 1000.0, 4), round(st.moment(x), 2)] for x in xs]
    v = [[round(x / 1000.0, 4), round(st.shear(x), 2)] for x in xs]
    cols = [[round(x / 1000.0, 4), 0.0] for x in (c.x for c in st.plan.cols)]
    return [
        {"id": "moments", "title": "Bending moment along the footing (factored)", "x": {"label": "x", "unit": "m"}, "y": {"label": "M_u", "unit": "kN m"},
         "series": [{"name": "Bending moment", "kind": "line", "points": m}, {"name": "Column centre lines", "kind": "point", "points": cols}],
         "note": "x from the left end. Sagging (tension at the bottom) positive; hogging between the columns negative. Each column's load is spread over "
                 "its depth; the design takes the faces."},
        {"id": "shear", "title": "Shear force along the footing (factored)", "x": {"label": "x", "unit": "m"}, "y": {"label": "V_u", "unit": "kN"},
         "series": [{"name": "Shear force", "kind": "line", "points": v}, {"name": "Column centre lines", "kind": "point", "points": cols}],
         "note": "x from the left end; the net soil pressure up, the column loads down."},
    ]


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS), "status": "stopped", "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok), "checks_total": len(sheet.checks()), "max_utilisation": None, "key_results": [],
        "data": {}, "reinforcement": None, "sheet": sheet.to_dict(), "bbs": None, "quantities": None, "drawing": None, "charts": [],
    }
