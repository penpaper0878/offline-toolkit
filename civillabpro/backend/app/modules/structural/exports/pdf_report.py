"""A4 calculation report (PDF) for any structural design.

Reads only the generic result structure (key results, calculation sheet, bar
schedule, quantities, drawing model), so every element type prints through the
same code. Each page carries the title block and "Page n of m".
"""

from __future__ import annotations

import html
import io
import math
import re
from pathlib import Path
from typing import Any

from reportlab.graphics.shapes import Circle, Drawing, Group, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle

INK = colors.HexColor("#1b2430")
MUTED = colors.HexColor("#5b6675")
RULE = colors.HexColor("#c9d0d9")
BAND = colors.HexColor("#eef1f5")
OK = colors.HexColor("#1a7f4b")
BAD = colors.HexColor("#b42318")
LAYER_COLOURS = {"concrete": INK, "rebar": colors.HexColor("#b42318"), "stirrup": colors.HexColor("#1f5fbf"),
                 "dimension": MUTED, "text": INK, "support": MUTED, "centerline": MUTED}

_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"


def _register_fonts() -> tuple[str, str, str, bool]:
    """Embed the bundled DejaVu Sans (Greek letters and maths signs print the same on every machine).

    Falls back to the PDF base fonts, with Greek from the Symbol font, if the files are missing.
    """
    regular, bold = _FONT_DIR / "DejaVuSans.ttf", _FONT_DIR / "DejaVuSans-Bold.ttf"
    if regular.exists() and bold.exists():
        pdfmetrics.registerFont(TTFont("CLP-Sans", str(regular)))
        pdfmetrics.registerFont(TTFont("CLP-Sans-Bold", str(bold)))
        pdfmetrics.registerFontFamily("CLP-Sans", normal="CLP-Sans", bold="CLP-Sans-Bold", italic="CLP-Sans", boldItalic="CLP-Sans-Bold")
        return "CLP-Sans", "CLP-Sans-Bold", "CLP-Sans", True
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", False


REG, BOLD, ITAL, UNICODE_FONT = _register_fonts()

BODY = ParagraphStyle("body", fontName=REG, fontSize=8.5, leading=11, textColor=INK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5, textColor=MUTED)
H2 = ParagraphStyle("h2", parent=BODY, fontName=BOLD, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4, keepWithNext=1)
EQ = ParagraphStyle("eq", parent=BODY, fontName=ITAL, fontSize=8.5, leading=11.5)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=2)

_GREEK = ({"tau": "\u03c4", "gamma": "\u03b3", "eps": "\u03b5", "alpha": "\u03b1"} if UNICODE_FONT
          else {"tau": "t", "gamma": "g", "eps": "e", "alpha": "a"})


def _greek(name: str) -> str:
    return _GREEK[name] if UNICODE_FONT else f'<font face="Symbol">{_GREEK[name]}</font>'
_SUB = re.compile(r"\b(tau|gamma|eps|[A-Za-z]+)('?)_([A-Za-z0-9]+(?:,[A-Za-z0-9]+)*)('?)")


def fx(text: str, prose: bool = False) -> str:
    """Calculation-sheet markup to reportlab paragraph markup (subscripts, powers, Greek letters).

    With ``prose`` (titles, notes) " x " and "sqrt" stay words: "about the x axis" is not a product.
    """
    t = html.escape(str(text), quote=False)

    def sub(m: re.Match[str]) -> str:
        base = _greek(m.group(1)) if m.group(1) in _GREEK else m.group(1)
        return f"{base}{m.group(2)}<sub>{m.group(3)}</sub>{m.group(4)}"

    t = _SUB.sub(sub, t)
    t = re.sub(r"\bgamma\b", _greek("gamma"), t)
    t = re.sub(r"\^(\d+(?:\.\d+)?)", r"<super>\1</super>", t)
    t = re.sub(r"\^((?:<font[^>]*>[^<]*</font>|[^\s<^()]+)(?:<sub>[^<]*</sub>)?)", r"<super>\1</super>", t)  # ^alpha_n
    t = re.sub(r"\b(mm|m)(2|3)\b", r"\1<super>\2</super>", t)
    if not prose:
        t = t.replace(" x ", " \u00d7 ")
    if UNICODE_FONT:
        t = t.replace("&lt;=", "\u2264").replace("&gt;=", "\u2265")
        if not prose:
            t = t.replace("sqrt", "\u221a")
    return t


_LE, _GE = ("\u2264", "\u2265") if UNICODE_FONT else ("&lt;=", "&gt;=")


def fmt(value: Any, dp: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int | float):
        return f"{value:,.{dp}f}" if dp > 0 else f"{value:,.0f}"
    return str(value)


class _NumberedCanvas(canvas.Canvas):
    """Defers page output so the title block can print the total page count."""

    def __init__(self, *args: Any, title_block: dict[str, str], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict[str, Any]] = []
        self._tb = title_block

    def showPage(self) -> None:  # noqa: N802 (reportlab API)
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._title_block(total)
            super().showPage()
        super().save()

    def _title_block(self, total: int) -> None:
        w, h = A4
        x0, x1, top = 15 * mm, w - 15 * mm, h - 10 * mm
        rows = [
            [("Organisation", self._tb["organization"]), ("Project", self._tb["project"]), ("Job no.", self._tb["job"])],
            [("Calculation", self._tb["calculation"]), ("Client", self._tb["client"]), ("Rev.", self._tb["revision"])],
            [("Designed", self._tb["designed"]), ("Checked", self._tb["checked"]), ("Date", self._tb["date"])],
        ]
        widths = [0.40, 0.40, 0.20]
        row_h = 7.2 * mm
        self.setStrokeColor(RULE)
        self.setLineWidth(0.6)
        self.rect(x0, top - 3 * row_h, x1 - x0, 3 * row_h)
        for r, row in enumerate(rows):
            y = top - (r + 1) * row_h
            if r:
                self.line(x0, y + row_h, x1, y + row_h)
            x = x0
            for (label, value), frac in zip(row, widths, strict=True):
                cw = frac * (x1 - x0)
                if x > x0:
                    self.line(x, y, x, y + row_h)
                self.setFillColor(MUTED)
                self.setFont(REG, 6)
                self.drawString(x + 1.5 * mm, y + row_h - 2.6 * mm, label.upper())
                self.setFillColor(INK)
                self.setFont(BOLD, 8.5)
                text = value
                while text and self.stringWidth(text, BOLD, 8.5) > cw - 3 * mm:
                    text = text[:-1]
                self.drawString(x + 1.5 * mm, y + 1.7 * mm, text if text == value else text[:-1] + ".")
                x += cw
        self.setFont(REG, 7)
        self.setFillColor(MUTED)
        self.drawString(x0, 9 * mm, self._tb["footer"])
        self.drawRightString(x1, 9 * mm, f"Page {self._pageNumber} of {total}")


def _table(data: list[list[Any]], widths: list[float], header: bool = True, extra: list[tuple[Any, ...]] | None = None) -> Table:
    style = [
        ("FONT", (0, 0), (-1, -1), REG, 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BAND), ("FONT", (0, 0), (-1, 0), BOLD, 8), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    t.setStyle(TableStyle(style + (extra or [])))
    return t


def _verdict(ok: bool) -> Paragraph:
    colour = "#1a7f4b" if ok else "#b42318"
    return Paragraph(f'<font color="{colour}"><b>{"OK" if ok else "Not OK"}</b></font>', RIGHT)


def view_drawing(view: dict[str, Any], max_w: float, max_h: float) -> Drawing:
    """Render one drawing-model view to scale within a box (points)."""
    xmin, ymin, xmax, ymax = view["bounds"]
    scale = min(max_w / max(xmax - xmin, 1e-6), max_h / max(ymax - ymin, 1e-6))
    d = Drawing((xmax - xmin) * scale, (ymax - ymin) * scale)
    g = Group()

    def X(x: float) -> float:  # noqa: N802
        return (x - xmin) * scale

    def Y(y: float) -> float:  # noqa: N802
        return (y - ymin) * scale

    for it in view["items"]:
        colour = LAYER_COLOURS.get(it.get("layer", "text"), INK)
        t = it["t"]
        if t == "line":
            g.add(Line(X(it["x1"]), Y(it["y1"]), X(it["x2"]), Y(it["y2"]), strokeColor=colour, strokeWidth=0.9 if it["layer"] == "rebar" else 0.5))
        elif t == "polyline":
            pts = [c for x, y in it["points"] for c in (X(x), Y(y))]
            if it["closed"]:
                pts += pts[:2]
            g.add(PolyLine(pts, strokeColor=colour, strokeWidth=0.9 if it["layer"] == "concrete" else 0.6))
        elif t == "circle":
            g.add(Circle(X(it["cx"]), Y(it["cy"]), max(it["r"] * scale, 0.8), strokeColor=colour, strokeWidth=0.4, fillColor=colour if it["filled"] else None))
        elif t == "text":
            if it.get("rot"):
                label = Group(String(0, 0, it["text"], fontName=REG, fontSize=max(it["h"] * scale, 5.5), fillColor=colour, textAnchor=it["anchor"]))
                label.rotate(it["rot"])
                label.translate(Y(it["y"]), -X(it["x"]))  # in the turned frame: back to (X, Y) on the page
                g.add(label)
            else:
                g.add(String(X(it["x"]), Y(it["y"]), it["text"], fontName=REG, fontSize=max(it["h"] * scale, 5.5), fillColor=colour,
                             textAnchor=it["anchor"]))
        elif t == "leader":
            g.add(Line(X(it["x"]), Y(it["y"]), X(it["tx"]), Y(it["ty"]) + 0.3 * it["h"] * scale, strokeColor=MUTED, strokeWidth=0.4))
            left = it["tx"] < it["x"]  # a label placed to the left of its point reads towards it
            g.add(String(X(it["tx"]) + (-2 if left else 2), Y(it["ty"]), it["text"], fontName=REG, fontSize=max(it["h"] * scale, 5.5), fillColor=INK,
                         textAnchor="end" if left else "start"))
        elif t == "dim":
            fs = max(it["h"] * scale, 5.5)
            tick = 0.35 * it["h"] * scale
            if it["horizontal"]:
                yd = (max(it["y1"], it["y2"]) if it["offset"] >= 0 else min(it["y1"], it["y2"])) + it["offset"]
                g.add(Line(X(it["x1"]), Y(yd), X(it["x2"]), Y(yd), strokeColor=colour, strokeWidth=0.4))
                for x, y in ((it["x1"], it["y1"]), (it["x2"], it["y2"])):
                    g.add(Line(X(x), Y(y), X(x), Y(yd), strokeColor=colour, strokeWidth=0.25))
                    g.add(Line(X(x) - tick, Y(yd) - tick, X(x) + tick, Y(yd) + tick, strokeColor=colour, strokeWidth=0.6))
                g.add(String(X((it["x1"] + it["x2"]) / 2), Y(yd) + 0.25 * fs, it["text"], fontName=REG, fontSize=fs, fillColor=colour, textAnchor="middle"))
            else:
                xd = (max(it["x1"], it["x2"]) if it["offset"] >= 0 else min(it["x1"], it["x2"])) + it["offset"]
                g.add(Line(X(xd), Y(it["y1"]), X(xd), Y(it["y2"]), strokeColor=colour, strokeWidth=0.4))
                for x, y in ((it["x1"], it["y1"]), (it["x2"], it["y2"])):
                    g.add(Line(X(x), Y(y), X(xd), Y(y), strokeColor=colour, strokeWidth=0.25))
                    g.add(Line(X(xd) - tick, Y(y) - tick, X(xd) + tick, Y(y) + tick, strokeColor=colour, strokeWidth=0.6))
                label = Group(String(0, 0, it["text"], fontName=REG, fontSize=fs, fillColor=colour, textAnchor="middle"))
                label.rotate(90)
                label.translate(Y((it["y1"] + it["y2"]) / 2), -(X(xd) - 0.25 * fs))
                g.add(label)
    d.add(g)
    return d


SERIES_COLOURS = (colors.HexColor("#2a78d6"), colors.HexColor("#eb6834"))  # validated pair: line series, then point series


def _nice_step(span: float) -> float:
    raw = span / 5.0 if span > 0 else 1.0
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)


def chart_drawing(chart: dict[str, Any], width: float, height: float) -> Drawing:
    """A plain x-y chart: hairline grid, labelled axes, line series and marked points with their labels."""
    pts = [p for s_ in chart["series"] for p in s_["points"]]
    xmin, xmax = min(0.0, min(p[0] for p in pts)), max(p[0] for p in pts)
    ymin, ymax = min(0.0, min(p[1] for p in pts)), max(p[1] for p in pts)
    xs, ys = _nice_step(xmax - xmin), _nice_step(ymax - ymin)
    xmin, xmax = math.floor(xmin / xs) * xs, math.ceil(xmax * 1.05 / xs) * xs
    ymin, ymax = math.floor(ymin / ys) * ys, math.ceil(ymax * 1.05 / ys) * ys
    left, bottom, right, top = 46.0, 30.0, 10.0, 16.0
    pw, ph = width - left - right, height - bottom - top
    d = Drawing(width, height)

    def X(v: float) -> float:  # noqa: N802
        return left + (v - xmin) / (xmax - xmin) * pw

    def Y(v: float) -> float:  # noqa: N802
        return bottom + (v - ymin) / (ymax - ymin) * ph

    v = xmin
    while v <= xmax + 1e-9:
        d.add(Line(X(v), bottom, X(v), bottom + ph, strokeColor=RULE, strokeWidth=0.3))
        d.add(String(X(v), bottom - 10, f"{v:g}", fontName=REG, fontSize=6.5, fillColor=MUTED, textAnchor="middle"))
        v += xs
    v = ymin
    while v <= ymax + 1e-9:
        d.add(Line(left, Y(v), left + pw, Y(v), strokeColor=RULE, strokeWidth=0.3))
        d.add(String(left - 4, Y(v) - 2.2, f"{v:g}", fontName=REG, fontSize=6.5, fillColor=MUTED, textAnchor="end"))
        v += ys
    d.add(Line(left, bottom, left + pw, bottom, strokeColor=MUTED, strokeWidth=0.6))
    d.add(Line(left, bottom, left, bottom + ph, strokeColor=MUTED, strokeWidth=0.6))
    d.add(String(left + pw / 2, 4, f"{chart['x']['label']} ({chart['x']['unit']})", fontName=REG, fontSize=7, fillColor=INK, textAnchor="middle"))
    ylab = Group(String(0, 0, f"{chart['y']['label']} ({chart['y']['unit']})", fontName=REG, fontSize=7, fillColor=INK, textAnchor="middle"))
    ylab.rotate(90)
    ylab.translate(bottom + ph / 2, -10)
    d.add(ylab)
    lx = left + 6
    for i, series in enumerate(chart["series"]):
        colour = SERIES_COLOURS[min(i, len(SERIES_COLOURS) - 1)]
        if series["kind"] == "line":
            coords = [c for p in series["points"] for c in (X(p[0]), Y(p[1]))]
            d.add(PolyLine(coords, strokeColor=colour, strokeWidth=1.2))
            d.add(Line(lx, bottom + ph - 4, lx + 12, bottom + ph - 4, strokeColor=colour, strokeWidth=1.2))
        else:
            labels = series.get("labels") or []
            for j, p in enumerate(series["points"]):
                d.add(Circle(X(p[0]), Y(p[1]), 2.6, fillColor=colour, strokeColor=colors.white, strokeWidth=0.6))
                if j < len(labels):
                    d.add(String(X(p[0]) + 4, Y(p[1]) + 3 + 7 * j, labels[j], fontName=REG, fontSize=6.5, fillColor=INK))
            d.add(Circle(lx + 6, bottom + ph - 4, 2.6, fillColor=colour, strokeColor=colors.white, strokeWidth=0.6))
        d.add(String(lx + 16, bottom + ph - 6.3, series["name"], fontName=REG, fontSize=7, fillColor=INK))
        lx += 22 + 4.2 * len(series["name"])
    return d


def _input_rows(schema: dict[str, Any], inputs: dict[str, Any]) -> list[tuple[str, list[list[Any]]]]:
    """Group the inputs for the report from the element's own schema; hidden fields are left out."""
    groups: dict[str, list[list[Any]]] = {}
    for key, prop in schema.get("properties", {}).items():
        show_if = prop.get("show_if")
        if show_if and any((inputs.get(k) not in v) if isinstance(v, list) else inputs.get(k) != v for k, v in show_if.items()):
            continue
        value = inputs.get(key)
        labels = prop.get("labels") or {}
        shown = "-" if value is None else labels.get(str(value), fmt(value, 3).rstrip("0").rstrip(".") if isinstance(value, float) else fmt(value, 0))
        if value is None and prop.get("description"):
            shown = f"- ({prop['description']})"
        groups.setdefault(prop.get("group", "Input"), []).append(
            [Paragraph(fx(prop.get("title", key), prose=True), BODY), Paragraph(html.escape(shown), BODY), Paragraph(fx(prop.get("unit", "")), BODY)])
    return list(groups.items())


def build_pdf(meta: dict[str, str], inputs: dict[str, Any], input_schema: dict[str, Any], result: dict[str, Any]) -> bytes:
    """Render the report. ``meta`` holds the title-block strings."""
    buf = io.BytesIO()
    width = A4[0] - 30 * mm
    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=36 * mm, bottomMargin=16 * mm,
                          title=f"{meta['calculation']} - {meta['project']}", author=meta["designed"], subject="Structural design calculation")
    doc.addPageTemplates([PageTemplate(id="page", frames=[Frame(doc.leftMargin, doc.bottomMargin, width, A4[1] - 52 * mm, id="body", leftPadding=0,
                                                                rightPadding=0, topPadding=0, bottomPadding=0)])])
    s: list[Any] = []
    status = {"ok": ("All checks OK", "#1a7f4b"), "not_ok": ("Not OK: see the checks marked below", "#b42318"), "stopped": ("Calculation stopped", "#b42318")}[
        result["status"]]
    s.append(Paragraph(f'<b>{html.escape(meta["calculation"])}</b>', ParagraphStyle("title", parent=BODY, fontSize=13, leading=17)))
    s.append(Paragraph(f'Design basis: {", ".join(result["code_basis"])}. Engine {result["element_type"]} {result["engine_version"]}. '
                       f'<font color="{status[1]}"><b>{status[0]}</b></font> ({result["checks_passed"]} of {result["checks_total"]} checks).', BODY))
    if result.get("stop_message"):
        s.append(Paragraph(f'<font color="#b42318">{html.escape(result["stop_message"])}</font>', BODY))

    if result["key_results"]:
        s.append(Paragraph("Summary", H2))
        rows = [["Result", "Value", ""]] + [[k["label"], Paragraph(f"<b>{html.escape(fmt(k['value'], k['dp']))}</b>", BODY), Paragraph(fx(k["unit"]), BODY)]
                                            for k in result["key_results"]]
        s.append(_table(rows, [width * 0.45, width * 0.35, width * 0.20]))

    s.append(Paragraph("Input data", H2))
    for group, rows in _input_rows(input_schema, inputs):
        s.append(KeepTogether(_table([[group, "", ""]] + rows, [width * 0.45, width * 0.35, width * 0.20])))

    for flag in result["sheet"]["flags"]:
        colour = {"error": "#b42318", "warning": "#9a6700", "info": "#5b6675"}[flag["level"]]
        ref = f' <font color="#5b6675">[{html.escape(flag["ref"])}]</font>' if flag["ref"] else ""
        if flag is result["sheet"]["flags"][0]:
            s.append(Paragraph("Notes for the designer", H2))
        s.append(Paragraph(f'<font color="{colour}"><b>{flag["level"].capitalize()}:</b></font> {html.escape(flag["message"])}{ref}', BODY))

    s.append(Paragraph("Calculation", H2))
    col = [width * 0.20, width * 0.58, width * 0.22]
    for section in result["sheet"]["sections"]:
        rows: list[list[Any]] = [[section["title"], "", ""]]
        for it in section["items"]:
            if it["kind"] == "step":
                body = [Paragraph(fx(it["title"], prose=True), BODY)]
                if it["eq"]:
                    body.append(Paragraph(fx(it["eq"]) + (f" = {fx(it['sub'])}" if it["sub"] and it["eq"] else ""), EQ))
                elif it["sub"]:
                    body.append(Paragraph(fx(it["sub"]), EQ))
                value = f"<b>{html.escape(fmt(it['value'], it['dp']))}</b> {fx(it['unit'])}"
                rows.append([Paragraph(html.escape(it["ref"]), SMALL), body, Paragraph(value, RIGHT)])
            else:
                util = f" (utilisation {it['util']:.2f})" if it["util"] is not None else ""
                line = (f"{fx(it['lhs_label'])} = {fmt(it['lhs'], it['dp'])} {_LE if it['op'] == '<=' else _GE} "
                        f"{fx(it['rhs_label'])} = {fmt(it['rhs'], it['dp'])} {fx(it['unit'])}{util}")
                rows.append([Paragraph(html.escape(it["ref"]), SMALL), [Paragraph(f"<b>Check:</b> {fx(it['title'], prose=True)}", BODY), Paragraph(line, EQ)],
                             _verdict(it["ok"])])
        s.append(_table(rows, col, extra=[("SPAN", (0, 0), (-1, 0))]))
        s.append(Spacer(1, 4))

    bbs = result.get("bbs")
    if bbs:
        s.append(Paragraph(f"Bar bending schedule: member {html.escape(bbs['member'])}", H2))
        head = ParagraphStyle("head", parent=SMALL, fontName=BOLD, alignment=1)
        rows = [[Paragraph(h, head) for h in ("Mark", "Description", "Shape", "Dia", "Nos.", "Dimensions (mm)", "Cut length (mm)", "Total (m)", "Mass (kg)")]]
        for it in bbs["items"]:
            dims = ", ".join(f"{k} {v:.0f}" for k, v in it["dims"].items())
            rows.append([it["mark"], Paragraph(html.escape(it["description"]), BODY), Paragraph(html.escape(it["shape"]), SMALL), f"T{it['dia']}", str(it["count"]),
                         Paragraph(dims, SMALL), f"{it['cutting_length_mm']:.0f}", f"{it['total_length_m']:.2f}", f"{it['weight_kg']:.2f}"])
        rows.append(["", "Total", "", "", "", "", "", "", f"{bbs['total_weight_kg']:.2f}"])
        fr = [0.06, 0.23, 0.15, 0.06, 0.06, 0.15, 0.10, 0.09, 0.10]
        s.append(_table(rows, [width * f for f in fr], extra=[("FONT", (0, -1), (-1, -1), BOLD, 8.5), ("ALIGN", (3, 0), (4, -1), "CENTER"),
                                                              ("ALIGN", (6, 0), (-1, -1), "RIGHT")]))
        for note in bbs["notes"]:
            s.append(Paragraph(html.escape(note), SMALL))

    q = result.get("quantities")
    if q:
        s.append(Paragraph("Quantities", H2))
        rows = [["Item", "Quantity", "Unit"], ["Concrete", f"{q['concrete_m3']:.3f}", Paragraph(fx("m3"), BODY)], ["Formwork", f"{q['formwork_m2']:.2f}", Paragraph(fx("m2"), BODY)],
                ["Reinforcement", f"{q['steel_kg']:.1f}", "kg"], ["Steel per volume of concrete", fmt(q["steel_kg_per_m3"], 1), Paragraph(fx("kg/m3"), BODY)]]
        s.append(KeepTogether([_table(rows, [width * 0.45, width * 0.35, width * 0.20])] + [Paragraph(html.escape(b), SMALL) for b in q["basis"]]))

    charts = result.get("charts") or []
    for i, chart in enumerate(charts):
        block = ([Paragraph("Charts", H2)] if i == 0 else []) + [Paragraph(f"<b>{fx(chart['title'], prose=True)}</b>", BODY), Spacer(1, 3),
                                                                 chart_drawing(chart, width * 0.75, 70 * mm)]
        if chart.get("note"):
            block.append(Paragraph(html.escape(chart["note"]), SMALL))
        s.append(KeepTogether(block + [Spacer(1, 6)]))

    drawing = result.get("drawing")
    if drawing:
        views = drawing["views"]
        for i, view in enumerate(views):
            x0, y0, x1, y1 = view["bounds"]
            aspect = (x1 - x0) / max(y1 - y0, 1e-9)
            # a section, a tall elevation, a near-square plan and a long elevation each get the height that suits them
            max_h = 95 * mm if view["id"] == "section" else 120 * mm if aspect < 1 else 110 * mm if aspect < 2 else 60 * mm
            block = [Paragraph(f"<b>{html.escape(view['title'])}</b>", BODY), Spacer(1, 3), view_drawing(view, width * (0.55 if view["id"] == "section" else 1.0), max_h),
                     Spacer(1, 6)]
            if i == len(views) - 1:  # the notes stay with the last view rather than starting a page of their own
                block += [Paragraph(html.escape(note), SMALL) for note in drawing["notes"]]
            # The heading travels with the first view, so it never sits alone at the foot of a page.
            s.append(KeepTogether(([Paragraph("Reinforcement details", H2)] if i == 0 else []) + block))

    doc.build(s, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, title_block=meta, **k))
    return buf.getvalue()
