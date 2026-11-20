"""Combined footing detailing: the bar layout, bar bending schedule, quantities, plan and sections."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight

if TYPE_CHECKING:
    from app.modules.structural.domain.combined_footing import CombinedFootingInput, Plan, Trial

PCC_THICKNESS_MM = 75.0  # levelling course under the footing, measured with the footing
BEND_LEG_DIAMETERS = 12.0  # leg of an end bend: 90 degree bend plus a straight extension (IS 2502 practice)


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def distribution_counts(L: float, cover: float, bands: list[dict[str, Any]], s: float) -> list[dict[str, Any]]:
    """Bars across outside the bands at spacing s: from each band's edge outwards to the ends, and between the bands."""
    (lo1, hi1), (lo2, hi2) = (bands[0]["lo"], bands[0]["hi"]), (bands[1]["lo"], bands[1]["hi"])
    out = []
    for lo, hi, kind in ((cover, lo1, "end"), (hi1, lo2, "middle"), (hi2, L - cover, "end")):
        ln = hi - lo
        if ln <= 0:
            n = 0
        elif kind == "end":
            n = math.floor(ln / s + 1e-9)  # at s, 2s, ... from the band's edge
        else:
            n = max(math.ceil(ln / s - 1e-9) - 1, 0)  # no gap wider than s between the bands' edges
        out.append({"lo": round(lo, 1), "hi": round(hi, 1), "count": n})
    return out


def reinforcement(inp: CombinedFootingInput, plan: Plan, t: Trial, cover: float) -> dict[str, Any]:
    assert t.bottom is not None and t.top is not None and t.dist is not None
    bands = []
    for i, b in enumerate(t.bands, start=1):
        g = b.bars
        assert g is not None
        bands.append({"column": i, "lo": round(b.lo, 1), "hi": round(b.hi, 1), "w": round(b.w, 1), "dia": g.dia, "count": g.n, "spacing": g.s,
                      "area": round(g.area, 1), "bent": g.bent, "label": f"{g.n}-T{g.dia} @ {g.s:.0f}"})
    segs = distribution_counts(plan.L, cover, bands, t.dist.s)
    n_dist = sum(s["count"] for s in segs)
    return {
        "L": plan.L, "B": plan.B, "D": t.D, "a": plan.a, "cover": cover,
        "columns": [{"x": c.x, "b": c.b, "D": c.D} for c in plan.cols],
        "layer_across": max(t.bands[0].bars.dia if t.bands[0].bars else 0, t.dist.dia),
        "bottom": {"dia": t.bottom.dia, "count": t.bottom.n, "spacing": t.bottom.s, "area": round(t.bottom.area, 1), "bent": t.bottom.bent,
                   "label": f"{t.bottom.n}-T{t.bottom.dia} @ {t.bottom.s:.0f}"},
        "top": {"dia": t.top.dia, "count": t.top.n, "spacing": t.top.s, "area": round(t.top.area, 1), "bent": t.top.bent,
                "label": f"{t.top.n}-T{t.top.dia} @ {t.top.s:.0f}"},
        "bands": bands,
        "dist": {"dia": t.dist.dia, "spacing": t.dist.s, "segments": segs, "count": n_dist, "label": f"{n_dist}-T{t.dist.dia} @ {t.dist.s:.0f}"},
    }


def bar_schedule(inp: CombinedFootingInput, reinf: dict[str, Any]) -> dict[str, Any]:
    L, B, c = reinf["L"], reinf["B"], reinf["cover"]
    items: list[dict[str, Any]] = []

    def add(desc: str, dia: int, count: int, run: float, bent: bool, which: str = "up") -> None:
        if count <= 0:
            return
        leg = BEND_LEG_DIAMETERS * dia
        length = _ceil5(run + 2 * leg - 4 * dia) if bent else _ceil5(run)
        uw = bar_unit_weight(dia)
        items.append({"mark": chr(ord("a") + len(items)), "description": desc, "shape": f"bent {which} 90 deg both ends" if bent else "straight",
                      "dia": dia, "count": count, "dims": {"A": round(run, 0), "B": round(leg, 0)} if bent else {"A": round(run, 0)},
                      "cutting_length_mm": length, "total_length_m": round(count * length / 1000.0, 3), "unit_weight_kg_m": round(uw, 4),
                      "weight_kg": round(count * length / 1000.0 * uw, 2),
                      "formula": "A + 2B - 2 x 2d (two 90 deg bends); A = side - 2 cover" if bent else "A = side - 2 cover"})

    bot, top, bands, dist = reinf["bottom"], reinf["top"], reinf["bands"], reinf["dist"]
    add(f"Bars along, bottom, T{bot['dia']} at {bot['spacing']:.0f}", bot["dia"], bot["count"], L - 2 * c, bot["bent"])
    add(f"Bars along, top, T{top['dia']} at {top['spacing']:.0f}", top["dia"], top["count"], L - 2 * c, top["bent"], "down")
    b1, b2 = bands
    if (b1["dia"], b1["spacing"], b1["bent"]) == (b2["dia"], b2["spacing"], b2["bent"]):
        add(f"Bars across, bands under both columns, T{b1['dia']} at {b1['spacing']:.0f}", b1["dia"], b1["count"] + b2["count"], B - 2 * c, b1["bent"])
    else:
        for b in bands:
            add(f"Bars across, band under column {b['column']}, T{b['dia']} at {b['spacing']:.0f}", b["dia"], b["count"], B - 2 * c, b["bent"])
    add(f"Bars across, outside the bands, T{dist['dia']} at {dist['spacing']:.0f}", dist["dia"], dist["count"], B - 2 * c, False)
    total = round(sum(i["weight_kg"] for i in items), 2)
    by_dia: dict[int, list[dict[str, Any]]] = {}
    for i in items:
        by_dia.setdefault(i["dia"], []).append(i)
    return {
        "member": inp.mark, "members": 1, "items": items,
        "summary": [{"dia": d, "length_m": round(sum(i["total_length_m"] for i in rows), 2), "weight_kg": round(sum(i["weight_kg"] for i in rows), 2)}
                    for d, rows in sorted(by_dia.items())],
        "total_weight_kg": total, "stirrup_count": 0,
        "notes": [
            "Bars across are the lowest layer, bars along the bottom rest on them; the top bars run the full length.",
            "Under each column the bars across are in a band of the column's length plus 0.75 d each side; elsewhere at the minimum.",
            "Chairs to hold the top bars, and the column bars or dowels (at least 0.5 percent of each column, Cl. 34.4.3), are not scheduled here.",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no wastage.",
        ],
    }


def quantities(inp: CombinedFootingInput, reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
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


def _band_positions(band: dict[str, Any], L: float, c: float) -> list[float]:
    n, s = band["count"], band["spacing"]
    mid = (band["lo"] + band["hi"]) / 2.0
    xs = [mid + (i - (n - 1) / 2.0) * s for i in range(n)]
    return [min(max(x, c + band["dia"] / 2.0), L - c - band["dia"] / 2.0) for x in xs]


def _dist_positions(reinf: dict[str, Any]) -> list[float]:
    s = reinf["dist"]["spacing"]
    (e1, mid, e2) = reinf["dist"]["segments"]
    xs = [e1["hi"] - (i + 1) * s for i in range(e1["count"])]
    if mid["count"]:
        step = (mid["hi"] - mid["lo"]) / (mid["count"] + 1)
        xs += [mid["lo"] + (i + 1) * step for i in range(mid["count"])]
    xs += [e2["lo"] + (i + 1) * s for i in range(e2["count"])]
    return xs


def drawing(inp: CombinedFootingInput, reinf: dict[str, Any]) -> dict[str, Any]:
    L, B, D, c, a = reinf["L"], reinf["B"], reinf["D"], reinf["cover"], reinf["a"]
    cols, bands, bot, top, dist = reinf["columns"], reinf["bands"], reinf["bottom"], reinf["top"], reinf["dist"]
    model = DrawingModel(f"Combined footing {inp.mark}: reinforcement details")

    # ------------------------------------------------------------------ plan: L along x, B along y
    plan = model.view("plan", "Plan", "to scale")
    th = max(L, B) / 36.0

    def fit(text: str, room: float) -> float:
        """A text height that keeps the text within the room it has (about 0.6 of the height per character)."""
        return max(min(0.8 * th, room / (0.7 * len(text))), 0.25 * th)

    plan.rect(0, 0, L, B, "concrete")
    for i, col in enumerate(cols, start=1):
        plan.rect(col["x"] - col["D"] / 2, (B - col["b"]) / 2, col["D"], col["b"], "support")
        label = f"C{i} {col['b']:.0f} x {col['D']:.0f}"
        plan.text(col["x"], (B + col["b"]) / 2 + 0.3 * fit(label, 1.6 * col["D"]), label, fit(label, 1.6 * col["D"]), "middle")
        plan.line(col["x"], -0.6 * th, col["x"], B + 0.6 * th, "centerline")
    room = B - 2 * c - 0.4 * th

    def bar_label(x: float, label: str) -> None:
        """Along the bar where it fits (the legend below the plan names every set in any case)."""
        if fit(label, room) > 0.4 * th:
            plan.text(x - 0.15 * th, c + 0.2 * th, label, fit(label, room), "start", vertical=True)

    for b in bands:
        for x in (b["lo"], b["hi"]):
            if 0 < x < L:
                plan.line(x, 0, x, B, "centerline")
        xb = b["hi"] - 0.12 * (b["hi"] - b["lo"]) if b["column"] == 1 else b["lo"] + 0.2 * (b["hi"] - b["lo"])  # on the gap's side
        plan.line(xb, c, xb, B - c, "rebar")
        bar_label(xb, f"band {b['column']}: {b['label']}")
    gap0, gap1 = bands[0]["hi"], bands[1]["lo"]
    if gap1 - gap0 > 0:
        xm = (gap0 + gap1) / 2
        plan.line(xm, c, xm, B - c, "rebar")
        bar_label(xm, f"{dist['label']} outside the bands")
    for y, layer in ((0.30 * B, "rebar"), (0.70 * B, "stirrup")):  # bars along: bottom, top
        plan.line(c, y, L - c, y, layer)  # type: ignore[arg-type]
    plan.dim(0, 0, L, 0, -2.0 * th, f"L = {L:.0f}", th)
    plan.dim(0, 0, 0, B, -2.2 * th, f"B = {B:.0f}", th)
    plan.dim(0, B, cols[0]["x"], B, 1.6 * th, f"{a:.0f}", th)
    plan.dim(cols[0]["x"], B, cols[1]["x"], B, 1.6 * th, f"{cols[1]['x'] - cols[0]['x']:.0f}", th)
    plan.dim(cols[1]["x"], B, L, B, 1.6 * th, f"{L - cols[1]['x']:.0f}", th)
    plan.text(0, -3.6 * th, f"Bars along: bottom {bot['label']} (red), top {top['label']} (blue), the full length.", 0.7 * th, "start")
    plan.text(0, -4.6 * th, f"Bars across: band 1 {bands[0]['label']}, band 2 {bands[1]['label']} (between the thin lines across), elsewhere "
                            f"{dist['label']}.", 0.7 * th, "start")

    # ------------------------------------------------------------------ section along L
    sec = model.view("elevation", "Section along the footing", "to scale")
    ts = max(L / 40.0, 0.12 * D)
    pcc = PCC_THICKNESS_MM
    sec.rect(-150, -pcc, L + 300, pcc, "support")
    sec.rect(0, 0, L, D, "concrete")
    stub = max(1.0 * D, 600.0)
    for col in cols:
        x0, x1 = col["x"] - col["D"] / 2, col["x"] + col["D"] / 2
        sec.polyline([(x0, D), (x0, D + stub), (x1, D + stub), (x1, D)], closed=False, layer="concrete")
        for x in (x0 + 50, x1 - 50):  # column bars into the footing
            sec.polyline([(x, D + stub), (x, c + 3 * bot["dia"]), (x + (300 if x < col["x"] else -300), c + 3 * bot["dia"])], closed=False, layer="stirrup")
    y_across = c + reinf["layer_across"] / 2
    y_bot = c + reinf["layer_across"] + bot["dia"] / 2
    y_top = D - c - top["dia"] / 2
    leg_b, leg_t = 12 * bot["dia"], 12 * top["dia"]
    if bot["bent"]:
        sec.polyline([(c, y_bot + leg_b), (c, y_bot), (L - c, y_bot), (L - c, y_bot + leg_b)], closed=False, layer="rebar")
    else:
        sec.line(c, y_bot, L - c, y_bot, "rebar")
    if top["bent"]:
        sec.polyline([(c, y_top - leg_t), (c, y_top), (L - c, y_top), (L - c, y_top - leg_t)], closed=False, layer="rebar")
    else:
        sec.line(c, y_top, L - c, y_top, "rebar")
    xs = [x for b in bands for x in _band_positions(b, L, c)] + _dist_positions(reinf)
    for x in xs[:200]:
        sec.circle(x, y_across, max(bands[0]["dia"], dist["dia"]) / 2, "rebar")
    for b in bands:
        if 0 < b["lo"]:
            sec.line(b["lo"], -pcc - 0.4 * ts, b["lo"], 0, "centerline")
        if b["hi"] < L:
            sec.line(b["hi"], -pcc - 0.4 * ts, b["hi"], 0, "centerline")
    sec.leader(0.30 * L, y_top, 0.26 * L, D + 0.5 * stub, f"top: {top['label']}", ts)
    sec.leader(0.70 * L, y_bot, 0.74 * L, -pcc - 2.6 * ts, f"bottom: {bot['label']}", ts)
    sec.dim(0, -pcc, L, -pcc, -1.4 * ts, f"{L:.0f}", ts)
    sec.dim(L, 0, L, D, 1.6 * ts, f"D = {D:.0f}", ts)
    sec.text(L / 2, -pcc - 4.2 * ts, f"{pcc:.0f} mm levelling course; the ticks below mark the bands of bars across under the columns", 0.8 * ts,
             "middle")

    # ------------------------------------------------------------------ section across, under column 2
    x2 = model.view("section", "Section across, under column 2", "to scale")
    tb = max(B / 24.0, 0.12 * D)
    col = cols[1]
    band = bands[1]
    x2.rect(-150, -pcc, B + 300, pcc, "support")
    x2.rect(0, 0, B, D, "concrete")
    x2.polyline([((B - col["b"]) / 2, D), ((B - col["b"]) / 2, D + stub), ((B + col["b"]) / 2, D + stub), ((B + col["b"]) / 2, D)], closed=False,
                layer="concrete")
    leg = 12 * band["dia"]
    if band["bent"]:
        x2.polyline([(c, y_across + leg), (c, y_across), (B - c, y_across), (B - c, y_across + leg)], closed=False, layer="rebar")
    else:
        x2.line(c, y_across, B - c, y_across, "rebar")
    for k in range(bot["count"]):
        x2.circle(c + bot["dia"] / 2 + k * bot["spacing"], y_bot, bot["dia"] / 2, "rebar")
    for k in range(top["count"]):
        x2.circle(c + top["dia"] / 2 + k * top["spacing"], y_top, top["dia"] / 2, "rebar")
    x2.leader(0.25 * B, y_across, 0.12 * B, -pcc - 2.4 * tb, f"band: {band['label']}", 0.8 * tb)
    x2.leader(0.8 * B, y_top, 0.86 * B, D + 0.5 * stub, f"top: {top['label']}", 0.8 * tb)
    x2.dim(0, -pcc, B, -pcc, -1.2 * tb, f"B = {B:.0f}", tb)
    x2.dim(B, 0, B, D, 1.6 * tb, f"D = {D:.0f}", tb)

    model.notes = [
        f"Concrete M{inp.fck}; bars Fe {inp.fy}. Cover {c:.0f} mm.",
        "Bars across in the lowest layer, bars along the bottom above them; top bars along the full length.",
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()
