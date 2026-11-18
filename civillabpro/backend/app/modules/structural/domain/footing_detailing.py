"""Footing detailing: bar bending schedule, quantities, plan and section."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight

if TYPE_CHECKING:
    from app.modules.structural.domain.footing import FootingInput

PCC_THICKNESS_MM = 75.0  # levelling course under the footing, measured with the footing
BEND_LEG_DIAMETERS = 12.0  # leg of an end bend: 90 degree bend plus a straight extension (IS 2502 practice)


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def bar_schedule(inp: FootingInput, reinf: dict[str, Any]) -> dict[str, Any]:
    L, B, c, dia = reinf["L"], reinf["B"], reinf["cover"], reinf["dia"]
    al, ab = reinf["along_l"], reinf["along_b"]
    items: list[dict[str, Any]] = []

    bent = reinf.get("bent_ends", False)
    leg = BEND_LEG_DIAMETERS * dia  # bent up at both ends where the straight length cannot develop the bar

    def add(desc: str, count: int, run: float) -> None:
        if count <= 0:
            return
        length = _ceil5(run + 2 * leg - 4 * dia) if bent else _ceil5(run)
        dims = {"A": round(run, 0), "B": round(leg, 0)} if bent else {"A": round(run, 0)}
        uw = bar_unit_weight(dia)
        items.append({"mark": chr(ord("a") + len(items)), "description": desc, "shape": "bent up 90 deg both ends" if bent else "straight", "dia": dia,
                      "count": count, "dims": dims, "cutting_length_mm": length, "total_length_m": round(count * length / 1000.0, 3),
                      "unit_weight_kg_m": round(uw, 4), "weight_kg": round(count * length / 1000.0 * uw, 2),
                      "formula": "A + 2B - 2 x 2d (two 90 deg bends); A = side - 2 cover" if bent else "A = side - 2 cover"})

    add(f"Bars along L, bottom, T{dia} at {al['spacing']:.0f}", al["count"], L - 2 * c)
    add(f"Bars along B, {'' if not ab['outer_count'] else 'central band, '}T{dia} at {ab['band_spacing']:.0f}", ab["band_count"], B - 2 * c)
    if ab["outer_count"]:
        add(f"Bars along B, outer parts, T{dia} at {ab['outer_spacing']:.0f}", 2 * ab["outer_count"], B - 2 * c)
    total = round(sum(i["weight_kg"] for i in items), 2)
    return {
        "member": inp.mark, "members": 1, "items": items,
        "summary": [{"dia": dia, "length_m": round(sum(i["total_length_m"] for i in items), 2), "weight_kg": total}],
        "total_weight_kg": total, "stirrup_count": 0,
        "notes": [
            "Bars along L are the outer (lower) layer. Bars along B: the central band of width B carries 2/(beta + 1) of them (IS 456 Cl. 34.3.1(b))"
            + ("; at the band spacing they already cover the whole length, so they are spread uniformly." if not ab["outer_count"] else "."),
            "Column bars or dowels into the footing are scheduled with the column; at least 0.5 percent of the column area (Cl. 34.4.3).",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no wastage.",
        ],
    }


def quantities(inp: FootingInput, reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
    L, B, D = reinf["L"], reinf["B"], reinf["D"]
    concrete = L * B * D * 1e-9
    steel = bbs["total_weight_kg"]
    pcc = (L + 300) * (B + 300) * PCC_THICKNESS_MM * 1e-9
    return {
        "length_m": round(L / 1000.0, 3),
        "concrete_m3": round(concrete, 3),
        "formwork_m2": round(2 * (L + B) * D * 1e-6, 3),
        "steel_kg": round(steel, 1),
        "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Reinforced concrete of the footing; formwork to its four sides.",
            f"Levelling course of plain concrete, {PCC_THICKNESS_MM:.0f} mm thick and 150 mm wider all round, {pcc:.3f} m3 (not included above).",
            "Excavation and backfill depend on the founding depth and are not measured here.",
        ],
    }


def drawing(inp: FootingInput, reinf: dict[str, Any]) -> dict[str, Any]:
    L, B, D, c, dia = reinf["L"], reinf["B"], reinf["D"], reinf["cover"], reinf["dia"]
    bc, dc = inp.column_width_mm, inp.column_depth_mm
    al, ab = reinf["along_l"], reinf["along_b"]
    model = DrawingModel(f"Footing {inp.mark}: reinforcement details")

    # ------------------------------------------------------------------ plan: L along x, B along y
    plan = model.view("plan", "Plan", "to scale")
    th = max(L, B) / 28.0
    plan.rect(0, 0, L, B, "concrete")
    plan.rect((L - dc) / 2, (B - bc) / 2, dc, bc, "support")
    uniform = not ab["outer_count"]  # nearly square: the band spacing suits the whole length
    if L > B and not uniform:  # central band boundaries
        for x in ((L - B) / 2, (L + B) / 2):
            plan.line(x, 0, x, B, "centerline")
        plan.text(L / 2, B + 0.6 * th, "central band, width B", 0.8 * th, "middle")
    xb = 0.22 * L
    plan.line(c, 0.30 * B, L - c, 0.30 * B, "rebar")  # a bar along L
    plan.line(xb, c, xb, B - c, "rebar")  # a bar along B
    plan.leader(0.62 * L, 0.30 * B, 0.70 * L, 0.12 * B, f"{al['label']} along L", th)
    plan.leader(xb, 0.75 * B, 0.08 * L, 0.88 * B,
                f"{ab['label']} along B" if uniform else
                f"T{dia} along B: {ab['band_count']} @ {ab['band_spacing']:.0f} in band, {ab['outer_count']} @ {ab['outer_spacing']:.0f} each outer part", th)
    plan.leader(L / 2 + dc / 2, B / 2 + bc / 2, L / 2 + dc / 2 + 0.12 * L, B / 2 + bc / 2 + 0.12 * B, f"column {bc:.0f} x {dc:.0f}", th)
    plan.dim(0, 0, L, 0, -2.2 * th, f"L = {L:.0f}", th)
    plan.dim(0, 0, 0, B, -2.2 * th, f"B = {B:.0f}", th)

    # ------------------------------------------------------------------ section along L
    sec = model.view("elevation", "Section along L", "to scale")
    ts = max(L / 32.0, 0.12 * D)
    pcc = 75.0
    sec.rect(-150, -pcc, L + 300, pcc, "support")  # levelling course
    sec.rect(0, 0, L, D, "concrete")
    stub = max(1.2 * D, 600.0)
    sec.polyline([((L - dc) / 2, D), ((L - dc) / 2, D + stub), ((L + dc) / 2, D + stub), ((L + dc) / 2, D)], closed=False, layer="concrete")
    yl = c + dia / 2
    sec.line(c, yl, L - c, yl, "rebar")
    n_show = min(int(round((L - 2 * c) / 150.0)), 40)
    for i in range(n_show + 1):  # bars along B seen end on
        sec.circle(c + dia / 2 + i * (L - 2 * c - dia) / max(n_show, 1), yl + dia, dia / 2, "rebar")
    for x in ((L - dc) / 2 + 50, (L + dc) / 2 - 50):  # column bars into the footing
        sec.polyline([(x, D + stub), (x, yl + 2 * dia), (x + (-1 if x < L / 2 else 1) * 300, yl + 2 * dia)], closed=False, layer="stirrup")
    sec.dim(0, -pcc, L, -pcc, -1.6 * ts, f"{L:.0f}", ts)
    sec.dim(L, 0, L, D, 1.6 * ts, f"D = {D:.0f}", ts)
    sec.text(L / 2, -pcc - 3.6 * ts, f"{pcc:.0f} mm levelling course", 0.8 * ts, "middle")
    sec.leader((L + dc) / 2 - 50, D + 0.6 * stub, (L + dc) / 2 + 0.15 * L, D + 0.75 * stub, "column bars (with the column)", ts)

    model.notes = [
        f"Concrete M{inp.fck}; bars Fe {inp.fy}. Cover {c:.0f} mm.",
        "Bars along L in the bottom layer; bars along B above them.",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
