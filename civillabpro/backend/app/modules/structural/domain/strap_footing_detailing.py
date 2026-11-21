"""Strap footing detailing: the layout, bar bending schedule, quantities, plan and sections."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight

if TYPE_CHECKING:
    from app.modules.structural.domain.strap_footing import Pad1, Strap, StrapFootingInput

PCC_THICKNESS_MM = 75.0
BEND_LEG_DIAMETERS = 12.0  # leg of an end bend: 90 degree bend plus a straight extension (IS 2502 practice)
FIRST_STIRRUP_MM = 50.0


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def stirrup_counts(zones: list[dict[str, Any]], cover: float) -> list[int]:
    """Stirrups in each zone: the first 50 mm from the property line, then at the zone's spacing; the next zone starts where the last ended."""
    counts = []
    x = cover + FIRST_STIRRUP_MM
    for z in zones:
        n = 0
        while x <= z["x1"] - cover + 1e-6:
            n += 1
            x += z["s"]
        counts.append(n)
    return counts


def reinforcement(inp: StrapFootingInput, L1: float, B1: float, x2: float, pad1: Pad1, strap: Strap, pad2: dict[str, Any], cover: float) -> dict[str, Any]:
    zones = [{"name": z.name, "x0": z.x0, "x1": z.x1, "dia": z.dia, "s": z.s} for z in strap.zones]
    counts = stirrup_counts(zones, cover)
    for z, n in zip(zones, counts, strict=True):
        z["count"] = n
    return {
        "cover": cover, "a": inp.left_end(), "x2": x2, "L1": L1, "B1": B1, "D1": pad1.D,
        "L2": pad2["data"]["L"], "B2": pad2["data"]["B"], "D2": pad2["data"]["D"],
        "columns": [{"x": inp.left_end(), "b": inp.column1_width_mm, "D": inp.column1_depth_mm},
                    {"x": x2, "b": inp.column2_width_mm, "D": inp.column2_depth_mm}],
        "strap": {"b": strap.b, "D": strap.D, "x_end": strap.x_end,
                  "top": {"dia": strap.dia, "count": strap.n, "bent": strap.bent, "label": f"{strap.n}-T{strap.dia}"},
                  "bottom": {"dia": strap.dia_bot, "count": strap.n_bot, "label": f"{strap.n_bot}-T{strap.dia_bot}"},
                  "side": ({"dia": strap.side_dia, "per_face": strap.side_per_face, "label": f"{strap.side_per_face}-T{strap.side_dia} each face"}
                           if strap.side_per_face else None),
                  "zones": zones},
        "pad1": {"across": {"dia": pad1.dia, "count": pad1.n, "spacing": pad1.s, "bent": pad1.bent, "label": f"{pad1.n}-T{pad1.dia} @ {pad1.s:.0f}"},
                 "along": {"dia": pad1.dia_along, "count": pad1.n_along, "spacing": pad1.s_along,
                           "label": f"{pad1.n_along}-T{pad1.dia_along} @ {pad1.s_along:.0f}"}},
        "pad2": pad2["reinforcement"],
    }


def bar_schedule(inp: StrapFootingInput, reinf: dict[str, Any], pad2_bbs: dict[str, Any]) -> dict[str, Any]:
    c = reinf["cover"]
    st = reinf["strap"]
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

    run = st["x_end"] - 2 * c
    top = st["top"]
    if top["bent"]:
        leg = BEND_LEG_DIAMETERS * top["dia"]
        add(f"Strap, top bars, {top['label']}, bent down at the property line", "L-bend at one end", top["dia"], top["count"],
            {"A": run, "B": leg}, run + leg - 2 * top["dia"], "A + B - 2d (one 90 deg bend)")
    else:
        add(f"Strap, top bars, {top['label']}", "straight", top["dia"], top["count"], {"A": run}, run, "A = strap length - 2 cover")
    add(f"Strap, bottom bars, {st['bottom']['label']}", "straight", st["bottom"]["dia"], st["bottom"]["count"], {"A": run}, run,
        "A = strap length - 2 cover")
    if st["side"]:
        add(f"Strap, side-face bars, {st['side']['label']}", "straight", st["side"]["dia"], 2 * st["side"]["per_face"], {"A": run}, run,
            "A = strap length - 2 cover")
    a_, h_ = st["b"] - 2 * c, st["D"] - 2 * c
    merged: dict[tuple[int, float], dict[str, Any]] = {}
    for z in st["zones"]:
        key = (z["dia"], z["s"])
        merged.setdefault(key, {"count": 0, "where": []})
        merged[key]["count"] += z["count"]
        merged[key]["where"].append(z["name"])
    for (dia, s), m in merged.items():
        hook = max(10.0 * dia, 75.0)
        add(f"Strap, stirrups, 2-legged T{dia} at {s:.0f}, {' and '.join(m['where'])}", "closed stirrup, 135 deg hooks", dia, m["count"],
            {"A": a_, "B": h_, "hook": hook}, 2.0 * (a_ + h_) + 2.0 * hook - 12.0 * dia,
            "2(A + B) + 2 x hook - 3 x 2d - 2 x 3d (three 90 deg and two 135 deg bends)")
    p1 = reinf["pad1"]
    across = p1["across"]
    run_b = reinf["B1"] - 2 * c
    if across["bent"]:
        leg = BEND_LEG_DIAMETERS * across["dia"]
        add(f"Pad 1, bars across, {across['label']}", "bent up 90 deg both ends", across["dia"], across["count"], {"A": run_b, "B": leg},
            run_b + 2 * leg - 4 * across["dia"], "A + 2B - 2 x 2d (two 90 deg bends); A = side - 2 cover")
    else:
        add(f"Pad 1, bars across, {across['label']}", "straight", across["dia"], across["count"], {"A": run_b}, run_b, "A = side - 2 cover")
    along = p1["along"]
    add(f"Pad 1, bars along, {along['label']}", "straight", along["dia"], along["count"], {"A": reinf["L1"] - 2 * c}, reinf["L1"] - 2 * c,
        "A = side - 2 cover")
    for i in pad2_bbs["items"]:
        items.append({**i, "mark": chr(ord("a") + len(items)), "description": f"Pad 2, {i['description'][0].lower()}{i['description'][1:]}"})
    total = round(sum(i["weight_kg"] for i in items), 2)
    by_dia: dict[int, list[dict[str, Any]]] = {}
    for i in items:
        by_dia.setdefault(i["dia"], []).append(i)
    return {
        "member": inp.mark, "members": 1, "items": items,
        "summary": [{"dia": d, "length_m": round(sum(i["total_length_m"] for i in rows), 2), "weight_kg": round(sum(i["weight_kg"] for i in rows), 2)}
                    for d, rows in sorted(by_dia.items())],
        "total_weight_kg": total, "stirrup_count": sum(z["count"] for z in st["zones"]),
        "notes": [
            "The strap runs from the property line into pad 2, past column 2; its top bars carry the hogging, bent down at the property line where "
            "the straight length cannot develop them.",
            "Keep the strap off the soil between the pads: a layer of loose fill or a compressible board under it.",
            "Pad 1: bars across in the lower layer, bars along above them. Pad 2 as an isolated footing.",
            "Column bars or dowels (at least 0.5 percent of each column, Cl. 34.4.3) are scheduled with the columns.",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no wastage.",
        ],
    }


def quantities(reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
    st = reinf["strap"]
    L1, B1, D1, L2, B2, D2 = reinf["L1"], reinf["B1"], reinf["D1"], reinf["L2"], reinf["B2"], reinf["D2"]
    x2 = reinf["x2"]
    left2 = x2 - L2 / 2.0
    b, Ds, x_end = st["b"], st["D"], st["x_end"]
    right2 = x2 + L2 / 2.0
    over2 = max(min(x_end, right2) - left2, 0)
    beyond = max(x_end - right2, 0)  # a short pad 2: the strap runs past its far edge
    strap = b * (Ds * (left2 - L1) + max(Ds - D1, 0) * L1 + max(Ds - D2, 0) * over2 + Ds * beyond)
    concrete = (L1 * B1 * D1 + L2 * B2 * D2 + strap) * 1e-9
    formwork = (2 * (L1 + B1) * D1 + 2 * (L2 + B2) * D2 + 2 * Ds * (left2 - L1) + 2 * max(Ds - D1, 0) * L1
                + 2 * max(Ds - D2, 0) * over2 + (2 * Ds + b) * beyond) * 1e-6
    steel = bbs["total_weight_kg"]
    pcc = ((L1 + 300) * (B1 + 300) + (L2 + 300) * (B2 + 300)) * PCC_THICKNESS_MM * 1e-9
    return {
        "length_m": round(x_end / 1000.0, 3),
        "concrete_m3": round(concrete, 3),
        "formwork_m2": round(formwork, 3),
        "steel_kg": round(steel, 1),
        "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Reinforced concrete of the two pads and the strap; formwork to their sides.",
            f"Levelling course under the pads, {PCC_THICKNESS_MM:.0f} mm thick and 150 mm wider all round, {pcc:.3f} m3 (not included above).",
            "Excavation, backfill and the fill under the strap depend on the founding depth and are not measured here.",
        ],
    }


def drawing(inp: StrapFootingInput, reinf: dict[str, Any]) -> dict[str, Any]:
    c = reinf["cover"]
    st = reinf["strap"]
    L1, B1, D1, L2, B2, D2, x2 = reinf["L1"], reinf["B1"], reinf["D1"], reinf["L2"], reinf["B2"], reinf["D2"], reinf["x2"]
    b, Ds, x_end = st["b"], st["D"], st["x_end"]
    cols = reinf["columns"]
    model = DrawingModel(f"Strap footing {inp.mark}: reinforcement details")

    # ------------------------------------------------------------------ plan
    plan = model.view("plan", "Plan", "to scale")
    W = max(B1, B2)
    yc = W / 2.0
    th = max(x2 + L2 / 2.0, W) / 40.0
    plan.line(0, -1.2 * th, 0, W + 1.2 * th, "support")  # the property line
    plan.text(-0.3 * th, W / 2.0, "property line", 0.8 * th, "middle", vertical=True)
    plan.rect(0, yc - B1 / 2, L1, B1, "concrete")
    plan.rect(x2 - L2 / 2, yc - B2 / 2, L2, B2, "concrete")
    plan.rect(L1, yc - b / 2, x2 - L2 / 2 - L1, b, "concrete")  # the strap between the pads
    plan.line(0, yc - b / 2, L1, yc - b / 2, "centerline")  # the strap over the pads
    plan.line(0, yc + b / 2, L1, yc + b / 2, "centerline")
    plan.line(x2 - L2 / 2, yc - b / 2, x_end, yc - b / 2, "centerline")
    plan.line(x2 - L2 / 2, yc + b / 2, x_end, yc + b / 2, "centerline")
    for i, col in enumerate(cols, start=1):
        plan.rect(col["x"] - col["D"] / 2, yc - col["b"] / 2, col["D"], col["b"], "support")
        plan.text(col["x"], yc + max(col["b"], b) / 2 + 0.4 * th, f"C{i}", 0.8 * th, "middle")
    plan.line(c, yc, x_end - c, yc, "rebar")
    plan.dim(0, yc - W / 2, L1, yc - W / 2, -1.8 * th, f"L1 = {L1:.0f}", th)
    plan.dim(x2 - L2 / 2, yc - W / 2, x2 + L2 / 2, yc - W / 2, -1.8 * th, f"L2 = {L2:.0f}", th)
    plan.dim(0, W, cols[0]["x"], W, 1.6 * th, f"{cols[0]['x']:.0f}", th)
    plan.dim(cols[0]["x"], W, x2, W, 1.6 * th, f"s = {x2 - cols[0]['x']:.0f}", th)
    plan.dim(L1, yc - B1 / 2, L1, yc + B1 / 2, 0.8 * th, f"B1 = {B1:.0f}", th)
    plan.dim(x2 + L2 / 2, yc - B2 / 2, x2 + L2 / 2, yc + B2 / 2, 1.2 * th, f"B2 = {B2:.0f}", th)
    p1 = reinf["pad1"]
    plan.text(0, -3.6 * th, f"Strap {b:.0f} x {Ds:.0f}: top {st['top']['label']}, bottom {st['bottom']['label']}; stirrups "
              + ", ".join(f"T{z['dia']} @ {z['s']:.0f} {z['name']}" for z in st["zones"]) + ".", 0.7 * th, "start")
    plan.text(0, -4.6 * th, f"Pad 1: {p1['across']['label']} across, {p1['along']['label']} along. Pad 2: {reinf['pad2']['along_l']['label']} along, "
              f"{reinf['pad2']['along_b']['label']} across.", 0.7 * th, "start")

    # ------------------------------------------------------------------ elevation along the strap
    el = model.view("elevation", "Section along the strap", "to scale")
    te = max(x_end / 40.0, 0.12 * Ds)
    pcc = PCC_THICKNESS_MM
    el.rect(-150, -pcc, L1 + 300, pcc, "support")
    el.rect(x2 - L2 / 2 - 150, -pcc, L2 + 300, pcc, "support")
    el.rect(0, 0, L1, D1, "concrete")
    el.rect(x2 - L2 / 2, 0, L2, D2, "concrete")
    el.rect(0, 0, x_end, Ds, "concrete")
    stub = max(0.8 * Ds, 600.0)
    for col in cols:
        x0, x1 = col["x"] - col["D"] / 2, col["x"] + col["D"] / 2
        el.polyline([(x0, Ds), (x0, Ds + stub), (x1, Ds + stub), (x1, Ds)], closed=False, layer="concrete")
    yt = Ds - c - 12 - st["top"]["dia"] / 2
    yb = c + 12 + st["bottom"]["dia"] / 2
    if st["top"]["bent"]:
        leg = BEND_LEG_DIAMETERS * st["top"]["dia"]
        el.polyline([(c, yt - leg), (c, yt), (x_end - c, yt)], closed=False, layer="rebar")
    else:
        el.line(c, yt, x_end - c, yt, "rebar")
    el.line(c, yb, x_end - c, yb, "rebar")
    x = c + FIRST_STIRRUP_MM
    for z in st["zones"]:
        for _ in range(z["count"]):
            el.line(x, c, x, Ds - c, "stirrup")
            x += z["s"]
    el.line(L1, -pcc - 0.5 * te, L1, 0, "centerline")
    el.leader(0.3 * x2, yt, 0.25 * x2, Ds + 0.5 * stub, f"top: {st['top']['label']}", te)
    el.leader(0.55 * x2, yb, 0.6 * x2, -pcc - 2.4 * te, f"bottom: {st['bottom']['label']}", te)
    el.dim(0, -pcc, x_end, -pcc, -1.2 * te, f"{x_end:.0f}", te)
    el.dim(x_end, 0, x_end, Ds, 1.4 * te, f"D = {Ds:.0f}", te)
    el.text(x_end / 2, -pcc - 4.0 * te, "Stirrups: " + ", ".join(f"{z['count']} T{z['dia']} @ {z['s']:.0f} {z['name']}" for z in st["zones"])
            + "; keep the strap off the soil between the pads", 0.8 * te, "middle")

    # ------------------------------------------------------------------ section across pad 1
    sx = model.view("section", "Section across pad 1", "to scale")
    ts = max(B1 / 24.0, 0.12 * Ds)
    sx.rect(-150, -pcc, B1 + 300, pcc, "support")
    sx.rect(0, 0, B1, D1, "concrete")
    sx.rect((B1 - b) / 2, 0, b, Ds, "concrete")
    across = p1["across"]
    ya = c + across["dia"] / 2
    if across["bent"]:
        leg = BEND_LEG_DIAMETERS * across["dia"]
        sx.polyline([(c, ya + leg), (c, ya), (B1 - c, ya), (B1 - c, ya + leg)], closed=False, layer="rebar")
    else:
        sx.line(c, ya, B1 - c, ya, "rebar")
    along = p1["along"]
    for k in range(along["count"]):
        sx.circle(c + along["dia"] / 2 + k * along["spacing"], ya + across["dia"] / 2 + along["dia"] / 2, along["dia"] / 2, "rebar")
    o = c + 6
    sx.polyline([((B1 - b) / 2 + o, o), ((B1 + b) / 2 - o, o), ((B1 + b) / 2 - o, Ds - o), ((B1 - b) / 2 + o, Ds - o)], closed=True, layer="stirrup")
    for k in range(st["top"]["count"]):
        n = st["top"]["count"]
        xb = (B1 - b) / 2 + c + 12 + st["top"]["dia"] / 2 + k * (b - 2 * c - 24 - st["top"]["dia"]) / max(n - 1, 1)
        sx.circle(xb, yt, st["top"]["dia"] / 2, "rebar")
    sx.leader((B1 + b) / 2 - c, yt, B1 * 0.85, Ds + 1.2 * ts, f"strap top: {st['top']['label']}", 0.8 * ts)
    sx.leader(0.2 * B1, ya, 0.1 * B1, -pcc - 2.2 * ts, f"across: {across['label']}", 0.8 * ts)
    sx.dim(0, -pcc, B1, -pcc, -1.0 * ts, f"B1 = {B1:.0f}", ts)
    sx.dim(B1, 0, B1, D1, 1.2 * ts, f"{D1:.0f}", ts)

    model.notes = [
        f"Concrete M{inp.fck}; bars Fe {inp.fy}. Cover {c:.0f} mm.",
        "The strap is rigid and kept off the soil between the pads.",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
