"""Strap (cantilever) footing to IS 456:2000: an exterior column at a property line on an eccentric pad, tied by a rigid strap beam to
an interior column on its own pad.

The strap carries the eccentricity of the exterior pad's reaction to the interior column, so that each pad bears uniformly:

    R_1 = P_1 s / (s - e),  R_2 = P_1 + P_2 - R_1,  e = L_1 / 2 - a   (moments about the interior column; Cl. 34.1.3 for the
    distribution of pressure; the statics are the standard ones for a strap footing)

* Pad 1, under the exterior column, starts at the property line. Its length along the strap is the least, in 50 mm steps, that keeps its
  width across within twice the length (interpretation 105); it is a slab cantilevering across from the faces of the strap, with bars
  across for that bending (Cl. 34.2.3.2), one-way shear at d from the strap (Cl. 34.2.4.1(a)) and the minimum along.
* Pad 2, under the interior column, is an isolated footing for R_2 (the isolated footing engine, hand-checked on its own); the bearing
  at the column is checked for the column's whole load.
* The strap is a rectangular beam from the property line to the interior column. It hogs, most where its shear is nil over pad 1; its
  top bars are designed for that (Annex G, Cl. 26.5.1.1), developed toward the property line (Cl. 26.2.1, with a bend where needed);
  its shear is taken at d from the exterior column's face over pad 1 and as the constant shear of the free span, with stirrups to
  Cl. 40.4 and 26.5.1.5/26.5.1.6 and tau_c,max checked at the face (Table 20).

Worked example (the defaults): exterior column 400 x 400 with 800 kN at the property line, interior column 450 x 450 with 1200 kN
4.5 m away, safe bearing pressure 200 kN/m2, M25 / Fe 415. tests/handcheck/check_strap_footing.py reproduces it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engineering import is456
from app.engineering import is456_slabs as sl
from app.engineering.rebar import bar_area, bend_radius
from app.engineering.trace import CalcSheet
from app.modules.structural.domain import footing as iso
from app.modules.structural.domain.footing import FOOTING_BAR_DIAMETERS, FOOTING_MIN_COVER, PRACTICAL_MIN_SPACING, bars_across, bent_value

ELEMENT_TYPE = "strap_footing"
ENGINE_VERSION = "1.0.0"
CODE_BASIS = ("IS 456:2000", "IS 2502:1963")
REF = is456.CODE

STEP = 50.0
EDGE_MIN = 150.0  # Cl. 34.1.2
WIDTH_TO_LENGTH = 2.0  # pad 1 no wider across than twice its length along (interpretation 105)
MIN_GAP = 100.0  # clear distance between the pads
STRAP_BAR_DIAMETERS = (12, 16, 20, 25, 32)
STIRRUP_DIAMETERS = (8, 10, 12)
LEGS = 2
STIRRUP_ALLOWANCE = 12.0  # the strap's effective depths allow for the largest stirrup, whichever is chosen (on the safe side)


def _f(default: Any, title: str, group: str, unit: str = "", labels: dict[str, str] | None = None, **kw: Any) -> Any:
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


class StrapFootingInput(BaseModel):
    """Everything the strap footing engine reads. Lengths in mm, loads in kN, pressures in kN/m2."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("SF1", "Footing mark", "Member", min_length=1, max_length=40)
    column1_width_mm: float = _f(400, "Column 1 width b_1", "Column 1 (at the property line)", "mm", ge=150, le=2000, description="Across the strap")
    column1_depth_mm: float = _f(400, "Column 1 depth D_1", "Column 1 (at the property line)", "mm", ge=150, le=2000, description="Along the strap")
    p1_service_kn: float = _f(800, "Column 1 service load", "Column 1 (at the property line)", "kN", gt=0, le=1e5, description="Dead + imposed, unfactored")
    column2_width_mm: float = _f(450, "Column 2 width b_2", "Column 2 (interior)", "mm", ge=150, le=2000, description="Across the strap")
    column2_depth_mm: float = _f(450, "Column 2 depth D_2", "Column 2 (interior)", "mm", ge=150, le=2000, description="Along the strap")
    p2_service_kn: float = _f(1200, "Column 2 service load", "Column 2 (interior)", "kN", gt=0, le=1e5, description="Dead + imposed, unfactored")
    spacing_mm: float = _f(4500, "Column spacing", "Columns", "mm", ge=1500, le=15000, description="Centre to centre, along the strap")
    left_end_mm: float | None = _f(None, "Property line to column 1", "Columns", "mm", ge=75, le=3000,
                                   description="To the centre of column 1. Blank: the column's face on the property line")

    load_factor: float = _f(1.5, "Load factor", "Loading", "", ge=1.0, le=2.0, description="For design of the concrete, Table 18")
    self_weight_pct: float = _f(10, "Allowance for own weight", "Loading", "%", ge=0, le=40, description="Pads, strap and backfill, for sizing only")
    sbc_kn_m2: float = _f(200, "Safe bearing pressure", "Soil", "kN/m2", gt=0, le=5000, description="Net, from the soil investigation")

    pad1_length_mm: float | None = _f(None, "Pad 1 length L_1", "Pad 1 (exterior)", "mm", ge=300, le=10000, description="Along the strap. Blank: chosen")
    pad1_width_mm: float | None = _f(None, "Pad 1 width B_1", "Pad 1 (exterior)", "mm", ge=500, le=20000, description="Across. Blank: chosen")
    pad1_depth_mm: float | None = _f(None, "Pad 1 depth", "Pad 1 (exterior)", "mm", ge=200, le=3000, description="Blank: the least that passes")
    pad2_length_mm: float | None = _f(None, "Pad 2 length L_2", "Pad 2 (interior)", "mm", ge=500, le=20000, description="Along the strap. Blank: chosen")
    pad2_width_mm: float | None = _f(None, "Pad 2 width B_2", "Pad 2 (interior)", "mm", ge=500, le=20000, description="Across. Blank: chosen")
    pad2_depth_mm: float | None = _f(None, "Pad 2 depth", "Pad 2 (interior)", "mm", ge=200, le=3000, description="Blank: the least that passes")
    strap_width_mm: float | None = _f(None, "Strap width", "Strap", "mm", ge=230, le=2000, description="Blank: column 1's width, at least 300")
    strap_depth_mm: float | None = _f(None, "Strap depth", "Strap", "mm", ge=300, le=3000, description="Blank: the least that passes")

    fck: Literal[20, 25, 30, 35, 40] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in (20, 25, 30, 35, 40)})
    fy: Literal[250, 415, 500, 550] = _f(415, "Steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Clear cover", "Materials", "mm", ge=40, le=100, description="Blank: 50 mm or Table 16, whichever is more")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)
    bar_dia_mm: Literal[10, 12, 16, 20, 25] | None = _f(None, "Bar size in the pads", "Reinforcement", "mm", description="Blank lets the engine choose")

    def left_end(self) -> float:
        return self.left_end_mm if self.left_end_mm is not None else self.column1_depth_mm / 2.0

    def strap_width(self) -> float:
        return self.strap_width_mm if self.strap_width_mm is not None else max(self.column1_width_mm, 300.0)

    @model_validator(mode="after")
    def _consistent(self) -> StrapFootingInput:
        a = self.left_end()
        if a < self.column1_depth_mm / 2 - 1e-9:
            raise ValueError("The property line cannot cut column 1: the distance to its centre must be at least half its depth.")
        for n in (1, 2):
            if (getattr(self, f"pad{n}_length_mm") is None) != (getattr(self, f"pad{n}_width_mm") is None):
                raise ValueError(f"Enter both the length and the width of pad {n}, or leave both blank.")
        if self.pad1_length_mm is not None and self.pad1_length_mm < a + self.column1_depth_mm / 2:
            raise ValueError("Pad 1 must reach past the inner face of column 1.")
        if self.pad1_width_mm is not None and self.pad1_width_mm <= max(self.column1_width_mm, self.strap_width()):
            raise ValueError("Pad 1 must be wider than column 1 and the strap.")
        if self.strap_width() < self.column1_width_mm:
            raise ValueError("The strap must be at least as wide as column 1, which it carries.")
        return self


def reactions(inp: StrapFootingInput, L1: float) -> tuple[float, float, float]:
    """(e, R_1, R_2): the eccentricity of pad 1's reaction from column 1 (mm) and the service reactions (kN), by moments about column 2."""
    s = inp.spacing_mm
    e = L1 / 2.0 - inp.left_end()
    r1 = inp.p1_service_kn * s / (s - e)
    return e, r1, inp.p1_service_kn + inp.p2_service_kn - r1


def pad1_plan(inp: StrapFootingInput) -> tuple[float, float]:
    """The least length in 50 mm steps whose width, the least in 50 mm steps that keeps the pressure within the safe bearing pressure, is
    no more than twice the length; and that width (at least 100 mm wider than the column and the strap each side)."""
    a, d1 = inp.left_end(), inp.column1_depth_mm
    b_min = max(inp.column1_width_mm, inp.strap_width()) + 2 * 100.0
    L1 = math.ceil((a + d1 / 2.0 + 100.0) / STEP - 1e-9) * STEP
    while L1 < inp.spacing_mm:
        _, r1, _ = reactions(inp, L1)
        area = r1 * (1 + inp.self_weight_pct / 100.0) / inp.sbc_kn_m2 * 1e6
        B1 = max(b_min, math.ceil(area / L1 / STEP - 1e-9) * STEP)
        if B1 <= WIDTH_TO_LENGTH * L1 + 1e-9:
            return L1, B1
        L1 += STEP
    return math.inf, math.inf


class StrapStatics:
    """Shear and bending along the strap from the property line (x = 0) to column 2 (kN, kN m; sagging positive). Pad 1's factored
    reaction acts up uniformly over [0, L_1]; column 1's load acts down, spread over its depth. Column 2 and pad 2 close the statics."""

    def __init__(self, inp: StrapFootingInput, L1: float, gamma: float) -> None:
        _, r1, _ = reactions(inp, L1)
        self.L1 = L1
        self.a = inp.left_end()
        self.d1 = inp.column1_depth_mm
        self.x2 = self.a + inp.spacing_mm
        self.p1u = gamma * inp.p1_service_kn
        self.r1u = gamma * r1
        self.w = self.r1u / (L1 / 1000.0)  # kN/m over pad 1

    @property
    def lo1(self) -> float:
        return self.a - self.d1 / 2.0

    @property
    def hi1(self) -> float:
        return self.a + self.d1 / 2.0

    def shear(self, x: float) -> float:
        return self.w * min(x, self.L1) / 1000.0 - self.p1u * min(max((x - self.lo1) / self.d1, 0.0), 1.0)

    def moment(self, x: float) -> float:
        t, l1 = x / 1000.0, self.L1 / 1000.0
        up = self.w * t * t / 2.0 if x <= self.L1 else self.w * l1 * (t - l1 / 2.0)
        if x >= self.hi1:
            down = self.p1u * (x - self.a) / 1000.0
        elif x > self.lo1:
            down = self.p1u * (x - self.lo1) ** 2 / (2.0 * self.d1) / 1000.0
        else:
            down = 0.0
        return up - down

    def zero_shear(self) -> float:
        """Where the shear changes sign over pad 1, beyond column 1 (bisection)."""
        lo, hi = self.hi1, self.L1
        if self.shear(hi) <= 0:
            return hi
        for _ in range(80):
            m = (lo + hi) / 2.0
            if self.shear(m) < 0:
                lo = m
            else:
                hi = m
        return (lo + hi) / 2.0

    def greatest_sagging(self) -> float:
        """Sagging from pad 1's pressure under the overhang beyond the property line side of column 1 (nil when the face is on the line)."""
        return max(0.0, max(self.moment(self.lo1 + self.d1 * k / 20.0) for k in range(21)))


@dataclass
class Pad1:
    D: float
    dia: int
    d: float  # bars across
    d_along: float
    a_t: float
    q: float  # kN/m2, factored
    m: float  # kN m over L1
    as_flex: float
    as_req: float
    n: int
    s: float
    area: float
    bent: bool
    ld_req: float
    avail: float
    v: float
    tau: float
    tc: float
    dia_along: int
    as_along: float
    n_along: int
    s_along: float
    area_along: float
    ok: bool


@dataclass
class Zone:
    name: str
    x0: float
    x1: float
    v: float  # design shear, kN
    tau: float
    tc: float
    dia: int
    s: float  # stirrup spacing
    s_max: float
    vus: float  # kN, taken by the stirrups (0 where minimum steel)


@dataclass
class Strap:
    b: float
    D: float
    d: float
    dia: int
    n: int
    area: float
    as_flex: float
    as_req: float
    bent: bool
    ld_req: float
    avail: float
    m_hog: float
    x_hog: float
    dia_bot: int
    n_bot: int
    as_bot_req: float
    m_sag: float
    tau_face: float
    zones: list[Zone] = field(default_factory=list)
    side_dia: int = 0
    side_per_face: int = 0
    side_area: float = 0.0
    x_end: float = 0.0
    ok: bool = True


def effective_cover(inp: StrapFootingInput) -> float:
    if inp.clear_cover_mm is not None:
        return inp.clear_cover_mm
    return max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure))


def _spacing_ok(s: float, dia: int, agg: float) -> bool:
    return s >= PRACTICAL_MIN_SPACING - 1e-9 and s - dia >= is456.min_clear_bar_spacing_horizontal(dia, agg) - 1e-9


def pad1_trial(inp: StrapFootingInput, L1: float, B1: float, b_s: float, st: StrapStatics, D: float, cover: float) -> Pad1 | None:
    """Pad 1 at one depth: the smallest bar across that fits and develops (straight before bent), with the shear at d from the strap."""
    fck, fy, agg = float(inp.fck), float(inp.fy), inp.max_aggregate_mm
    dias = [inp.bar_dia_mm] if inp.bar_dia_mm else list(FOOTING_BAR_DIAMETERS)
    q = st.r1u / (L1 / 1000.0 * B1 / 1000.0)
    a_t = (B1 - b_s) / 2.0
    m = q * (L1 / 1000.0) * (a_t / 1000.0) ** 2 / 2.0
    for allow_bent in (False, True):
        for dia in dias:
            d = D - cover - dia / 2.0
            if m * 1e6 > is456.limiting_moment(fck, fy, L1, d):
                return None
            asf = is456.design_rectangular(m * 1e6, fck, fy, L1, d, 0).ast_req if m > 0 else 0.0
            asr = max(asf, sl.min_steel(L1, D, fy))
            s, n, area = bars_across(asr, L1, dia, sl.max_spacing_main(d), cover)
            if not _spacing_ok(s, dia, agg):
                continue
            ld = is456.development_length(dia, fck, fy) * min(asf / area, 1.0)
            avail = a_t - cover
            straight = ld <= avail + 1e-9
            if not (straight or (allow_bent and ld <= bent_value(avail, dia, fy) + 1e-9)):
                continue
            v = q * (L1 / 1000.0) * max(a_t - d, 0.0) / 1000.0
            tau = v * 1e3 / (L1 * d)
            tc = is456.tau_c(fck, 100.0 * area / (L1 * d))
            along = None
            for dl in (dias if inp.bar_dia_mm else FOOTING_BAR_DIAMETERS):
                d_l = D - cover - dia - dl / 2.0
                s_l, n_l, a_l = bars_across(sl.min_steel(B1, D, fy), B1, dl, sl.max_spacing_main(d_l), cover)
                if _spacing_ok(s_l, dl, agg):
                    along = (dl, d_l, s_l, n_l, a_l)
                    break
            if along is None:
                continue
            dl, d_l, s_l, n_l, a_l = along
            return Pad1(D, dia, d, d_l, a_t, q, m, asf, asr, n, s, area, not straight, ld, avail, v, tau, tc, dl, sl.min_steel(B1, D, fy), n_l, s_l, a_l,
                        tau <= tc + 1e-12)
    return None


def select_pad1(inp: StrapFootingInput, L1: float, B1: float, b_s: float, st: StrapStatics, cover: float) -> Pad1 | None:
    depths = [float(inp.pad1_depth_mm)] if inp.pad1_depth_mm else [float(d) for d in range(300, 3001, int(STEP))]
    for D in depths:
        t = pad1_trial(inp, L1, B1, b_s, st, D, cover)
        if t is not None and (t.ok or inp.pad1_depth_mm):
            return t
    return None


def stirrups(fy: float, b: float, d: float, v: float, tc: float, agg: float) -> tuple[int, float, float, float] | None:
    """(dia, spacing, the most it may be, V_us) for two-legged stirrups: Cl. 40.4(a) where tau_v exceeds tau_c, Cl. 26.5.1.6 otherwise,
    and Cl. 26.5.1.5 (0.75 d, 300 mm); spacing in 10 mm steps, at least 100 mm."""
    fys = is456.shear_fy(fy)
    vus = max(v * 1e3 - tc * b * d, 0.0)
    for dia in STIRRUP_DIAMETERS:
        asv = LEGS * bar_area(dia)
        s_max = min(is456.stirrup_spacing_minimum_steel(fys, asv, b), 0.75 * d, 300.0)
        s = s_max if vus <= 0 else min(is456.stirrup_spacing_for_shear(vus, fys, asv, d), s_max)
        s = math.floor(s / 10.0 + 1e-9) * 10.0
        if s >= PRACTICAL_MIN_SPACING - 1e-9:
            return dia, s, s_max, vus / 1e3
    return None


def strap_trial(inp: StrapFootingInput, st: StrapStatics, b: float, D: float, cover: float, x_end: float) -> Strap | None:
    """The strap at one depth: the top bars with the least steel that fit in one layer and develop toward the property line; stirrups for
    the two zones; bottom bars and side-face bars. None where the section needs compression steel, tau_c,max is exceeded or no bars fit."""
    fck, fy, agg = float(inp.fck), float(inp.fy), inp.max_aggregate_mm
    x0 = st.zero_shear()
    m_hog = max(-st.moment(x0), 0.0)
    best: tuple[float, int, Strap] | None = None
    for dia in STRAP_BAR_DIAMETERS:
        d = D - cover - STIRRUP_ALLOWANCE - dia / 2.0
        if m_hog * 1e6 > is456.limiting_moment(fck, fy, b, d):
            continue
        asf = is456.design_rectangular(m_hog * 1e6, fck, fy, b, d, 0).ast_req if m_hog > 0 else 0.0
        asr = max(asf, is456.min_tension_steel(b, d, fy))
        n = max(2, math.ceil(asr / bar_area(dia) - 1e-9))
        clear = (b - 2 * cover - 2 * STIRRUP_ALLOWANCE - n * dia) / (n - 1)
        if clear < max(dia, agg + 5.0) - 1e-9 or n * bar_area(dia) > is456.max_steel(b, D) + 1e-9:
            continue
        area = n * bar_area(dia)
        ld = is456.development_length(dia, fck, fy) * min(asf / area, 1.0)
        avail = x0 - cover
        straight = ld <= avail + 1e-9
        if not straight and ld > bent_value(avail, dia, fy) + 1e-9:
            continue
        cand = Strap(b, D, d, dia, n, area, asf, asr, not straight, ld, avail, m_hog, x0, 0, 0, 0.0, 0.0, 0.0, x_end=x_end)
        if best is None or (area, n) < (best[0], best[1]):
            best = (area, n, cand)
    if best is None:
        return None
    s = best[2]
    # shear: at the face of column 1 (tau_c,max) and at d from it over pad 1; the constant shear of the free span
    tc = is456.tau_c(fck, 100.0 * s.area / (b * s.d))
    v_face = abs(st.shear(st.hi1))
    s.tau_face = v_face * 1e3 / (b * s.d)
    if s.tau_face > is456.tau_c_max(fck) + 1e-12:
        return None
    xa = min(st.hi1 + s.d, st.L1)
    for name, x0z, x1z, v in (("over pad 1", 0.0, st.L1, abs(st.shear(xa))), ("free span", st.L1, x_end, abs(st.shear((st.L1 + st.x2) / 2.0)))):
        res = stirrups(fy, b, s.d, v, tc, agg)
        if res is None:
            return None
        dia, sp, s_max, vus = res
        s.zones.append(Zone(name, x0z, x1z, v, v * 1e3 / (b * s.d), tc, dia, sp, s_max, vus))
    # bottom bars: two at least, more where the overhang beyond the property line side of column 1 sags
    s.m_sag = st.greatest_sagging()
    for dia in STRAP_BAR_DIAMETERS:
        d_b = D - cover - STIRRUP_ALLOWANCE - dia / 2.0
        need = is456.design_rectangular(s.m_sag * 1e6, fck, fy, b, d_b, 0).ast_req if s.m_sag > 0 else 0.0
        n_b = max(2, math.ceil(need / bar_area(dia) - 1e-9))
        if (b - 2 * cover - 2 * STIRRUP_ALLOWANCE - n_b * dia) / max(n_b - 1, 1) >= max(dia, agg + 5.0) - 1e-9:
            s.dia_bot, s.n_bot, s.as_bot_req = dia, n_b, need
            break
    if not s.n_bot:
        return None
    # Cl. 26.5.1.3: side-face bars where the depth exceeds 750 mm, 0.1 percent of the web area, at most 300 mm (and the width) apart
    if D > 750.0:
        per_face_area = 0.0005 * b * D
        h = D - 2.0 * (cover + STIRRUP_ALLOWANCE)
        for dia in (10, 12, 16):
            n = max(math.ceil(h / min(300.0, b) - 1e-9) - 1, math.ceil(per_face_area / bar_area(dia) - 1e-9), 1)
            if n * bar_area(dia) >= per_face_area - 1e-9:
                s.side_dia, s.side_per_face, s.side_area = dia, n, 2 * n * bar_area(dia)
                break
    return s


def select_strap(inp: StrapFootingInput, st: StrapStatics, b: float, d_min: float, cover: float, x_end: float) -> Strap | None:
    depths = [float(inp.strap_depth_mm)] if inp.strap_depth_mm else [float(d) for d in range(int(max(300.0, math.ceil(d_min / STEP) * STEP)), 3001, int(STEP))]
    for D in depths:
        t = strap_trial(inp, st, b, D, cover, x_end)
        if t is not None:
            return t
    return None


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def _pad2_input(inp: StrapFootingInput, r2: float) -> iso.FootingInput:
    return iso.FootingInput(
        mark=f"{inp.mark} pad 2", column_width_mm=inp.column2_width_mm, column_depth_mm=inp.column2_depth_mm, p_service_kn=r2,
        m_l_service_knm=0, m_b_service_knm=0, load_factor=inp.load_factor, self_weight_pct=inp.self_weight_pct, sbc_kn_m2=inp.sbc_kn_m2,
        length_mm=inp.pad2_length_mm, width_mm=inp.pad2_width_mm, depth_mm=inp.pad2_depth_mm, fck=inp.fck, fy=inp.fy, exposure=inp.exposure,
        clear_cover_mm=inp.clear_cover_mm, max_aggregate_mm=inp.max_aggregate_mm, bar_dia_mm=inp.bar_dia_mm)


def design_strap_footing(inp: StrapFootingInput) -> dict[str, Any]:
    from app.modules.structural.domain import strap_footing_detailing as det

    sheet = CalcSheet()
    fck, fy = float(inp.fck), float(inp.fy)
    cover = effective_cover(inp)
    gamma = inp.load_factor
    a, s_c = inp.left_end(), inp.spacing_mm
    b_s = inp.strap_width()

    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade and steel", "f_ck, f_y", "", f"M{inp.fck}, Fe {inp.fy}", "")
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.step(f"{REF}, Cl. 26.4.2.2 and Table 16" if inp.clear_cover_mm is None else "Input",
               "Clear cover: 50 mm for footings, and not less than Table 16", "c", "", cover, "mm", 0)
    sheet.check("cover", f"{REF}, Cl. 26.4.2.2", "Cover in a footing", "c", cover, ">=", "c_min",
                max(FOOTING_MIN_COVER, is456.nominal_cover(inp.exposure)), "mm", 0, ratio=False)

    # ------------------------------------------------------------------ plan and reactions
    sheet.section("2. Pad 1 and the reactions")
    sheet.step("Input" if inp.left_end_mm is not None else "Geometry", "Property line to the centre of column 1", "a", "", a, "mm", 0)
    if inp.pad1_length_mm is None:
        L1, B1 = pad1_plan(inp)
        if math.isinf(L1):
            return _stopped(sheet, "No pad under column 1, shorter than the spacing, keeps the pressure within the safe bearing pressure: check "
                                   "the loads and the soil.")
        sheet.step("Selected", "Pad 1: the least length in 50 mm steps whose width, for the bearing pressure, is at most twice the length "
                   "(interpretation 105)", "L_1, B_1", "", f"{_n(L1, 0)}, {_n(B1, 0)}", "mm")
    else:
        L1, B1 = float(inp.pad1_length_mm), float(inp.pad1_width_mm or 0)
        sheet.step("Input", "Pad 1", "L_1, B_1", "", f"{_n(L1, 0)}, {_n(B1, 0)}", "mm")
    e, r1, r2 = reactions(inp, L1)
    sheet.step("Statics", "Eccentricity of pad 1's reaction from column 1", "e = L_1/2 - a", f"{_n(L1, 0)}/2 - {_n(a, 0)}", e, "mm", 0)
    sheet.step("Statics", "Reaction under pad 1, by moments about column 2", "R_1 = P_1 s / (s - e)",
               f"{_n(inp.p1_service_kn, 1)} x {_n(s_c, 0)} / ({_n(s_c, 0)} - {_n(e, 0)})", r1, "kN", 1)
    sheet.step("Statics", "Reaction under pad 2", "R_2 = P_1 + P_2 - R_1", f"{_n(inp.p1_service_kn, 1)} + {_n(inp.p2_service_kn, 1)} - {_n(r1, 1)}",
               r2, "kN", 1)
    if not sheet.check("r2", "Statics", "Column 2 holds the strap down: pad 2's reaction positive", "R_2", r2, ">=", "0", 0.0, "kN", 1, ratio=False):
        return _stopped(sheet, "Column 2 is too light to balance column 1's eccentricity (R_2 would pull the pad up): a combined footing suits "
                               "these columns, or a pad 1 with less eccentricity.")
    q1 = r1 * (1 + inp.self_weight_pct / 100.0) / (L1 / 1000.0 * B1 / 1000.0)
    sheet.step("Statics", "Pressure under pad 1 with the own-weight allowance, uniform (the strap is rigid)", "q_1 = R_1 (1 + alpha) / (L_1 B_1)",
               f"{_n(r1, 1)} x (1 + {_n(inp.self_weight_pct, 0)}/100) / ({_n(L1 / 1000, 3)} x {_n(B1 / 1000, 3)})", q1, "kN/m2", 1)
    sheet.check("bearing_soil_1", "Soil", "Pressure under pad 1 within the safe bearing pressure", "q_1", q1, "<=", "q_safe", inp.sbc_kn_m2, "kN/m2", 1)

    # pad 2: the isolated footing engine for R_2
    pad2 = iso.design_footing(_pad2_input(inp, r2))
    if pad2["status"] == "stopped":
        return _stopped(sheet, f"Pad 2: {pad2['stop_message']}")
    L2, B2, D2p = pad2["data"]["L"], pad2["data"]["B"], pad2["data"]["D"]
    x2 = a + s_c
    gap = (x2 - L2 / 2.0) - L1
    sheet.step("Geometry", "Clear distance between the pads", "x_2 - L_2/2 - L_1", f"{_n(x2, 0)} - {_n(L2, 0)}/2 - {_n(L1, 0)}", gap, "mm", 0)
    if gap < MIN_GAP - 1e-9:
        return _stopped(sheet, f"The two pads would meet (clear distance {gap:.0f} mm): a combined footing suits these columns better.")

    # ------------------------------------------------------------------ strap
    st = StrapStatics(inp, L1, gamma)
    x_end = min(x2 + inp.column2_depth_mm / 2.0 + 300.0, x2 + L2 / 2.0)  # the strap runs into pad 2, past the far face of column 2
    widened = False
    if inp.strap_width_mm is None and select_strap(inp, st, b_s, D2p, cover, x_end) is None:
        # column 1's width suits no depth: of the wider straps, in 50 mm steps leaving 100 mm of pad 1 each side, the least cross-section
        found, best_area = None, math.inf
        b_try = b_s + STEP
        while b_try <= B1 - 200.0 + 1e-9:
            t = select_strap(inp, st, b_try, D2p, cover, x_end)
            if t is not None and b_try * t.D < best_area - 1e-6:
                found, best_area = b_try, b_try * t.D
            b_try += STEP
        if found is None:
            return _stopped(sheet, "The strap depth entered is too shallow for its hogging or its shear at any width pad 1 allows: increase it or "
                                   "leave it blank." if inp.strap_depth_mm else
                                   "No strap as wide as pad 1 allows carries the hogging and the shear (tau_c,max at the face of column 1): "
                                   "enter a larger pad 1, or check the loads.")
        widened, b_s = found > b_s, found
    pad1 = select_pad1(inp, L1, B1, b_s, st, cover)
    if pad1 is None:
        return _stopped(sheet, "No depth of pad 1 up to 3 m carries its bending and shear across with bars that can be developed: enter a "
                               "larger pad 1, or leave it blank." if not inp.pad1_depth_mm else
                               "The depth of pad 1 entered needs compression steel, or its bars cannot be developed: increase it or leave it blank.")
    strap = select_strap(inp, st, b_s, max(pad1.D, D2p), cover, x_end)
    if strap is None:
        return _stopped(sheet, "No strap depth up to 3 m carries the hogging and the shear (tau_c,max at the face of column 1) with one layer of "
                               "top bars: enter a wider strap." if not inp.strap_depth_mm else
                               "The strap depth entered is too shallow for its hogging or its shear: increase it or leave it blank.")
    # the top bars run past column 2, where the hogging ends, by d or 12 diameters (Cl. 26.2.3.1)
    # (beyond pad 2's far edge where pad 2 is short: the strap is a beam and may run past it)
    strap.x_end = math.ceil(max(x_end, x2 + max(strap.d, 12.0 * strap.dia) + cover) / 25.0 - 1e-9) * 25.0
    strap.zones[-1].x1 = strap.x_end

    sheet.section("3. Strap beam")
    sheet.step(f"{REF}, Table 18", "Factored load of column 1 and reaction under pad 1", "P_u1, R_u1 = gamma_f (P_1, R_1)", f"gamma_f = {_n(gamma)}",
               f"{_n(st.p1u, 1)}, {_n(st.r1u, 1)}", "kN")
    sheet.step("Statics", "Pad 1's reaction per metre along the strap", "w = R_u1 / L_1", f"{_n(st.r1u, 1)} / {_n(L1 / 1000, 3)}", st.w, "kN/m", 1)
    sheet.step("Statics", "Greatest hogging, over pad 1 where the shear is nil", "M_hog at V = 0", f"x = {_n(strap.x_hog, 0)} mm", -strap.m_hog, "kN m", 1)
    sheet.step("Statics", "Shear at the inner face of column 1, and in the free span", "V", f"x = {_n(st.hi1, 0)}; between the pads",
               f"{_n(abs(st.shear(st.hi1)), 1)}, {_n(abs(st.shear((L1 + x2) / 2)), 1)}", "kN")
    sheet.step("Selected" if not inp.strap_depth_mm else "Input", "Strap section: width" + (
               (" widened, column 1's suiting no depth: of the widths in 50 mm steps, the least cross-section" if widened
                else " (column 1's, at least 300)")
               if inp.strap_width_mm is None else "")
               + "; depth the least in 50 mm steps, not less than the pads, that needs no compression steel", "b x D", "", f"{_n(b_s, 0)} x {_n(strap.D, 0)}", "mm")
    sheet.step("Geometry", f"Effective depth, T{strap.dia} top bars inside stirrups of up to 12 mm", "d = D - c - 12 - phi/2", "", strap.d, "mm", 1)
    sheet.check("mulim_strap", f"{REF}, Annex G-1.1(c)", "Strap: no compression steel for the hogging", "M", strap.m_hog, "<=", "M_u,lim",
                is456.limiting_moment(fck, fy, b_s, strap.d) / 1e6, "kN m", 2)
    sheet.step(f"{REF}, Annex G-1.1(b), Cl. 26.5.1.1(a)", "Strap: top steel for the hogging, not less than 0.85 b d / f_y", "A_s,req",
               f"A_s = {_n(strap.as_flex, 0)}", strap.as_req, "mm2", 0)
    sheet.check("as_strap", f"{REF}, Cl. 26.5.1.1", f"Strap: {strap.n} T{strap.dia} at the top, in one layer", "A_s,req", strap.as_req, "<=", "A_s,prov",
                strap.area, "mm2", 0)
    sheet.check("asmax_strap", f"{REF}, Cl. 26.5.1.1(b)", "Strap: top steel not more than 4 percent", "A_s,prov", strap.area, "<=", "0.04 b D",
                is456.max_steel(b_s, strap.D), "mm2", 0)
    if strap.bent:
        sheet.check("anchor_strap", f"{REF}, Cl. 26.2.1, 26.2.2.1(b)", "Top bars developed toward the property line, at the stress there, bent down "
                    f"90 degrees at the end (r = {bend_radius(strap.dia, fy):.0f})", "L_d sigma_s/(0.87 f_y)", strap.ld_req, "<=",
                    "x - c - (r + phi) + 8 phi", bent_value(strap.avail, strap.dia, fy), "mm", 0)
    else:
        sheet.check("anchor_strap", f"{REF}, Cl. 26.2.1", "Top bars developed toward the property line, at the stress there", "L_d sigma_s/(0.87 f_y)",
                    strap.ld_req, "<=", "x - c", strap.avail, "mm", 0)
    sheet.check("extend_strap", f"{REF}, Cl. 26.2.3.1", "Top bars run past column 2, where the hogging ends, by d or 12 phi at least",
                "max(d, 12 phi)", max(strap.d, 12.0 * strap.dia), "<=", "x_end - c - x_2", strap.x_end - cover - x2, "mm", 0)
    sheet.check("tcmax_strap", f"{REF}, Cl. 40.2.3, Table 20", "Strap: shear stress at the face of column 1 within tau_c,max", "tau_v", strap.tau_face,
                "<=", "tau_c,max", is456.tau_c_max(fck), "N/mm2", 2)
    for z in strap.zones:
        sheet.step(f"{REF}, Cl. 40.1, Table 19", f"Strap {z.name}: design shear" + (" at d from the face of column 1" if z.name == "over pad 1" else ""),
                   "tau_v = V_u/(b d); tau_c", f"V_u = {_n(z.v, 1)} kN", f"{_n(z.tau, 3)}; {_n(z.tc, 3)}", "N/mm2")
        if z.vus > 0:
            sheet.step(f"{REF}, Cl. 40.4(a)", f"Strap {z.name}: stirrups for V_us = V_u - tau_c b d", "s_v = 0.87 f_y A_sv d / V_us",
                       f"V_us = {_n(z.vus, 1)} kN, 2-legged T{z.dia}", z.s, "mm", 0)
        else:
            sheet.step(f"{REF}, Cl. 26.5.1.6", f"Strap {z.name}: minimum shear reinforcement", "s_v = 0.87 f_y A_sv / (0.4 b)", f"2-legged T{z.dia}",
                       z.s, "mm", 0)
        sheet.check(f"sv_{'pad' if z.name == 'over pad 1' else 'span'}", f"{REF}, Cl. 26.5.1.5, 26.5.1.6", f"Strap {z.name}: stirrup spacing",
                    "s_v", z.s, "<=", "s_v,max", z.s_max, "mm", 0)
    sheet.step(f"{REF}, Cl. 26.5.1.1", f"Strap: bottom bars, {strap.n_bot} T{strap.dia_bot}" + (
               f", for the sagging {strap.m_sag:.1f} kN m beyond the property line side of column 1" if strap.m_sag > 0 else ", hangers for the stirrups"),
               "A_s", "", strap.n_bot * bar_area(strap.dia_bot), "mm2", 0)
    if strap.side_per_face:
        sheet.step(f"{REF}, Cl. 26.5.1.3", f"Side-face bars, the strap deeper than 750 mm: {strap.side_per_face} T{strap.side_dia} each face", "A_s,side",
                   "0.1 percent of the web", strap.side_area, "mm2", 0)

    # ------------------------------------------------------------------ pad 1
    sheet.section("4. Pad 1, across the strap")
    sheet.step("Selected" if not inp.pad1_depth_mm else "Input", "Depth: the least in 50 mm steps with no compression steel and no shear steel"
               if not inp.pad1_depth_mm else "Depth", "D_1", "", pad1.D, "mm", 0)
    sheet.check("edge_1", f"{REF}, Cl. 34.1.2", "Thickness at the edge of pad 1", "D", pad1.D, ">=", "D_edge,min", EDGE_MIN, "mm", 0, ratio=False)
    sheet.step("Statics", "Factored pressure under pad 1, uniform", "q_u1 = R_u1 / (L_1 B_1)", "", pad1.q, "kN/m2", 1)
    sheet.step(f"{REF}, Cl. 34.2.3.2", "Bending across at the face of the strap, over the length of the pad", "M = q_u1 L_1 a_t^2 / 2",
               f"a_t = ({_n(B1, 0)} - {_n(b_s, 0)})/2 = {_n(pad1.a_t, 0)}", pad1.m, "kN m", 2)
    sheet.check("mulim_pad1", f"{REF}, Annex G-1.1(c)", "Pad 1: no compression steel", "M", pad1.m, "<=", "M_u,lim",
                is456.limiting_moment(fck, fy, L1, pad1.d) / 1e6, "kN m", 2)
    sheet.step(f"{REF}, Annex G-1.1(b), Cl. 26.5.2.1", "Pad 1: steel across for the moment, not less than the minimum", "A_s,req", f"A_s = {_n(pad1.as_flex, 0)}, "
               f"d = {_n(pad1.d, 1)}", pad1.as_req, "mm2", 0)
    sheet.check("as_pad1", f"{REF}, Cl. 26.5.2.1", f"Pad 1: {pad1.n} T{pad1.dia} across at {pad1.s:.0f}", "A_s,req", pad1.as_req, "<=", "A_s,prov", pad1.area, "mm2", 0)
    sheet.check("spacing_pad1", f"{REF}, Cl. 26.3.3(b)", "Pad 1: spacing across", "s", pad1.s, "<=", "s_max", sl.max_spacing_main(pad1.d), "mm", 0)
    if pad1.bent:
        sheet.check("anchor_pad1", f"{REF}, Cl. 26.2.1, 26.2.2.1(b)", "Pad 1: bars across developed beyond the strap face, with end bends",
                    "L_d sigma_s/(0.87 f_y)", pad1.ld_req, "<=", "a_t - c - (r + phi) + 8 phi", bent_value(pad1.avail, pad1.dia, fy), "mm", 0)
    else:
        sheet.check("anchor_pad1", f"{REF}, Cl. 26.2.1, 34.2.4.3", "Pad 1: bars across developed beyond the strap face, at the stress there",
                    "L_d sigma_s/(0.87 f_y)", pad1.ld_req, "<=", "a_t - c", pad1.avail, "mm", 0)
    sheet.step(f"{REF}, Cl. 34.2.4.1(a)", "Pad 1: one-way shear at d from the face of the strap", "V = q_u1 L_1 (a_t - d)", "", pad1.v, "kN", 1)
    sheet.check("shear_pad1", f"{REF}, Cl. 34.2.4.1(a), Table 19", "Pad 1: one-way shear", "tau_v", pad1.tau, "<=", "tau_c", pad1.tc, "N/mm2", 3)
    sheet.step(f"{REF}, Cl. 26.5.2.1", f"Pad 1: bars along, the minimum: {pad1.n_along} T{pad1.dia_along} at {pad1.s_along:.0f}", "A_s,min",
               f"over B_1 = {_n(B1, 0)}", pad1.as_along, "mm2", 0)

    # ------------------------------------------------------------------ pad 2 (the isolated footing's own sheet, without its bearing)
    sheet_dict = sheet.to_dict()
    nested = pad2["sheet"]["sections"]
    renumber = 5
    for sec in nested:
        title = sec["title"]
        if title.startswith(("1.", "6.")):
            continue  # materials as above; the bearing for the column's whole load follows
        items = [{**i, "id": f"pad2_{i['id']}"} if i["kind"] == "check" else i for i in sec["items"]]
        sheet_dict["sections"].append({"title": f"{renumber}. Pad 2: {title.split('. ', 1)[1].lower()}", "items": items})
        renumber += 1
    pre = CalcSheet()
    pre.section("Pad 2 load")  # a step that says what pad 2 carries, at the head of its plan section
    pre.step("Statics", "Pad 2 is an isolated footing under column 2 for the reaction R_2, its pressure uniform", "P = R_2", "", r2, "kN", 1)
    first_pad2 = next(i for i, sct in enumerate(sheet_dict["sections"]) if ": plan size" in sct["title"])
    sheet_dict["sections"][first_pad2]["items"] = pre.to_dict()["sections"][0]["items"] + sheet_dict["sections"][first_pad2]["items"]

    # ------------------------------------------------------------------ bearing
    bear = CalcSheet()
    bear.section(f"{renumber}. Transfer of load at the base of the columns")
    bearing = []
    for i, (bc, dc, pu, ratio, where) in enumerate((
            (inp.column1_width_mm, inp.column1_depth_mm, st.p1u, min(2.0 * a / inp.column1_depth_mm, b_s / inp.column1_width_mm,
                                                                     1.0 + 4.0 * strap.D / max(inp.column1_width_mm, inp.column1_depth_mm), 2.0), "the strap"),
            (inp.column2_width_mm, inp.column2_depth_mm, gamma * inp.p2_service_kn, min(L2 / inp.column2_depth_mm, B2 / inp.column2_width_mm,
                                                                                        1.0 + 4.0 * D2p / max(inp.column2_width_mm, inp.column2_depth_mm), 2.0), "pad 2")),
            start=1):
        ratio = max(ratio, 1.0)
        allow = 0.45 * fck * ratio
        sigma = pu * 1e3 / (bc * dc)
        bearing.append((sigma, allow, ratio))
        bear.step(f"{REF}, Cl. 34.4", f"Column {i} on {where}: allowable bearing, A_1 within the support at 1 in 2, sqrt(A_1/A_2) not more than 2",
                  "0.45 f_ck sqrt(A_1/A_2)", f"sqrt(A_1/A_2) = {_n(ratio, 3)}", allow, "N/mm2", 2)
        if not bear.check(f"bearing{i}", f"{REF}, Cl. 34.4", f"Bearing at the base of column {i}, its whole load", "sigma = P_u/(b D)", sigma, "<=",
                          "sigma_allow", allow, "N/mm2", 2):
            sheet.flag("warning", f"Bearing under column {i} exceeds the allowable by {(sigma - allow) * bc * dc / 1e3:.0f} kN: carry the excess on "
                                  "column bars or dowels continued into the footing, or raise the concrete grade.", f"{REF}, Cl. 34.4")
        bear.step(f"{REF}, Cl. 34.4.3", f"Column {i}: bars or dowels continued into the footing, at least 0.5 percent of the column", "A_s,dowel,min",
                  "", 0.005 * bc * dc, "mm2", 0)
    sheet_dict["sections"] += bear.to_dict()["sections"]

    # ------------------------------------------------------------------ flags and outputs
    flags = [
        {"level": "info", "message": "The strap is taken as rigid and kept off the soil between the pads (loose fill or a gap under it); its own "
                                     "weight is within the allowance for sizing and left out of its design, which is on the safe side for its hogging.",
         "ref": ""},
        {"level": "info", "message": "Pad 1 carries the strap along its length, so it is checked in one-way shear from the strap's faces; punching "
                                     "does not apply to it.", "ref": ""},
    ]
    flags += [f for f in pad2["sheet"]["flags"] if "Bearing" not in f["message"]]
    flags += [asdict(f) for f in sheet.flags] + [asdict(f) for f in bear.flags]
    sheet_dict["flags"] = flags

    def all_checks() -> list[dict[str, Any]]:
        return [i for sec in sheet_dict["sections"] for i in sec["items"] if i["kind"] == "check"]

    checks = all_checks()
    utils = [c["util"] for c in checks if c.get("util") is not None]
    ok = all(c["ok"] for c in checks) and pad1.ok and not any(f["level"] == "error" for f in flags)

    reinforcement = det.reinforcement(inp, L1, B1, x2, pad1, strap, pad2, cover)
    bbs = det.bar_schedule(inp, reinforcement, pad2["bbs"])
    quantities = det.quantities(reinforcement, bbs)
    drawing = det.drawing(inp, reinforcement)
    charts = _charts(st, strap)
    key_results = [
        {"label": "Pad 1 L x B x D", "sym": "", "value": f"{L1:.0f} x {B1:.0f} x {pad1.D:.0f}", "unit": "mm", "dp": 0},
        {"label": "Pad 2 L x B x D", "sym": "", "value": f"{L2:.0f} x {B2:.0f} x {D2p:.0f}", "unit": "mm", "dp": 0},
        {"label": "Strap b x D", "sym": "", "value": f"{b_s:.0f} x {strap.D:.0f}", "unit": "mm", "dp": 0},
        {"label": "Reactions R1, R2", "sym": "", "value": f"{r1:.0f}, {r2:.0f}", "unit": "kN", "dp": 0},
        {"label": "Strap top bars", "sym": "", "value": f"{strap.n}-T{strap.dia}", "unit": "", "dp": 0},
        {"label": "Strap stirrups", "sym": "", "value": " / ".join(f"T{z.dia} @ {z.s:.0f}" for z in strap.zones), "unit": "", "dp": 0},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
        {"label": "Concrete", "sym": "", "value": quantities["concrete_m3"], "unit": "m3", "dp": 3},
    ]
    data = {
        "cover": cover, "a": a, "x2": x2, "L1": L1, "B1": B1, "e": round(e, 6), "R1": round(r1, 6), "R2": round(r2, 6), "q1": round(q1, 6),
        "L2": L2, "B2": B2, "gap": round(gap, 3), "p1u": round(st.p1u, 6), "r1u": round(st.r1u, 6), "w": round(st.w, 6),
        "pad1": {"D": pad1.D, "dia": pad1.dia, "d": round(pad1.d, 3), "a_t": pad1.a_t, "q": round(pad1.q, 6), "m": round(pad1.m, 6),
                 "as_flex": round(pad1.as_flex, 4), "as_req": round(pad1.as_req, 4), "n": pad1.n, "s": pad1.s, "area": round(pad1.area, 4),
                 "bent": pad1.bent, "ld_req": round(pad1.ld_req, 3), "avail": round(pad1.avail, 3), "v": round(pad1.v, 6), "tau": round(pad1.tau, 6),
                 "tc": round(pad1.tc, 6), "dia_along": pad1.dia_along, "as_along": round(pad1.as_along, 4), "n_along": pad1.n_along,
                 "s_along": pad1.s_along, "area_along": round(pad1.area_along, 4)},
        "pad2": pad2["data"],
        "strap": {"b": b_s, "D": strap.D, "d": round(strap.d, 3), "dia": strap.dia, "n": strap.n, "area": round(strap.area, 4),
                  "as_flex": round(strap.as_flex, 4), "as_req": round(strap.as_req, 4), "bent": strap.bent, "ld_req": round(strap.ld_req, 3),
                  "avail": round(strap.avail, 3), "m_hog": round(strap.m_hog, 6), "x_hog": round(strap.x_hog, 3), "tau_face": round(strap.tau_face, 6),
                  "v_face": round(abs(st.shear(st.hi1)), 6), "dia_bot": strap.dia_bot, "n_bot": strap.n_bot, "m_sag": round(strap.m_sag, 6),
                  "side_dia": strap.side_dia, "side_per_face": strap.side_per_face, "x_end": strap.x_end,
                  "zones": [{"name": z.name, "x0": z.x0, "x1": z.x1, "v": round(z.v, 6), "tau": round(z.tau, 6), "tc": round(z.tc, 6), "dia": z.dia,
                             "s": z.s, "s_max": round(z.s_max, 3), "vus": round(z.vus, 6)} for z in strap.zones]},
        "bearing": [{"sigma": round(sg, 6), "allow": round(al, 6), "ratio": round(r, 6)} for sg, al, r in bearing],
    }
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok", "stop_message": None,
        "checks_passed": sum(1 for c in checks if c["ok"]), "checks_total": len(checks), "max_utilisation": max(utils) if utils else None,
        "key_results": key_results, "data": data, "reinforcement": reinforcement, "sheet": sheet_dict, "bbs": bbs, "quantities": quantities,
        "drawing": drawing, "charts": charts,
    }


def _charts(st: StrapStatics, strap: Strap) -> list[dict[str, Any]]:
    xs = sorted({*(st.x2 * i / 100.0 for i in range(101)), st.lo1, st.hi1, st.L1, strap.x_hog})
    return [
        {"id": "moments", "title": "Bending moment along the strap (factored)", "x": {"label": "x", "unit": "m"}, "y": {"label": "M_u", "unit": "kN m"},
         "series": [{"name": "Bending moment", "kind": "line", "points": [[round(x / 1000, 4), round(st.moment(x), 2)] for x in xs]}],
         "note": "x from the property line to column 2. Hogging (tension at the top) negative; greatest over pad 1, nil at column 2."},
        {"id": "shear", "title": "Shear force along the strap (factored)", "x": {"label": "x", "unit": "m"}, "y": {"label": "V_u", "unit": "kN"},
         "series": [{"name": "Shear force", "kind": "line", "points": [[round(x / 1000, 4), round(st.shear(x), 2)] for x in xs]}],
         "note": "x from the property line; pad 1's pressure up over its length, column 1's load down; constant between the pads."},
    ]


def _stopped(sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE, "engine_version": ENGINE_VERSION, "code_basis": list(CODE_BASIS), "status": "stopped", "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok), "checks_total": len(sheet.checks()), "max_utilisation": None, "key_results": [],
        "data": {}, "reinforcement": None, "sheet": sheet.to_dict(), "bbs": None, "quantities": None, "drawing": None, "charts": [],
    }
