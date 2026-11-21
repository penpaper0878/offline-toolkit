"""Detailing of the continuous beam by the elastic method: layout of the top bars, bar bending schedule, quantities and drawing.

Every span and every interior support has its own bars. Top bars over a support are centred on it and run into each
span to their own extent; between them hangers lap in compression (Cl. 26.2.5.1(d)); where the support bars of a span
would leave no room for that, they run on and lap with each other in tension (Cl. 26.2.5.1(c)), or in an end span run
on to the end support. Rows of the schedule that are alike (same shape, size and lengths) are merged across spans and
supports. Lengths follow IS 2502 practice as for the simple beam.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from app.engineering import is456
from app.engineering.drawing import DrawingModel
from app.engineering.rebar import bar_unit_weight, bend_radius
from app.engineering.trace import CalcSheet
from app.modules.structural.domain.beam_detailing import cross_section, hook_allowance
from app.modules.structural.domain.continuous_beam import support_widths

if TYPE_CHECKING:
    from app.modules.structural.domain.continuous_beam import ContinuousBeamInput

FIRST_STIRRUP_MM = 50.0


def _ceil5(x: float) -> float:
    return math.ceil(x / 5.0 - 1e-9) * 5.0


def lap_compression(dia: float, fck: float, fy: float) -> float:
    """Cl. 26.2.5.1(d): L_d in compression, at least 24 phi."""
    return max(is456.development_length(dia, fck, fy, compression=True), 24.0 * dia)


def lap_tension(dia: float, fck: float, fy: float) -> float:
    """Cl. 26.2.5.1(c): L_d, at least 30 phi."""
    return max(is456.development_length(dia, fck, fy), 30.0 * dia)


def layout(inp: ContinuousBeamInput, reinf: dict[str, Any]) -> list[dict[str, Any]]:
    """For each span, the extents of the support bars from its left and right faces, and its hangers or the lap between them.

    kind: "hanger" (hangers lap with the support bars in compression), "meet" (the support bars lap with each other in tension) or
    "run_on" (an end span's support bars run on to the end support).
    """
    ws, cover, n = support_widths(inp), reinf["cover"], reinf["spans"]
    fck, fy = float(inp.fck), float(inp.fy)
    out = []
    for i in range(n):
        sp = reinf["span"][i]
        lc = sp["lc"]
        left, right = reinf["support"][i], reinf["support"][i + 1]
        lap = lap_compression(sp["top"]["dia"], fck, fy)
        a_l = left["into_right"] if left else 0.0
        a_r = right["into_left"] if right else 0.0
        if left and right:
            if lc - a_l - a_r > 2.0 * lap:
                out.append({"kind": "hanger", "a_left": a_l, "a_right": a_r, "hanger": lc - a_l - a_r + 2.0 * lap, "lap": lap,
                            "h_from": a_l - lap, "h_to": lc - a_r + lap})
            else:
                lt = lap_tension(max(left["top"]["dia"], right["top"]["dia"]), fck, fy)
                half = (lc + lt) / 2.0
                out.append({"kind": "meet", "a_left": max(a_l, half), "a_right": max(a_r, half), "hanger": 0.0, "lap": lt})
        elif right:  # first span: the end support at its left
            sw = ws[0]
            if lc - a_r > lap:
                out.append({"kind": "hanger", "a_left": 0.0, "a_right": a_r, "hanger": (sw - cover) + (lc - a_r) + lap, "lap": lap,
                            "h_from": -(sw - cover), "h_to": lc - a_r + lap})
            else:
                out.append({"kind": "run_on", "a_left": 0.0, "a_right": lc + sw - cover, "hanger": 0.0, "lap": 0.0})
        else:  # last span: the end support at its right
            assert left is not None
            sw = ws[n]
            if lc - a_l > lap:
                out.append({"kind": "hanger", "a_left": a_l, "a_right": 0.0, "hanger": (sw - cover) + (lc - a_l) + lap, "lap": lap,
                            "h_from": a_l - lap, "h_to": lc + sw - cover})
            else:
                out.append({"kind": "run_on", "a_left": lc + sw - cover, "a_right": 0.0, "hanger": 0.0, "lap": 0.0})
    return out


def _where(kind: str, nums: list[int]) -> str:
    nums = sorted(set(nums))
    if len(nums) == 1:
        return f"{kind} {nums[0]}"
    return f"{kind}s {', '.join(str(k) for k in nums[:-1])} and {nums[-1]}"


def bar_schedule(inp: ContinuousBeamInput, reinf: dict[str, Any], sheet: CalcSheet) -> dict[str, Any]:
    n, ws, b, D = reinf["spans"], support_widths(inp), inp.width_mm, inp.depth_mm
    fck, fy = float(inp.fck), float(inp.fy)
    cover = reinf["cover"]
    embeds = [w - cover for w in ws]  # the bars run to the far face of each support less cover
    lay, cp, st = reinf["layout"], reinf["curtailment"], reinf["stirrups"]
    rows: list[dict[str, Any]] = []

    def add(role: str, kind: str, num: int, shape: str, dia: int, count: int, dims: dict[str, float], length: float, formula: str) -> None:
        if count <= 0:
            return
        rows.append({"role": role, "kind": kind, "num": num, "shape": shape, "dia": dia, "count": count,
                     "dims": {k: round(v, 0) for k, v in dims.items()}, "length": _ceil5(length), "formula": formula})

    def comp_ext(dia: float, sup: dict[str, Any] | None, j: int) -> float:
        """Past the far face of support j where its section uses the bottom bars in compression (Cl. 26.2.1)."""
        if sup is None or not sup["doubly"]:
            return 0.0
        return max(0.0, is456.development_length(dia, fck, fy, compression=True) - embeds[j])

    # ---- bottom bars of each span
    for i in range(n):
        sp, cut = reinf["span"][i], cp["bottom"][i]
        lc = sp["lc"]
        run_g = cut["continuing"] if cut else sp["bottom"]
        dia = run_g["dia"]
        left_sup, right_sup = reinf["support"][i], reinf["support"][i + 1]
        run = lc + embeds[i] + embeds[i + 1] + comp_ext(dia, left_sup, i) + comp_ext(dia, right_sup, i + 1)
        role = f"Bottom bars, {run_g['label']}" + (" continuing" if cut else "")
        # the end details belong to simple end supports; a cantilever's support takes the bars on like an interior one
        ends = ([cp["end_detail"]["left"]] if i == 0 and left_sup is None else []) + (
            [cp["end_detail"]["right"]] if i == n - 1 and right_sup is None else [])
        ld3 = is456.development_length(dia, fck, fy) / 3.0
        embed = embeds[0] if i == 0 and left_sup is None else embeds[n]  # the end support's
        if "hook" in ends:
            h_al = _ceil5(hook_allowance(dia, fy))
            add(role, "span", i + 1, "U-hook at the end support", dia, run_g["count"], {"A": run, "hook": h_al}, run + h_al,
                "A + hook (standard U-hook, IS 2502)")
        elif ends and (ends[0] == "bend" or embed < ld3):
            leg = _ceil5(max(9.0 * dia, ld3 - embed + 2.0 * dia))
            add(role, "span", i + 1, "L-bend at the end support", dia, run_g["count"], {"A": run, "B": leg}, run + leg - 2.0 * dia,
                "A + B - 2d (one 90 deg bend)")
        else:
            add(role, "span", i + 1, "straight", dia, run_g["count"], {"A": run}, run, "A")
        if cut:
            c_len = lc - cut["left"] - cut["right"]
            add(f"Bottom bars, curtailed, {cut['curtailed']['label']}, {cut['left']:.0f} and {cut['right']:.0f} from the left and right faces",
                "span", i + 1, "straight", cut["curtailed"]["dia"], cut["curtailed"]["count"], {"A": c_len}, c_len, "A = clear span - both cut-off distances")
    # ---- top bars over each support that has them; over a cantilever's support they run to the tip and are bent down there
    cants = reinf.get("cantilever", {})
    tip_leg = _ceil5(D - 2.0 * (cover + st[0]["dia"]))
    for j in range(n + 1):
        sup, tc = reinf["support"][j], cp["top"][j]
        if sup is None:
            continue
        side = "left" if j == 0 else "right" if j == n else None
        if side is not None:
            a_c = cants[side]["lc"] - cover
            a_s = lay[0]["a_left"] if j == 0 else lay[n - 1]["a_right"]
            length = ws[j] + a_c + a_s
            add(f"Top bars over the support and the {side} cantilever, {sup['top']['label']}, to the tip and {a_s:.0f} into the span", "support",
                j + 1, "L-bend at the cantilever tip", sup["top"]["dia"], sup["top"]["count"], {"A": length, "B": tip_leg},
                length + tip_leg - 2.0 * sup["top"]["dia"], "A + B - 2d (bent down at the tip)")
            continue
        a_l, a_r = lay[j - 1]["a_right"], lay[j]["a_left"]
        long_ = tc["long"] if tc else sup["top"]
        length = ws[j] + a_l + a_r
        add(f"Top bars over the support, {long_['label']}" + (" long" if tc else "") + f", {a_l:.0f} and {a_r:.0f} into the spans",
            "support", j + 1, "straight", long_["dia"], long_["count"], {"A": length}, length, "A = support + extents into both spans")
        if tc:
            len_s = ws[j] + tc["cut"]["left"] + tc["cut"]["right"]
            add(f"Top bars over the support, short, {tc['short']['label']}, {tc['cut']['left']:.0f} and {tc['cut']['right']:.0f} into the spans",
                "support", j + 1, "straight", tc["short"]["dia"], tc["short"]["count"], {"A": len_s}, len_s, "A = support + cut-off distances")
    # ---- hangers
    for i in range(n):
        sp, s_ = reinf["span"][i], lay[i]
        if s_["hanger"] > 0:
            role = "compression bars" if sp["doubly"] else "hangers"
            add(f"Top {role}, {sp['top']['label']}", "span", i + 1, "straight", sp["top"]["dia"], sp["top"]["count"], {"A": s_["hanger"]},
                s_["hanger"], "A = span - support bar extents + laps (to the end support in an end span)")
    # ---- the cantilevers' bottom bars (two, the hanger size) and stirrups
    for side, c in cants.items():
        j = 0 if side == "left" else n
        hd = inp.hanger_bar_dia_mm
        run_c = c["lc"] - cover + ws[j] - cover
        add(f"Bottom bars of the {side} cantilever, 2-T{hd}, from the tip into the support", "support", j + 1, "straight", hd, 2, {"A": run_c},
            run_c, "A = projection + support - 2 x cover")
    # ---- side face bars
    side = reinf.get("side_face")
    if side:
        for i in range(n):
            run_s = reinf["span"][i]["lc"] + embeds[i] + embeds[i + 1]
            add(f"Side face bars, {side['label']}", "span", i + 1, "straight", side["dia"], 2 * side["per_face"], {"A": run_s}, run_s, "A")
    # ---- stirrups
    dst = st[0]["dia"]
    a_st, h_st = b - 2.0 * cover, D - 2.0 * cover
    hook = max(10.0 * dst, 75.0)
    formula = "2(A + B) + 2 x hook - 3 x 2d - 2 x 3d (three 90 deg and two 135 deg bends)"
    counts = []
    for i in range(n):
        z = cp["zones"][i]
        per = len(z["positions"])
        counts.append(per)
        desc = f"Stirrups, T{dst} {st[i]['legs']}-legged, {z['s_mid']:.0f} c/c" + (
            f", closer in {len(z['bands'])} band{'s' if len(z['bands']) > 1 else ''} (down to {min(bd[2] for bd in z['bands']):.0f} c/c)"
            if z["bands"] else "") + f", {per} per span"
        add(desc, "span", i + 1, "closed stirrup, 135 deg hooks", dst, per, {"A": a_st, "B": h_st, "hook": hook},
            2.0 * (a_st + h_st) + 2.0 * hook - 12.0 * dst, formula)
        if st[i]["legs"] == 4:
            first = reinf["span"][i]["bottom"]
            n1 = first["layers"][0]
            pitch = (a_st - 2.0 * dst - first["dia"]) / (n1 - 1)
            a_in = _ceil5((n1 - 3) * pitch + first["dia"] + 2.0 * dst)
            add(f"Inner stirrups, T{dst}, with the stirrups, {per} per span", "span", i + 1, "closed stirrup, 135 deg hooks", dst, per,
                {"A": a_in, "B": h_st, "hook": hook}, 2.0 * (a_in + h_st) + 2.0 * hook - 12.0 * dst, formula)

    for side, c in cants.items():
        per = len(c["positions"])
        counts.append(per)
        num = (0 if side == "left" else n) + 1
        add(f"Stirrups of the {side} cantilever, T{dst} {inp.stirrup_legs}-legged at {c['spacing']:.0f} c/c, {per}", "support", num,
            "closed stirrup, 135 deg hooks", dst, per, {"A": a_st, "B": h_st, "hook": hook}, 2.0 * (a_st + h_st) + 2.0 * hook - 12.0 * dst, formula)
        if inp.stirrup_legs == 4:
            first = reinf["support"][num - 1]["top"]
            n1 = first["layers"][0]
            pitch = (a_st - 2.0 * dst - first["dia"]) / max(n1 - 1, 1)
            a_in = _ceil5(max(n1 - 3, 1) * pitch + first["dia"] + 2.0 * dst)
            add(f"Inner stirrups of the {side} cantilever, T{dst}, with the stirrups, {per}", "support", num, "closed stirrup, 135 deg hooks", dst,
                per, {"A": a_in, "B": h_st, "hook": hook}, 2.0 * (a_in + h_st) + 2.0 * hook - 12.0 * dst, formula)

    # ---- merge alike rows across spans and supports
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        key = (r["role"], r["kind"], r["shape"], r["dia"], r["count"], tuple(sorted(r["dims"].items())), r["length"], r["formula"])
        merged.setdefault(key, {**r, "nums": []})["nums"].append(r["num"])
    items: list[dict[str, Any]] = []
    for r in merged.values():
        count = r["count"] * len(r["nums"])
        uw = bar_unit_weight(r["dia"])
        items.append({"mark": chr(ord("a") + len(items)) if len(items) < 26 else f"a{chr(ord('a') + len(items) - 26)}",
                      "description": f"{r['role']}, {_where(r['kind'], r['nums'])}", "shape": r["shape"], "dia": r["dia"], "count": count,
                      "dims": r["dims"], "cutting_length_mm": r["length"], "total_length_m": round(count * r["length"] / 1000.0, 3),
                      "unit_weight_kg_m": round(uw, 4), "weight_kg": round(count * r["length"] / 1000.0 * uw, 2), "formula": r["formula"]})

    by_dia: dict[int, dict[str, float]] = {}
    for it in items:
        e = by_dia.setdefault(it["dia"], {"length_m": 0.0, "weight_kg": 0.0})
        e["length_m"] += it["total_length_m"]
        e["weight_kg"] += it["weight_kg"]
    summary = [{"dia": k, "length_m": round(v["length_m"], 2), "weight_kg": round(v["weight_kg"], 2)} for k, v in sorted(by_dia.items())]
    spans = ", ".join(f"{reinf['span'][i]['lc']:.0f}" for i in range(n))
    return {
        "member": inp.mark, "members": 1, "items": items, "summary": summary,
        "total_weight_kg": round(sum(x["weight_kg"] for x in summary), 2), "stirrup_count": sum(counts), "stirrups_per_span": counts,
        "notes": [
            f"The whole beam: {n} spans of {spans} mm clear on supports "
            + (f"{ws[0]:.0f} mm wide" if len(set(ws)) == 1 else f"{', '.join(f'{w:.0f}' for w in ws)} mm wide") + f", numbered from the left; supports 1 and {n + 1} "
            "are the end supports. Counts include every span and support named.",
            "Top bars over a support are centred on it and run into each span to the extents given; hangers lap with them in compression "
            "(IS 456 Cl. 26.2.5.1(d)).",
            "Bottom bars run to the far face of each support less cover; at the end supports they are anchored as shown (Cl. 26.2.3.3).",
            "Cutting lengths to IS 2502:1963 practice, rounded up to 5 mm. Unit mass from 7850 kg/m3; no laps beyond those shown, no wastage.",
        ],
    }


def quantities(inp: ContinuousBeamInput, bbs: dict[str, Any]) -> dict[str, Any]:
    rows, ws, b, D = inp.span_table, support_widths(inp), inp.width_mm, inp.depth_mm
    flanged = inp.section != "rectangular"
    rib = D - inp.flange_thickness_mm if flanged else D
    clear = sum(r.clear_span_mm for r in rows) + inp.cantilever_left_mm + inp.cantilever_right_mm
    length = clear + sum(ws)
    concrete = b * rib * length * 1e-9
    sides = rib + D if inp.section == "l_beam" else 2.0 * rib
    formwork = (b + sides) * clear * 1e-6
    steel = bbs["total_weight_kg"]
    return {
        "length_m": round(length / 1000.0, 3), "concrete_m3": round(concrete, 3), "formwork_m2": round(formwork, 3),
        "steel_kg": round(steel, 1), "steel_kg_per_m3": round(steel / concrete, 1) if concrete > 0 else None,
        "basis": [
            "Concrete over the whole length, the supports included" + ("; the rib below the slab only." if flanged else "."),
            "Formwork: soffit and sides over the clear spans and the cantilevers" + (" (an L-beam's outer face to the full depth)." if inp.section == "l_beam" else "."),
            "Steel from the bar bending schedule, the whole beam.",
        ],
    }


def drawing(inp: ContinuousBeamInput, reinf: dict[str, Any], bbs: dict[str, Any]) -> dict[str, Any]:
    """An elevation of every span, with its supports, and two cross-sections."""
    n, ws, b, D = reinf["spans"], support_widths(inp), inp.width_mm, inp.depth_mm
    cover = reinf["cover"]
    lay, cp, st = reinf["layout"], reinf["curtailment"], reinf["stirrups"]
    shape = reinf["section"]
    flanged = shape["kind"] != "rectangular"
    dst = st[0]["dia"]
    model = DrawingModel(f"Continuous beam {inp.mark}: reinforcement details")
    sh = 0.5 * D

    for i in range(n):
        sp, s_, cut = reinf["span"][i], lay[i], cp["bottom"][i]
        lc = sp["lc"]
        wl, wr = ws[i], ws[i + 1]
        total = wl + lc + wr
        left, right = reinf["support"][i], reinf["support"][i + 1]
        el = model.view(f"elevation_{i + 1}", f"Span {i + 1}: support {i + 1} to support {i + 2}", "to scale")
        te = min(max(total / 55.0, 0.10 * D), 0.30 * D)
        el.rect(0, -sh, wl, sh, "support")
        el.rect(wl + lc, -sh, wr, sh, "support")
        el.rect(0, 0, total, D, "concrete")
        if flanged:
            el.line(0, D - shape["df"], total, D - shape["df"], "centerline")
        bot = sp["bottom"]
        y_b = cover + dst + bot["dia"] / 2.0
        # bottom bars, with the end detail at an end support
        simple_l, simple_r = i == 0 and left is None, i == n - 1 and right is None  # simple end supports (no cantilever beyond)
        x0, x1 = (cover if simple_l else 0.0), (total - cover if simple_r else total)
        detail = (cp["end_detail"]["left"] if simple_l else None, cp["end_detail"]["right"] if simple_r else None)
        dia = (cut["continuing"] if cut else bot)["dia"]
        rad = bend_radius(dia, inp.fy) + dia / 2.0
        for at_left, d_ in ((True, detail[0]), (False, detail[1])):
            if d_ is None:
                continue
            sgn, xf = (1.0, cover) if at_left else (-1.0, total - cover)
            if d_ == "hook":
                cx = xf + sgn * (dia / 2.0 + rad)
                arc = [(cx - sgn * rad * math.sin(math.pi * k / 12), y_b + rad - rad * math.cos(math.pi * k / 12)) for k in range(13)]
                el.polyline([*arc, (cx + sgn * 4.0 * dia, y_b + 2.0 * rad)], closed=False, layer="rebar")
                if at_left:
                    x0 = cx
                else:
                    x1 = cx
            else:
                ld3 = is456.development_length(dia, float(inp.fck), float(inp.fy)) / 3.0
                w_end = wl if at_left else wr
                if d_ == "bend" or w_end - cover < ld3:
                    el.line(xf, y_b, xf, y_b + _ceil5(max(9.0 * dia, ld3 - (w_end - cover) + 2.0 * dia)), "rebar")
        el.line(x0, y_b, x1, y_b, "rebar")
        if cut:
            y_c = y_b + 1.6 * bot["dia"]
            el.line(wl + cut["left"], y_c, wl + lc - cut["right"], y_c, "rebar")
            el.dim(wl, 0.0, wl + cut["left"], 0.0, -1.2 * te, f"{cut['left']:.0f}", te)
        # top bars over the supports at each end of the span
        for at_left, sup in ((True, left), (False, right)):
            if sup is None:
                continue
            j = i if at_left else i + 1
            y_t = D - (cover + dst + sup["top"]["dia"] / 2.0)
            a = s_["a_left"] if at_left else s_["a_right"]
            if at_left:
                el.line(0.0, y_t, min(wl + a, total), y_t, "rebar")
                el.dim(wl, D, min(wl + a, wl + lc), D, 2.2 * te, f"{a:.0f}", te)
            else:
                el.line(max(wl + lc - a, 0.0), y_t, total, y_t, "rebar")
                el.dim(max(wl + lc - a, wl), D, wl + lc, D, 2.2 * te, f"{a:.0f}", te)
            tc = cp["top"][j]
            if tc:
                y_s = y_t - 1.6 * sup["top"]["dia"]
                c = tc["cut"]["right" if at_left else "left"]
                if at_left:
                    el.line(0.0, y_s, wl + c, y_s, "rebar")
                else:
                    el.line(wl + lc - c, y_s, total, y_s, "rebar")
            el.text(wl / 2.0 if at_left else wl + lc + wr / 2.0, D + 6.2 * te, f"{sup['top']['label']} top over support {j + 1}", te,
                    "start" if at_left else "end")
        # hangers
        if s_["hanger"] > 0:
            y_h = D - (cover + dst + sp["top"]["dia"] / 2.0) - 0.8 * sp["top"]["dia"]
            el.line(max(wl + s_["h_from"], cover), y_h, min(wl + s_["h_to"], total - cover), y_h, "stirrup")
            el.text(wl + 0.5 * lc, D - 2.2 * te, f"{sp['top']['label']} {'compression bars' if sp['doubly'] else 'hangers'}", 0.8 * te, "middle")
        # stirrups
        xs = [wl + p for p in cp["zones"][i]["positions"]]
        for x in xs[::max(1, math.ceil(len(xs) / 120))]:
            el.line(x, cover, x, D - cover, "stirrup")
        # dimensions and labels
        el.dim(wl, -sh, wl + lc, -sh, -2.0 * te, f"{lc:.0f} clear", te)
        el.dim(0, -sh, wl, -sh, -2.0 * te, f"{wl:.0f}", te)
        el.dim(wl + lc, -sh, total, -sh, -2.0 * te, f"{wr:.0f}", te)
        el.dim(0, 0, 0, D, -2.0 * te, f"{D:.0f}", te)
        z = cp["zones"][i]
        band_text = "; ".join(f"{x0_:.0f}-{x1_:.0f} @ {s:.0f}" for x0_, x1_, s in z["bands"])
        el.text(wl + lc / 2.0, -sh - 5.0 * te, f"{bot['label']} bottom; stirrups {st[i]['label'].split(' @ ')[0]} @ {z['s_mid']:.0f}"
                + (f", closer {band_text}" if band_text else ""), te, "middle")

    # ------------------------------------------------------------------ cantilevers
    for side, c in reinf.get("cantilever", {}).items():
        j = 0 if side == "left" else n
        sup = reinf["support"][j]
        lc = c["lc"]
        sw = ws[j]
        total = sw + lc
        te = min(max(total / 55.0, 0.08 * D), 0.25 * D)
        el = model.view(f"cantilever_{side}", f"The {side} cantilever at support {j + 1}", "to scale")
        # drawn with the support on the left whichever end it is; the free end on the right
        el.rect(0, -sh, sw, sh, "support")
        el.rect(0, 0, total, D, "concrete")
        if flanged:
            el.line(0, D - shape["df"], total, D - shape["df"], "centerline")
        y_t = D - (cover + dst + sup["top"]["dia"] / 2.0)
        leg = _ceil5(D - 2.0 * (cover + dst))
        el.line(0.0, y_t, total - cover, y_t, "rebar")
        el.line(total - cover, y_t, total - cover, y_t - leg + sup["top"]["dia"], "rebar")
        hd = inp.hanger_bar_dia_mm
        y_b = cover + dst + hd / 2.0
        el.line(cover, y_b, total - cover, y_b, "rebar")
        for x in c["positions"]:
            el.line(sw + x, cover, sw + x, D - cover, "stirrup")
        el.dim(sw, -sh, total, -sh, -2.0 * te, f"{lc:.0f} projection", te)
        el.dim(0, -sh, sw, -sh, -2.0 * te, f"{sw:.0f}", te)
        el.dim(total, 0, total, D, 2.0 * te, f"{D:.0f}", te)
        el.text(sw / 2.0, D + 2.6 * te, f"{sup['top']['label']} top, to the tip and bent down; into the span as shown there", te, "start")
        el.text(sw + lc / 2.0, -sh - 5.0 * te, f"2-T{hd} bottom; stirrups T{dst} {inp.stirrup_legs}-legged @ {c['spacing']:.0f}", te, "middle")

    # ------------------------------------------------------------------ cross-sections: the heaviest span and support
    sec = model.view("sections", "Sections A-A and B-B", "to scale")
    i_a = max(range(n), key=lambda k: reinf["span"][k]["bottom"]["area"])
    sp = reinf["span"][i_a]
    stir = {"dia": dst, "legs": st[i_a]["legs"], "label": st[i_a]["label"]}
    inner_a = next((it["dims"]["A"] for it in bbs["items"] if it["description"].startswith("Inner stirrups")), None)
    th, right_x = cross_section(sec, 0.0, b, D, cover, stir, sp["top"], sp["bottom"], 0.0, sp["gap"], shape, reinf.get("side_face"), inner_a,
                                f"A-A: span {i_a + 1}, greatest moment")
    e_l = 0.0
    if flanged:
        tee = shape["kind"] == "t_beam"
        e_l = min((shape["bf"] - b) / (2.0 if tee else 1.0), max(1.2 * b, 300.0))
    j_b = max((k for k in range(n + 1) if reinf["support"][k] is not None), key=lambda k: reinf["support"][k]["top"]["area"])
    sup = reinf["support"][j_b]
    lo = min((k for k in (j_b - 1, j_b) if 0 <= k < n), key=lambda k: reinf["span"][k]["bottom"]["area"])
    cross_section(sec, right_x + e_l + 4.0 * th, b, D, cover, stir, sup["top"], reinf["span"][lo]["bottom"], sup["gap"], reinf["span"][lo]["gap"],
                  shape, reinf.get("side_face"), inner_a, f"B-B: over support {j_b + 1}")

    model.notes = [
        f"Concrete M{inp.fck}; main bars Fe {inp.fy}; stirrups Fe {inp.fy_stirrup}.",
        f"Nominal cover {cover:.0f} mm to stirrups ({inp.exposure.replace('_', ' ')} exposure).",
        "Supports numbered from the left; top bars over each support centred on it, extents from its faces. Full schedule for every span "
        "in the bar bending schedule.",
        *(["The flange is the slab, cast with the beam; its bars are the slab's. Dashed line in the elevations: slab soffit."] if flanged else []),
        "All dimensions in millimetres. Do not scale from the drawing.",
    ]
    return model.to_dict()

