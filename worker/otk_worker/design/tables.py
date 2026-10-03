"""Stage 5: ruled tables become real tables (rows, columns, merged cells, cell text and fills).

The grid comes from the line detector shared with the document converter (horizontal and vertical
rules, merged cells where a separator is missing). A grid only counts as a table when text sits in at
least two of its cells; a button or a frame has one. Words are assigned to cells by their centres, so a
line the OCR read across two cells is split between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import assets, fontmatch
from .textdetect import TextLine, Word
from .textstyle import LineInk, coverage, line_ink


@dataclass
class TableCell:
    row: int
    col: int
    row_span: int
    col_span: int
    box: tuple[float, float, float, float]
    lines: list[LineInk] = field(default_factory=list)
    fill: str | None = None
    weight: int = 400
    italic: bool = False
    align: str = "left"
    valign: str = "middle"

    @property
    def text(self) -> str:
        return "\n".join(li.line.text for li in self.lines)


@dataclass
class Table:
    box: tuple[int, int, int, int]
    xs: list[float]
    ys: list[float]
    cells: list[TableCell]
    border_color: str = "#000000"
    border_width: float = 1.0
    family: str = "Noto Sans"
    size: float = 14.0
    color: str = "#000000"
    candidates: list = field(default_factory=list)

    @property
    def rows(self) -> int:
        return len(self.ys) - 1

    @property
    def cols(self) -> int:
        return len(self.xs) - 1


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _split_line(line: TextLine, cells: list[TableCell]) -> list[tuple[TableCell, TextLine]]:
    """A line inside one cell stays whole; a line across cells is cut into per-cell lines by its words."""
    def cell_of(x: float, y: float) -> TableCell | None:
        for c in cells:
            x0, y0, x1, y1 = c.box
            if x0 <= x <= x1 and y0 <= y <= y1:
                return c
        return None

    x0, y0, x1, y1 = line.box
    whole = cell_of((x0 + x1) / 2, (y0 + y1) / 2)
    if whole is not None and whole.box[0] - 2 <= x0 and x1 <= whole.box[2] + 2:
        return [(whole, line)]
    groups: dict[int, list[Word]] = {}
    owner: dict[int, TableCell] = {}
    for w in line.words:
        c = cell_of((w.box[0] + w.box[2]) / 2, (w.box[1] + w.box[3]) / 2)
        if c is None:
            continue
        groups.setdefault(id(c), []).append(w)
        owner[id(c)] = c
    out = []
    for key, ws in groups.items():
        bx0, by0 = min(w.box[0] for w in ws), min(w.box[1] for w in ws)
        bx1, by1 = max(w.box[2] for w in ws), max(w.box[3] for w in ws)
        out.append((owner[key], TextLine(" ".join(w.text for w in ws), [[bx0, by0], [bx1, by0], [bx1, by1], [bx0, by1]],
                                         float(np.mean([w.conf for w in ws])), line.engine, ws)))
    return out


def _rule_width(img: np.ndarray, xs: list[float], ys: list[float]) -> float:
    """Half the thickness of the grid's rules (px), read across the top and left borders."""
    import cv2

    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    H, W = lab.shape[:2]
    widths = []
    for a, b in zip(xs, xs[1:]):
        x, y = int(round((a + b) / 2)), int(round(ys[0]))
        if 0 <= x < W and 8 <= y < H - 8:
            col = lab[y - 8:y + 9, x]
            widths.append(int((np.linalg.norm(col - col[8], axis=1) < 20).sum()))
    for a, b in zip(ys, ys[1:]):
        x, y = int(round(xs[0])), int(round((a + b) / 2))
        if 8 <= x < W - 8 and 0 <= y < H:
            row = lab[y, x - 8:x + 9]
            widths.append(int((np.linalg.norm(row - row[8], axis=1) < 20).sum()))
    return float(np.median(widths)) / 2 if widths else 1.0


def _thin_rules(img: np.ndarray, xs: list[float], ys: list[float], limit: int = 10) -> float:
    """Share of points on the grid's outer border where the rule is a thin line. The edge of a filled
    area (a button, a coloured box) is found as a 'rule' too, but its colour runs on into the fill."""
    import cv2

    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    H, W = lab.shape[:2]

    def run(y: int, x: int, dy: int, dx: int, col) -> int:
        n = 0
        while 0 <= y < H and 0 <= x < W and n <= limit and np.linalg.norm(lab[y, x] - col) < 20:
            n, y, x = n + 1, y + dy, x + dx
        return n

    thin = total = 0
    for y in (ys[0], ys[-1]):
        for a, b in zip(xs, xs[1:]):
            yy, xx = int(round(y)), int(round((a + b) / 2))
            if 0 <= yy < H and 0 <= xx < W:
                col = lab[yy, xx]
                total += 1
                thin += run(yy, xx, -1, 0, col) + run(yy, xx, 1, 0, col) - 1 <= limit
    for x in (xs[0], xs[-1]):
        for a, b in zip(ys, ys[1:]):
            yy, xx = int(round((a + b) / 2)), int(round(x))
            if 0 <= yy < H and 0 <= xx < W:
                col = lab[yy, xx]
                total += 1
                thin += run(yy, xx, 0, -1, col) + run(yy, xx, 0, 1, col) - 1 <= limit
    return thin / total if total else 0.0


def detect(arr: np.ndarray, clean: np.ndarray, lines: list[TextLine]) -> tuple[list[Table], list[TextLine]]:
    """(tables, the text lines not inside any table)."""
    import cv2

    from ..converter import ocr as tocr

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    tables: list[Table] = []
    remaining = list(lines)
    for t in tocr.detect_tables(gray):
        xs, ys = [float(v) for v in t["xs"]], [float(v) for v in t["ys"]]
        if _thin_rules(clean, xs, ys) < 0.5:
            continue   # the outline of a filled shape, not ruled lines
        cells = [TableCell(r, c, rs, cs, (xs[c], ys[r], xs[c + cs], ys[r + rs])) for r, c, rs, cs in t["cells"]]
        x0, y0, x1, y1 = t["bbox"]
        inside = [ln for ln in remaining if x0 - 2 <= (ln.box[0] + ln.box[2]) / 2 <= x1 + 2
                  and y0 - 2 <= (ln.box[1] + ln.box[3]) / 2 <= y1 + 2]
        assigned: list[tuple[TableCell, TextLine]] = []
        for ln in inside:
            assigned.extend(_split_line(ln, cells))
        with_text = {id(c) for c, _ in assigned}
        if len(xs) < 3 and len(ys) < 3 or len(with_text) < 2:
            continue   # a box or a button, not a table
        inset = 2 + _rule_width(arr, xs, ys)
        for cell, ln in assigned:
            # Inside the cell only, so its rules never count as ink.
            cx0, cy0, cx1, cy1 = cell.box
            li = line_ink(arr, ln, bounds=(cx0 + inset, cy0 + inset, cx1 - inset, cy1 - inset))
            if li is not None:
                cell.lines.append(li)
        for cell in cells:
            cell.lines.sort(key=lambda li: li.box[1])
        remaining = [ln for ln in remaining if ln not in inside]
        tables.append(_style(Table((x0, y0, x1, y1), xs, ys, cells), arr, clean, gray))
    return tables, remaining


def _style(table: Table, arr: np.ndarray, clean: np.ndarray, gray: np.ndarray) -> Table:
    import cv2

    # Rules: their colour and thickness, read along the first horizontal rule.
    y = int(round(table.ys[0]))
    band = arr[max(0, y - 6):y + 7, int(table.xs[0]) + 4:int(table.xs[-1]) - 4]
    if band.size:
        g = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY).astype(np.float64)
        dark = g.mean(axis=1) < np.median(g) - 20
        rows = band[dark] if dark.any() else band
        table.border_color = _hex(np.median(rows.reshape(-1, 3), axis=0))
        table.border_width = float(max(1, int(dark.sum())))
    # Cell fills: the text-free picture inside each cell, away from the rules.
    for cell in table.cells:
        x0, y0, x1, y1 = (int(round(v)) for v in cell.box)
        inner = clean[y0 + 4:y1 - 3, x0 + 4:x1 - 3]
        if inner.size:
            cell.fill = _hex(np.median(inner.reshape(-1, 3), axis=0))
    # A cell the colour of the page around the table is see-through (the page may be a gradient, so
    # compare with what surrounds the table, not with one page colour).
    from .textstyle import color_distance

    x0, y0, x1, y1 = (int(round(v)) for v in table.box)
    H, W = clean.shape[:2]
    outer = np.zeros((H, W), bool)
    outer[max(0, y0 - 12):min(H, y1 + 13), max(0, x0 - 12):min(W, x1 + 13)] = True
    outer[max(0, y0 - 4):min(H, y1 + 5), max(0, x0 - 4):min(W, x1 + 5)] = False
    if outer.any():
        around = _hex(np.median(clean[outer], axis=0))
        for cell in table.cells:
            if cell.fill and color_distance(cell.fill, around) < 5.0:
                cell.fill = None
    # One font for the table (from the longest cell lines), then bold or regular per cell.
    lines = [li for c in table.cells for li in c.lines]
    longest = sorted(lines, key=lambda li: -len(li.line.text))[:6]
    samples = [fontmatch.Sample(li.line.text.strip(), li.ink) for li in longest if li.line.text.strip()]
    if samples:
        script = fontmatch.script_of(" ".join(li.line.text for li in lines))
        table.candidates = fontmatch.match(samples, script)
        if table.candidates:
            table.family = table.candidates[0].family
            face = assets.face(table.family, table.candidates[0].weight)
            sizes = [fontmatch.score_face([fontmatch.Sample(li.line.text.strip(), li.ink)], face)[1]
                     for li in lines if li.line.text.strip()]
            sizes = [z for z in sizes if z > 0]
            table.size = float(np.median(sizes)) if sizes else table.size
            # Bold or regular per cell, from how much ink its text puts down.
            for c in table.cells:
                obs = [(li.line.text.strip(), coverage(arr, li)) for li in c.lines if li.line.text.strip()]
                w = fontmatch.pick_weight(table.family, False, table.size, obs) if obs else None
                c.weight = w or 400
    if lines:
        from .textstyle import _rgb
        table.color = _hex(np.median([_rgb(li.color) for li in lines], axis=0))
    for cell in table.cells:
        if not cell.lines:
            continue
        x0, _, x1, _ = cell.box
        lx0 = min(li.box[0] for li in cell.lines)
        lx1 = max(li.box[2] for li in cell.lines)
        left, right = lx0 - x0, x1 - lx1
        cell.align = "center" if abs(left - right) < 0.15 * (x1 - x0) and left > 0.2 * (x1 - x0) else (
            "right" if right < left * 0.5 else "left")
    return table
