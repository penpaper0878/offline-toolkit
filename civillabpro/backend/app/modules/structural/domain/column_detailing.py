"""Column detailing outputs: bar bending schedule, quantities and drawing for one lift.

A lift runs from the floor to the top of the floor beam above. The main bars start at the
floor and continue through the beam to lap with the next lift. Ties are spaced over the clear
height. Bending deductions follow the same IS 2502:1963 practice as the beam schedule.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight

if TYPE_CHECKING:
    from app.modules.structural.domain.column import ColumnInput

FIRST_TIE_MM = 50.0  # first and last tie from the floor and from the beam soffit


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def tie_count(clear_height: float, pitch: float) -> int:
    return int(math.floor(max(clear_height - 2.0 * FIRST_TIE_MM, 0.0) / pitch + 1e-9)) + 1


def bar_positions(n: int, length: float, edge: float) -> list[float]:
    return [edge + i * (length - 2.0 * edge) / (n - 1) for i in range(n)]


def bar_schedule(inp: ColumnInput, cover: float, reinf: dict[str, Any]) -> dict[str, Any]:
    b, D, lc, hb = inp.width_mm, inp.depth_mm, inp.unsupported_length_mm, inp.beam_depth_mm
    main, ties, cross = reinf["main"], reinf["ties"], reinf["cross_ties"]
    dt, pitch = ties["dia"], ties["spacing"]
    lap = reinf["lap"]
    n_t = tie_count(lc, pitch)
    hook = max(10.0 * dt, 75.0)
    items: list[dict[str, Any]] = []

    def add(desc: str, shape: str, dia: int, count: int, dims: dict[str, float], length: float, formula: str) -> None:
        length = _ceil5(length)
        uw = bar_unit_weight(dia)
        items.append({
            "mark": chr(ord("a") + len(items)), "description": desc, "shape": shape, "dia": dia, "count": count,
            "dims": {k: round(v, 0) for k, v in dims.items()}, "cutting_length_mm": length,
            "total_length_m": round(count * length / 1000.0, 3), "unit_weight_kg_m": round(uw, 4),
            "weight_kg": round(count * length / 1000.0 * uw, 2), "formula": formula,
        })

    run = lc + hb + lap
    add(f"Main bars, {main['label']}", "straight", main["dia"], main["count"], {"A": run}, run, "A = clear height + beam depth + lap")
    a, bb = b - 2.0 * cover, D - 2.0 * cover
    add(f"Ties, T{dt} at {pitch:.0f} c/c", "closed tie, 135 deg hooks", dt, n_t, {"A": a, "B": bb, "hook": hook},
        2.0 * (a + bb) + 2.0 * hook - 12.0 * dt, "2(A + B) + 2 x hook - 3 x 2d - 2 x 3d (three 90 deg and two 135 deg bends)")
    if cross["across_D"]:
        add(f"Cross-ties across D, T{dt} at {pitch:.0f} c/c", "single leg, 135 deg hooks", dt, len(cross["across_D"]) * n_t,
            {"A": bb, "hook": hook}, bb + 2.0 * hook - 6.0 * dt, "A + 2 x hook - 2 x 3d (two 135 deg bends)")
    if cross["across_b"]:
        add(f"Cross-ties across b, T{dt} at {pitch:.0f} c/c", "single leg, 135 deg hooks", dt, len(cross["across_b"]) * n_t,
            {"A": a, "hook": hook}, a + 2.0 * hook - 6.0 * dt, "A + 2 x hook - 2 x 3d (two 135 deg bends)")

    by_dia: dict[int, dict[str, float]] = {}
    for it in items:
        e = by_dia.setdefault(it["dia"], {"length_m": 0.0, "weight_kg": 0.0})
        e["length_m"] += it["total_length_m"]
        e["weight_kg"] += it["weight_kg"]
    summary = [{"dia": k, "length_m": round(v["length_m"], 2), "weight_kg": round(v["weight_kg"], 2)} for k, v in sorted(by_dia.items())]
    return {
        "member": inp.mark,
        "members": 1,
        "items": items,
        "summary": summary,
        "total_weight_kg": round(sum(s["weight_kg"] for s in summary), 2),
        "stirrup_count": n_t,
        "notes": [
            "One lift: main bars from the floor through the floor beam to a compression lap with the next lift (IS 456:2000, Cl. 26.2.5.1).",
            f"Ties over the clear height, the first and last {FIRST_TIE_MM:.0f} mm from the floor and the beam soffit. "
            "Ties through the beam-column joint are not included (IS 13920 detailing is not applied).",
            "Cutting lengths to IS 2502:1963 practice: outside dimensions less 2d per 90 degree bend and 3d per 135 degree bend, rounded up to 5 mm.",
            f"Tie hooks 135 degrees with a {hook:.0f} mm extension (10d, at least 75 mm). Unit mass from 7850 kg/m3; no wastage.",
        ],
    }


def quantities(inp: ColumnInput, bbs: dict[str, Any]) -> dict[str, Any]:
    b, D, lc = inp.width_mm, inp.depth_mm, inp.unsupported_length_mm
    concrete = b * D * lc * 1e-9
    steel = bbs["total_weight_kg"]
    return {
        "length_m": round(lc / 1000.0, 3),
        "concrete_m3": round(concrete, 3),
        "formwork_m2": round(2.0 * (b + D) * lc * 1e-6, 3),
        "steel_kg": round(steel, 1),
        "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Concrete and formwork over the clear height; the joint is measured with the floor beam.",
            "Formwork on all four faces.",
            "Steel from the bar bending schedule, including the lap above.",
        ],
    }


def drawing(inp: ColumnInput, cover: float, reinf: dict[str, Any]) -> dict[str, Any]:
    b, D, lc, hb = inp.width_mm, inp.depth_mm, inp.unsupported_length_mm, inp.beam_depth_mm
    main, ties, cross = reinf["main"], reinf["ties"], reinf["cross_ties"]
    dt, dia, e = ties["dia"], main["dia"], main["edge"]
    model = DrawingModel(f"Column {inp.mark}: reinforcement details")

    # ------------------------------------------------------------ cross-section (b along x, D along y)
    sec = model.view("section", "Section", "to scale")
    th = max(b, D) / 20.0
    sec.rect(0, 0, b, D, "concrete")
    o = cover + dt / 2.0
    r = 2.0 * dt
    sec.polyline([(o + r, o), (b - o - r, o), (b - o, o + r), (b - o, D - o - r), (b - o - r, D - o), (o + r, D - o), (o, D - o - r), (o, o + r)],
                 closed=True, layer="stirrup")
    sec.line(o + r, D - o, o + r + 4 * dt, D - o - 4 * dt, "stirrup")
    sec.line(o, D - o - r, o + 4 * dt, D - o - r - 4 * dt, "stirrup")
    xs = bar_positions(main["n_b"], b, e)
    ys = bar_positions(main["n_d"], D, e)
    for x in xs:
        sec.circle(x, e, dia / 2.0, "rebar")
        sec.circle(x, D - e, dia / 2.0, "rebar")
    for y in ys[1:-1]:
        sec.circle(e, y, dia / 2.0, "rebar")
        sec.circle(b - e, y, dia / 2.0, "rebar")
    for i in cross["across_D"]:
        x = xs[i]
        sec.line(x, o, x, D - o, "stirrup")
        sec.line(x, D - o, x + 3 * dt, D - o - 3 * dt, "stirrup")
        sec.line(x, o, x - 3 * dt, o + 3 * dt, "stirrup")
    for j in cross["across_b"]:
        y = ys[j]
        sec.line(o, y, b - o, y, "stirrup")
        sec.line(o, y, o + 3 * dt, y + 3 * dt, "stirrup")
        sec.line(b - o, y, b - o - 3 * dt, y - 3 * dt, "stirrup")
    # principal axes, marked outside the section so they never hide a cross-tie:
    # M_ux bends about x (horizontal), M_uy about y (vertical)
    ext = 0.18 * max(b, D)
    gap = 0.04 * max(b, D)
    # Marked on the right and at the top only: the left and bottom carry the dimensions.
    sec.line(b + gap, D / 2.0, b + ext, D / 2.0, "centerline")
    sec.line(b / 2.0, D + gap, b / 2.0, D + ext, "centerline")
    sec.text(b + ext + 0.3 * th, D / 2.0 - 0.35 * th, "x", th, "start")
    sec.text(b / 2.0, D + ext + 0.3 * th, "y", th, "middle")
    sec.dim(0, 0, b, 0, -2.4 * th, f"b = {b:.0f}", th)
    sec.dim(0, 0, 0, D, -2.4 * th, f"D = {D:.0f}", th)
    lx = b + ext + 2.0 * th
    sec.leader(xs[-1], D - e, lx, D + 0.4 * th, main["label"], th)
    sec.leader(b - o, D * 0.25, lx, D * 0.25, ties["label"], th)
    if cross["across_D"] or cross["across_b"]:
        n = len(cross["across_D"]) + len(cross["across_b"])
        if cross["across_D"]:
            sec.leader(xs[cross["across_D"][0]], D * 0.6, lx, D * 0.6, f"{n} cross-tie{'s' if n > 1 else ''}, T{dt}", th)
        else:
            sec.leader(b * 0.6, ys[cross["across_b"][0]], lx, D * 0.6, f"{n} cross-tie{'s' if n > 1 else ''}, T{dt}", th)
    sec.text(b / 2.0, -5.4 * th, f"Cover {cover:.0f} mm to ties", 0.8 * th, "middle")

    # ------------------------------------------------------------ elevation in the plane of D
    elev = model.view("elevation", "Elevation of one lift", "to scale")
    lap = reinf["lap"]
    top = lc + hb
    te = min(max(top / 45.0, 0.12 * D), 0.35 * D)
    elev.line(-0.9 * D, 0, 1.9 * D, 0, "support")  # floor
    elev.polyline([(-0.9 * D, lc), (0, lc), (0, 0), (D, 0), (D, lc), (1.9 * D, lc)], closed=False, layer="concrete")
    elev.polyline([(-0.9 * D, top), (1.9 * D, top)], closed=False, layer="concrete")
    for x in (e, D - e):
        elev.line(x, 0, x, top + lap, "rebar")
    pitch = ties["spacing"]
    n_t = tie_count(lc, pitch)
    step = max(1, math.ceil(n_t / 200))
    for i in range(0, n_t, step):
        y = FIRST_TIE_MM + i * pitch
        elev.line(cover, y, D - cover, y, "stirrup")
    elev.dim(D, 0, D, lc, 1.2 * D, f"{lc:.0f} clear", te)
    elev.dim(D, lc, D, top, 1.2 * D, f"{hb:.0f}", te)
    elev.dim(D - e, top, D - e, top + lap, 0.6 * D, f"lap {lap:.0f}", te)
    elev.dim(0, 0, D, 0, -2.0 * te, f"{D:.0f}", te)
    elev.leader(e, top + 0.5 * lap, -0.9 * D, top + 0.75 * lap, main["label"], te)
    elev.leader(cover, lc * 0.5, -0.9 * D, lc * 0.5, f"{n_t} nos. {ties['label']}", te)
    elev.text(1.45 * D, lc + 0.5 * hb - 0.3 * te, "beam", 0.8 * te, "middle")

    model.notes = [
        f"Concrete M{inp.fck}; main bars Fe {inp.fy}.",
        f"Cover {cover:.0f} mm to ties; {cover + dt:.0f} mm to main bars.",
        f"Laps in compression {lap:.0f} mm; stagger them where the steel exceeds 4 percent at the lap.",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
