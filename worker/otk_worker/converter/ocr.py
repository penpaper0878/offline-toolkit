"""OCR with Tesseract: page images to a document model with word boxes, tables and figures.

- Orientation (Tesseract OSD) and small skew are detected first. A page that
  is upside down or sideways is turned upright (lossless, reported); a small
  skew is only corrected for recognition, and the word boxes are mapped back
  onto the untouched image.
- Words below the confidence threshold are reported.
- Ruled tables are found with OpenCV (line masks); a missing separator between
  two grid cells means they are merged. Word boxes are assigned to cells.
- Figures are large non-text regions, cropped from the original image.
"""

from __future__ import annotations

import csv
import io
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image as PILImage

from . import engines
from .docmodel import Block, Cell, DocModel, Image, Line, Page, Span, Table, is_rtl

PILImage.MAX_IMAGE_PIXELS = 300_000_000


def languages_available() -> list[str]:
    td = engines.tessdata_dir()
    dirs = [Path(td)] if td else []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        dirs.append(Path(env))
    for guess in ("/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata",
                  "/usr/share/tessdata", "/opt/homebrew/share/tessdata"):
        dirs.append(Path(guess))
    langs: set[str] = set()
    for d in dirs:
        if d.is_dir():
            langs.update(p.stem for p in d.glob("*.traineddata"))
    if not langs:
        try:
            res = engines.run([engines.require("tesseract"), "--list-langs"], timeout=30, what="Tesseract")
            langs.update(ln.strip() for ln in res.stdout.splitlines()[1:] if ln.strip())
        except Exception:
            pass
    langs.discard("osd")
    return sorted(langs)


def _tess_cmd() -> list[str]:
    return [engines.require("tesseract")]


@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]   # px in the original (upright) image
    conf: float                              # 0..1
    line: tuple[int, int, int]               # block, paragraph, line


@dataclass
class OcrPage:
    image: Path                               # upright page image (px)
    width: int
    height: int
    dpi: float
    words: list[Word] = field(default_factory=list)
    skew: float = 0.0
    rotated: int = 0
    tables: list[dict] = field(default_factory=list)   # px: {"bbox", "xs", "ys", "cells": [(r, c, rs, cs)]}
    figures: list[tuple[int, int, int, int]] = field(default_factory=list)


# ------------------------------------------------------------------ geometry helpers
def _gray(img: PILImage.Image) -> np.ndarray:
    return np.asarray(img.convert("L"))


def estimate_skew(gray: np.ndarray) -> float:
    """The rotation (degrees, counter-clockwise positive, as cv2) that levels the text rows, by
    projection-profile search within ±5°. Text rising to the right gives a negative value."""
    import cv2

    h, w = gray.shape
    scale = min(1.0, 1200 / max(h, w))
    small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if bw.mean() < 0.5:  # blank page
        return 0.0
    center = (bw.shape[1] / 2, bw.shape[0] / 2)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(bw, m, (bw.shape[1], bw.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)
        prof = rot.sum(axis=1, dtype=np.float64)
        return float(np.var(prof))

    best = max(np.arange(-5.0, 5.01, 0.5), key=score)
    fine = max(np.arange(best - 0.5, best + 0.51, 0.1), key=score)
    return round(float(fine), 2)


def _rotate_for_ocr(img: PILImage.Image, angle: float) -> tuple[PILImage.Image, np.ndarray]:
    """Rotate by `angle` degrees (counter-clockwise, as cv2) on a white canvas; returns image + inverse matrix."""
    import cv2

    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rot = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    inv = cv2.invertAffineTransform(m)
    return PILImage.fromarray(rot), inv


def _map_box(box, inv: np.ndarray | None) -> tuple[float, float, float, float]:
    if inv is None:
        return box
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], dtype=np.float64)
    mapped = pts @ inv.T
    return (float(mapped[:, 0].min()), float(mapped[:, 1].min()), float(mapped[:, 0].max()), float(mapped[:, 1].max()))


# ------------------------------------------------------------------ tesseract
def osd_rotation(path: Path, check: Callable[[], None]) -> int:
    """Clockwise rotation (0/90/180/270) that makes the page upright, when Tesseract is confident."""
    try:
        res = engines.run(_tess_cmd() + [str(path), "stdout", "--psm", "0", "-l", "osd"], check=check, timeout=120,
                          what="Tesseract (orientation)", ok_codes=(0, 1))
    except engines.EngineFailed:
        return 0
    rot, conf = 0, 0.0
    for line in res.stdout.splitlines():
        if line.startswith("Rotate:"):
            rot = int(line.split(":")[1].strip())
        elif line.startswith("Orientation confidence:"):
            conf = float(line.split(":")[1].strip())
    return rot if rot in (90, 180, 270) and conf >= 2.0 else 0


def run_tesseract(path: Path, langs: list[str], dpi: float, check: Callable[[], None], psm: int = 3) -> list[dict]:
    cmd = _tess_cmd() + [str(path), "stdout", "-l", "+".join(langs), "--oem", "1", "--psm", str(psm),
                         "--dpi", str(int(round(dpi))), "-c", "preserve_interword_spaces=1", "tsv"]
    res = engines.run(cmd, check=check, timeout=600, what="Tesseract")
    rows = list(csv.DictReader(io.StringIO(res.stdout), delimiter="\t", quoting=csv.QUOTE_NONE))
    return [r for r in rows if r.get("level") == "5" and (r.get("text") or "").strip()]


# ------------------------------------------------------------------ tables and figures
def detect_tables(gray: np.ndarray) -> list[dict]:
    import cv2

    h, w = gray.shape
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 40), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 40)))
    horiz = cv2.dilate(cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk), np.ones((3, 3), np.uint8))
    vert = cv2.dilate(cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk), np.ones((3, 3), np.uint8))
    grid = cv2.bitwise_or(horiz, vert)
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tables = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw * ch < 0.01 * w * h or cw < 40 or ch < 20:
            continue
        hs = horiz[y:y + ch, x:x + cw]
        vs = vert[y:y + ch, x:x + cw]
        ys = _line_positions(hs.mean(axis=1), cw) + y
        xs = _line_positions(vs.mean(axis=0), ch) + x
        if len(xs) < 2 or len(ys) < 2 or (len(xs) == 2 and len(ys) == 2):
            continue
        cells = _merge_cells(xs, ys, horiz, vert)
        tables.append({"bbox": (int(xs[0]), int(ys[0]), int(xs[-1]), int(ys[-1])), "xs": [int(v) for v in xs],
                       "ys": [int(v) for v in ys], "cells": cells})
    return tables


def _line_positions(profile: np.ndarray, length: int) -> np.ndarray:
    on = profile > 255 * 0.35
    pos, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            pos.append((i + j - 1) / 2)
            i = j
        else:
            i += 1
    return np.array(pos, dtype=np.float64)


def _merge_cells(xs, ys, horiz, vert) -> list[tuple[int, int, int, int]]:
    rows, cols = len(ys) - 1, len(xs) - 1
    parent = {(r, c): (r, c) for r in range(rows) for c in range(cols)}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    def covered(mask, x0, y0, x1, y1) -> float:
        seg = mask[int(y0):int(y1) + 1, int(x0):int(x1) + 1]
        return float((seg > 0).mean()) if seg.size else 0.0

    for r in range(rows):
        for c in range(cols - 1):  # vertical separator between (r,c) and (r,c+1)
            x = xs[c + 1]
            if covered(vert, x - 2, ys[r] + 3, x + 2, ys[r + 1] - 3) < 0.5:
                union((r, c), (r, c + 1))
    for r in range(rows - 1):
        for c in range(cols):
            y = ys[r + 1]
            if covered(horiz, xs[c] + 3, y - 2, xs[c + 1] - 3, y + 2) < 0.5:
                union((r, c), (r + 1, c))
    groups: dict = {}
    for k in parent:
        groups.setdefault(find(k), []).append(k)
    cells = []
    for members in groups.values():
        r0 = min(m[0] for m in members)
        c0 = min(m[1] for m in members)
        r1 = max(m[0] for m in members)
        c1 = max(m[1] for m in members)
        cells.append((r0, c0, r1 - r0 + 1, c1 - c0 + 1))
    return sorted(cells)


def detect_figures(gray: np.ndarray, words: list[Word], tables: list[dict]) -> list[tuple[int, int, int, int]]:
    """Large non-text, non-table regions (photos, logos, charts)."""
    import cv2

    h, w = gray.shape
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Colourful or mid-grey areas count as ink too (photos are not black text).
    bw = cv2.bitwise_or(bw, (gray < 235).astype(np.uint8) * 255)
    for wd in words:
        x0, y0, x1, y1 = (int(v) for v in wd.box)
        bw[max(0, y0 - 3):y1 + 3, max(0, x0 - 3):x1 + 3] = 0
    for t in tables:
        x0, y0, x1, y1 = t["bbox"]
        bw[max(0, y0 - 4):y1 + 5, max(0, x0 - 4):x1 + 5] = 0
    k = max(3, int(min(w, h) * 0.01))
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    figs = []
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if cw * ch >= 0.015 * w * h and min(cw, ch) >= 0.04 * min(w, h) and area >= 0.3 * cw * ch:
            figs.append((int(x), int(y), int(x + cw), int(y + ch)))
    return figs


# ------------------------------------------------------------------ main entry
def effective_dpi(img: PILImage.Image) -> tuple[float, bool]:
    """(dpi, assumed). Missing or implausible DPI: fit the long side to A4 (11.69 in)."""
    dpi = img.info.get("dpi")
    if dpi and 100 <= float(dpi[0]) <= 1200:
        return float(dpi[0]), False
    guess = max(72.0, min(600.0, max(img.size) / 11.69))
    return round(guess, 1), True


def ocr_page(image_path: Path, work: Path, *, langs: list[str], dpi: float | None, check: Callable[[], None],
             upright: bool = True) -> OcrPage:
    img = PILImage.open(image_path)
    img.load()
    if img.mode not in ("RGB", "L"):
        bg = PILImage.new("RGB", img.size, "white")
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img.convert("RGB"))
        img = bg
    if dpi is None:
        dpi, _ = effective_dpi(img)
    rotated = 0
    if upright:
        rotated = osd_rotation(image_path, check)
        if rotated:
            img = img.rotate(-rotated, expand=True)
            up = work / f"{image_path.stem}-upright.png"
            img.save(up, dpi=(dpi, dpi))
            image_path = up
    gray = _gray(img)
    skew = estimate_skew(gray)
    ocr_input, inv = image_path, None
    if abs(skew) >= 0.3:
        straight, inv = _rotate_for_ocr(img, skew)
        ocr_input = work / f"{image_path.stem}-deskew.png"
        straight.save(ocr_input, dpi=(dpi, dpi))
    rows = run_tesseract(ocr_input, langs, dpi, check)
    words = []
    for r in rows:
        box = (float(r["left"]), float(r["top"]), float(r["left"]) + float(r["width"]), float(r["top"]) + float(r["height"]))
        words.append(Word(text=r["text"], box=_map_box(box, inv), conf=max(0.0, float(r["conf"])) / 100.0,
                          line=(int(r["block_num"]), int(r["par_num"]), int(r["line_num"]))))
    tables = detect_tables(gray)
    figures = detect_figures(gray, words, tables)
    return OcrPage(image=image_path, width=img.width, height=img.height, dpi=dpi, words=words, skew=skew,
                   rotated=rotated, tables=tables, figures=figures)


def _ink_color(arr: np.ndarray, box) -> str:
    x0, y0, x1, y1 = (int(v) for v in box)
    patch = arr[max(0, y0):y1, max(0, x0):x1]
    if patch.size == 0:
        return "#000000"
    lum = patch.mean(axis=2) if patch.ndim == 3 else patch
    thr = lum.mean() - 0.5 * lum.std()
    ink = patch[lum < thr] if patch.ndim == 3 else None
    if ink is None or len(ink) == 0:
        return "#000000"
    r, g, b = (int(v) for v in np.median(ink, axis=0))
    # Near-black ink is black (scanner noise must not become dark grey text).
    if max(r, g, b) < 90:
        r = g = b = 0
    return f"#{r:02x}{g:02x}{b:02x}"


_ASC = set("bdfhijklt0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DESC = set("gjpqy")


def _font_size(words: list[Word], sy: float) -> float:
    """Font size (pt) from tight ink boxes: the ink height depends on which letters a word has."""
    est = []
    for w in words:
        h = (w.box[3] - w.box[1]) * sy
        letters = set(w.text)
        if not any(ch.isalpha() and ord(ch) < 0x250 for ch in w.text):
            est.append(h / 0.95)  # other scripts: headline to descender is about one em
        elif letters & _DESC and letters & _ASC:
            est.append(h / 0.95)
        elif letters & _ASC:
            est.append(h / 0.73)
        elif letters & _DESC:
            est.append(h / 0.72)
        else:
            est.append(h / 0.52)
    est.sort()
    size = est[len(est) // 2] if est else 10.0
    return max(4.0, round(size * 2) / 2)


def to_page(op: OcrPage, index: int, page_w_pt: float, page_h_pt: float, out_dir: Path, *,
            image_file: str | None = None, keep_original: bool = False) -> Page:
    """OcrPage (px) -> docmodel Page (pt): scan picture, OCR lines (with confidence), tables, figure crops."""
    sx, sy = page_w_pt / op.width, page_h_pt / op.height
    arr = np.asarray(PILImage.open(op.image).convert("RGB"))
    page = Page(index=index, width=round(page_w_pt, 2), height=round(page_h_pt, 2), scanned=True)
    name = image_file or op.image.name
    if not (out_dir / name).exists():
        PILImage.open(op.image).save(out_dir / name)
    page.images.append(Image(bbox=[0, 0, page.width, page.height], file=name, width=op.width, height=op.height,
                             ext=Path(name).suffix.lstrip(".").replace("jpg", "jpeg"), z=0, original=keep_original,
                             scan=True))
    # Lines in Tesseract's reading order.
    by_line: dict[tuple, list[Word]] = {}
    for w in op.words:
        by_line.setdefault(w.line, []).append(w)
    by_par: dict[tuple, list[Line]] = {}
    for key, ws in by_line.items():
        text = " ".join(w.text for w in ws)
        rtl = is_rtl(text)
        x0 = min(w.box[0] for w in ws) * sx
        y0 = min(w.box[1] for w in ws) * sy
        x1 = max(w.box[2] for w in ws) * sx
        y1 = max(w.box[3] for w in ws) * sy
        size = _font_size(ws, sy)
        color = _ink_color(arr, (x0 / sx, y0 / sy, x1 / sx, y1 / sy))
        spans = []
        for i, w in enumerate(ws):
            t = w.text + (" " if i < len(ws) - 1 else "")
            spans.append(Span(text=t, bbox=[round(w.box[0] * sx, 2), round(y0, 2), round(w.box[2] * sx, 2), round(y1, 2)],
                              font="Arial", size=size, color=color, origin=[round(w.box[0] * sx, 2), round(y1, 2)]))
        conf = min(w.conf for w in ws)
        line = Line(spans=spans, bbox=[round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
                    angle=-op.skew if abs(op.skew) >= 0.3 else 0.0, rtl=rtl, conf=round(conf, 3))
        by_par.setdefault(key[:2], []).append(line)
    for lines in by_par.values():
        bb = [min(ln.bbox[0] for ln in lines), min(ln.bbox[1] for ln in lines),
              max(ln.bbox[2] for ln in lines), max(ln.bbox[3] for ln in lines)]
        page.blocks.append(Block(lines=lines, bbox=[round(v, 2) for v in bb]))
    # Tables (px -> pt); blocks inside a table are split per cell.
    for t in op.tables:
        xs = [round(x * sx, 2) for x in t["xs"]]
        ys = [round(y * sy, 2) for y in t["ys"]]
        cells = [Cell(row=r, col=c, rowspan=rs, colspan=cs, bbox=[xs[c], ys[r], xs[c + cs], ys[r + rs]])
                 for r, c, rs, cs in t["cells"]]
        page.tables.append(Table(bbox=[xs[0], ys[0], xs[-1], ys[-1]], rows=len(ys) - 1, cols=len(xs) - 1,
                                 xs=xs, ys=ys, cells=cells))
    if page.tables:
        from .docmodel import _assign_tables
        _split_ocr_blocks_by_cells(page)
        _assign_tables(page)
    # Figures: crops of the original pixels.
    src = PILImage.open(op.image)
    for k, (x0, y0, x1, y1) in enumerate(op.figures):
        fname = f"p{index + 1}-fig{k + 1}.png"
        src.crop((x0, y0, x1, y1)).save(out_dir / fname)
        page.images.append(Image(bbox=[round(x0 * sx, 2), round(y0 * sy, 2), round(x1 * sx, 2), round(y1 * sy, 2)],
                                 file=fname, width=x1 - x0, height=y1 - y0, ext="png", z=1, original=False))
    return page


def _split_ocr_blocks_by_cells(page: Page) -> None:
    """Paragraphs that touch a table become one block per line and cell (words assigned by centre)."""
    def cell_of(sp):
        cx, cy = (sp.bbox[0] + sp.bbox[2]) / 2, (sp.bbox[1] + sp.bbox[3]) / 2
        for ti, t in enumerate(page.tables):
            for ci, c in enumerate(t.cells):
                if c.bbox[0] <= cx <= c.bbox[2] and c.bbox[1] <= cy <= c.bbox[3]:
                    return ti, ci
        return None

    new_blocks: list[Block] = []
    for blk in page.blocks:
        if not any(_overlaps(blk.bbox, t.bbox) for t in page.tables):
            new_blocks.append(blk)
            continue
        for ln in blk.lines:
            groups: dict = {}
            for sp in ln.spans:
                groups.setdefault(cell_of(sp), []).append(sp)
            for spans in groups.values():
                spans[-1] = Span(**{**spans[-1].__dict__, "text": spans[-1].text.rstrip(" ")})
                bb = [min(s.bbox[0] for s in spans), ln.bbox[1], max(s.bbox[2] for s in spans), ln.bbox[3]]
                new_blocks.append(Block([Line(spans=spans, bbox=bb, angle=ln.angle, rtl=ln.rtl, conf=ln.conf)], bb))
    page.blocks = new_blocks


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _in(inner, outer) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def low_confidence(model: DocModel, threshold: float, ops: list[OcrPage]) -> list[dict]:
    out = []
    for pi, op in enumerate(ops):
        for w in op.words:
            if w.conf < threshold:
                out.append({"page": pi + 1, "text": w.text, "confidence": round(w.conf, 2)})
    return out


def rotate_note(op: OcrPage, page_no: int) -> str | None:
    if op.rotated:
        return f"Page {page_no} was turned {op.rotated}° clockwise so its text is upright."
    return None


def skew_note(op: OcrPage, page_no: int) -> str | None:
    if abs(op.skew) >= 0.3:
        return f"Page {page_no} is tilted by {abs(op.skew):.1f}°; text was recognised on a straightened copy (the page image is unchanged)."
    return None


def degrees(v: float) -> float:
    return math.degrees(v)
