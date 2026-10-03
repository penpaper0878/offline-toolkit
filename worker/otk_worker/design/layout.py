"""Geometry the exporters share: page units, text baselines, table cells, shape outlines.

Everything in a scene is in page pixels. A text layer's first baseline lies the font's ascent (at the
layer's size) below the box top and each next line `lineHeight * size` lower; every writer reproduces
those baselines with its own rule for where a text frame puts them (measured in LibreOffice, see the
writers). Strokes of shapes lie inside the box, as the analysis measured them.
"""

from __future__ import annotations

import base64
import mimetypes
from functools import lru_cache
from pathlib import Path

from . import fontmatch

RTL_SCRIPTS = {"arabic", "hebrew"}


@lru_cache(maxsize=256)
def metrics(family: str, weight: int, italic: bool) -> dict:
    try:
        return fontmatch.metrics(family, weight, italic)
    except Exception:
        return {"ascent": 0.9, "descent": 0.25, "lineGap": 0.0, "capHeight": 0.7, "xHeight": 0.5}


def page_scale(scene: dict, *, max_in: float, min_in: float = 1.0) -> tuple[float, str | None]:
    """Points per pixel for an output whose page sides must stay within [min_in, max_in] inches."""
    dpi = float(scene["source"].get("dpi") or 96.0)
    w, h = scene["page"]["width"], scene["page"]["height"]
    k = 72.0 / dpi
    s = 1.0
    if max(w, h) * k > max_in * 72:
        s = max_in * 72 / (max(w, h) * k)
    elif min(w, h) * k < min_in * 72:
        s = min_in * 72 / (min(w, h) * k)
    note = None if s == 1.0 else f"The page was scaled by {s:.3f} to fit the format's page size limits."
    return k * s, note


def is_rtl(lyr: dict) -> bool:
    return lyr.get("script") in RTL_SCRIPTS


def text_geometry(lyr: dict) -> dict:
    """Lines of a text layer with their baselines (page px), the anchor x for the alignment."""
    st = lyr["style"]
    x, y, w, h = lyr["box"]
    m = metrics(st["family"], int(st["weight"]), bool(st["italic"]))
    size = float(st["size"])
    pitch = float(st["lineHeight"]) * size
    first = y + m["ascent"] * size
    lines = lyr["text"].split("\n")
    align = st.get("align", "left")
    anchor = {"left": x, "justify": x, "center": x + w / 2, "right": x + w}.get(align, x)
    return {"lines": lines, "baselines": [first + i * pitch for i in range(len(lines))], "pitch": pitch,
            "size": size, "ascent": m["ascent"], "descent": m["descent"], "anchor": anchor, "align": align,
            "rtl": is_rtl(lyr)}


def table_grid(lyr: dict) -> tuple[list[float], list[float]]:
    """Column and row edges (page px), the stored widths scaled to the box."""
    x, y, w, h = lyr["box"]
    cw, rh = lyr["colWidths"], lyr["rowHeights"]
    sx, sy = w / max(1e-6, sum(cw)), h / max(1e-6, sum(rh))
    xs, ys = [x], [y]
    for v in cw:
        xs.append(xs[-1] + v * sx)
    for v in rh:
        ys.append(ys[-1] + v * sy)
    return xs, ys


def table_cells(lyr: dict) -> list[tuple[dict, tuple[float, float, float, float]]]:
    xs, ys = table_grid(lyr)
    out = []
    for c in lyr["cells"]:
        r, col = c["row"], c["col"]
        r1, c1 = min(len(ys) - 1, r + c.get("rowSpan", 1)), min(len(xs) - 1, col + c.get("colSpan", 1))
        out.append((c, (xs[col], ys[r], xs[c1], ys[r1])))
    return out


def cell_text(lyr: dict, cell: dict, box: tuple[float, float, float, float]) -> dict:
    """Lines of one table cell, centred vertically, with the anchor x for its alignment."""
    st = lyr["style"]
    pad = lyr.get("padding") or [6, 2, 6, 2]
    half = lyr["border"]["width"] / 2
    m = metrics(st["family"], int(cell.get("weight", 400)), bool(cell.get("italic", False)))
    size = float(st["size"])
    pitch = (m["ascent"] + m["descent"] + m["lineGap"]) * size
    lines = cell["text"].split("\n") if cell["text"] else []
    x0, y0, x1, y1 = box
    block = (len(lines) - 1) * pitch + (m["ascent"] + m["descent"]) * size if lines else 0
    valign = cell.get("valign", "middle")
    top = {"top": y0 + half + pad[1], "bottom": y1 - half - pad[3] - block}.get(valign, (y0 + y1) / 2 - block / 2)
    first = top + m["ascent"] * size
    align = cell.get("align", "left")
    anchor = {"left": x0 + half + pad[0], "center": (x0 + x1) / 2, "right": x1 - half - pad[2]}.get(align, x0 + half + pad[0])
    return {"lines": lines, "baselines": [first + i * pitch for i in range(len(lines))], "pitch": pitch,
            "size": size, "anchor": anchor, "align": align, "ascent": m["ascent"], "descent": m["descent"]}


def cell_edges(lyr: dict) -> list[tuple[float, float, float, float]]:
    """The rules of a table as segments (x0, y0, x1, y1): every cell's outline, shared edges once."""
    seen, out = set(), []
    for _, (x0, y0, x1, y1) in table_cells(lyr):
        for seg in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)):
            key = tuple(round(v, 1) for v in seg)
            if key not in seen:
                seen.add(key)
                out.append(seg)
    return out


def shape_outline(lyr: dict) -> tuple[float, float, float, float, float]:
    """(x, y, w, h, radius) of the path a stroke is centred on: the box inset by half the stroke."""
    x, y, w, h = lyr["box"]
    sw = float(lyr.get("strokeWidth") or 0) if lyr.get("stroke") else 0.0
    r = float(lyr.get("radius") or 0)
    i = sw / 2
    return x + i, y + i, max(0.5, w - sw), max(0.5, h - sw), max(0.0, r - i)


def vector_scale(lyr: dict) -> tuple[float, float]:
    nw, nh = lyr.get("natural") or lyr["box"][2:]
    return lyr["box"][2] / max(1e-6, nw), lyr["box"][3] / max(1e-6, nh)


def line_points(lyr: dict) -> tuple[float, float, float, float]:
    x, y, w, h = lyr["box"]
    px = lyr.get("points") or [0, h / 2, w, h / 2]
    return x + px[0], y + px[1], x + px[2], y + px[3]


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def visible_layers(scene: dict) -> list[dict]:
    return [lyr for lyr in scene["layers"] if lyr.get("visible", True)]
