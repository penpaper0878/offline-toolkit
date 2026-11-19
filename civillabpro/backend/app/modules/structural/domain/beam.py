"""Rectangular reinforced concrete beam to IS 456:2000 (limit state method).

Scope: simply supported beams and cantilevers of rectangular, T or L section
under a uniformly distributed load, or under factored forces from an external
analysis (with optional torsion). The engine selects the bars, checks flexure,
shear, torsion, deflection (span/depth), lateral stability and detailing rules,
and returns a calculation sheet in which every line cites its clause.

Flanged sections (version 1.1): the effective width of Cl. 23.1.2, flexure by
Annex G-2 when the flange is in compression (a rectangle of the web width when
it is in tension, as over a cantilever's support), shear on the web (Cl. 40.1),
Fig. 6 for deflection, and the self-weight of the rib below the slab.

Worked example (the defaults): 230 x 450 beam, 4.0 m clear span on 230 mm
supports, M25 / Fe 500, moderate exposure, DL 12 kN/m + LL 8 kN/m. Expected:
wu = 33.881 kN/m, l = 4230 mm, Mu = 75.78 kN m, Vu = 54.07 kN, Ast,req = 481 mm2,
3-T16 bottom, 2-T12 top, T8 2-legged at 300 c/c, steel 36.3 kg.
tests/handcheck/check_beam.py reproduces these figures independently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engineering import is456
from app.engineering.is456 import FlangeKind, FlexureDesign, MomentCapacity
from app.engineering.rebar import MAIN_BAR_DIAMETERS, BarGroup, bar_area
from app.engineering.trace import CalcSheet

ELEMENT_TYPE = "beam"
ENGINE_VERSION = "1.1.0"
CODE_BASIS = ("IS 456:2000", "SP 16:1980", "IS 2502:1963")
REF = is456.CODE

Support = Literal["simply_supported", "cantilever"]


def _f(default: Any, title: str, group: str, unit: str = "", show_if: dict[str, Any] | None = None, labels: dict[str, str] | None = None,
       **kw: Any) -> Any:
    """A field with the metadata the schema-driven property grid and the report input table read."""
    extra: dict[str, Any] = {"group": group, "unit": unit}
    if show_if:
        extra["show_if"] = show_if
    if labels:
        extra["labels"] = labels
    return Field(default, title=title, json_schema_extra=extra, **kw)


_LOADS, _FORCES = {"mode": "loads"}, {"mode": "forces"}
_FLANGED: dict[str, Any] = {"section": ["t_beam", "l_beam"]}
SECTION_LABELS = {"rectangular": "Rectangular", "t_beam": "T-beam (slab on both sides)", "l_beam": "L-beam (slab on one side)"}


class BeamInput(BaseModel):
    """Everything the beam engine reads. Lengths in mm, loads in kN/m, moments in kN m."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = _f("B1", "Member mark", "Member", min_length=1, max_length=40)
    support: Support = _f("simply_supported", "Support condition", "Member",
                          labels={"simply_supported": "Simply supported", "cantilever": "Cantilever"})
    clear_span_mm: float = _f(4000, "Clear span", "Geometry", "mm", ge=300, le=30000, description="Clear projection for a cantilever")
    support_width_mm: float = _f(230, "Support width", "Geometry", "mm", ge=100, le=2000, description="Along the span, each support")
    section: Literal["rectangular", "t_beam", "l_beam"] = _f("rectangular", "Section", "Geometry", labels=SECTION_LABELS)
    width_mm: float = _f(230, "Width b", "Geometry", "mm", ge=150, le=2000, description="The web width b_w of a T or L beam")
    depth_mm: float = _f(450, "Overall depth D", "Geometry", "mm", ge=150, le=3000, description="Including the slab for a T or L beam")
    flange_thickness_mm: float = _f(120, "Flange thickness D_f", "Geometry", "mm", _FLANGED, ge=50, le=500, description="The slab thickness")
    flange_width_mm: float = _f(3000, "Flange width available", "Geometry", "mm", _FLANGED, ge=150, le=20000,
                                description="T-beam: spacing of the beams; L-beam: web plus half the clear distance to the next beam")
    isolated_flange: bool = _f(False, "Isolated beam", "Geometry", "", _FLANGED, description="The flange is not part of a continuous slab (Cl. 23.1.2(c), (d))")
    l0_mm: float | None = _f(None, "Distance between points of zero moment l_0", "Geometry", "mm", _FLANGED, gt=0, le=60000,
                             description="Blank: the effective span (Cl. 23.1.2); about 0.7 l for continuous beams")

    fck: Literal[20, 25, 30, 35, 40, 45, 50, 55] = _f(25, "Concrete grade", "Materials", "N/mm2", labels={str(g): f"M{g}" for g in is456.CONCRETE_GRADES})
    fy: Literal[250, 415, 500, 550] = _f(500, "Main steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    fy_stirrup: Literal[250, 415, 500, 550] = _f(500, "Stirrup steel", "Materials", "N/mm2", labels={str(g): f"Fe {g}" for g in is456.STEEL_GRADES})
    exposure: Literal["mild", "moderate", "severe", "very_severe", "extreme"] = _f(
        "moderate", "Exposure", "Materials", labels={"mild": "Mild", "moderate": "Moderate", "severe": "Severe", "very_severe": "Very severe", "extreme": "Extreme"})
    clear_cover_mm: float | None = _f(None, "Cover to stirrups", "Materials", "mm", ge=15, le=100, description="Blank takes IS 456 Table 16")
    max_aggregate_mm: float = _f(20, "Aggregate size", "Materials", "mm", ge=10, le=40)

    mode: Literal["loads", "forces"] = _f("loads", "Input mode", "Loading", labels={"loads": "Loads (UDL)", "forces": "Factored forces"})
    dead_load_kn_m: float = _f(12, "Dead load", "Loading", "kN/m", _LOADS, ge=0, le=5000, description="Characteristic, excluding self-weight")
    live_load_kn_m: float = _f(8, "Imposed load", "Loading", "kN/m", _LOADS, ge=0, le=5000, description="Characteristic")
    include_self_weight: bool = _f(True, "Add self-weight", "Loading", "", _LOADS)
    unit_weight_kn_m3: float = _f(25, "Unit weight of concrete", "Loading", "kN/m3", _LOADS, ge=20, le=30, description="IS 875 (Part 1)")
    load_factor: float = _f(1.5, "Load factor", "Loading", "", _LOADS, ge=1.0, le=2.0, description="On DL + LL, IS 456 Table 18")
    mu_knm: float | None = _f(None, "Moment Mu", "Loading", "kN m", _FORCES, gt=0, le=1e5, description="Factored")
    vu_kn: float | None = _f(None, "Shear Vu", "Loading", "kN", _FORCES, ge=0, le=1e5, description="Factored, at the critical section")
    tu_knm: float = _f(0, "Torsion Tu", "Loading", "kN m", _FORCES, ge=0, le=1e5, description="Factored")

    main_bar_dia_mm: Literal[12, 16, 20, 25, 32] | None = _f(None, "Main bar size", "Reinforcement", "mm", description="Blank lets the engine choose")
    hanger_bar_dia_mm: Literal[10, 12, 16] = _f(12, "Hanger bar size", "Reinforcement", "mm")
    stirrup_dia_mm: Literal[8, 10, 12] = _f(8, "Stirrup size", "Reinforcement", "mm")
    stirrup_legs: Literal[2, 4] = _f(2, "Stirrup legs", "Reinforcement")

    @model_validator(mode="after")
    def _consistent(self) -> BeamInput:
        if self.section != "rectangular":
            if self.flange_thickness_mm > self.depth_mm - 100:
                raise ValueError("The flange must be at least 100 mm thinner than the overall depth of the beam.")
            if self.flange_width_mm <= self.width_mm:
                raise ValueError("The flange width available must be more than the web width.")
        if self.mode == "forces":
            if self.mu_knm is None or self.vu_kn is None:
                raise ValueError("Enter the factored moment and shear, or switch to load input.")
        else:
            if self.tu_knm > 0:
                raise ValueError("Torsion is read only with force input: switch the input mode to forces.")
            if self.dead_load_kn_m + self.live_load_kn_m <= 0 and not self.include_self_weight:
                raise ValueError("Enter a dead or imposed load, or include the self-weight.")
        return self


@dataclass(frozen=True)
class Forces:
    l_eff: float  # mm
    w_self: float  # kN/m
    w_service: float  # kN/m
    w_factored: float  # kN/m
    mu: float  # kN m
    vu_face: float  # kN
    vu: float  # kN at the critical section
    tu: float  # kN m
    ve: float  # kN, equivalent shear (= vu without torsion)
    mt: float  # kN m
    me1: float  # kN m, design moment on the flexural tension face
    me2: float  # kN m, design moment on the other face (torsion only)


@dataclass(frozen=True)
class Arrangement:
    tension: BarGroup
    other: BarGroup  # bars on the opposite face: hangers, compression steel or torsion steel
    d: float  # effective depth to the centroid of the tension steel, mm
    d_c: float  # depth of the other-face steel from its own face, mm
    clear_spacing: float  # clear horizontal distance in the first tension layer, mm
    layer_gap: float  # clear vertical distance between tension layers, mm


def effective_cover(inp: BeamInput) -> float:
    return inp.clear_cover_mm if inp.clear_cover_mm is not None else is456.nominal_cover(inp.exposure)


def compute_forces(inp: BeamInput, d: float) -> Forces:
    """Effective span (Cl. 22.2) and factored design forces for an effective depth ``d``."""
    lc, sw, b, D = inp.clear_span_mm, inp.support_width_mm, inp.width_mm, inp.depth_mm
    cantilever = inp.support == "cantilever"
    l_eff = lc + d / 2.0 if cantilever else min(lc + d, lc + sw)
    rib = D - inp.flange_thickness_mm if inp.section != "rectangular" else D  # a flanged beam's slab is part of the dead load
    w_self = inp.unit_weight_kn_m3 * b * rib * 1e-6 if inp.include_self_weight and inp.mode == "loads" else 0.0
    if inp.mode == "loads":
        w = inp.dead_load_kn_m + w_self + inp.live_load_kn_m
        wu = inp.load_factor * w
        le, lcm, dm = l_eff / 1000.0, lc / 1000.0, d / 1000.0
        if cantilever:
            mu, vu_face = wu * le * le / 2.0, wu * lcm
            vu = vu_face  # face shear kept: the support may be indirect (Cl. 22.6.2.1 not relied on)
        else:
            mu, vu_face = wu * le * le / 8.0, wu * lcm / 2.0
            vu = max(wu * (lcm / 2.0 - dm), 0.0)  # Cl. 22.6.2.1: critical section at d from the face
        tu = 0.0
    else:
        w, wu = 0.0, 0.0
        mu, vu, tu = float(inp.mu_knm or 0.0), float(inp.vu_kn or 0.0), inp.tu_knm
        vu_face = vu
    ve = vu + 1.6 * tu * 1000.0 / b  # Cl. 41.3.1
    mt = tu * (1.0 + D / b) / 1.7  # Cl. 41.4.2
    me1 = mu + mt
    me2 = mt - mu if mt > mu else 0.0  # Cl. 41.4.2.1
    return Forces(l_eff, w_self, w, wu, mu, vu_face, vu, tu, ve, mt, me1, me2)


@dataclass(frozen=True)
class Flange:
    kind: FlangeKind
    df: float  # mm
    b_actual: float  # mm, width available
    l0: float  # mm, distance between points of zero moment
    bf: float  # mm, effective width (Cl. 23.1.2)
    in_compression: bool  # True for sagging (simply supported); a cantilever's flange is in tension


def flange_of(inp: BeamInput, l_eff: float) -> Flange | None:
    """The flange of a T or L beam for an effective span; None for a rectangular beam."""
    if inp.section == "rectangular":
        return None
    kind: FlangeKind = "T" if inp.section == "t_beam" else "L"
    l0 = float(inp.l0_mm) if inp.l0_mm else l_eff
    bf = is456.effective_flange_width(kind, l0, inp.width_mm, inp.flange_thickness_mm, inp.flange_width_mm, inp.isolated_flange)
    return Flange(kind, inp.flange_thickness_mm, inp.flange_width_mm, l0, bf, inp.support != "cantilever")


def flexure_design(inp: BeamInput, fl: Flange | None, md: float, d: float, d_c: float) -> FlexureDesign:
    """Annex G-2 with the flange in compression, otherwise a rectangle of the (web) width (Annex G-1)."""
    fck, fy, b = float(inp.fck), float(inp.fy), inp.width_mm
    if fl is not None and fl.in_compression:
        return is456.design_flanged(md, fck, fy, fl.bf, b, fl.df, d, d_c)
    return is456.design_rectangular(md, fck, fy, b, d, d_c)


def flexure_capacity(inp: BeamInput, fl: Flange | None, d: float, ast: float, asc: float, d_c: float) -> MomentCapacity:
    fck, fy, b = float(inp.fck), float(inp.fy), inp.width_mm
    if fl is not None and fl.in_compression:
        return is456.moment_capacity_flanged(fck, fy, fl.bf, b, fl.df, d, ast, asc, d_c)
    return is456.moment_capacity(fck, fy, b, d, ast, asc, d_c)


def tension_candidates(inp: BeamInput, cover: float) -> list[tuple[BarGroup, float, float, float]]:
    """Bar groups that fit the tension face in one or two layers.

    Returns (group, depth of centroid from the face, clear spacing, layer gap).
    """
    b, dst, agg = inp.width_mm, inp.stirrup_dia_mm, inp.max_aggregate_mm
    inner = b - 2.0 * (cover + dst)
    n_min = 2 if inp.stirrup_legs == 2 else 4
    s_max = is456.max_clear_bar_spacing(inp.fy)
    out: list[tuple[BarGroup, float, float, float]] = []
    dias = (inp.main_bar_dia_mm,) if inp.main_bar_dia_mm else MAIN_BAR_DIAMETERS
    for dia in dias:
        s_h = is456.min_clear_bar_spacing_horizontal(dia, agg)
        s_v = is456.min_clear_bar_spacing_vertical(dia, agg)
        n_layer = int(math.floor((inner + s_h) / (dia + s_h) + 1e-9))
        if n_layer < n_min:
            continue
        for n in range(n_min, 2 * n_layer + 1):
            layers = (n,) if n <= n_layer else (n_layer, n - n_layer)
            if len(layers) == 2 and layers[1] < 2:
                continue
            clear = (inner - layers[0] * dia) / (layers[0] - 1)
            if clear > s_max + 1e-9:
                continue
            y1 = cover + dst + dia / 2.0
            y2 = y1 + dia + s_v
            ybar = y1 if len(layers) == 1 else (layers[0] * y1 + layers[1] * y2) / n
            out.append((BarGroup(dia, layers), ybar, clear, s_v if len(layers) == 2 else 0.0))
    return out


def other_candidates(inp: BeamInput, cover: float) -> list[BarGroup]:
    """Single-layer bar groups for the face opposite the flexural tension face."""
    inner = inp.width_mm - 2.0 * (cover + inp.stirrup_dia_mm)
    n_min = 2 if inp.stirrup_legs == 2 else 4
    dias = sorted({inp.hanger_bar_dia_mm, *[x for x in MAIN_BAR_DIAMETERS if x > inp.hanger_bar_dia_mm]})
    out: list[BarGroup] = []
    for dia in dias:
        s_h = is456.min_clear_bar_spacing_horizontal(dia, inp.max_aggregate_mm)
        n_layer = int(math.floor((inner + s_h) / (dia + s_h) + 1e-9))
        out += [BarGroup(dia, (n,)) for n in range(n_min, n_layer + 1)]
    return out


def select_bars(inp: BeamInput, cover: float) -> tuple[Arrangement, Forces] | None:
    """Least-steel arrangement that meets Annex G, the steel limits of Cl. 26.5.1 and Cl. 38.1(f).

    The effective span, and with it the design forces, depend on the effective
    depth (Cl. 22.2), which depends on the bars. Each candidate is therefore
    judged against the forces computed for its own effective depth, so the
    arrangement returned is consistent without iteration.
    """
    b, D, fck, fy, dst = inp.width_mm, inp.depth_mm, inp.fck, inp.fy, inp.stirrup_dia_mm
    as_max = is456.max_steel(b, D)
    best: tuple[tuple[float, int, int], Arrangement, Forces] | None = None
    others = sorted(other_candidates(inp, cover), key=lambda g: g.area)
    if not others:
        return None
    for ten, ybar, clear, gap in sorted(tension_candidates(inp, cover), key=lambda c: c[0].area):
        if best is not None and ten.area + others[0].area > best[0][0] + 1e-6:
            break  # candidates are in order of area: nothing lighter remains
        d = D - ybar
        if d <= 0:
            continue
        f = compute_forces(inp, d)
        fl = flange_of(inp, f.l_eff)
        md, m2 = f.me1 * 1e6, f.me2 * 1e6
        if ten.area > as_max or ten.area < is456.min_tension_steel(b, d, fy):
            continue
        for oth in others:
            if best is not None and ten.area + oth.area > best[0][0] + 1e-6:
                break
            d_c = cover + dst + oth.dia / 2.0
            if oth.area > as_max or d - d_c <= 0:
                continue
            fd = flexure_design(inp, fl, md, d, d_c)
            if ten.area < fd.ast_req or oth.area < fd.asc_req:
                continue
            cap = flexure_capacity(inp, fl, d, ten.area, oth.area, d_c)
            if cap.limited or cap.mu < md:
                continue
            if m2 > 0:
                d2 = D - d_c
                fl2 = is456.design_rectangular(m2, fck, fy, b, d2, ybar)
                need2 = max(fl2.ast_req, is456.min_tension_steel(b, d2, fy))
                cap2 = is456.moment_capacity(fck, fy, b, d2, oth.area, ten.area, ybar)
                if fl2.doubly or oth.area < need2 or cap2.limited or cap2.mu < m2:
                    continue
            key = (round(ten.area + oth.area, 3), len(ten.layers), ten.count + oth.count)
            if best is None or key < best[0]:
                best = (key, Arrangement(ten, oth, d, d_c, clear, gap), f)
    return (best[1], best[2]) if best else None


def practical_spacing(s: float) -> float:
    """Round a stirrup spacing down to what is set out on site: 25 mm steps from 100 mm, 5 mm steps below."""
    s = min(s, 300.0)
    return math.floor(s / 25.0 + 1e-9) * 25.0 if s >= 100.0 else math.floor(s / 5.0 + 1e-9) * 5.0


def _n(x: float, dp: int = 2) -> str:
    return f"{x:.{dp}f}"


def design_beam(inp: BeamInput) -> dict[str, Any]:
    """Design the beam and return the full result (see ``DesignResult`` in the API schemas)."""
    from app.modules.structural.domain import beam_detailing  # local import: detailing reads this module's types

    sheet = CalcSheet()
    b, D, fck, fy = inp.width_mm, inp.depth_mm, float(inp.fck), float(inp.fy)
    dst, legs = inp.stirrup_dia_mm, inp.stirrup_legs
    cantilever = inp.support == "cantilever"
    cover = effective_cover(inp)
    fyv = is456.shear_fy(inp.fy_stirrup)
    face_t, face_o = ("top", "bottom") if cantilever else ("bottom", "top")

    # ------------------------------------------------------------------ durability
    sheet.section("1. Materials and durability")
    sheet.step("Input", "Concrete grade", "f_ck", "", fck, "N/mm2", 0)
    sheet.step("Input", "Steel grade of main bars", "f_y", "", fy, "N/mm2", 0)
    sheet.step(f"{REF}, Cl. 40.4", "Steel strength taken for stirrups (not above 415)", "f_yv", f"min({inp.fy_stirrup}, 415)", fyv, "N/mm2", 0)
    sheet.check("grade", f"{REF}, Table 5", f"Minimum grade for {inp.exposure.replace('_', ' ')} exposure",
                "f_ck", fck, ">=", "f_ck,min", is456.min_grade(inp.exposure), "N/mm2", 0, ratio=False)
    sheet.check("cover", f"{REF}, Table 16", "Nominal cover to all reinforcement",
                "c", cover, ">=", "c_nom", is456.nominal_cover(inp.exposure), "mm", 0, ratio=False)

    # ------------------------------------------------------------- bar selection
    d_est = D - cover - dst - (inp.main_bar_dia_mm or 20) / 2.0
    if d_est <= 0.25 * D:
        return _stopped(inp, sheet, "The cover and bar sizes leave too little effective depth: increase the depth of the section.")
    forces = compute_forces(inp, d_est)
    if not cantilever and forces.l_eff / D < 2.0:
        return _stopped(inp, sheet, "Effective span is less than twice the overall depth: this is a deep beam "
                                    "(IS 456:2000, Cl. 29), which this engine does not design.")
    selected = select_bars(inp, cover)
    if selected is None:
        _forces_section(sheet, inp, forces, d_est, cantilever)
        return _stopped(inp, sheet, "No arrangement of up to two layers of bars carries the design moment within the "
                                    "steel limits of Cl. 26.5.1: increase the section, the concrete grade or the bar size.")
    arr, forces = selected
    d, d_c, ten, oth = arr.d, arr.d_c, arr.tension, arr.other
    md = forces.me1 * 1e6
    flg = flange_of(inp, forces.l_eff)
    bw_sym = "b_w" if flg else "b"

    # ---------------------------------------------------------- section and forces
    sheet.section("2. Section and effective depth")
    if flg:
        sheet.step("Input", f"{SECTION_LABELS[inp.section]}: web width, overall depth, flange thickness", "b_w x D, D_f", "",
                   f"{_n(b, 0)} x {_n(D, 0)}, {_n(flg.df, 0)}", "mm")
        flange_steps(sheet, inp, flg, forces.l_eff)
    else:
        sheet.step("Input", "Width and overall depth", "b x D", "", f"{_n(b, 0)} x {_n(D, 0)}", "mm")
    sheet.step(f"{REF}, Table 16", "Cover to stirrups", "c", "", cover, "mm", 0)
    if len(ten.layers) == 1:
        sheet.step("Geometry", f"Effective depth to the {face_t} steel", "d = D - c - d_st - d_b/2",
                   f"{_n(D, 0)} - {_n(cover, 0)} - {dst} - {ten.dia}/2", d, "mm", 1)
    else:
        sheet.step("Geometry", f"Effective depth to the centroid of the {face_t} steel ({ten.layers[0]} + {ten.layers[1]} bars, "
                   f"{_n(arr.layer_gap, 0)} mm clear between layers)", "d = D - y", "", d, "mm", 1)
    sheet.step("Geometry", f"Depth of the {face_o} steel from its face", "d' = c + d_st + d_b'/2",
               f"{_n(cover, 0)} + {dst} + {oth.dia}/2", d_c, "mm", 1)

    _forces_section(sheet, inp, forces, d, cantilever)

    # ------------------------------------------------------------------- flexure
    sheet.section("4. Flexure")
    fl = flexure_design(inp, flg, md, d, d_c)
    flanged_comp = flg is not None and flg.in_compression
    xr = is456.xu_max_ratio(fy)
    sheet.step(f"{REF}, Cl. 38.1(f)", "Limiting neutral-axis depth", "x_u,max = d x 0.0035 / (0.0055 + 0.87 f_y/E_s)", f"{_n(xr, 3)} x {_n(d, 1)}", fl.xu_max, "mm", 1)
    if flanged_comp:
        assert flg is not None
        flanged_flexure_steps(sheet, flg, fl, md, fck, fy, b, d)
    else:
        if flg is not None:
            sheet.step(f"{REF}, Annex G-1", "The flange is on the tension face (hogging): the section acts as a rectangle of the web width",
                       "b = b_w", "", b, "mm", 0)
        sheet.step(f"{REF}, Annex G-1.1(c)", "Limiting moment of resistance", "M_u,lim = 0.36 f_ck b x_u,max (d - 0.42 x_u,max)",
                   f"0.36 x {_n(fck, 0)} x {_n(b, 0)} x {_n(fl.xu_max, 1)} x ({_n(d, 1)} - 0.42 x {_n(fl.xu_max, 1)})",
                   fl.mu_lim / 1e6, "kN m")
    if flanged_comp:
        pass  # steel steps written by flanged_flexure_steps
    elif not fl.doubly:
        sheet.step(f"{REF}, Annex G-1.1(b)", "Singly reinforced: steel required",
                   "A_st = 0.5 (f_ck/f_y) [1 - sqrt(1 - 4.6 M_u / (f_ck b d^2))] b d",
                   f"0.5 x ({_n(fck, 0)}/{_n(fy, 0)}) x [1 - sqrt(1 - 4.6 x {_n(md / 1e6)} x 10^6 / ({_n(fck, 0)} x {_n(b, 0)} x {_n(d, 1)}^2))] x {_n(b, 0)} x {_n(d, 1)}",
                   fl.ast_req, "mm2", 0)
    else:
        sheet.step(f"{REF}, Annex G-1.2", "M_u exceeds M_u,lim: doubly reinforced. Steel balancing the concrete",
                   "A_st1 = 0.36 f_ck b x_u,max / (0.87 f_y)", f"0.36 x {_n(fck, 0)} x {_n(b, 0)} x {_n(fl.xu_max, 1)} / (0.87 x {_n(fy, 0)})",
                   fl.ast_lim, "mm2", 0)
        sheet.step(f"{REF}, Cl. 38.1(b)", "Strain in the compression steel", "eps_sc = 0.0035 (1 - d'/x_u,max)",
                   f"0.0035 x (1 - {_n(d_c, 1)}/{_n(fl.xu_max, 1)})", fl.eps_sc, "", 5)
        sheet.step(f"{REF}, Fig. 23", "Stress in the compression steel at that strain", "f_sc", "", fl.fsc, "N/mm2", 1)
        sheet.step("SP 16:1980, Cl. 2.3.2", "Compression steel required (concrete displaced deducted, f_cc = 0.446 f_ck)",
                   "A_sc = (M_u - M_u,lim) / [(f_sc - f_cc)(d - d')]",
                   f"({_n(md / 1e6)} - {_n(fl.mu_lim / 1e6)}) x 10^6 / [({_n(fl.fsc, 1)} - {_n(fl.fcc, 2)}) x ({_n(d, 1)} - {_n(d_c, 1)})]",
                   fl.asc_req, "mm2", 0)
        sheet.step(f"{REF}, Annex G-1.2", "Tension steel required", "A_st = A_st1 + A_sc (f_sc - f_cc) / (0.87 f_y)",
                   f"{_n(fl.ast_lim, 0)} + {_n(fl.asc_req, 0)} x ({_n(fl.fsc, 1)} - {_n(fl.fcc, 2)}) / (0.87 x {_n(fy, 0)})",
                   fl.ast_req, "mm2", 0)
    ast_min = is456.min_tension_steel(b, d, fy)
    as_max = is456.max_steel(b, D)
    sheet.step(f"{REF}, Cl. 26.5.1.1(a)", "Minimum tension steel" + (" (web width for a flanged beam)" if flg else ""),
               f"A_s,min = 0.85 {bw_sym} d / f_y", f"0.85 x {_n(b, 0)} x {_n(d, 1)} / {_n(fy, 0)}", ast_min, "mm2", 0)
    sheet.step("Selected", f"{face_t.capitalize()} bars provided", "", ten.label(), ten.area, "mm2", 0)
    sheet.step("Selected", f"{face_o.capitalize()} bars provided", "", oth.label(), oth.area, "mm2", 0)
    sheet.check("ast", f"{REF}, Annex G", "Tension steel provided", "A_st,req", max(fl.ast_req, ast_min), "<=", "A_st,prov", ten.area, "mm2", 0)
    if fl.doubly:
        sheet.check("asc", f"{REF}, Annex G-1.2", "Compression steel provided", "A_sc,req", fl.asc_req, "<=", "A_sc,prov", oth.area, "mm2", 0)
    sheet.check("ast_max", f"{REF}, Cl. 26.5.1.1(b)", f"Maximum tension steel (0.04 {bw_sym} D)", "A_st,prov", ten.area, "<=", f"0.04 {bw_sym} D",
                as_max, "mm2", 0)
    cap = flexure_capacity(inp, flg, d, ten.area, oth.area, d_c)
    sheet.step(f"{REF}, Cl. 38.1", "Neutral-axis depth with the bars provided (equilibrium, compression steel stress from its strain)",
               "x_u", "", cap.xu, "mm", 1)
    sheet.check("ductility", f"{REF}, Cl. 38.1(f)", "Section under-reinforced as detailed", "x_u", cap.xu, "<=", "x_u,max", fl.xu_max, "mm", 1)
    sheet.check("moment", f"{REF}, Cl. 38.1", "Moment of resistance as detailed", "M_u", md / 1e6, "<=", "M_u,R", cap.mu / 1e6, "kN m")

    ast2_req = 0.0
    if forces.me2 > 0:
        d2 = D - d_c
        ybar = D - d
        fl2 = is456.design_rectangular(forces.me2 * 1e6, fck, fy, b, d2, ybar)
        ast2_req = max(fl2.ast_req, is456.min_tension_steel(b, d2, fy))
        cap2 = is456.moment_capacity(fck, fy, b, d2, oth.area, ten.area, ybar)
        sheet.step(f"{REF}, Cl. 41.4.2.1", f"M_t exceeds M_u: steel required on the {face_o} face for M_e2", "A_st2", "", ast2_req, "mm2", 0)
        sheet.check("me2", f"{REF}, Cl. 41.4.2.1", f"Moment of resistance for M_e2 ({face_o} face in tension)",
                    "M_e2", forces.me2, "<=", "M_u,R2", cap2.mu / 1e6, "kN m")

    # --------------------------------------------------------------------- shear
    sheet.section("5. Shear" + (" and torsion" if forces.tu > 0 else ""))
    v_design = forces.ve
    tau_v = v_design * 1e3 / (b * d)
    pt = 100.0 * ten.area / (b * d)
    tc = is456.tau_c(fck, pt)
    tc_max = is456.tau_c_max(fck)
    asv = legs * bar_area(dst)
    if forces.tu > 0:
        sheet.step(f"{REF}, Cl. 41.3.1", "Equivalent nominal shear stress", "tau_ve = V_e / (b d)",
                   f"{_n(v_design)} x 10^3 / ({_n(b, 0)} x {_n(d, 1)})", tau_v, "N/mm2", 3)
    else:
        sheet.step(f"{REF}, Cl. 40.1", "Nominal shear stress" + (" on the web" if flg else ""), f"tau_v = V_u / ({bw_sym} d)",
                   f"{_n(v_design)} x 10^3 / ({_n(b, 0)} x {_n(d, 1)})", tau_v, "N/mm2", 3)
    sheet.step(f"{REF}, Table 19", "Tension steel at the section", f"p_t = 100 A_st / ({bw_sym} d)",
               f"100 x {_n(ten.area, 0)} / ({_n(b, 0)} x {_n(d, 1)})", pt, "%", 3)
    sheet.step(f"{REF}, Table 19", "Design shear strength of concrete (interpolated)", "tau_c", "", tc, "N/mm2", 3)
    sheet.check("tau_max", f"{REF}, Table 20", "Maximum shear stress", "tau_v", tau_v, "<=", "tau_c,max", tc_max, "N/mm2", 3)

    limits: dict[str, float] = {}
    limits["minimum shear steel, Cl. 26.5.1.6"] = is456.stirrup_spacing_minimum_steel(fyv, asv, b)
    limits["0.75 d, Cl. 26.5.1.5"] = 0.75 * d
    limits["300 mm, Cl. 26.5.1.5"] = 300.0
    vuc = tc * b * d / 1e3  # kN
    vus = max(v_design - vuc, 0.0)
    if vus > 0:
        limits["shear strength, Cl. 40.4(a)"] = is456.stirrup_spacing_for_shear(vus * 1e3, fyv, asv, d)
        sheet.step(f"{REF}, Cl. 40.4", "Shear carried by stirrups", "V_us = V_u - tau_c b d",
                   f"{_n(v_design)} - {_n(tc, 3)} x {_n(b, 0)} x {_n(d, 1)} / 10^3", vus, "kN")
        sheet.step(f"{REF}, Cl. 40.4(a)", f"Spacing of {legs}-legged T{dst} stirrups for V_us", "s_v = 0.87 f_yv A_sv d / V_us",
                   f"0.87 x {_n(fyv, 0)} x {_n(asv, 1)} x {_n(d, 1)} / ({_n(vus)} x 10^3)", limits["shear strength, Cl. 40.4(a)"], "mm", 0)
    else:
        sheet.step(f"{REF}, Cl. 40.3", "tau_v does not exceed tau_c: minimum shear reinforcement governs", "V_us", "", 0.0, "kN")
    sheet.step(f"{REF}, Cl. 26.5.1.6", "Spacing for minimum shear reinforcement", "s_v = 0.87 f_yv A_sv / (0.4 b)",
               f"0.87 x {_n(fyv, 0)} x {_n(asv, 1)} / (0.4 x {_n(b, 0)})", limits["minimum shear steel, Cl. 26.5.1.6"], "mm", 0)
    sheet.step(f"{REF}, Cl. 26.5.1.5", "Maximum spacing of vertical stirrups", "min(0.75 d, 300)", f"min({_n(0.75 * d, 0)}, 300)",
               min(0.75 * d, 300.0), "mm", 0)

    if forces.tu > 0:
        cx = cover + dst + ten.dia / 2.0
        b1 = b - 2.0 * cx  # centre to centre of corner bars across the width
        d1 = D - (cover + dst + ten.dia / 2.0) - d_c  # centre to centre of corner bars down the depth
        x1, y1 = b - 2.0 * cover - dst, D - 2.0 * cover - dst  # stirrup centre-line dimensions
        asv_t = 2.0 * bar_area(dst)  # only the outer closed hoop resists torsion
        sheet.step(f"{REF}, Cl. 41.4.3", "Centre-to-centre distances of the corner bars", "b_1, d_1", "", f"{_n(b1, 0)}, {_n(d1, 0)}", "mm")
        if tau_v > tc:
            s_t = 0.87 * fyv * asv_t / (forces.tu * 1e6 / (b1 * d1) + forces.vu * 1e3 / (2.5 * d1))
            s_e = 0.87 * fyv * asv_t / ((tau_v - tc) * b)
            limits["torsion and shear, Cl. 41.4.3"] = s_t
            limits["(tau_ve - tau_c) b s_v, Cl. 41.4.3"] = s_e
            sheet.step(f"{REF}, Cl. 41.4.3", "Hoop spacing for torsion with shear (outer two legs)",
                       "s_v = 0.87 f_yv A_sv / [T_u/(b_1 d_1) + V_u/(2.5 d_1)]",
                       f"0.87 x {_n(fyv, 0)} x {_n(asv_t, 1)} / [{_n(forces.tu)} x 10^6/({_n(b1, 0)} x {_n(d1, 0)}) + {_n(forces.vu)} x 10^3/(2.5 x {_n(d1, 0)})]",
                       s_t, "mm", 0)
            sheet.step(f"{REF}, Cl. 41.4.3", "Hoop spacing for the total transverse steel", "s_v = 0.87 f_yv A_sv / [(tau_ve - tau_c) b]",
                       f"0.87 x {_n(fyv, 0)} x {_n(asv_t, 1)} / [({_n(tau_v, 3)} - {_n(tc, 3)}) x {_n(b, 0)}]", s_e, "mm", 0)
        limits["x_1, Cl. 26.5.1.7(a)"] = x1
        limits["(x_1 + y_1)/4, Cl. 26.5.1.7(a)"] = (x1 + y1) / 4.0
        sheet.step(f"{REF}, Cl. 26.5.1.7(a)", "Hoop spacing limits with torsion", "min(x_1, (x_1 + y_1)/4, 300)",
                   f"min({_n(x1, 0)}, {_n((x1 + y1) / 4.0, 0)}, 300)", min(x1, (x1 + y1) / 4.0, 300.0), "mm", 0)

    governing = min(limits, key=lambda k: limits[k])
    sv_allow = limits[governing]
    sv = practical_spacing(sv_allow)
    sheet.step("Selected", f"Stirrups provided: {legs}-legged T{dst} (governed by {governing})", "s_v", "", sv, "mm", 0)
    sheet.check("sv", f"{REF}, Cl. 26.5.1.5 and 40.4", "Stirrup spacing provided", "s_v", sv, "<=", "s_v,allow", sv_allow, "mm", 0, ratio=False)
    sheet.check("sv_min", "Practice", "Stirrup spacing workable on site (75 mm or more)", "s_v", sv, ">=", "s_v,min", 75.0, "mm", 0, ratio=False)
    if sv > 0:
        vur = vuc + 0.87 * fyv * asv * d / sv / 1e3
        sheet.check("shear", f"{REF}, Cl. 40.4", "Shear resistance with the stirrups provided", "V_u", v_design, "<=", "V_u,R", vur, "kN")
    if sv < 75.0:
        sheet.flag("error", "Stirrup spacing is below 75 mm: use four-legged or larger stirrups, or a larger section.", f"{REF}, Cl. 40.4")

    # ---------------------------------------------------------------- deflection
    sheet.section("6. Deflection control (span to effective depth)")
    basic = is456.BASIC_SPAN_DEPTH[inp.support]
    le_m = forces.l_eff / 1000.0
    span_factor = 10.0 / le_m if (le_m > 10.0 and not cantilever) else 1.0
    fs = is456.service_steel_stress(fy, fl.ast_req, ten.area)
    b_defl = flg.bf if flanged_comp and flg else b  # Cl. 23.2.1(e): steel percentages on b_f d for flanged beams
    pt_defl = 100.0 * ten.area / (b_defl * d)
    kt = is456.tension_modification_factor(fs, pt_defl)
    pc = 100.0 * oth.area / (b_defl * d) if fl.doubly else 0.0
    kc = is456.compression_modification_factor(pc)
    kf = is456.flanged_reduction_factor(b / flg.bf) if flg else 1.0
    allow = basic * span_factor * kt * kc * kf
    sheet.step(f"{REF}, Cl. 23.2.1(a)", f"Basic span to effective depth ratio ({inp.support.replace('_', ' ')})", "", "", basic, "", 0)
    if span_factor != 1.0:
        sheet.step(f"{REF}, Cl. 23.2.1(b)", "Reduction for spans above 10 m", "10 / l", f"10 / {_n(le_m)}", span_factor, "", 3)
    sheet.step(f"{REF}, Fig. 4", "Steel stress at service", "f_s = 0.58 f_y A_st,req / A_st,prov",
               f"0.58 x {_n(fy, 0)} x {_n(fl.ast_req, 0)} / {_n(ten.area, 0)}", fs, "N/mm2", 1)
    if flg:
        sheet.step(f"{REF}, Cl. 23.2.1(e)", "Tension steel for Fig. 4 and 5" + (" on the effective flange width" if flanged_comp else
                   " on the web (the flange is in tension, on the safe side)"), f"p_t = 100 A_st / ({'b_f' if flanged_comp else 'b_w'} d)",
                   f"100 x {_n(ten.area, 0)} / ({_n(b_defl, 0)} x {_n(d, 1)})", pt_defl, "%", 3)
    sheet.step(f"{REF}, Fig. 4", "Modification factor for tension steel", "k_t = 1 / (0.225 + 0.00322 f_s + 0.625 log10 p_t) <= 2",
               f"1 / (0.225 + 0.00322 x {_n(fs, 1)} + 0.625 x log10 {_n(pt_defl, 3)})", kt, "", 3)
    sheet.step(f"{REF}, Fig. 5", "Modification factor for compression steel"
               + ("" if fl.doubly else " (taken as 1.0: the hanger bars are not counted)"),
               "k_c = 1 + p_c / (3 + p_c) <= 1.5", f"p_c = {_n(pc, 3)} %", kc, "", 3)
    if flg:
        sheet.step(f"{REF}, Cl. 23.2.1(e), Fig. 6", "Reduction factor for flanged beams: 0.8 up to b_w/b_f = 0.3, then linear to 1.0",
                   "k_f", f"b_w/b_f = {_n(b, 0)}/{_n(flg.bf, 0)} = {_n(b / flg.bf, 3)}", kf, "", 3)
    sheet.check("deflection", f"{REF}, Cl. 23.2.1", "Span to effective depth ratio", "l/d", forces.l_eff / d, "<=", "allowable", allow, "", 2)
    if cantilever and le_m > 10.0:
        sheet.flag("error", "Cantilever longer than 10 m: the span/depth rule does not apply; calculate the deflection (Cl. 23.2.1(b)).",
                   f"{REF}, Cl. 23.2.1(b)")

    # ----------------------------------------------------------------- detailing
    sheet.section("7. Detailing")
    ld_t = is456.development_length(ten.dia, fck, fy)
    ld_o = is456.development_length(oth.dia, fck, fy, compression=fl.doubly and forces.me2 <= 0)
    sheet.step(f"{REF}, Cl. 26.2.1", f"Development length of T{ten.dia} in tension", "L_d = d_b 0.87 f_y / (4 tau_bd)",
               f"{ten.dia} x 0.87 x {_n(fy, 0)} / (4 x {_n(is456.bond_stress(fck, fy), 2)})", ld_t, "mm", 0)
    sheet.check("cover_bar", f"{REF}, Cl. 26.4.1", "Cover to main bars not less than the bar diameter",
                "c + d_st", cover + dst, ">=", "d_b", float(max(ten.dia, oth.dia)), "mm", 0, ratio=False)
    s_min = is456.min_clear_bar_spacing_horizontal(ten.dia, inp.max_aggregate_mm)
    sheet.check("spacing_min", f"{REF}, Cl. 26.3.2(a)", "Minimum clear distance between tension bars",
                "s", arr.clear_spacing, ">=", "s_min", s_min, "mm", 0, ratio=False)
    sheet.check("spacing_max", f"{REF}, Cl. 26.3.3(a), Table 15", "Maximum clear distance between tension bars (crack control)",
                "s", arr.clear_spacing, "<=", "s_max", is456.max_clear_bar_spacing(fy), "mm", 0)
    if cantilever:
        ls_lim = min(25.0 * b, 100.0 * b * b / d)
        sheet.check("lateral", f"{REF}, Cl. 23.3(b)", "Lateral stability: clear projection not above 25 b or 100 b^2/d",
                    "l", inp.clear_span_mm, "<=", "limit", ls_lim, "mm", 0)
    else:
        bc = flg.bf if flanged_comp and flg else b  # breadth of the compression face
        ls_lim = min(60.0 * bc, 250.0 * bc * bc / d)
        sheet.check("lateral", f"{REF}, Cl. 23.3(a)", "Lateral stability: clear span not above 60 b or 250 b^2/d"
                    + (" (b: the flange, which is the compression face)" if flanged_comp else ""),
                    "l", inp.clear_span_mm, "<=", "limit", ls_lim, "mm", 0)

    side = beam_detailing.side_face_bars(inp, cover, ten, oth, torsion=forces.tu > 0)
    if side:
        sheet.step(f"{REF}, Cl. 26.5.1.3" + (" and 26.5.1.7(b)" if forces.tu > 0 else ""),
                   "Side face reinforcement: 0.1 % of the web area, half on each face, at not more than 300 mm or b",
                   "A_s = 0.001 b D", f"0.001 x {_n(b, 0)} x {_n(D, 0)}", 0.001 * b * D, "mm2", 0)
        sheet.step("Selected", "Side face bars provided on each face", "", f"{side['per_face']}-T{side['dia']}", side["area_total"], "mm2", 0)

    # ------------------------------------------------------------------ assemble
    reinforcement = {
        "tension_face": face_t,
        face_t: {"count": ten.count, "dia": ten.dia, "layers": list(ten.layers), "area": round(ten.area, 1), "label": ten.label()},
        face_o: {"count": oth.count, "dia": oth.dia, "layers": list(oth.layers), "area": round(oth.area, 1), "label": oth.label()},
        "stirrups": {"dia": dst, "legs": legs, "spacing": sv, "label": f"T{dst} {legs}-legged @ {_n(sv, 0)} c/c"},
        "side_face": side,
        "cover": cover,
        "layer_gap": arr.layer_gap,
        "section": {"kind": inp.section, "bw": b, "D": D} | ({"df": flg.df, "bf": round(flg.bf, 1), "b_actual": flg.b_actual} if flg else {}),
    }
    anch = {"ld_tension": ld_t, "ld_other": ld_o, "other_in_compression": fl.doubly}
    bbs = beam_detailing.bar_schedule(inp, cover, reinforcement, anch, sheet)
    quantities = beam_detailing.quantities(inp, bbs)
    drawing = beam_detailing.drawing(inp, cover, reinforcement, bbs)

    if inp.mode == "loads":
        sheet.flag("info", "Bars run the full length without curtailment and stirrups are at one spacing throughout; "
                           "both are on the safe side.")
    if fl.doubly:
        sheet.flag("info", "The section is doubly reinforced. A deeper section usually costs less steel.")
    if flg:
        sheet.flag("info", "Where the slab spans parallel to this beam, provide transverse bars over the beam, at least 60 percent of the "
                           "slab's mid-span steel, so that the slab acts as the flange.", f"{REF}, Cl. 23.1.1(b)")
        if inp.mode == "loads" and inp.include_self_weight:
            sheet.flag("info", "Self-weight is the rib below the slab; the slab's own weight belongs in the dead load entered.")
        if not flg.in_compression:
            sheet.flag("info", "The flange is in tension at the support of a cantilever, so it adds no strength; the web is designed "
                               "as a rectangle.")

    checks = sheet.checks()
    utils = [c.util for c in checks if c.util is not None]
    ok = sheet.all_ok() and not any(f.level == "error" for f in sheet.flags)
    key_results = [
        {"label": "Design moment", "sym": "M_u", "value": round(md / 1e6, 2), "unit": "kN m", "dp": 2},
        {"label": "Design shear", "sym": "V_u", "value": round(v_design, 2), "unit": "kN", "dp": 2},
        *([{"label": "Effective flange width", "sym": "b_f", "value": round(flg.bf, 0), "unit": "mm", "dp": 0}] if flg else []),
        {"label": "Tension steel required", "sym": "A_st,req", "value": round(max(fl.ast_req, ast_min), 0), "unit": "mm2", "dp": 0},
        {"label": f"{face_t.capitalize()} bars", "sym": "", "value": ten.label(), "unit": "", "dp": 0},
        {"label": f"{face_o.capitalize()} bars", "sym": "", "value": oth.label(), "unit": "", "dp": 0},
        {"label": "Stirrups", "sym": "", "value": reinforcement["stirrups"]["label"], "unit": "", "dp": 0},
        {"label": "Steel", "sym": "", "value": quantities["steel_kg"], "unit": "kg", "dp": 1},
        {"label": "Concrete", "sym": "", "value": quantities["concrete_m3"], "unit": "m3", "dp": 3},
    ]
    return {
        "element_type": ELEMENT_TYPE,
        "engine_version": ENGINE_VERSION,
        "code_basis": list(CODE_BASIS),
        "status": "ok" if ok else "not_ok",
        "stop_message": None,
        "checks_passed": sum(1 for c in checks if c.ok),
        "checks_total": len(checks),
        "max_utilisation": max(utils) if utils else None,
        "key_results": key_results,
        "data": {
            "cover": cover, "d": round(d, 2), "d_c": round(d_c, 2), "l_eff": round(forces.l_eff, 1),
            "w_self": round(forces.w_self, 4), "w_service": round(forces.w_service, 4), "w_factored": round(forces.w_factored, 4),
            "mu": round(forces.mu, 4), "vu_face": round(forces.vu_face, 4), "vu": round(forces.vu, 4), "tu": forces.tu,
            "ve": round(forces.ve, 4), "me1": round(forces.me1, 4), "me2": round(forces.me2, 4),
            "mu_lim": round(fl.mu_lim / 1e6, 4), "doubly": fl.doubly,
            "ast_req": round(fl.ast_req, 2), "asc_req": round(fl.asc_req, 2), "ast_min": round(ast_min, 2), "ast2_req": round(ast2_req, 2),
            "ast_prov": round(ten.area, 2), "asc_prov": round(oth.area, 2),
            "mu_capacity": round(cap.mu / 1e6, 4), "xu": round(cap.xu, 3), "xu_max": round(fl.xu_max, 3),
            "tau_v": round(tau_v, 5), "pt": round(pt, 5), "tau_c": round(tc, 5), "tau_c_max": tc_max, "vus": round(vus, 4),
            "sv_allow": round(sv_allow, 2), "sv": sv, "sv_governing": governing,
            "span_depth": round(forces.l_eff / d, 4), "span_depth_allow": round(allow, 4), "fs": round(fs, 3), "kt": round(kt, 5), "kc": round(kc, 5),
            "ld_tension": round(ld_t, 1),
            "section": inp.section, "bf": round(flg.bf, 2) if flg else None, "l0": round(flg.l0, 1) if flg else None,
            "na_in_flange": fl.na_in_flange, "pt_defl": round(pt_defl, 5), "kf": round(kf, 5),
        },
        "reinforcement": reinforcement,
        "sheet": sheet.to_dict(),
        "bbs": bbs,
        "quantities": quantities,
        "drawing": drawing,
    }


def _forces_section(sheet: CalcSheet, inp: BeamInput, f: Forces, d: float, cantilever: bool) -> None:
    lc, sw = inp.clear_span_mm, inp.support_width_mm
    sheet.section("3. Effective span and design forces")
    if cantilever:
        sheet.step(f"{REF}, Cl. 22.2(c)", "Effective length of the cantilever", "l = l_c + d/2", f"{_n(lc, 0)} + {_n(d, 1)}/2", f.l_eff, "mm", 0)
    else:
        sheet.step(f"{REF}, Cl. 22.2(a)", "Effective span: clear span + d, or centre to centre of supports, whichever is less",
                   "l = min(l_c + d, l_c + w_s)", f"min({_n(lc, 0)} + {_n(d, 1)}, {_n(lc, 0)} + {_n(sw, 0)})", f.l_eff, "mm", 0)
    if inp.mode == "loads":
        if inp.include_self_weight and inp.section != "rectangular":
            sheet.step("IS 875 (Part 1):1987", "Self-weight of the rib below the slab", "w_sw = gamma b_w (D - D_f)",
                       f"{_n(inp.unit_weight_kn_m3, 0)} x {_n(inp.width_mm / 1000, 3)} x ({_n(inp.depth_mm / 1000, 3)} - "
                       f"{_n(inp.flange_thickness_mm / 1000, 3)})", f.w_self, "kN/m", 3)
        elif inp.include_self_weight:
            sheet.step("IS 875 (Part 1):1987", "Self-weight", "w_sw = gamma b D",
                       f"{_n(inp.unit_weight_kn_m3, 0)} x {_n(inp.width_mm / 1000, 3)} x {_n(inp.depth_mm / 1000, 3)}", f.w_self, "kN/m", 3)
        sheet.step("Input", "Characteristic load", "w = DL + w_sw + LL",
                   f"{_n(inp.dead_load_kn_m)} + {_n(f.w_self, 3)} + {_n(inp.live_load_kn_m)}", f.w_service, "kN/m", 3)
        sheet.step(f"{REF}, Table 18", "Factored load", "w_u = gamma_f w", f"{_n(inp.load_factor)} x {_n(f.w_service, 3)}", f.w_factored, "kN/m", 3)
        le = f.l_eff / 1000.0
        if cantilever:
            sheet.step("Statics", "Factored moment at the support", "M_u = w_u l^2 / 2", f"{_n(f.w_factored, 3)} x {_n(le, 3)}^2 / 2", f.mu, "kN m")
            sheet.step("Statics", "Factored shear at the face of the support", "V_u = w_u l_c",
                       f"{_n(f.w_factored, 3)} x {_n(lc / 1000, 3)}", f.vu, "kN")
        else:
            sheet.step("Statics", "Factored moment at midspan", "M_u = w_u l^2 / 8", f"{_n(f.w_factored, 3)} x {_n(le, 3)}^2 / 8", f.mu, "kN m")
            sheet.step(f"{REF}, Cl. 22.6.2.1", "Factored shear at d from the face of the support", "V_u = w_u (l_c/2 - d)",
                       f"{_n(f.w_factored, 3)} x ({_n(lc / 2000, 3)} - {_n(d / 1000, 3)})", f.vu, "kN")
    else:
        sheet.step("Input", "Factored bending moment", "M_u", "", f.mu, "kN m")
        sheet.step("Input", "Factored shear at the critical section", "V_u", "", f.vu, "kN")
        if f.tu > 0:
            sheet.step("Input", "Factored torsion", "T_u", "", f.tu, "kN m")
            sheet.step(f"{REF}, Cl. 41.3.1", "Equivalent shear", "V_e = V_u + 1.6 T_u / b",
                       f"{_n(f.vu)} + 1.6 x {_n(f.tu)} / {_n(inp.width_mm / 1000, 3)}", f.ve, "kN")
            sheet.step(f"{REF}, Cl. 41.4.2", "Moment from torsion", "M_t = T_u (1 + D/b) / 1.7",
                       f"{_n(f.tu)} x (1 + {_n(inp.depth_mm, 0)}/{_n(inp.width_mm, 0)}) / 1.7", f.mt, "kN m")
            sheet.step(f"{REF}, Cl. 41.4.2", "Equivalent bending moment", "M_e1 = M_u + M_t", f"{_n(f.mu)} + {_n(f.mt)}", f.me1, "kN m")
            if f.me2 > 0:
                sheet.step(f"{REF}, Cl. 41.4.2.1", "Moment on the opposite face", "M_e2 = M_t - M_u", f"{_n(f.mt)} - {_n(f.mu)}", f.me2, "kN m")


_WIDTH_RULE = {
    ("T", False): ("Cl. 23.1.2(a)", "b_f = l_0/6 + b_w + 6 D_f"),
    ("L", False): ("Cl. 23.1.2(b)", "b_f = l_0/12 + b_w + 3 D_f"),
    ("T", True): ("Cl. 23.1.2(c)", "b_f = l_0/(l_0/b + 4) + b_w"),
    ("L", True): ("Cl. 23.1.2(d)", "b_f = 0.5 l_0/(l_0/b + 4) + b_w"),
}


def flange_steps(sheet: CalcSheet, inp: Any, flg: Flange, l_eff: float, continuous: bool = False) -> None:
    """Steps for l_0 and the effective flange width (Cl. 23.1.2). ``inp`` is any beam input with the flange fields."""
    bw, df, b_act, l0 = inp.width_mm, flg.df, flg.b_actual, flg.l0
    if inp.l0_mm:
        sheet.step("Input", "Distance between points of zero moment", "l_0", "", l0, "mm", 0)
    elif continuous:
        sheet.step(f"{REF}, Cl. 23.1.2, note", "Distance between points of zero moment: 0.7 times the effective span of a continuous beam",
                   "l_0 = 0.7 l", f"0.7 x {_n(l_eff, 0)}", l0, "mm", 0)
    else:
        sheet.step(f"{REF}, Cl. 23.1.2", "Distance between points of zero moment: the effective span"
                   + (" (the flange is in tension; used only for Fig. 6)" if not flg.in_compression else ""), "l_0 = l", "", l0, "mm", 0)
    clause, eq = _WIDTH_RULE[(flg.kind, inp.isolated_flange)]
    if inp.isolated_flange:
        k = 1.0 if flg.kind == "T" else 0.5
        raw = k * l0 / (l0 / b_act + 4.0) + bw
        sub = f"{'' if k == 1 else '0.5 x '}{_n(l0, 0)}/({_n(l0, 0)}/{_n(b_act, 0)} + 4) + {_n(bw, 0)}"
    elif flg.kind == "T":
        raw, sub = l0 / 6.0 + bw + 6.0 * df, f"{_n(l0, 0)}/6 + {_n(bw, 0)} + 6 x {_n(df, 0)}"
    else:
        raw, sub = l0 / 12.0 + bw + 3.0 * df, f"{_n(l0, 0)}/12 + {_n(bw, 0)} + 3 x {_n(df, 0)}"
    sheet.step(f"{REF}, {clause}", "Effective width of the flange", eq, sub, raw, "mm", 0)
    sheet.step(f"{REF}, Cl. 23.1.2", "Not more than the width available", "b_f = min(b_f, b)", f"min({_n(raw, 0)}, {_n(b_act, 0)})", flg.bf, "mm", 0)


def flanged_flexure_steps(sheet: CalcSheet, flg: Flange, fl: FlexureDesign, md: float, fck: float, fy: float, bw: float, d: float) -> None:
    bf, df = flg.bf, flg.df
    mu_f = 0.36 * fck * bf * df * (d - 0.42 * df)
    xm = fl.xu_max
    yf_m = is456.flange_depth_yf(xm, df)
    if df >= xm:
        sheet.step(f"{REF}, Annex G-2.1", "D_f is not less than x_u,max: the neutral axis stays in the flange; a rectangle b_f wide",
                   "M_u,lim = 0.36 f_ck b_f x_u,max (d - 0.42 x_u,max)", "", fl.mu_lim / 1e6, "kN m")
    else:
        g = "G-2.2.1" if yf_m >= df - 1e-9 else "G-2.2.2"
        sub_yf = "" if g == "G-2.2.1" else f"y_f = 0.15 x {_n(xm, 1)} + 0.65 x {_n(df, 0)} = {_n(yf_m, 1)}; "
        sheet.step(f"{REF}, Annex {g}", "Limiting moment of the flanged section (y_f = D_f while D_f <= 3/7 x_u,max, else 0.15 x_u + 0.65 D_f)",
                   "M_u,lim = 0.36 f_ck b_w x_u,max (d - 0.42 x_u,max) + 0.45 f_ck (b_f - b_w) y_f (d - y_f/2)",
                   f"{sub_yf}0.36 x {_n(fck, 0)} x {_n(bw, 0)} x {_n(xm, 1)} x ({_n(d, 1)} - 0.42 x {_n(xm, 1)}) + 0.45 x {_n(fck, 0)} x "
                   f"({_n(bf, 0)} - {_n(bw, 0)}) x {_n(yf_m, 1)} x ({_n(d, 1)} - {_n(yf_m, 1)}/2)", fl.mu_lim / 1e6, "kN m")
        sheet.step(f"{REF}, Annex G-2.1", "Moment with the neutral axis at the underside of the flange", "M_u,f = 0.36 f_ck b_f D_f (d - 0.42 D_f)",
                   f"0.36 x {_n(fck, 0)} x {_n(bf, 0)} x {_n(df, 0)} x ({_n(d, 1)} - 0.42 x {_n(df, 0)})", mu_f / 1e6, "kN m")
    if fl.doubly:
        sheet.step(f"{REF}, Annex G-2.2", "M_u exceeds M_u,lim: doubly reinforced. Steel balancing the concrete at x_u,max",
                   "A_st1 = C(x_u,max) / (0.87 f_y)", "", fl.ast_lim, "mm2", 0)
        sheet.step(f"{REF}, Cl. 38.1(b)", "Strain in the compression steel", "eps_sc = 0.0035 (1 - d'/x_u,max)", "", fl.eps_sc, "", 5)
        sheet.step(f"{REF}, Fig. 23", "Stress in the compression steel at that strain", "f_sc", "", fl.fsc, "N/mm2", 1)
        sheet.step("SP 16:1980, Cl. 2.3.2", "Compression steel required (concrete displaced deducted, f_cc = 0.446 f_ck)",
                   "A_sc = (M_u - M_u,lim) / [(f_sc - f_cc)(d - d')]", "", fl.asc_req, "mm2", 0)
        sheet.step(f"{REF}, Annex G-1.2", "Tension steel required", "A_st = A_st1 + A_sc (f_sc - f_cc) / (0.87 f_y)", "", fl.ast_req, "mm2", 0)
    elif fl.na_in_flange:
        sheet.step(f"{REF}, Annex G-2.1", "M_u <= M_u,f: the neutral axis lies in the flange; singly reinforced rectangle b_f x d",
                   "A_st = 0.5 (f_ck/f_y) [1 - sqrt(1 - 4.6 M_u / (f_ck b_f d^2))] b_f d",
                   f"0.5 x ({_n(fck, 0)}/{_n(fy, 0)}) x [1 - sqrt(1 - 4.6 x {_n(md / 1e6)} x 10^6 / ({_n(fck, 0)} x {_n(bf, 0)} x {_n(d, 1)}^2))] "
                   f"x {_n(bf, 0)} x {_n(d, 1)}", fl.ast_req, "mm2", 0)
        sheet.step(f"{REF}, Annex G-2.1", "Neutral-axis depth, within the flange", "x_u = 0.87 f_y A_st / (0.36 f_ck b_f)", "", fl.xu, "mm", 1)
    else:
        yf = is456.flange_depth_yf(fl.xu, df)
        sheet.step(f"{REF}, Annex G-2.2", "M_u,f < M_u <= M_u,lim: the neutral axis lies in the web; x_u from the G-2.2 moment with x_u for x_u,max",
                   "M_u = 0.36 f_ck b_w x_u (d - 0.42 x_u) + 0.45 f_ck (b_f - b_w) y_f (d - y_f/2)", f"y_f = {_n(yf, 1)} mm", fl.xu, "mm", 1)
        sheet.step(f"{REF}, Annex G-2.2", "Tension steel balancing the compression", "A_st = [0.36 f_ck b_w x_u + 0.45 f_ck (b_f - b_w) y_f] / (0.87 f_y)",
                   f"[0.36 x {_n(fck, 0)} x {_n(bw, 0)} x {_n(fl.xu, 1)} + 0.45 x {_n(fck, 0)} x ({_n(bf, 0)} - {_n(bw, 0)}) x {_n(yf, 1)}] / "
                   f"(0.87 x {_n(fy, 0)})", fl.ast_req, "mm2", 0)


def _stopped(inp: BeamInput, sheet: CalcSheet, message: str) -> dict[str, Any]:
    sheet.flag("error", message)
    return {
        "element_type": ELEMENT_TYPE,
        "engine_version": ENGINE_VERSION,
        "code_basis": list(CODE_BASIS),
        "status": "stopped",
        "stop_message": message,
        "checks_passed": sum(1 for c in sheet.checks() if c.ok),
        "checks_total": len(sheet.checks()),
        "max_utilisation": None,
        "key_results": [],
        "data": {},
        "reinforcement": None,
        "sheet": sheet.to_dict(),
        "bbs": None,
        "quantities": None,
        "drawing": None,
    }
