"""Continuous beam detailing: bar bending schedule, quantities and drawing for the whole beam.

Bars per span type: bottom bars of the end spans and of the interior spans; top bars over the supports next
to the ends (B) and over the other interior supports (C), each set centred on its support; hanger bars between
them, lapped in compression (Cl. 26.2.5.1(d)); stirrups at one spacing per span type. Lengths follow IS 2502
practice as for the simple beam.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering import is456
from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.beam_detailing import cross_section

if TYPE_CHECKING:
    from app.modules.structural.domain.continuous_beam import ContinuousBeamInput

FIRST_STIRRUP_MM = 50.0


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def layout(inp: ContinuousBeamInput, reinf: dict[str, Any]) -> dict[str, Any]:
    """Extents of the top bars and hangers in each span, mm from the faces of the supports.

    Where the support bars from the two ends of a span would leave no room for a lapped hanger, they run on
    and lap with each other at mid-span (a tension lap, Cl. 26.2.5.1(c)); in an end span they run on to the
    end support.
    """
    lc, sw, n, cover = inp.clear_span_mm, inp.support_width_mm, inp.spans, reinf["cover"]
    fck, fy = float(inp.fck), float(inp.fy)
    sb, sc = reinf["support_b"], reinf["support_c"]
    h_end, h_int = reinf["end"]["top"], reinf["interior"]["top"]

    def lap_c(dia: float) -> float:  # compression lap, Cl. 26.2.5.1(d): L_d in compression, at least 24 phi
        return max(is456.development_length(dia, fck, fy, compression=True), 24.0 * dia)

    def lap_t(dia: float) -> float:  # tension lap, Cl. 26.2.5.1(c): L_d, at least 30 phi
        return max(is456.development_length(dia, fck, fy), 30.0 * dia)

    out: dict[str, Any] = {}
    # end span: support B bars from the B end, hangers from the end support A
    a = sb["into_end"]
    lap = lap_c(h_end["dia"])
    if lc - a > lap:
        out["end"] = {"a_b": a, "hanger": (sw - cover) + (lc - a) + lap, "lap": lap}
    else:  # the B bars run on to the end support
        out["end"] = {"a_b": lc + sw - cover, "hanger": 0.0, "lap": 0.0}
    # interior spans: (left support, right support) kinds and counts
    kinds: list[tuple[str, str, int]] = [("B", "B", 1)] if n == 3 else [("B", "C", 2)] + ([("C", "C", n - 4)] if n > 4 else [])
    ext = {"B": sb["into_interior"], "C": sc["into_interior"] if sc else 0.0}
    dia_top = {"B": sb["top"]["dia"], "C": sc["top"]["dia"] if sc else 0}
    spans = []
    for left, right, count in kinds:
        al, ar = ext[left], ext[right]
        lap = lap_c(h_int["dia"])
        if lc - al - ar > 2.0 * lap:
            spans.append({"left": left, "right": right, "count": count, "a_left": al, "a_right": ar, "hanger": lc - al - ar + 2.0 * lap, "lap": lap,
                          "meet": False})
        else:  # the support bars meet: each set runs to mid-span and they lap there in tension
            lt = lap_t(max(dia_top[left], dia_top[right]))
            half = (lc + lt) / 2.0
            spans.append({"left": left, "right": right, "count": count, "a_left": half, "a_right": half, "hanger": 0.0, "lap": lt, "meet": True})
    out["interior"] = spans
    # each support set reaches as far as the farthest span asks
    out["b_into_interior"] = max(s["a_left" if s["left"] == "B" else "a_right"] for s in spans if "B" in (s["left"], s["right"]))
    c_ext = [s["a_left"] for s in spans if s["left"] == "C"] + [s["a_right"] for s in spans if s["right"] == "C"]
    out["c_into_interior"] = max(c_ext) if c_ext else 0.0
    return out


def bar_schedule(inp: ContinuousBeamInput, reinf: dict[str, Any], sheet: CalcSheet) -> dict[str, Any]:
    lc, sw, n, b, D = inp.clear_span_mm, inp.support_width_mm, inp.spans, inp.width_mm, inp.depth_mm
    fck, fy = float(inp.fck), float(inp.fy)
    cover = reinf["cover"]
    embed = sw - cover
    end, inner, sb, sc, st = reinf["end"], reinf["interior"], reinf["support_b"], reinf["support_c"], reinf["stirrups"]
    lay = reinf["layout"]
    items: list[dict[str, Any]] = []

    def add(desc: str, shape: str, dia: int, count: int, dims: dict[str, float], length: float, formula: str) -> None:
        if count <= 0:
            return
        length = _ceil5(length)
        uw = bar_unit_weight(dia)
        items.append({"mark": chr(ord("a") + len(items)), "description": desc, "shape": shape, "dia": dia, "count": count,
                      "dims": {k: round(v, 0) for k, v in dims.items()}, "cutting_length_mm": length,
                      "total_length_m": round(count * length / 1000.0, 3), "unit_weight_kg_m": round(uw, 4),
                      "weight_kg": round(count * length / 1000.0 * uw, 2), "formula": formula})

    def comp_ext(dia: float, doubly: bool) -> float:
        """Past the far face of a support whose section uses the bottom bars in compression (Cl. 26.2.1)."""
        return max(0.0, is456.development_length(dia, fck, fy, compression=True) - embed) if doubly else 0.0

    # ---- bottom bars, end spans: anchored at the end support (one third of L_d, Cl. 26.2.3.3), to the far face of B
    eb = end["bottom"]
    ld3 = is456.development_length(eb["dia"], fck, fy) / 3.0
    run = lc + 2.0 * embed + comp_ext(eb["dia"], sb["doubly"])
    if embed >= ld3:
        add(f"Bottom bars, end spans, {eb['label']}", "straight", eb["dia"], 2 * eb["count"], {"A": run}, run, "A")
    else:
        leg = _ceil5(max(9.0 * eb["dia"], ld3 - embed + 2.0 * eb["dia"]))
        add(f"Bottom bars, end spans, {eb['label']}", "L-bend at the end support", eb["dia"], 2 * eb["count"], {"A": run, "B": leg},
            run + leg - 2.0 * eb["dia"], "A + B - 2d (one 90 deg bend)")
    # ---- bottom bars, interior spans
    ib = inner["bottom"]
    doubly_any = sb["doubly"] or bool(sc and sc["doubly"])
    run_i = lc + 2.0 * embed + 2.0 * comp_ext(ib["dia"], doubly_any)
    add(f"Bottom bars, interior spans, {ib['label']}", "straight", ib["dia"], (n - 2) * ib["count"], {"A": run_i}, run_i, "A")
    # ---- top bars over the supports
    tb = sb["top"]
    len_b = sw + lay["end"]["a_b"] + lay["b_into_interior"]
    add(f"Top bars over supports next to the ends (B), {tb['label']}", "straight", tb["dia"], 2 * tb["count"],
        {"A": len_b}, len_b, "A = support + extents into both spans")
    if sc:
        tc = sc["top"]
        len_c = sw + 2.0 * lay["c_into_interior"]
        add(f"Top bars over interior supports (C), {tc['label']}", "straight", tc["dia"], (n - 3) * tc["count"], {"A": len_c}, len_c,
            "A = support + extents into both spans")
    # ---- hangers
    he, hi = end["top"], inner["top"]
    if lay["end"]["hanger"] > 0:
        role = "compression bars" if end["doubly"] else "hangers"
        add(f"Top {role}, end spans, {he['label']}", "straight", he["dia"], 2 * he["count"], {"A": lay["end"]["hanger"]}, lay["end"]["hanger"],
            "A = end support + span - support bar extent + lap")
    for s in lay["interior"]:
        if s["hanger"] > 0 and s["count"] > 0:
            role = "compression bars" if inner["doubly"] else "hangers"
            add(f"Top {role}, interior spans between {s['left']} and {s['right']}, {hi['label']}", "straight", hi["dia"], s["count"] * hi["count"],
                {"A": s["hanger"]}, s["hanger"], "A = span - support bar extents + 2 laps")
    # ---- side face bars
    side = reinf.get("side_face")
    if side:
        run_s = lc + 2.0 * embed
        add(f"Side face bars, {side['label']}", "straight", side["dia"], 2 * side["per_face"] * n, {"A": run_s}, run_s, "A, each span")
    # ---- stirrups
    dst = st["end"]["dia"]
    a_st, h_st = b - 2.0 * cover, D - 2.0 * cover
    hook = max(10.0 * dst, 75.0)
    formula = "2(A + B) + 2 x hook - 3 x 2d - 2 x 3d (three 90 deg and two 135 deg bends)"
    counts = {}
    for kind, spans_of_kind in (("end", 2), ("interior", n - 2)):
        sv = st[kind]["spacing"]
        per = int(math.floor(max(lc - 2.0 * FIRST_STIRRUP_MM, 0.0) / sv + 1e-9)) + 1
        counts[kind] = per
        add(f"Stirrups, {kind} spans, T{dst} at {sv:.0f} c/c ({per} per span)", "closed stirrup, 135 deg hooks", dst, per * spans_of_kind,
            {"A": a_st, "B": h_st, "hook": hook}, 2.0 * (a_st + h_st) + 2.0 * hook - 12.0 * dst, formula)
        if st[kind]["legs"] == 4:
            first = (end if kind == "end" else inner)["bottom"]
            n1 = first["layers"][0]
            pitch = (a_st - 2.0 * dst - first["dia"]) / (n1 - 1)
            a_in = _ceil5((n1 - 3) * pitch + first["dia"] + 2.0 * dst)
            add(f"Inner stirrups, {kind} spans, T{dst} at {sv:.0f} c/c", "closed stirrup, 135 deg hooks", dst, per * spans_of_kind,
                {"A": a_in, "B": h_st, "hook": hook}, 2.0 * (a_in + h_st) + 2.0 * hook - 12.0 * dst, formula)

    by_dia: dict[int, dict[str, float]] = {}
    for it in items:
        e = by_dia.setdefault(it["dia"], {"length_m": 0.0, "weight_kg": 0.0})
        e["length_m"] += it["total_length_m"]
        e["weight_kg"] += it["weight_kg"]
    summary = [{"dia": k, "length_m": round(v["length_m"], 2), "weight_kg": round(v["weight_kg"], 2)} for k, v in sorted(by_dia.items())]
    return {
        "member": inp.mark, "members": 1, "items": items, "summary": summary,
        "total_weight_kg": round(sum(x["weight_kg"] for x in summary), 2), "stirrup_count": counts["end"],
        "stirrups_per_span": counts,
        "notes": [
            f"The whole beam: {n} spans of {lc:.0f} mm clear on supports {sw:.0f} mm wide. Counts include every span and support.",
            "Top bars over a support are centred on it and run into both spans to the extents shown; hangers lap with them in "
            "compression (IS 456 Cl. 26.2.5.1(d)).",
            "Bottom bars run to the far face of each support less cover; at the end supports they are anchored one third of L_d "
            "(Cl. 26.2.3.3).",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no laps beyond those shown, "
            "no wastage.",
        ],
    }


def quantities(inp: ContinuousBeamInput, bbs: dict[str, Any]) -> dict[str, Any]:
    lc, sw, n, b, D = inp.clear_span_mm, inp.support_width_mm, inp.spans, inp.width_mm, inp.depth_mm
    flanged = inp.section != "rectangular"
    rib = D - inp.flange_thickness_mm if flanged else D
    length = n * lc + (n + 1) * sw
    concrete = b * rib * length * 1e-9
    sides = rib + D if inp.section == "l_beam" else 2.0 * rib
    formwork = (b + sides) * n * lc * 1e-6
    steel = bbs["total_weight_kg"]
    return {
        "length_m": round(length / 1000.0, 3), "concrete_m3": round(concrete, 3), "formwork_m2": round(formwork, 3),
        "steel_kg": round(steel, 1), "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Concrete over the whole length, the supports included" + ("; the rib below the slab only." if flanged else "."),
            "Formwork: soffit and sides over the clear spans" + (" (an L-beam's outer face to the full depth)." if inp.section == "l_beam" else "."),
            "Steel from the bar bending schedule, the whole beam.",
        ],
    }


def drawing(inp: ContinuousBeamInput, reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
    lc, sw, n, b, D = inp.clear_span_mm, inp.support_width_mm, inp.spans, inp.width_mm, inp.depth_mm
    cover = reinf["cover"]
    end, inner, sb, st = reinf["end"], reinf["interior"], reinf["support_b"], reinf["stirrups"]
    lay = reinf["layout"]
    shape = reinf["section"]
    flanged = shape["kind"] != "rectangular"
    dst = st["end"]["dia"]
    model = DrawingModel(f"Continuous beam {inp.mark}: reinforcement details")

    # ------------------------------------------------------------------ elevation: end span, support B and half of span 2
    el = model.view("elevation", "Elevation: end span and half of span 2", "to scale")
    x_b = sw + lc  # face of support B on the end-span side
    x_end = 2.0 * sw + 1.5 * lc
    te = min(max(x_end / 55.0, 0.10 * D), 0.30 * D)
    sh = 0.5 * D
    el.rect(0, -sh, sw, sh, "support")
    el.rect(x_b, -sh, sw, sh, "support")
    zig = [(x_end, 0.0), (x_end, 0.35 * D), (x_end + 0.12 * D, 0.45 * D), (x_end - 0.12 * D, 0.55 * D), (x_end, 0.65 * D), (x_end, D)]
    el.polyline([(x_end, D), (0.0, D), (0.0, 0.0), (x_end, 0.0)], closed=False, layer="concrete")
    el.polyline(zig, closed=False, layer="concrete")
    if flanged:
        el.line(0, D - shape["df"], x_end, D - shape["df"], "centerline")
    eb, ib, tb, he = end["bottom"], inner["bottom"], sb["top"], end["top"]
    y_b = cover + dst + eb["dia"] / 2.0
    y_t = D - (cover + dst + tb["dia"] / 2.0)
    main = next(i for i in bbs["items"] if i["description"].startswith("Bottom bars, end spans"))
    leg = main["dims"].get("B", 0.0)
    el.line(cover, y_b, x_b + sw - cover, y_b, "rebar")  # end span bottom
    if leg:
        el.line(cover, y_b, cover, y_b + leg, "rebar")
    el.line(x_b + cover, y_b + 0.8 * ib["dia"], x_end, y_b + 0.8 * ib["dia"], "rebar")  # span 2 bottom, drawn just above
    a_end, a_int = lay["end"]["a_b"], lay["b_into_interior"]
    x_tb0, x_tb1 = max(x_b - a_end, cover), min(x_b + sw + a_int, x_end)
    el.line(x_tb0, y_t, x_tb1, y_t, "rebar")  # top bars over B
    y_h = y_t - 0.8 * he["dia"]
    if lay["end"]["hanger"] > 0:
        el.line(cover, y_h, x_b - a_end + lay["end"]["lap"], y_h, "stirrup")
    first_int = lay["interior"][0]
    if first_int["hanger"] > 0 and x_b + sw + a_int - first_int["lap"] < x_end:
        el.line(x_b + sw + a_int - first_int["lap"], y_h, x_end, y_h, "stirrup")
    # stirrups
    for x0, x1, sv in ((sw + FIRST_STIRRUP_MM, x_b - FIRST_STIRRUP_MM, st["end"]["spacing"]),
                       (x_b + sw + FIRST_STIRRUP_MM, x_end, st["interior"]["spacing"])):
        count = int(math.floor((x1 - x0) / sv + 1e-9)) + 1
        step = max(1, math.ceil(count / 120))
        for i in range(0, count, step):
            el.line(x0 + i * sv, cover, x0 + i * sv, D - cover, "stirrup")
    # dimensions and labels
    el.dim(sw, -sh, x_b, -sh, -2.0 * te, f"{lc:.0f} clear", te)
    el.dim(0, -sh, sw, -sh, -2.0 * te, f"{sw:.0f}", te)
    el.dim(x_b, -sh, x_b + sw, -sh, -2.0 * te, f"{sw:.0f}", te)
    el.dim(0, 0, 0, D, -2.0 * te, f"{D:.0f}", te)
    if x_tb0 > cover:
        el.dim(x_tb0, D, x_b, D, 2.2 * te, f"{a_end:.0f}", te)
    el.dim(x_b + sw, D, x_tb1, D, 2.2 * te, f"{a_int:.0f}" + (" (past the break)" if x_b + sw + a_int > x_end else ""), te)
    el.text(sw + lc / 2.0, D + 4.2 * te, f"{st['end']['label']} ({bbs['stirrups_per_span']['end']} per span)", te, "middle")
    el.text(x_b + sw / 2.0, D + 6.0 * te, f"{tb['label']} top over B", te, "middle")
    if lay["end"]["hanger"] > 0:
        el.text(sw + 0.3 * lc, D + 2.6 * te, f"{he['label']} {'compression bars' if end['doubly'] else 'hangers'}", te, "middle")
    el.text(sw + lc / 2.0, -sh - 5.0 * te, f"{eb['label']} bottom, end span", te, "middle")
    el.text(x_b + sw + 0.25 * lc, -sh - 5.0 * te, f"{ib['label']} bottom, interior spans", te, "start")
    el.text(x_b + sw + 0.25 * lc, D + 4.2 * te, f"{st['interior']['label']}", te, "start")
    for x, mark in ((sw + lc / 2.0, "A"), (x_b - 0.4 * D, "B")):  # section marks
        el.line(x, -0.35 * D, x, -0.15 * D, "dimension")
        el.line(x, D + 0.15 * D, x, D + 0.35 * D, "dimension")
        el.text(x + 0.4 * te, -0.35 * D, mark, 0.9 * te, "start")
    el.text(x_end, -sh - 7.0 * te, f"Spans 2 to {n - 1} as span 2; the beam is symmetrical about its centre." if n > 3 else
            "Span 3 as span 1; the beam is symmetrical about the centre of span 2.", 0.8 * te, "end")

    # ------------------------------------------------------------------ cross-sections A-A and B-B side by side
    sec = model.view("sections", "Sections A-A and B-B", "to scale")
    stir_e = {"dia": dst, "legs": st["end"]["legs"], "label": st["end"]["label"]}
    inner_a = next((i["dims"]["A"] for i in bbs["items"] if i["description"].startswith("Inner stirrups, end")), None)
    th, right = cross_section(sec, 0.0, b, D, cover, stir_e, he, eb, 0.0, end["gap"], shape, reinf.get("side_face"), inner_a,
                              "A-A: mid-span of the end span")
    e_l = 0.0
    if flanged:
        tee = shape["kind"] == "t_beam"
        e_l = min((shape["bf"] - b) / (2.0 if tee else 1.0), max(1.2 * b, 300.0))
    ox = right + e_l + 4.0 * th
    comp = eb if eb["count"] * eb["dia"] ** 2 <= ib["count"] * ib["dia"] ** 2 else ib
    cross_section(sec, ox, b, D, cover, stir_e, tb, comp, sb["gap"], end["gap"] if comp is eb else inner["gap"], shape, reinf.get("side_face"),
                  inner_a, "B-B: at the support next to the end")

    model.notes = [
        f"Concrete M{inp.fck}; main bars Fe {inp.fy}; stirrups Fe {inp.fy_stirrup}.",
        f"Nominal cover {cover:.0f} mm to stirrups ({inp.exposure.replace('_', ' ')} exposure).",
        "Top bars over each support centred on it; hangers lap with them. Full schedule for every span in the bar bending schedule.",
        *(["The flange is the slab, cast with the beam; its bars are the slab's. Dashed line in the elevation: slab soffit."] if flanged else []),
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
