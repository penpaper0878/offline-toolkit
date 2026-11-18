"""Slab panel detailing: bar bending schedule, quantities, plan and section.

Bar extents follow Annex D-1.4 to D-1.10 (applied to one-way panels as practice): bottom bars
run into the supports; top bars over a continuous edge extend 0.3 of the span on each side of
the support and are scheduled whole with this panel (leave them out of the adjacent panel's
schedule); top bars at a discontinuous edge extend 0.1 of the span and turn down into the
support; torsion mats at corners extend one-fifth of the short span. Bending deductions as
IS 2502 practice, as for the beam and column schedules.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering import is456_slabs as sl
from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight

if TYPE_CHECKING:
    from app.modules.structural.domain.slab import SlabInput


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def count_over(width: float, spacing: float) -> int:
    """Bars at a spacing across a width, one at each end."""
    return int(math.floor(max(width, 0.0) / spacing + 1e-9)) + 1


def bar_schedule(inp: SlabInput, reinf: dict[str, Any]) -> dict[str, Any]:
    lxc, lyc, sw, D = inp.span_x_mm, inp.span_y_mm, inp.support_width_mm, inp.thickness_mm
    dia, c = reinf["dia"], reinf["cover"]
    loc = reinf["locations"]
    edges = reinf["edges"]
    lx, ly = reinf["lx"], reinf["ly"]
    into = sw - c  # bottom bars run to the far face of the support, less cover
    items: list[dict[str, Any]] = []

    def add(desc: str, shape: str, count: int, dims: dict[str, float], length: float, formula: str) -> None:
        if count <= 0:
            return
        length = _ceil5(length)
        uw = bar_unit_weight(dia)
        items.append({
            "mark": chr(ord("a") + len(items)), "description": desc, "shape": shape, "dia": dia, "count": count,
            "dims": {k: round(v, 0) for k, v in dims.items()}, "cutting_length_mm": length,
            "total_length_m": round(count * length / 1000.0, 3), "unit_weight_kg_m": round(uw, 4),
            "weight_kg": round(count * length / 1000.0 * uw, 2), "formula": formula,
        })

    run_x, run_y = lxc + 2 * into, lyc + 2 * into
    if reinf["one_way"]:
        s = loc["bottom_x"]["spacing"]
        add(f"Main bars, bottom, T{dia} at {s:.0f}", "straight", count_over(lyc, s), {"A": run_x}, run_x, "A = l_xc + 2 (support - cover)")
        s = loc["bottom_y"]["spacing"]
        add(f"Distribution bars, bottom, T{dia} at {s:.0f}", "straight", count_over(lxc, s), {"A": run_y}, run_y, "A = l_yc + 2 (support - cover)")
    else:
        mid_y, edge_y = sl.MIDDLE_STRIP * lyc, sl.EDGE_STRIP * lyc
        mid_x, edge_x = sl.MIDDLE_STRIP * lxc, sl.EDGE_STRIP * lxc
        s = loc["bottom_x"]["spacing"]
        add(f"Short span bottom, middle strip, T{dia} at {s:.0f}", "straight", count_over(mid_y, s), {"A": run_x}, run_x, "A = l_xc + 2 (support - cover)")
        s = loc["bottom_x_edge"]["spacing"]
        add(f"Short span bottom, edge strips, T{dia} at {s:.0f}", "straight", 2 * count_over(edge_y, s) - 2, {"A": run_x}, run_x,
            "A = l_xc + 2 (support - cover); two strips, outer bars shared with the middle strip")
        s = loc["bottom_y"]["spacing"]
        add(f"Long span bottom, middle strip, T{dia} at {s:.0f}", "straight", count_over(mid_x, s), {"A": run_y}, run_y, "A = l_yc + 2 (support - cover)")
        s = loc["bottom_y_edge"]["spacing"]
        add(f"Long span bottom, edge strips, T{dia} at {s:.0f}", "straight", 2 * count_over(edge_x, s) - 2, {"A": run_y}, run_y,
            "A = l_yc + 2 (support - cover); two strips, outer bars shared with the middle strip")

    # top bars over continuous edges: full bars across the support
    n_long_cont = [edges["long_edge_1"], edges["long_edge_2"]].count("continuous")
    n_short_cont = [edges["short_edge_1"], edges["short_edge_2"]].count("continuous")
    top_zones: list[tuple[float, float]] = []  # (zone width across the edge, edge length) for distribution bars
    if "top_x_cont" in loc and n_long_cont:
        s = loc["top_x_cont"]["spacing"]
        a = 2 * sl.TOP_EXTENT_FULL * lx + sw
        add(f"Top bars over continuous long edges, T{dia} at {s:.0f}", "straight", n_long_cont * count_over(lyc, s), {"A": a}, a,
            "A = support + 2 x 0.3 l_x")
        top_zones += [(a, lyc)] * n_long_cont
    if "top_y_cont" in loc and n_short_cont:
        s = loc["top_y_cont"]["spacing"]
        a = 2 * sl.TOP_EXTENT_FULL * ly + sw
        add(f"Top bars over continuous short edges, T{dia} at {s:.0f}", "straight", n_short_cont * count_over(lxc, s), {"A": a}, a,
            "A = support + 2 x 0.3 l_y")
        top_zones += [(a, lxc)] * n_short_cont
    leg = D - 2 * c
    for key, n_disc, span, edge_len, name in (("top_x_disc", 2 - n_long_cont, lx, lyc, "long"), ("top_y_disc", 2 - n_short_cont, ly, lxc, "short")):
        if key in loc and n_disc:
            s = loc[key]["spacing"]
            a = sl.DISCONTINUOUS_TOP_EXTENT * span + into
            add(f"Top bars at discontinuous {name} edges, T{dia} at {s:.0f}", "L-bar, leg down into the support", n_disc * count_over(edge_len, s),
                {"A": a, "B": leg}, a + leg - 2 * dia, "A + B - 2d; A = 0.1 l + support - cover, B = D - 2 cover")
            top_zones.append((a, edge_len))

    tor = reinf["torsion"]
    if tor.get("corners") and "spacing" in tor:
        s = tor["spacing"]
        ext = tor["extent"]
        a = ext + into
        per_layer = count_over(ext, s)
        full = sum(1 for k in tor["corners"] if k["factor"] == 1.0)
        half = len(tor["corners"]) - full
        # half-area corners: the same bars at twice the spacing
        n = full * 4 * per_layer + half * 4 * count_over(ext, 2 * s)
        add(f"Torsion mats at corners, top and bottom, both ways ({full} full, {half} half)", "straight", n, {"A": a}, a,
            "A = l_x/5 + support - cover; four layers per corner")

    # distribution bars holding the top bars, at minimum steel spacing, parallel to each edge and as long as it
    if top_zones:
        sd = loc["bottom_y"]["spacing"] if reinf["one_way"] else max(loc["bottom_x_edge"]["spacing"], loc["bottom_y_edge"]["spacing"])
        for edge_len, name in ((lyc, "long edges" if lxc != lyc else "the edges"), (lxc, "short edges")):
            n = sum(count_over(width, sd) for width, length in top_zones if length == edge_len)
            if n:
                add(f"Distribution bars under top bars along {name}, T{dia} at {sd:.0f}", "straight", n, {"A": edge_len}, edge_len,
                    "A = clear length of the edge")
            if lxc == lyc:  # a square panel: both directions were counted in the first pass
                break

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
        "total_weight_kg": round(sum(x["weight_kg"] for x in summary), 2),
        "stirrup_count": 0,
        "notes": [
            "Top bars over a continuous edge are scheduled whole with this panel: leave them out of the adjacent panel's schedule.",
            "Bottom bars run to the far face of the supports less cover. Top bars over continuous edges extend 0.3 of the span each side "
            "(IS 456 Annex D-1.5); at discontinuous edges half the mid-span steel extends 0.1 of the span (D-1.6).",
            "Edge strips one-eighth of each side carry the minimum steel (D-1.2, D-1.7)." if not reinf["one_way"] else
            "One-way panel: distribution bars at the minimum steel of Cl. 26.5.2.1.",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no wastage or laps.",
        ],
    }


def quantities(inp: SlabInput, bbs: dict[str, Any]) -> dict[str, Any]:
    lxc, lyc, D = inp.span_x_mm, inp.span_y_mm, inp.thickness_mm
    concrete = lxc * lyc * D * 1e-9
    steel = bbs["total_weight_kg"]
    return {
        "length_m": round(lyc / 1000.0, 3),
        "concrete_m3": round(concrete, 3),
        "formwork_m2": round(lxc * lyc * 1e-6, 3),
        "steel_kg": round(steel, 1),
        "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Concrete and soffit formwork over the clear panel; the slab over the supports is measured with the beams.",
            "Steel from the bar bending schedule, including top bars scheduled whole over continuous edges.",
        ],
    }


def drawing(inp: SlabInput, reinf: dict[str, Any]) -> dict[str, Any]:
    lxc, lyc, sw, D = inp.span_x_mm, inp.span_y_mm, inp.support_width_mm, inp.thickness_mm
    dia, c = reinf["dia"], reinf["cover"]
    loc, edges = reinf["locations"], reinf["edges"]
    lx, ly = reinf["lx"], reinf["ly"]
    model = DrawingModel(f"Slab {inp.mark}: reinforcement plan")
    tag = lambda key: f"T{dia} @ {loc[key]['spacing']:.0f}"  # noqa: E731

    # ------------------------------------------------------------------ plan: long span along x, short span along y
    plan = model.view("plan", "Plan", "to scale")
    th = max(lxc, lyc) / 45.0
    plan.rect(0, 0, lyc, lxc, "concrete")
    # supports: long edges are y = 0 (long edge 1) and y = lxc (long edge 2); short edges x = 0 (short 1), x = lyc (short 2)
    plan.rect(-sw, -sw, lyc + 2 * sw, sw, "support")
    plan.rect(-sw, lxc, lyc + 2 * sw, sw, "support")
    plan.rect(-sw, 0, sw, lxc, "support")
    plan.rect(lyc, 0, sw, lxc, "support")
    plan.text(lyc / 2, -sw - 1.4 * th, f"Long edge 1: {edges['long_edge_1']}", 0.8 * th, "middle")
    plan.text(lyc / 2, lxc + sw + 0.5 * th, f"Long edge 2: {edges['long_edge_2']}", 0.8 * th, "middle")
    # short edge labels run along their edges, clear of the l_x dimension
    plan.text(-sw - 0.4 * th, lxc / 2, f"Short edge 1: {edges['short_edge_1']}", 0.8 * th, "middle", vertical=True)
    plan.text(lyc + sw + 1.2 * th, lxc / 2, f"Short edge 2: {edges['short_edge_2']}", 0.8 * th, "middle", vertical=True)
    if not reinf["one_way"]:  # edge strip boundaries
        for x in (lyc / 8, 7 * lyc / 8):
            plan.line(x, 0, x, lxc, "centerline")
        for y in (lxc / 8, 7 * lxc / 8):
            plan.line(0, y, lyc, y, "centerline")
    # representative bottom bars (red) and top bars (blue)
    xb = 0.38 * lyc
    plan.line(xb, -(sw - c), xb, lxc + (sw - c), "rebar")
    plan.leader(xb, 0.62 * lxc, xb + 0.06 * lyc, 0.70 * lxc, f"{tag('bottom_x')} B", th)
    yb = 0.30 * lxc
    plan.line(-(sw - c), yb, lyc + (sw - c), yb, "rebar")
    plan.leader(0.58 * lyc, yb, 0.62 * lyc, yb - 1.8 * th, f"{tag('bottom_y')} B", th)
    if "top_x_cont" in loc:
        for name, y_edge, sign in (("long_edge_1", 0.0, -1), ("long_edge_2", lxc, 1)):
            if edges[name] == "continuous":
                x = 0.70 * lyc
                y0, y1 = y_edge - sign * sl.TOP_EXTENT_FULL * lx, y_edge + sign * sw
                plan.line(x, y0, x, y1, "stirrup")
                plan.leader(x, (y0 + y_edge) / 2, x + 0.05 * lyc, (y0 + y_edge) / 2, f"{tag('top_x_cont')} T", th)
    if "top_y_cont" in loc:
        for name, x_edge, sign in (("short_edge_1", 0.0, -1), ("short_edge_2", lyc, 1)):
            if edges[name] == "continuous":
                y = 0.55 * lxc
                x0, x1 = x_edge - sign * sl.TOP_EXTENT_FULL * ly, x_edge + sign * sw
                plan.line(x0, y, x1, y, "stirrup")
                plan.leader((x0 + x_edge) / 2, y, (x0 + x_edge) / 2, y + 2.2 * th, f"{tag('top_y_cont')} T", th)
    tor = reinf["torsion"]
    if tor.get("corners") and "spacing" in tor:
        ext = tor["extent"]
        for corner in tor["corners"]:
            x0 = 0.0 if corner["short"] == "S1" else lyc - ext
            y0 = 0.0 if corner["long"] == "L1" else lxc - ext
            n = 4
            for i in range(n + 1):
                plan.line(x0 + i * ext / n, y0, x0 + i * ext / n, y0 + ext, "stirrup")
                plan.line(x0, y0 + i * ext / n, x0 + ext, y0 + i * ext / n, "stirrup")
        first = tor["corners"][0]
        cx = (0.0 if first["short"] == "S1" else lyc - ext) + ext / 2
        cy = (0.0 if first["long"] == "L1" else lxc - ext) + ext / 2
        plan.leader(cx, cy, cx + (0.12 * lyc if first["short"] == "S1" else -0.12 * lyc), cy + (0.12 * lxc if first["long"] == "L1" else -0.12 * lxc),
                    f"torsion mats T{dia} @ {tor['spacing']:.0f}", th)
    plan.dim(0, -sw, lyc, -sw, -3.0 * th, f"l_y = {lyc:.0f} clear", th)
    plan.dim(-sw, 0, -sw, lxc, -3.0 * th, f"l_x = {lxc:.0f} clear", th)

    # ------------------------------------------------------------------ section across the short span
    sec = model.view("elevation", "Section across the short span", "to scale")
    ts = max(lxc / 40.0, 0.35 * D)
    sec.rect(0, 0, lxc, D, "concrete")
    sec.rect(-sw, -1.5 * D, sw, 2.5 * D, "support")
    sec.rect(lxc, -1.5 * D, sw, 2.5 * D, "support")
    yb = c + dia / 2
    sec.line(-(sw - c), yb, lxc + (sw - c), yb, "rebar")
    yt = D - c - dia / 2
    for name, x_edge, sign in (("long_edge_1", 0.0, 1), ("long_edge_2", lxc, -1)):
        if edges[name] == "continuous" and "top_x_cont" in loc:
            sec.line(x_edge - sign * sw, yt, x_edge + sign * sl.TOP_EXTENT_FULL * lx, yt, "stirrup")
        elif "top_x_disc" in loc:
            xa = x_edge - sign * (sw - c)
            sec.line(xa, yt, x_edge + sign * sl.DISCONTINUOUS_TOP_EXTENT * lx, yt, "stirrup")
            sec.line(xa, yt, xa, c, "stirrup")
    sec.dim(0, -1.5 * D, lxc, -1.5 * D, -1.6 * ts, f"{lxc:.0f}", ts)
    sec.dim(lxc + sw, 0, lxc + sw, D, 1.4 * ts, f"D = {D:.0f}", ts)
    sec.text(lxc / 2, D + 1.2 * ts, f"{tag('bottom_x')} B" + (f"; {tag('top_x_cont')} T over continuous edges" if "top_x_cont" in loc else ""),
             0.9 * ts, "middle")

    model.notes = [
        f"Concrete M{inp.fck}; bars Fe {inp.fy}. Cover {c:.0f} mm.",
        "Red: bottom bars (B). Blue: top bars (T) and torsion mats. Dashed-weight lines: edge strip boundaries.",
        "Short span bars in the outer layer, long span bars inside them, top and bottom.",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
