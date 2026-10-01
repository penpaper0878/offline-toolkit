"""Document model: what each page of a born-digital PDF contains, and where.

Extracted with PyMuPDF. Coordinates are PDF points with the origin at the top
left of the page as displayed (page rotation removed first). The model is
saved as JSON next to the images it references, so later steps (and a resumed
job) can read it back. Module 3 builds the same structure from OCR.

Text fidelity rules:
- ligatures are expanded (ﬁ -> fi) so the text stays searchable and editable;
- nothing is dropped: whitespace-only fragments that a PDF writer drew in a
  fallback font (LibreOffice does this for Indic scripts) are put back into
  the line they belong to, at their position;
- a hyphen at a line end is kept as it is (never guessed away).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

_RTL = re.compile("[֐-ࣿיִ-﷿ﹰ-ﻼ]")
_LTR_LETTER = re.compile(r"[A-Za-zÀ-ɏͰ-ϿЀ-ӿऀ-෿]")


def is_rtl(text: str) -> bool:
    return len(_RTL.findall(text)) > len(_LTR_LETTER.findall(text))


@dataclass
class Span:
    text: str
    bbox: list[float]
    font: str
    size: float
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    mono: bool = False
    serif: bool = False
    sup: bool = False
    origin: list[float] = field(default_factory=list)
    alpha: float = 1.0
    link: str | None = None
    ascent: float | None = None   # the font's layout ascent (em) when its program is embedded; see font_ascents()


@dataclass
class Line:
    spans: list[Span]
    bbox: list[float]
    angle: float = 0.0            # degrees counter-clockwise; 0 = horizontal
    rtl: bool = False
    invisible: bool = False       # e.g. OCR text layered over a scan
    conf: float | None = None     # OCR confidence (0..1) when the line came from OCR

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class Block:
    lines: list[Line]
    bbox: list[float]
    table: int | None = None      # index into Page.tables when the block sits in a table cell

    @property
    def text(self) -> str:
        return join_lines([ln.text for ln in self.lines])


@dataclass
class Image:
    bbox: list[float]
    file: str                     # file name next to the model JSON
    width: int
    height: int
    ext: str
    z: int = 0
    original: bool = True         # the PDF's own stream (JPEG bytes copied as-is)
    scan: bool = False            # a full-page scan


@dataclass
class Shape:
    ops: list[list]               # ["m",x,y] ["l",x,y] ["c",x1,y1,x2,y2,x3,y3] ["h"]
    bbox: list[float]
    fill: str | None = None
    stroke: str | None = None
    width: float = 1.0
    fill_opacity: float = 1.0
    stroke_opacity: float = 1.0
    even_odd: bool = False
    dashes: list[float] = field(default_factory=list)
    cap: int = 0
    join: int = 0
    z: int = 0


@dataclass
class Cell:
    row: int
    col: int
    rowspan: int
    colspan: int
    bbox: list[float]
    text: str = ""


@dataclass
class Table:
    bbox: list[float]
    rows: int
    cols: int
    xs: list[float]
    ys: list[float]
    cells: list[Cell]


@dataclass
class Link:
    bbox: list[float]
    uri: str | None = None
    page: int | None = None


@dataclass
class Page:
    index: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    scanned: bool = False
    raster_fallback: bool = False  # too many vector paths: drawn as one picture instead


@dataclass
class DocModel:
    pages: list[Page]
    toc: list[list] = field(default_factory=list)        # [level, title, page (1-based)]
    metadata: dict = field(default_factory=dict)
    fonts: dict[str, bool] = field(default_factory=dict)  # base font -> embedded
    notes: list[str] = field(default_factory=list)

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "DocModel":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        pages = []
        for p in d["pages"]:
            pages.append(Page(
                index=p["index"], width=p["width"], height=p["height"],
                blocks=[Block([Line([Span(**s) for s in ln["spans"]], ln["bbox"], ln["angle"], ln["rtl"],
                                     ln.get("invisible", False), ln.get("conf")) for ln in b["lines"]],
                              b["bbox"], b.get("table")) for b in p["blocks"]],
                images=[Image(**i) for i in p["images"]], shapes=[Shape(**s) for s in p["shapes"]],
                tables=[Table(t["bbox"], t["rows"], t["cols"], t["xs"], t["ys"], [Cell(**c) for c in t["cells"]])
                        for t in p["tables"]],
                links=[Link(**lk) for lk in p["links"]], scanned=p.get("scanned", False),
                raster_fallback=p.get("raster_fallback", False)))
        return cls(pages, d.get("toc", []), d.get("metadata", {}), d.get("fonts", {}), d.get("notes", []))

    # Convenience used by several writers.
    def body_size(self) -> float:
        sizes: dict[float, int] = {}
        for p in self.pages:
            for b in p.blocks:
                for ln in b.lines:
                    for s in ln.spans:
                        sizes[round(s.size, 1)] = sizes.get(round(s.size, 1), 0) + len(s.text.strip())
        return max(sizes, key=sizes.get) if sizes else 11.0


def join_lines(lines: list[str]) -> str:
    """Paragraph text from its lines: a line ending in a hyphen joins without a space (hyphen kept)."""
    out = ""
    for ln in lines:
        ln = ln.rstrip("\n")
        if not out:
            out = ln
        elif out.endswith(("-", "­", "‐")) or not ln:
            out += ln
        else:
            out += ("" if out.endswith(" ") else " ") + ln.lstrip(" ")
    return out


# ------------------------------------------------------------------ extraction
MAX_SHAPES = 4000
_WS = re.compile(r"^\s+$")


def _hex(color) -> str | None:
    if color is None:
        return None
    if isinstance(color, int):
        return f"#{color:06x}"
    if len(color) == 1:
        v = int(round(color[0] * 255))
        return f"#{v:02x}{v:02x}{v:02x}"
    if len(color) == 4:  # CMYK -> RGB
        c, m, y, k = color
        color = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    r, g, b = (max(0, min(255, int(round(x * 255)))) for x in color[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _r(v) -> list[float]:
    return [round(float(x), 2) for x in v]


def _spans_from_raw(line: dict) -> list[dict]:
    out = []
    for s in line["spans"]:
        text = "".join(c["c"] for c in s["chars"])
        if not text:
            continue
        out.append({"span": s, "text": text, "chars": s["chars"]})
    return out


def _make_span(s: dict, text: str, bbox, chars=None) -> Span:
    flags = s.get("flags", 0)
    alpha = s.get("alpha", 255)
    return Span(text=text, bbox=_r(bbox), font=s.get("font", ""), size=round(float(s.get("size", 0)), 2),
                color=_hex(s.get("color", 0)) or "#000000", bold=bool(flags & 16) or "bold" in s.get("font", "").lower(),
                italic=bool(flags & 2), mono=bool(flags & 8), serif=bool(flags & 4), sup=bool(flags & 1),
                origin=_r(s.get("origin", bbox[:2])), alpha=round((alpha if alpha is not None else 255) / 255, 3))


def _space_already_there(host: dict, ch: dict) -> bool:
    """True when `host` already has a whitespace char covering most of `ch`'s horizontal extent."""
    x0, x1 = ch["bbox"][0], ch["bbox"][2]
    width = max(x1 - x0, 0.01)
    for sp in host["spans"]:
        for c in sp["chars"]:
            if c["c"].isspace():
                overlap = min(x1, c["bbox"][2]) - max(x0, c["bbox"][0])
                if overlap >= 0.5 * min(width, max(c["bbox"][2] - c["bbox"][0], 0.01)):
                    return True
    return False


def _insert_orphans(host: dict, orphans: list[dict], rtl: bool) -> None:
    """Put whitespace chars drawn separately back into `host` at their x position."""
    for orph in orphans:
        for ch in orph["chars"]:
            if _space_already_there(host, ch):
                # LibreOffice on Windows draws the spaces of an Arabic line twice: with the words and again in a
                # fallback font. The copy is not a second space.
                continue
            cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
            # Position in logical order = number of host chars on the reading side of the space.
            flat = [(si, ci, c) for si, sp in enumerate(host["spans"]) for ci, c in enumerate(sp["chars"])]
            if rtl:
                n = sum(1 for _, _, c in flat if (c["bbox"][0] + c["bbox"][2]) / 2 > cx)
            else:
                n = sum(1 for _, _, c in flat if (c["bbox"][0] + c["bbox"][2]) / 2 < cx)
            if n >= len(flat):
                si, ci = len(host["spans"]) - 1, len(host["spans"][-1]["chars"])
            else:
                si, ci, _ = flat[n]
            host["spans"][si]["chars"].insert(ci, dict(ch))
            host["spans"][si]["text"] = "".join(c["c"] for c in host["spans"][si]["chars"])


def _drop_repeated_spaces(line: dict) -> dict:
    """A whitespace-only span whose spaces sit on spaces of another span in the same line is a second
    drawing of them (LibreOffice on Windows, Arabic: once in the line's font, once in a fallback font).
    The copy in the font of the line's words is kept."""
    ws = [sp for sp in line["spans"] if _WS.match(sp["text"])]
    if not ws or len(ws) == len(line["spans"]):
        return line
    word_fonts = {sp["span"].get("font") for sp in line["spans"] if sp not in ws}
    # Decide in priority order (same font as the words first), then rebuild in the original order.
    kept: dict[int, dict] = {}
    for sp in sorted(ws, key=lambda sp: sp["span"].get("font") not in word_fonts):
        others = {"spans": [o for o in line["spans"] if o not in ws] + list(kept.values())}
        chars = [c for c in sp["chars"] if not _space_already_there(others, c)]
        if chars:
            kept[id(sp)] = sp if len(chars) == len(sp["chars"]) else {**sp, "chars": chars,
                                                                     "text": "".join(c["c"] for c in chars)}
    spans = [kept.get(id(sp)) if sp in ws else sp for sp in line["spans"]]
    return {**line, "spans": [sp for sp in spans if sp is not None]}


def _page_lines(page) -> list[tuple[int, dict]]:
    """(block number, line) pairs with orphan whitespace merged back into its line."""
    import pymupdf

    # No TEXT_ACCURATE_BBOXES: it drops whitespace glyphs (they have no ink).
    flags = pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP
    raw = page.get_text("rawdict", flags=flags)
    lines: list[tuple[int, dict]] = []
    for bi, b in enumerate(raw["blocks"]):
        if b.get("type", 0) != 0:
            continue
        for ln in b["lines"]:
            spans = _spans_from_raw(ln)
            if spans:
                lines.append((bi, _drop_repeated_spaces({"dir": ln["dir"], "bbox": ln["bbox"], "spans": spans})))
    hosts = [(bi, ln) for bi, ln in lines if not all(_WS.match(s["text"]) for s in ln["spans"])]
    orphans = [(bi, ln) for bi, ln in lines if all(_WS.match(s["text"]) for s in ln["spans"])]
    for _, orph in orphans:
        ob = orph["bbox"]
        oy = (ob[1] + ob[3]) / 2
        ox = (ob[0] + ob[2]) / 2
        best = None
        for _, host in hosts:
            hb = host["bbox"]
            if hb[0] - 1 <= ox <= hb[2] + 1 and hb[1] - 1 <= oy <= hb[3] + 1 and abs(host["dir"][1]) < 0.01:
                best = host
                break
        if best is not None:
            text = "".join(s["text"] for s in best["spans"])
            _insert_orphans(best, orph["spans"], is_rtl(text))
    return hosts


def _split_by_cells(lines: list[tuple[int, dict]], tables: list[Table]) -> list[tuple[int, dict]]:
    """A PDF line that runs across table cells ("001234 3.50") becomes one line per cell."""
    if not tables:
        return lines
    cells = [(ti, ci, c.bbox) for ti, t in enumerate(tables) for ci, c in enumerate(t.cells)]
    out: list[tuple[int, dict]] = []
    for bi, ln in lines:
        groups: dict = {}
        order: list = []
        for sp in ln["spans"]:
            for ch in sp["chars"]:
                cb = ch["bbox"]
                cx, cy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
                key = next(((ti, ci) for ti, ci, b in cells if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]), None)
                if key not in groups:
                    groups[key] = {}
                    order.append(key)
                g = groups[key]
                if id(sp) not in g:
                    g[id(sp)] = {"span": sp["span"], "chars": []}
                g[id(sp)]["chars"].append(ch)
        if len(order) <= 1:
            out.append((bi, ln))
            continue
        for key in order:
            spans = []
            for part in groups[key].values():
                text = "".join(c["c"] for c in part["chars"])
                if text.strip():
                    spans.append({"span": part["span"], "text": text, "chars": part["chars"]})
            if spans:
                bb = [min(c["bbox"][0] for s_ in spans for c in s_["chars"]), min(c["bbox"][1] for s_ in spans for c in s_["chars"]),
                      max(c["bbox"][2] for s_ in spans for c in s_["chars"]), max(c["bbox"][3] for s_ in spans for c in s_["chars"])]
                # Strip the separating space at the edges of the cell text.
                spans[0]["text"] = spans[0]["text"].lstrip(" ")
                spans[-1]["text"] = spans[-1]["text"].rstrip(" ")
                out.append((bi * 1000 + (key[1] + 1 if key else 0), {"dir": ln["dir"], "bbox": bb, "spans": spans}))
    return out


def _split_by_links(lines: list[tuple[int, dict]], links: list[Link]) -> list[tuple[int, dict]]:
    """Cut spans where a link starts or ends, so only the linked characters carry the link."""
    uri_links = [lk for lk in links if lk.uri]
    if not uri_links:
        return lines
    for _, ln in lines:
        new_spans = []
        for sp in ln["spans"]:
            cur_key, cur = object(), None
            for ch in sp["chars"]:
                cb = ch["bbox"]
                cx, cy = (cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2
                key = next((lk.uri for lk in uri_links
                            if lk.bbox[0] <= cx <= lk.bbox[2] and lk.bbox[1] - 1 <= cy <= lk.bbox[3] + 1), None)
                if cur is None or key != cur_key:
                    cur = {"span": sp["span"], "chars": [], "link": key}
                    new_spans.append(cur)
                    cur_key = key
                cur["chars"].append(ch)
        for ns in new_spans:
            ns["text"] = "".join(c["c"] for c in ns["chars"])
        ln["spans"] = new_spans
    return lines


def _dominant(line: Line) -> tuple[float, bool]:
    best = max(line.spans, key=lambda s: len(s.text.strip()))
    return best.size, best.bold


def _split_paragraphs(blocks: list[Block]) -> list[Block]:
    """Split PDF blocks where the style or the spacing changes (a heading glued to its paragraph)."""
    out: list[Block] = []
    for blk in blocks:
        cur: list[Line] = []
        prev: Line | None = None
        for ln in blk.lines:
            if prev is not None:
                ps, pb = _dominant(prev)
                cs, cb = _dominant(ln)
                height = max(1.0, prev.bbox[3] - prev.bbox[1])
                gap = ln.bbox[1] - prev.bbox[3]
                if abs(cs - ps) > 0.1 * max(cs, ps) or pb != cb or gap > 0.8 * height:
                    out.append(Block(cur, _bbox_of(cur), blk.table))
                    cur = []
            cur.append(ln)
            prev = ln
        if cur:
            out.append(Block(cur, _bbox_of(cur), blk.table))
    return out


def _lines_to_blocks(lines: list[tuple[int, dict]]) -> list[Block]:
    blocks: dict[int, Block] = {}
    order: list[int] = []
    for bi, ln in lines:
        spans = []
        for sp in ln["spans"]:
            chars = sp["chars"]
            xs0 = [c["bbox"][0] for c in chars]
            ys0 = [c["bbox"][1] for c in chars]
            xs1 = [c["bbox"][2] for c in chars]
            ys1 = [c["bbox"][3] for c in chars]
            bbox = [min(xs0), min(ys0), max(xs1), max(ys1)]
            s = sp["span"]
            if (s.get("char_flags", 24) & 0x30) == 0:  # neither filled nor stroked: invisible text (render mode 3)
                span = _make_span(s, sp["text"], bbox)
                span.alpha = 0.0
            else:
                span = _make_span(s, sp["text"], bbox)
            span.link = sp.get("link")
            spans.append(span)
        if not spans:
            continue
        cos, sin = ln["dir"]
        import math
        angle = round(math.degrees(math.atan2(-sin, cos)), 2)
        text = "".join(s.text for s in spans)
        line = Line(spans=spans, bbox=_r([min(s.bbox[0] for s in spans), min(s.bbox[1] for s in spans),
                                          max(s.bbox[2] for s in spans), max(s.bbox[3] for s in spans)]),
                    angle=angle, rtl=is_rtl(text), invisible=all(s.alpha == 0 for s in spans))
        if bi not in blocks:
            blocks[bi] = Block(lines=[], bbox=list(line.bbox))
            order.append(bi)
        blk = blocks[bi]
        blk.lines.append(line)
        blk.bbox = _r([min(blk.bbox[0], line.bbox[0]), min(blk.bbox[1], line.bbox[1]),
                       max(blk.bbox[2], line.bbox[2]), max(blk.bbox[3], line.bbox[3])])
    return _split_paragraphs([blocks[i] for i in order])


def _save_image(doc, xref: int, dest: Path, stem: str) -> tuple[str, int, int, str, bool] | None:
    """Original stream when it is JPEG or a plain RGB/grey bitmap; otherwise a lossless PNG."""
    import pymupdf

    try:
        info = doc.extract_image(xref)
    except Exception:
        info = None
    if info and not info.get("smask") and info.get("ext") in ("jpeg", "jpg") and info.get("colorspace", 3) in (1, 3):
        name = f"{stem}.jpg"
        (dest / name).write_bytes(info["image"])
        return name, info["width"], info["height"], "jpeg", True
    try:
        pix = pymupdf.Pixmap(doc, xref)
        if info and info.get("smask"):
            mask = pymupdf.Pixmap(doc, info["smask"])
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)
            if pix.colorspace and pix.colorspace.n not in (1, 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix = pymupdf.Pixmap(pix, mask)
        elif pix.colorspace and pix.colorspace.n not in (1, 3):
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        name = f"{stem}.png"
        pix.save(dest / name)
        original = bool(info and info.get("ext") == "png" and not info.get("smask"))
        return name, pix.width, pix.height, "png", original
    except Exception:
        return None


def _grid(values: list[float], tol: float = 1.0) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _index(grid: list[float], v: float) -> int:
    return min(range(len(grid)), key=lambda i: abs(grid[i] - v))


def _tables(page) -> list[Table]:
    out: list[Table] = []
    try:
        found = page.find_tables(strategy="lines").tables
    except Exception:
        return out
    for t in found:
        cells = [c for c in t.cells if c]
        if len(cells) < 2:
            continue
        xs = _grid([c[0] for c in cells] + [c[2] for c in cells])
        ys = _grid([c[1] for c in cells] + [c[3] for c in cells])
        tcells = []
        for c in cells:
            c0, c1 = _index(xs, c[0]), _index(xs, c[2])
            r0, r1 = _index(ys, c[1]), _index(ys, c[3])
            if c1 <= c0 or r1 <= r0:
                continue
            tcells.append(Cell(row=r0, col=c0, rowspan=r1 - r0, colspan=c1 - c0, bbox=_r(c)))
        rows, cols = len(ys) - 1, len(xs) - 1
        if rows < 1 or cols < 1 or (rows == 1 and cols == 1):
            continue
        out.append(Table(bbox=_r(t.bbox), rows=rows, cols=cols, xs=_r(xs), ys=_r(ys), cells=tcells))
    return out


def _inside(inner, outer, tol=1.5) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] - tol <= cx <= outer[2] + tol and outer[1] - tol <= cy <= outer[3] + tol


def _assign_tables(page: Page) -> None:
    """Cell text from the page's lines. Each line is assigned on its own: a PDF block can hold a table
    and the paragraph after it, and that paragraph must stay ordinary text."""
    if not page.tables:
        return
    new_blocks: list[Block] = []
    for blk in page.blocks:
        outside: list[Line] = []
        for ln in blk.lines:
            ti = next((i for i, t in enumerate(page.tables) if _inside(ln.bbox, t.bbox)), None)
            if ti is None:
                outside.append(ln)
                continue
            if outside:
                new_blocks.append(Block(outside, _bbox_of(outside)))
                outside = []
            new_blocks.append(Block([ln], list(ln.bbox), ti))
        if outside:
            new_blocks.append(Block(outside, _bbox_of(outside)))
    page.blocks = new_blocks
    for ti, t in enumerate(page.tables):
        for cell in t.cells:
            texts = []
            for blk in page.blocks:
                if blk.table != ti:
                    continue
                for ln in blk.lines:
                    if _inside(ln.bbox, cell.bbox, tol=0.5):
                        texts.append(ln.text)
            cell.text = join_lines(texts)


def _bbox_of(lines: list[Line]) -> list[float]:
    return _r([min(ln.bbox[0] for ln in lines), min(ln.bbox[1] for ln in lines),
               max(ln.bbox[2] for ln in lines), max(ln.bbox[3] for ln in lines)])


def _shapes(page, page_area: float) -> list[Shape]:
    out: list[Shape] = []
    for d in page.get_drawings():
        ops: list[list] = []
        cur = None
        for it in d["items"]:
            kind = it[0]
            if kind == "l":
                p1, p2 = it[1], it[2]
                if cur is None or abs(cur[0] - p1.x) > 0.01 or abs(cur[1] - p1.y) > 0.01:
                    ops.append(["m", round(p1.x, 2), round(p1.y, 2)])
                ops.append(["l", round(p2.x, 2), round(p2.y, 2)])
                cur = (p2.x, p2.y)
            elif kind == "c":
                p1, c1, c2, p2 = it[1], it[2], it[3], it[4]
                if cur is None or abs(cur[0] - p1.x) > 0.01 or abs(cur[1] - p1.y) > 0.01:
                    ops.append(["m", round(p1.x, 2), round(p1.y, 2)])
                ops.append(["c", round(c1.x, 2), round(c1.y, 2), round(c2.x, 2), round(c2.y, 2),
                            round(p2.x, 2), round(p2.y, 2)])
                cur = (p2.x, p2.y)
            elif kind == "re":
                r = it[1]
                ops += [["m", r.x0, r.y0], ["l", r.x1, r.y0], ["l", r.x1, r.y1], ["l", r.x0, r.y1], ["h"]]
                cur = None
            elif kind == "qu":
                q = it[1]
                ops += [["m", q.ul.x, q.ul.y], ["l", q.ur.x, q.ur.y], ["l", q.lr.x, q.lr.y], ["l", q.ll.x, q.ll.y], ["h"]]
                cur = None
        if not ops:
            continue
        if d.get("closePath") and ops[-1][0] != "h":
            ops.append(["h"])
        rect = d["rect"]
        fill = _hex(d.get("fill")) if d.get("type") in ("f", "fs") else None
        stroke = _hex(d.get("color")) if d.get("type") in ("s", "fs") else None
        if fill == "#ffffff" and not stroke and rect.width * rect.height >= 0.98 * page_area:
            continue  # plain white page background
        dashes = []
        m = re.match(r"\[([^\]]*)\]", d.get("dashes") or "")
        if m and m.group(1).strip():
            dashes = [float(x) for x in m.group(1).split()]
        out.append(Shape(ops=[[o[0], *[round(float(v), 2) for v in o[1:]]] for o in ops], bbox=_r(rect), fill=fill,
                         stroke=stroke, width=round(float(d.get("width") or 1.0), 2),
                         fill_opacity=float(d.get("fill_opacity") or 1.0),
                         stroke_opacity=float(d.get("stroke_opacity") or 1.0),
                         even_odd=bool(d.get("even_odd")), dashes=dashes,
                         cap=int((d.get("lineCap") or (0,))[0]), join=int(d.get("lineJoin") or 0),
                         z=int(d.get("seqno", 0))))
    return out


def _strip_subset(name: str) -> str:
    return name.split("+", 1)[1] if len(name) > 7 and name[6] == "+" else name


def font_ascents(doc, page) -> dict[str, float]:
    """For each embedded TrueType/OpenType font on the page: how far below the top of a word-processor text
    box the first baseline sits, in em. Measured in LibreOffice Writer (tests/test_converter_basics.py):
    ascender + line gap, both from the typographic metrics when the font sets USE_TYPO_METRICS, else from
    hhea (else the Windows ascent). PyMuPDF's line boxes use the PDF's /Ascent instead, which for fonts such
    as Caladea is 0.15 em taller, so text boxes placed from them land too high."""
    import io
    import logging

    from fontTools.ttLib import TTFont

    logging.getLogger("fontTools").setLevel(logging.ERROR)   # subset fonts have odd timestamps
    out: dict[str, float] = {}
    for f in page.get_fonts(full=True):
        xref, ext, base = f[0], f[1], _strip_subset(f[3])
        if base in out or ext not in ("ttf", "otf", "cff", "ttc"):
            continue
        try:
            buf = doc.extract_font(xref)[3]
            if not buf:
                continue
            tt = TTFont(io.BytesIO(buf), lazy=True)
            upm = tt["head"].unitsPerEm or 1000
            os2 = tt["OS/2"] if "OS/2" in tt else None
            hhea = tt["hhea"] if "hhea" in tt else None
            if os2 is not None and os2.fsSelection & (1 << 7) and os2.sTypoAscender > 0:
                asc = os2.sTypoAscender + max(0, os2.sTypoLineGap)
            elif hhea is not None and hhea.ascent > 0:
                asc = hhea.ascent + max(0, hhea.lineGap)
            elif os2 is not None and os2.usWinAscent > 0:
                asc = os2.usWinAscent
            else:
                continue
            out[base] = round(asc / upm, 4)
        except Exception:
            continue
    return out


def extract(pdf_path: Path, out_dir: Path, *, password: str | None = None, scanned: list[int] | None = None,
            ocr_page: Callable | None = None, check: Callable[[], None] = lambda: None,
            progress: Callable[[float, str], None] = lambda f, m: None) -> DocModel:
    """Build the model; images are written into out_dir. `ocr_page(pixmap_png_path, page_size)` -> Lines."""
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    if doc.needs_pass:
        doc.authenticate(password or "")
    scanned = set(scanned or [])
    model = DocModel(pages=[], toc=[list(t[:3]) for t in doc.get_toc(simple=True)], metadata=dict(doc.metadata or {}))
    n = doc.page_count
    for pno in range(n):
        check()
        progress(pno / max(1, n), f"Reading page {pno + 1} of {n}")
        page = doc[pno]
        if page.rotation:
            page.remove_rotation()
        w, h = page.rect.width, page.rect.height
        pg = Page(index=pno, width=round(w, 2), height=round(h, 2), scanned=pno in scanned)
        for f in page.get_fonts(full=True):
            base = f[3]
            model.fonts[base] = model.fonts.get(base, False) or f[1] != "n/a"
        for lk in page.get_links():
            if lk.get("kind") == pymupdf.LINK_URI and lk.get("uri"):
                pg.links.append(Link(bbox=_r(lk["from"]), uri=lk["uri"]))
            elif lk.get("kind") == pymupdf.LINK_GOTO and lk.get("page", -1) >= 0:
                pg.links.append(Link(bbox=_r(lk["from"]), page=int(lk["page"])))
        pg.tables = _tables(page)
        pg.blocks = _lines_to_blocks(_split_by_links(_split_by_cells(_page_lines(page), pg.tables), pg.links))
        ascents = font_ascents(doc, page)
        if ascents:
            for blk in pg.blocks:
                for ln in blk.lines:
                    for sp in ln.spans:
                        sp.ascent = ascents.get(_strip_subset(sp.font))
        # Images, in paint order.
        log = page.get_bboxlog()
        img_z = [i for i, (kind, _) in enumerate(log) if kind == "fill-image"]
        seen: dict[int, tuple] = {}
        infos = page.get_image_info(xrefs=True)
        for k, info in enumerate(infos):
            bbox = info["bbox"]
            if bbox[2] - bbox[0] < 0.5 or bbox[3] - bbox[1] < 0.5:
                continue
            xref = info.get("xref", 0)
            z = img_z[k] if k < len(img_z) else 0
            saved = None
            if xref:
                saved = seen.get(xref) or _save_image(doc, xref, out_dir, f"p{pno + 1}-x{xref}")
                seen[xref] = saved
            if saved is None:  # inline image or undecodable: render just that area
                pix = page.get_pixmap(clip=pymupdf.Rect(bbox), dpi=200, alpha=False)
                name = f"p{pno + 1}-img{k}.png"
                pix.save(out_dir / name)
                saved = (name, pix.width, pix.height, "png", False)
            name, iw, ih, ext, original = saved
            tr = info.get("transform") or (1, 0, 0, 1, 0, 0)
            flipped_or_rotated = abs(tr[1]) > 1e-3 or abs(tr[2]) > 1e-3 or tr[0] < 0 or tr[3] < 0
            if flipped_or_rotated:
                name, iw, ih, ext, original = _bake_transform(out_dir, name, tr, pno, k)
            pg.images.append(Image(bbox=_r(bbox), file=name, width=iw, height=ih, ext=ext, z=z, original=original,
                                   scan=pno in scanned and (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) >= 0.5 * w * h))
        shapes = _shapes(page, w * h)
        if len(shapes) > MAX_SHAPES:
            pg.raster_fallback = True
            model.notes.append(f"Page {pno + 1} has {len(shapes)} vector paths; they are kept as one picture.")
            shapes = []
        pg.shapes = shapes
        _assign_tables(pg)
        if pno in scanned and ocr_page is not None:
            png = out_dir / f"p{pno + 1}-ocr.png"
            page.get_pixmap(dpi=300, alpha=False).save(png)
            for line in ocr_page(png, (w, h)):
                line.invisible = True
                pg.blocks.append(Block([line], list(line.bbox)))
        if pg.raster_fallback:
            _raster_drawings(doc, pno, out_dir, pg)
        model.pages.append(pg)
    doc.close()
    progress(1.0, "Pages read")
    return model


def _bake_transform(out_dir: Path, name: str, tr, pno: int, k: int):
    """Rotated or mirrored picture: apply the orientation to the pixels (lossless PNG)."""
    from PIL import Image as PILImage

    img = PILImage.open(out_dir / name)
    a, b, c, d = tr[0], tr[1], tr[2], tr[3]
    # Image space -> page space. Pick the nearest of the 8 axis-aligned orientations.
    if abs(b) < 1e-3 and abs(c) < 1e-3:
        if a < 0:
            img = img.transpose(PILImage.Transpose.FLIP_LEFT_RIGHT)
        if d < 0:
            img = img.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)
    else:
        if b > 0 and c < 0:
            img = img.transpose(PILImage.Transpose.ROTATE_270)
        elif b < 0 and c > 0:
            img = img.transpose(PILImage.Transpose.ROTATE_90)
        else:
            img = img.transpose(PILImage.Transpose.TRANSPOSE)
    new = f"p{pno + 1}-img{k}-oriented.png"
    img.save(out_dir / new)
    return new, img.width, img.height, "png", False



def _raster_drawings(doc, pno: int, out_dir: Path, pg: Page) -> None:
    """Draw the page without its text into one picture (used when there are too many vector paths)."""
    import pymupdf

    tmp = pymupdf.open()
    tmp.insert_pdf(doc, from_page=pno, to_page=pno)
    page = tmp[0]
    page.add_redact_annot(page.rect)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    pix = page.get_pixmap(dpi=300, alpha=True)
    name = f"p{pno + 1}-graphics.png"
    pix.save(out_dir / name)
    tmp.close()
    pg.images = [Image(bbox=[0, 0, pg.width, pg.height], file=name, width=pix.width, height=pix.height, ext="png",
                       z=0, original=False)]


def plain_text(model: DocModel) -> str:
    """Model text in reading order (tables row by row), pages separated by form feeds."""
    pages = []
    for p in model.pages:
        parts = [b.text for b in p.blocks]
        pages.append("\n".join(parts))
    return "\f".join(pages)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def scale_page(p: Page, s: float, dx: float = 0.0, dy: float = 0.0) -> None:
    """Scale a page's contents in place (used to fit pages onto one slide size)."""
    def box(b):
        return [round(b[0] * s + dx, 2), round(b[1] * s + dy, 2), round(b[2] * s + dx, 2), round(b[3] * s + dy, 2)]

    for blk in p.blocks:
        blk.bbox = box(blk.bbox)
        for ln in blk.lines:
            ln.bbox = box(ln.bbox)
            for sp in ln.spans:
                sp.bbox = box(sp.bbox)
                sp.size = round(sp.size * s, 2)
                if len(sp.origin) == 2:
                    sp.origin = [round(sp.origin[0] * s + dx, 2), round(sp.origin[1] * s + dy, 2)]
    for img in p.images:
        img.bbox = box(img.bbox)
    for sh in p.shapes:
        sh.bbox = box(sh.bbox)
        sh.width = sh.width * s
        sh.ops = [[o[0], *[round(v * s + (dx if i % 2 == 0 else dy), 2) for i, v in enumerate(o[1:])]] for o in sh.ops]
    for t in p.tables:
        t.bbox = box(t.bbox)
        t.xs = [round(x * s + dx, 2) for x in t.xs]
        t.ys = [round(y * s + dy, 2) for y in t.ys]
        for c in t.cells:
            c.bbox = box(c.bbox)
    for lk in p.links:
        lk.bbox = box(lk.bbox)
    p.width, p.height = round(p.width * s + 2 * dx, 2), round(p.height * s + 2 * dy, 2)


def text_only(pdf_path: Path, password: str | None = None) -> str:
    """Page text (whitespace fragments merged back), pages separated by form feeds; no pictures or tables."""
    import pymupdf

    out = []
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        for page in doc:
            if page.rotation:
                page.remove_rotation()
            blocks = _lines_to_blocks(_page_lines(page))
            out.append("\n".join(ln.text for b in blocks for ln in b.lines))
    return "\f".join(out)
