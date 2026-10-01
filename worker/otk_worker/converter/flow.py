"""Reading-order structure of a document model: headings, paragraphs, lists, tables, pictures.

Used by the reflowing writers (HTML, DOCX editable, XLSX 'Text' sheet) for
both born-digital PDFs and OCR results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .docmodel import Block, DocModel, Image, Span, Table

_BULLET = re.compile(r"^\s*([•●▪◦–—\-\*•·]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)])\s+")


@dataclass
class Item:
    kind: str                                # heading | para | list | table | image | page
    page: int
    spans: list[Span] = field(default_factory=list)
    level: int = 0                           # heading level 1..3
    rtl: bool = False
    table: Table | None = None
    image: Image | None = None
    ordered: bool = False

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


def _block_spans(blk: Block) -> list[Span]:
    """Spans of a paragraph with line breaks turned into single spaces (hyphen at line end kept, no space)."""
    out: list[Span] = []
    for i, ln in enumerate(blk.lines):
        spans = [s for s in ln.spans]
        if i > 0 and out:
            prev = out[-1].text
            first = spans[0] if spans else None
            if first is not None and not prev.endswith((" ", "-", "­", "‐")) and not first.text.startswith(" "):
                sep = Span(**{**first.__dict__, "text": " ", "link": None})
                out.append(sep)
        out.extend(spans)
    return out


def heading_levels(model: DocModel) -> dict[float, int]:
    body = model.body_size()
    sizes = sorted({round(s.size, 1) for p in model.pages for b in p.blocks if b.table is None
                    for ln in b.lines for s in ln.spans if s.text.strip() and s.size >= body * 1.15}, reverse=True)
    return {sz: min(3, i + 1) for i, sz in enumerate(sizes)}


def build(model: DocModel, *, include_scans: bool = True) -> list[Item]:
    levels = heading_levels(model)
    items: list[Item] = []
    for p in model.pages:
        if p.index > 0:
            items.append(Item("page", p.index))
        page_items: list[tuple[float, Item]] = []
        placed_tables: set[int] = set()
        seq = 0.0
        for blk in p.blocks:
            if blk.table is not None:
                if blk.table not in placed_tables:
                    placed_tables.add(blk.table)
                    page_items.append((seq, Item("table", p.index, table=p.tables[blk.table])))
                    seq += 1
                continue
            if all(ln.invisible for ln in blk.lines) and not include_scans:
                continue
            spans = _block_spans(blk)
            text = "".join(s.text for s in spans).strip()
            if not text:
                continue
            big = max((round(s.size, 1) for s in spans if s.text.strip()), default=0)
            rtl = any(ln.rtl for ln in blk.lines)
            if big in levels and len(text) < 200:
                it = Item("heading", p.index, spans, level=levels[big], rtl=rtl)
            elif _BULLET.match(text):
                it = Item("list", p.index, spans, rtl=rtl, ordered=bool(re.match(r"^\s*\(?[\da-zA-Z]{1,3}[.)]", text)))
            else:
                it = Item("para", p.index, spans, rtl=rtl)
            page_items.append((seq, it))
            seq += 1
        # Tables with no text blocks (empty grid) still appear.
        for ti, t in enumerate(p.tables):
            if ti not in placed_tables:
                page_items.append((_position(page_items, p, t.bbox[1]), Item("table", p.index, table=t)))
        for img in sorted(p.images, key=lambda i: i.bbox[1]):
            if img.scan and not include_scans:
                continue
            page_items.append((_position(page_items, p, img.bbox[1]), Item("image", p.index, image=img)))
        page_items.sort(key=lambda t: t[0])
        items.extend(it for _, it in page_items)
    return items


def _position(page_items: list[tuple[float, Item]], page, top: float) -> float:
    """Sequence number that puts an object before the first text item that starts below it."""
    best = None
    for seq, it in page_items:
        y = _top(it, page)
        if y is not None and y >= top - 0.5:
            best = seq if best is None else min(best, seq)
    if best is None:
        return (max((s for s, _ in page_items), default=0.0)) + 0.5
    return best - 0.5 + 0.001 * top / 10000


def _top(it: Item, page) -> float | None:
    if it.spans:
        return min(s.bbox[1] for s in it.spans)
    if it.table is not None:
        return it.table.bbox[1]
    if it.image is not None:
        return it.image.bbox[1]
    return None
