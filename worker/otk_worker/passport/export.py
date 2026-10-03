"""Saving a passport photo, and print sheets.

Single photo: JPG or PNG at the spec's exact pixel size with its DPI in the file (JFIF / pHYs), or a PDF
whose page is exactly the photo's physical size. A JPG can be held to a file-size range with Module 1's
compressor (quality search, never resizing).

Print sheet: photos on a paper size in exact millimetres. A grid of rows x columns (or as many as fit),
margins, gutter, optional thin borders and cut marks along every cut line in the margins (never over a
photo). PDF: vector page, each photo embedded once and placed in every cell. PNG/JPG: the sheet rendered
at the chosen DPI with that DPI in the file.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..common.units import round_px
from ..errors import InputError
from ..resizer import compress
from ..resizer.encode import EncodeSettings, encode

MM_PER = {"mm": 1.0, "cm": 10.0, "in": 25.4}
PT_PER_MM = 72 / 25.4


def to_mm(v: float, unit: str) -> float:
    return float(v) * MM_PER[unit]


# ------------------------------------------------------------------ single photo
def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.part")
    tmp.write_bytes(data)
    tmp.replace(path)


def pdf_bytes(img: Image.Image, page_mm: tuple[float, float], jpeg_quality: int = 95) -> bytes:
    import pymupdf

    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=jpeg_quality, subsampling=0, dpi=img.info.get("dpi", (300, 300)))
    doc = pymupdf.open()
    page = doc.new_page(width=page_mm[0] * PT_PER_MM, height=page_mm[1] * PT_PER_MM)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.set_metadata({"producer": "Offline Toolkit", "creator": "Offline Toolkit"})
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def save_photo(rgb: np.ndarray, size_mm: tuple[float, float], dpi: float, fmt: str, path: str,
               size_limit: dict | None = None, check=lambda: None) -> dict:
    """Write one photo. `size_limit` {min, max, unit: B|KB|MB} applies to JPG."""
    img = Image.fromarray(rgb, "RGB")
    out = Path(path)
    notes: list[str] = []
    result: dict = {"format": fmt, "px": [img.width, img.height], "dpi": dpi,
                    "mm": [round(img.width / dpi * 25.4, 3), round(img.height / dpi * 25.4, 3)]}
    if fmt == "pdf":
        data = pdf_bytes(img, size_mm)
        result["mm"] = [round(size_mm[0], 3), round(size_mm[1], 3)]
        notes.append(f"The PDF page is exactly {size_mm[0]:g} × {size_mm[1]:g} mm. Print it at 100% (Actual size).")
    elif fmt in ("jpeg", "png"):
        base = EncodeSettings(fmt=fmt, dpi=(dpi, dpi), quality=95, subsampling="4:4:4" if fmt == "jpeg" else None)
        target = compress.Target()
        if size_limit and fmt == "jpeg":
            mult = {"B": 1, "KB": 1024, "MB": 1024 * 1024}[size_limit.get("unit", "KB")]
            target = compress.Target(
                min_bytes=int(size_limit["min"] * mult) if size_limit.get("min") is not None else None,
                max_bytes=int(size_limit["max"] * mult) if size_limit.get("max") is not None else None)
        if target.active:
            oc = compress.fit(img, base, target, compress.Options(quality=95, subsampling="auto"), check)
            data = oc.data
            result["compression"] = {"status": oc.status, "quality": oc.settings.quality, "message": oc.message}
            if oc.status not in ("ok", "ok_padded"):
                notes.append(oc.message or "The file size range could not be met.")
        else:
            data = encode(img, base)
    else:
        raise InputError(f"Unknown photo format: {fmt}")
    _atomic_write(out, data)
    result.update(path=str(out), bytes=len(data), notes=notes)
    return result


# ------------------------------------------------------------------ sheet layout
@dataclass
class Layout:
    paper: tuple[float, float]          # mm (after orientation)
    cell: tuple[float, float]           # mm
    rows: int
    cols: int
    cells: list[tuple[float, float]]    # top-left of each cell, mm, row by row
    origin: tuple[float, float]         # top-left of the grid
    grid: tuple[float, float]           # grid size
    fits: bool
    max_rows: int
    max_cols: int
    problems: list[str]

    def to_dict(self) -> dict:
        r = lambda v: round(float(v), 3)  # noqa: E731
        return {"paper": [r(v) for v in self.paper], "cell": [r(v) for v in self.cell], "rows": self.rows, "cols": self.cols,
                "cells": [[r(x), r(y)] for x, y in self.cells], "origin": [r(v) for v in self.origin],
                "grid": [r(v) for v in self.grid], "fits": self.fits, "maxRows": self.max_rows, "maxCols": self.max_cols,
                "count": self.rows * self.cols, "problems": self.problems}


def _margins(m) -> tuple[float, float, float, float]:
    if isinstance(m, (int, float)):
        return (float(m),) * 4
    return (float(m.get("top", 0)), float(m.get("right", 0)), float(m.get("bottom", 0)), float(m.get("left", 0)))


def layout(opts: dict, cell_mm: tuple[float, float]) -> Layout:
    """`opts`: paper {width, height, unit}, orientation portrait|landscape, rows, cols, auto (bool),
    margins (mm, one number or {top,right,bottom,left}), gutter (mm), center (bool)."""
    p = opts["paper"]
    pw, ph = to_mm(p["width"], p["unit"]), to_mm(p["height"], p["unit"])
    if opts.get("orientation") == "landscape" and pw < ph or opts.get("orientation") == "portrait" and pw > ph:
        pw, ph = ph, pw
    mt, mr, mb, ml = _margins(opts.get("margins", 5))
    g = float(opts.get("gutter", 2))
    cw, ch = cell_mm
    aw, ah = pw - ml - mr, ph - mt - mb
    max_cols = max(0, math.floor((aw + g + 1e-9) / (cw + g))) if cw + g > 0 else 0
    max_rows = max(0, math.floor((ah + g + 1e-9) / (ch + g))) if ch + g > 0 else 0
    if opts.get("auto", False):
        rows, cols = max_rows, max_cols
    else:
        rows, cols = int(opts.get("rows", 1)), int(opts.get("cols", 1))
    problems = []
    gw, gh = cols * cw + max(0, cols - 1) * g, rows * ch + max(0, rows - 1) * g
    if rows < 1 or cols < 1:
        problems.append("The photo does not fit on this paper with these margins." if opts.get("auto") else "Choose at least one row and one column.")
    if gw > aw + 1e-6:
        problems.append(f"{cols} columns need {gw:.1f} mm; the paper has {aw:.1f} mm between the margins (at most {max_cols} fit).")
    if gh > ah + 1e-6:
        problems.append(f"{rows} rows need {gh:.1f} mm; the paper has {ah:.1f} mm between the margins (at most {max_rows} fit).")
    fits = not problems
    ox = ml + ((aw - gw) / 2 if opts.get("center", True) and fits else 0.0)
    oy = mt + ((ah - gh) / 2 if opts.get("center", True) and fits else 0.0)
    cells = [(ox + c * (cw + g), oy + r * (ch + g)) for r in range(max(rows, 0)) for c in range(max(cols, 0))]
    return Layout((pw, ph), (cw, ch), rows, cols, cells, (ox, oy), (gw, gh), fits, max_rows, max_cols, problems)


def assign(lay: Layout, items: list[dict]) -> tuple[list[int | None], list[str]]:
    """Which item fills each cell: each item's copies in order; an item without `copies` fills the rest."""
    n = len(lay.cells)
    fixed = sum(int(it["copies"]) for it in items if it.get("copies") is not None)
    free = [i for i, it in enumerate(items) if it.get("copies") is None]
    out: list[int | None] = []
    for i, it in enumerate(items):
        k = it.get("copies")
        if k is None:
            continue
        out += [i] * int(k)
    notes = []
    if fixed > n:
        notes.append(f"{fixed} copies were asked for, but the sheet has {n} places: {fixed - n} left out.")
        out = out[:n]
    rest = n - len(out)
    if free and rest > 0:
        per = [rest // len(free) + (1 if j < rest % len(free) else 0) for j in range(len(free))]
        fill: list[int | None] = []
        for idx, k in zip(free, per):
            fill += [idx] * k
        # Interleave the free items' copies in order after the fixed ones.
        out += fill
    out += [None] * (n - len(out))
    return out, notes


def _cut_lines(lay: Layout) -> tuple[list[float], list[float]]:
    xs, ys = set(), set()
    for x, y in lay.cells:
        xs |= {round(x, 4), round(x + lay.cell[0], 4)}
        ys |= {round(y, 4), round(y + lay.cell[1], 4)}
    return sorted(xs), sorted(ys)


def _mark_segments(lay: Layout, length: float = 4.0, gap: float = 1.0) -> list[tuple[float, float, float, float]]:
    """Cut marks: every vertical cut line extended above and below the grid, every horizontal one left and
    right, in the margins (as long as the margin allows, at least 1 mm), never over a photo."""
    xs, ys = _cut_lines(lay)
    ox, oy = lay.origin
    gw, gh = lay.grid
    pw, ph = lay.paper
    seg = []
    up, down = min(length, oy - gap), min(length, ph - (oy + gh) - gap)
    left, right = min(length, ox - gap), min(length, pw - (ox + gw) - gap)
    for x in xs:
        if up >= 1:
            seg.append((x, oy - gap - up, x, oy - gap))
        if down >= 1:
            seg.append((x, oy + gh + gap, x, oy + gh + gap + down))
    for y in ys:
        if left >= 1:
            seg.append((ox - gap - left, y, ox - gap, y))
        if right >= 1:
            seg.append((ox + gw + gap, y, ox + gw + gap + right, y))
    return seg


def sheet_pdf(lay: Layout, images: list[Image.Image], cells: list[int | None], *, borders: bool, cut_marks: bool) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=lay.paper[0] * PT_PER_MM, height=lay.paper[1] * PT_PER_MM)
    xrefs: dict[int, int] = {}
    cw, ch = lay.cell
    for (x, y), idx in zip(lay.cells, cells):
        if idx is None:
            continue
        rect = pymupdf.Rect(x * PT_PER_MM, y * PT_PER_MM, (x + cw) * PT_PER_MM, (y + ch) * PT_PER_MM)
        if idx in xrefs:
            page.insert_image(rect, xref=xrefs[idx])
        else:
            buf = io.BytesIO()
            images[idx].convert("RGB").save(buf, "JPEG", quality=95, subsampling=0)
            xrefs[idx] = page.insert_image(rect, stream=buf.getvalue())
        if borders:
            page.draw_rect(rect, color=(0.6, 0.6, 0.6), width=0.1 * PT_PER_MM)
    if cut_marks:
        for x0, y0, x1, y1 in _mark_segments(lay):
            page.draw_line(pymupdf.Point(x0 * PT_PER_MM, y0 * PT_PER_MM), pymupdf.Point(x1 * PT_PER_MM, y1 * PT_PER_MM),
                           color=(0, 0, 0), width=0.1 * PT_PER_MM)
    doc.set_metadata({"producer": "Offline Toolkit", "creator": "Offline Toolkit"})
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def sheet_raster(lay: Layout, images: list[Image.Image], cells: list[int | None], dpi: float, *, borders: bool,
                 cut_marks: bool) -> Image.Image:
    from PIL import ImageDraw

    px = lambda mm: round_px(mm / 25.4 * dpi)  # noqa: E731
    W, H = px(lay.paper[0]), px(lay.paper[1])
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    cw, ch = lay.cell
    sized: dict[int, Image.Image] = {}
    draw = ImageDraw.Draw(sheet)
    line = max(1, round(0.1 / 25.4 * dpi))
    for (x, y), idx in zip(lay.cells, cells):
        if idx is None:
            continue
        x0, y0 = px(x), px(y)
        w, h = px(x + cw) - x0, px(y + ch) - y0
        im = sized.get((idx, w, h))
        if im is None:
            im = images[idx].convert("RGB")
            if im.size != (w, h):
                im = im.resize((w, h), Image.Resampling.LANCZOS)
            sized[(idx, w, h)] = im
        sheet.paste(im, (x0, y0))
        if borders:
            draw.rectangle([x0, y0, x0 + w - 1, y0 + h - 1], outline=(153, 153, 153), width=line)
    if cut_marks:
        for x0, y0, x1, y1 in _mark_segments(lay):
            draw.line([(px(x0), px(y0)), (px(x1), px(y1))], fill=(0, 0, 0), width=line)
    sheet.info["dpi"] = (dpi, dpi)
    return sheet


def sheet_html(lay: Layout, image_urls: list[str], cells: list[int | None], *, borders: bool, cut_marks: bool) -> str:
    """The sheet as a page sized in CSS millimetres (for printing at 100% from the app)."""
    cw, ch = lay.cell
    parts = [f'<!doctype html><html><head><meta charset="utf-8"><style>@page {{ size: {lay.paper[0]:.3f}mm {lay.paper[1]:.3f}mm; margin: 0 }}'
             f'html, body {{ margin: 0; padding: 0; }} .sheet {{ position: relative; width: {lay.paper[0]:.3f}mm; height: {lay.paper[1]:.3f}mm; overflow: hidden; }}'
             f'img {{ position: absolute; width: {cw:.3f}mm; height: {ch:.3f}mm; {"outline: 0.1mm solid #999; outline-offset: -0.1mm;" if borders else ""} }}'
             f'.m {{ position: absolute; background: #000; }}</style></head><body><div class="sheet">']
    for (x, y), idx in zip(lay.cells, cells):
        if idx is not None:
            parts.append(f'<img src="{image_urls[idx]}" style="left:{x:.3f}mm;top:{y:.3f}mm" alt="">')
    if cut_marks:
        for x0, y0, x1, y1 in _mark_segments(lay):
            if x0 == x1:
                parts.append(f'<div class="m" style="left:{x0 - 0.05:.3f}mm;top:{min(y0, y1):.3f}mm;width:0.1mm;height:{abs(y1 - y0):.3f}mm"></div>')
            else:
                parts.append(f'<div class="m" style="left:{min(x0, x1):.3f}mm;top:{y0 - 0.05:.3f}mm;width:{abs(x1 - x0):.3f}mm;height:0.1mm"></div>')
    parts.append("</div></body></html>")
    return "".join(parts)
