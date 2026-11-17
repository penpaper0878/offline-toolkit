"""Beam detailing outputs: bar bending schedule, quantities and drawing.

Bar shapes and cutting lengths follow IS 2502:1963 practice: lengths are
measured along the outside of the bar and each bend is deducted (2 bar
diameters for 90 degrees, 3 for 135 degrees). Every schedule row carries the
formula it was cut to, so the fixer and the checker read the same thing.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering.drawing import DrawingModel
from app.engineering.rebar import BarGroup, bar_area, bar_unit_weight
from app.engineering.trace import CalcSheet

if TYPE_CHECKING:
    from app.modules.structural.domain.beam import BeamInput

FIRST_STIRRUP_MM = 50.0  # first stirrup from the face of the support


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def side_face_bars(inp: BeamInput, cover: float, ten: BarGroup, oth: BarGroup, torsion: bool) -> dict[str, Any] | None:
    """Cl. 26.5.1.3 (D > 750 mm) and Cl. 26.5.1.7(b) (D > 450 mm with torsion)."""
    b, D, dst = inp.width_mm, inp.depth_mm, inp.stirrup_dia_mm
    if not (D > 750.0 or (torsion and D > 450.0)):
        return None
    per_face_area = 0.0005 * b * D
    y_lo = cover + dst + ten.dia / 2.0
    y_hi = D - (cover + dst + oth.dia / 2.0)
    s_max = min(300.0, b)
    n_spacing = max(1, math.ceil((y_hi - y_lo) / s_max - 1e-9) - 1)
    best: tuple[float, int, int] | None = None
    for dia in (10, 12, 16):
        n = max(n_spacing, math.ceil(per_face_area / bar_area(dia) - 1e-9))
        if best is None or n * bar_area(dia) < best[0]:
            best = (n * bar_area(dia), dia, n)
    assert best is not None
    _, dia, n = best
    return {
        "dia": dia,
        "per_face": n,
        "area_total": round(2 * n * bar_area(dia), 1),
        "spacing": round((y_hi - y_lo) / (n + 1), 1),
        "label": f"{n}-T{dia} each face",
    }


def bar_schedule(
    inp: BeamInput, cover: float, reinf: dict[str, Any], anch: dict[str, Any], sheet: CalcSheet
) -> dict[str, Any]:
    lc, sw, b, D = inp.clear_span_mm, inp.support_width_mm, inp.width_mm, inp.depth_mm
    cantilever = inp.support == "cantilever"
    face_t = reinf["tension_face"]
    face_o = "bottom" if face_t == "top" else "top"
    ten, oth, st = reinf[face_t], reinf[face_o], reinf["stirrups"]
    embed = sw - cover
    items: list[dict[str, Any]] = []

    def add(desc: str, shape: str, dia: int, count: int, dims: dict[str, float], length: float, formula: str) -> None:
        length = _ceil5(length)
        uw = bar_unit_weight(dia)
        items.append(
            {
                "mark": chr(ord("a") + len(items)),
                "description": desc,
                "shape": shape,
                "dia": dia,
                "count": count,
                "dims": {k: round(v, 0) for k, v in dims.items()},
                "cutting_length_mm": length,
                "total_length_m": round(count * length / 1000.0, 3),
                "unit_weight_kg_m": round(uw, 4),
                "weight_kg": round(count * length / 1000.0 * uw, 2),
                "formula": formula,
            }
        )

    # ---- main tension bars
    dia = ten["dia"]
    if cantilever:
        need = anch["ld_tension"]  # full development beyond the face of the support, Cl. 26.2.1
        run = lc - cover + embed
        if embed >= need:
            add(f"Top bars (tension), {ten['label']}", "straight", dia, ten["count"], {"A": run}, run, "A")
        else:
            leg = _ceil5(max(9.0 * dia, need - embed + 2.0 * dia))
            add(f"Top bars (tension), {ten['label']}", "L-bend at support", dia, ten["count"], {"A": run, "B": leg},
                run + leg - 2.0 * dia, "A + B - 2d (one 90 deg bend)")
            sheet.flag("warning", f"Top bars need L_d = {need:.0f} mm beyond the face of the support; the support gives "
                                  f"{embed:.0f} mm, so the bars are bent down with a {leg:.0f} mm leg. "
                                  "Check that the leg fits the supporting member.", "IS 456:2000, Cl. 26.2.1")
    else:
        need = anch["ld_tension"] / 3.0  # Cl. 26.2.3.3(a): one third of L_d into a simple support
        run = lc + 2.0 * embed
        if embed >= need:
            add(f"Bottom bars (tension), {ten['label']}", "straight", dia, ten["count"], {"A": run}, run, "A")
        else:
            leg = _ceil5(max(9.0 * dia, need - embed + 2.0 * dia))
            add(f"Bottom bars (tension), {ten['label']}", "L-bend both ends", dia, ten["count"], {"A": run, "B": leg},
                run + 2.0 * leg - 4.0 * dia, "A + 2B - 2 x 2d (two 90 deg bends)")
            if leg > D - 2.0 * cover:
                sheet.flag("warning", f"The {leg:.0f} mm anchorage leg of the bottom bars is longer than the beam is deep: "
                                      "widen the support or use smaller bars.", "IS 456:2000, Cl. 26.2.3.3(a)")

    # ---- bars on the other face
    run_o = (lc - cover + embed) if cantilever else (lc + 2.0 * embed)
    role = "compression" if anch["other_in_compression"] else "hanger"
    add(f"{face_o.capitalize()} bars ({role}), {oth['label']}", "straight", oth["dia"], oth["count"], {"A": run_o}, run_o, "A")
    if anch["other_in_compression"] and cantilever and embed < anch["ld_other"]:
        sheet.flag("warning", f"Compression bars need {anch['ld_other']:.0f} mm into the support; it gives {embed:.0f} mm.",
                   "IS 456:2000, Cl. 26.2.1")

    # ---- side face bars
    side = reinf.get("side_face")
    if side:
        add(f"Side face bars, {side['label']}", "straight", side["dia"], 2 * side["per_face"], {"A": run_o}, run_o, "A")

    # ---- stirrups
    dst, sv = st["dia"], st["spacing"]
    n_st = 0
    if sv > 0:
        zone = (lc - FIRST_STIRRUP_MM - cover) if cantilever else (lc - 2.0 * FIRST_STIRRUP_MM)
        n_st = int(math.floor(max(zone, 0.0) / sv + 1e-9)) + 1
    a, h = b - 2.0 * cover, D - 2.0 * cover
    hook = max(10.0 * dst, 75.0)
    stirrup_formula = "2(A + B) + 2 x hook - 3 x 2d - 2 x 3d (three 90 deg and two 135 deg bends)"
    add(f"Stirrups, T{dst} at {sv:.0f} c/c", "closed stirrup, 135 deg hooks", dst, n_st, {"A": a, "B": h, "hook": hook},
        2.0 * (a + h) + 2.0 * hook - 12.0 * dst, stirrup_formula)
    if st["legs"] == 4:
        n1 = ten["layers"][0]
        pitch = (a - 2.0 * dst - ten["dia"]) / (n1 - 1)
        a_in = _ceil5((n1 - 3) * pitch + ten["dia"] + 2.0 * dst)
        add(f"Inner stirrups, T{dst} at {sv:.0f} c/c", "closed stirrup, 135 deg hooks", dst, n_st, {"A": a_in, "B": h, "hook": hook},
            2.0 * (a_in + h) + 2.0 * hook - 12.0 * dst, stirrup_formula)

    by_dia: dict[int, dict[str, float]] = {}
    for it in items:
        e = by_dia.setdefault(it["dia"], {"dia": it["dia"], "length_m": 0.0, "weight_kg": 0.0})
        e["length_m"] += it["total_length_m"]
        e["weight_kg"] += it["weight_kg"]
    summary = [{"dia": k, "length_m": round(v["length_m"], 2), "weight_kg": round(v["weight_kg"], 2)} for k, v in sorted(by_dia.items())]
    return {
        "member": inp.mark,
        "members": 1,
        "items": items,
        "summary": summary,
        "total_weight_kg": round(sum(s["weight_kg"] for s in summary), 2),
        "stirrup_count": n_st,
        "notes": [
            "Cutting lengths to IS 2502:1963 practice: outside dimensions less 2d per 90 degree bend and 3d per 135 degree bend, rounded up to 5 mm.",
            f"Bar ends stop {cover:.0f} mm short of the concrete face. First stirrup {FIRST_STIRRUP_MM:.0f} mm from the face of the support.",
            f"Stirrup hooks 135 degrees with a {hook:.0f} mm extension (10d, at least 75 mm).",
            "Unit mass of bars from 7850 kg/m3 (IS 1786:2008). No allowance for laps, wastage or rolling margin.",
        ],
    }


def quantities(inp: BeamInput, bbs: dict[str, Any]) -> dict[str, Any]:
    lc, sw, b, D = inp.clear_span_mm, inp.support_width_mm, inp.width_mm, inp.depth_mm
    cantilever = inp.support == "cantilever"
    length = lc + (sw if cantilever else 2.0 * sw)
    concrete = b * D * length * 1e-9
    formwork = (b + 2.0 * D) * lc * 1e-6 + (b * D * 1e-6 if cantilever else 0.0)
    steel = bbs["total_weight_kg"]
    return {
        "length_m": round(length / 1000.0, 3),
        "concrete_m3": round(concrete, 3),
        "formwork_m2": round(formwork, 3),
        "steel_kg": round(steel, 1),
        "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Concrete measured over the bearings (clear span plus the supports).",
            "Formwork: soffit and both sides over the clear span" + (", plus the free end." if cantilever else "."),
            "Steel from the bar bending schedule.",
        ],
    }


def _bar_xs(b: float, edge: float, n: int) -> list[float]:
    if n == 1:
        return [b / 2.0]
    return [edge + i * (b - 2.0 * edge) / (n - 1) for i in range(n)]


def drawing(inp: BeamInput, cover: float, reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
    lc, sw, b, D = inp.clear_span_mm, inp.support_width_mm, inp.width_mm, inp.depth_mm
    cantilever = inp.support == "cantilever"
    face_t = reinf["tension_face"]
    top, bot, st = reinf["top"], reinf["bottom"], reinf["stirrups"]
    dst = st["dia"]
    model = DrawingModel(f"Beam {inp.mark}: reinforcement details")

    # ------------------------------------------------------------ cross-section
    sec = model.view("section", "Section A-A", "to scale")
    th = max(b, D) / 20.0
    sec.rect(0, 0, b, D, "concrete")
    o = cover + dst / 2.0
    r = 2.0 * dst
    sec.polyline(
        [(o + r, o), (b - o - r, o), (b - o, o + r), (b - o, D - o - r), (b - o - r, D - o), (o + r, D - o), (o, D - o - r), (o, o + r)],
        closed=True, layer="stirrup",
    )
    if st["legs"] == 4:  # inner hoop around the middle bars
        inner = next((i for i in bbs["items"] if i["description"].startswith("Inner stirrups")), None)
        if inner:
            xi = (b - inner["dims"]["A"] + dst) / 2.0
            sec.polyline([(xi, o), (b - xi, o), (b - xi, D - o), (xi, D - o)], closed=True, layer="stirrup")
    sec.line(o + r, D - o, o + r + 4 * dst, D - o - 4 * dst, "stirrup")  # 135 degree hooks
    sec.line(o, D - o - r, o + 4 * dst, D - o - r - 4 * dst, "stirrup")

    def face_bars(group: dict[str, Any], face: str) -> None:
        dia = group["dia"]
        edge = cover + dst + dia / 2.0
        gap = reinf["layer_gap"] if group is reinf[face_t] else 0.0
        for li, n in enumerate(group["layers"]):
            off = edge + li * (dia + gap)
            y = off if face == "bottom" else D - off
            for x in _bar_xs(b, edge, n):
                sec.circle(x, y, dia / 2.0, "rebar")

    face_bars(bot, "bottom")
    face_bars(top, "top")
    side = reinf.get("side_face")
    if side:
        y_lo = cover + dst + bot["dia"] / 2.0
        y_hi = D - (cover + dst + top["dia"] / 2.0)
        xs = cover + dst + side["dia"] / 2.0
        for i in range(side["per_face"]):
            y = y_lo + (i + 1) * (y_hi - y_lo) / (side["per_face"] + 1)
            sec.circle(xs, y, side["dia"] / 2.0, "rebar")
            sec.circle(b - xs, y, side["dia"] / 2.0, "rebar")
    sec.dim(0, 0, b, 0, -2.2 * th, f"{b:.0f}", th)
    sec.dim(0, 0, 0, D, -2.2 * th, f"{D:.0f}", th)
    lx = b + 1.5 * th
    sec.leader(b - cover - dst - top["dia"] / 2.0, D - cover - dst - top["dia"] / 2.0, lx, D - th, top["label"], th)
    sec.leader(b - o, D / 2.0, lx, D / 2.0, st["label"], th)
    if side:
        sec.leader(b - cover - dst - side["dia"] / 2.0, D * 0.36, lx, D * 0.30, side["label"], th)
    sec.leader(b - cover - dst - bot["dia"] / 2.0, cover + dst + bot["dia"] / 2.0, lx, 0.2 * th, bot["label"], th)
    sec.text(b / 2.0, -5.2 * th, f"Cover {cover:.0f} mm to stirrups", 0.8 * th, "middle")

    # ---------------------------------------------------------------- elevation
    elev = model.view("elevation", "Longitudinal section", "to scale")
    total = lc + (sw if cantilever else 2.0 * sw)
    te = min(max(total / 50.0, 0.10 * D), 0.30 * D)  # text height that stays legible at the width of the view
    y_b = cover + dst + bot["dia"] / 2.0
    y_t = D - (cover + dst + top["dia"] / 2.0)
    main = next(i for i in bbs["items"] if "tension" in i["description"])
    leg = main["dims"].get("B", 0.0)
    if cantilever:
        elev.rect(0, -0.75 * D, sw, 2.5 * D, "support")
        elev.polyline([(sw, 0), (total, 0), (total, D), (sw, D)], closed=False, layer="concrete")
        x_end = total - cover
        elev.line(cover, y_t, x_end, y_t, "rebar")
        if leg:
            elev.line(cover, y_t, cover, y_t - leg, "rebar")
        elev.line(cover, y_b, x_end, y_b, "rebar")
        x0 = sw + FIRST_STIRRUP_MM
        elev.dim(sw, -0.75 * D, total, -0.75 * D, -2.0 * te, f"{lc:.0f}", te)
        elev.dim(0, -0.75 * D, sw, -0.75 * D, -2.0 * te, f"{sw:.0f}", te)
    else:
        sh = 0.5 * D
        elev.rect(0, -sh, sw, sh, "support")
        elev.rect(total - sw, -sh, sw, sh, "support")
        elev.rect(0, 0, total, D, "concrete")
        elev.line(cover, y_b, total - cover, y_b, "rebar")
        if leg:
            elev.line(cover, y_b, cover, y_b + leg, "rebar")
            elev.line(total - cover, y_b, total - cover, y_b + leg, "rebar")
        elev.line(cover, y_t, total - cover, y_t, "rebar")
        x0 = sw + FIRST_STIRRUP_MM
        elev.dim(sw, -sh, total - sw, -sh, -2.0 * te, f"{lc:.0f} clear", te)
        elev.dim(0, -sh, sw, -sh, -2.0 * te, f"{sw:.0f}", te)
        elev.dim(total - sw, -sh, total, -sh, -2.0 * te, f"{sw:.0f}", te)
    n_st, sv = bbs["stirrup_count"], st["spacing"]
    step = max(1, math.ceil(n_st / 240))  # keep very long beams drawable
    for i in range(0, n_st, step):
        x = x0 + i * sv
        elev.line(x, cover, x, D - cover, "stirrup")
    elev.dim(total, 0, total, D, 2.0 * te, f"{D:.0f}", te)
    mid = sw + lc / 2.0
    elev.text(mid, D + 3.4 * te, f"{top['label']} top", te, "middle")
    elev.text(mid, D + 1.8 * te, f"{n_st} nos. {st['label']}", te, "middle")
    elev.text(mid, -1.6 * te if cantilever else -0.5 * D - 5.5 * te, f"{bot['label']} bottom", te, "middle")

    model.notes = [
        f"Concrete M{inp.fck}; main bars Fe {inp.fy}; stirrups Fe {inp.fy_stirrup}.",
        f"Nominal cover {cover:.0f} mm to stirrups ({inp.exposure.replace('_', ' ')} exposure).",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
