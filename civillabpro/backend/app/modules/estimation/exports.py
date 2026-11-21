"""An estimate as an Excel workbook (abstract with live formulas, details of measurement) and as an A4 PDF."""

from __future__ import annotations

import html
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer

from app.modules.estimation.domain.abstract import DESIGN_QUANTITIES
from app.modules.structural.exports.pdf_report import BODY, BOLD, H2, SMALL, _NumberedCanvas, _table  # the shared report style

_THIN = Side(style="thin", color="C9D0D9")


def _from_design(dl: dict[str, Any]) -> str:
    """Where a design-linked quantity came from: "From RCC beam B1, revision 2: reinforcement steel 527.9 kg"."""
    what, unit = DESIGN_QUANTITIES[dl["key"]]
    return f"From {dl['label']}, revision {dl['revision']}: {what.lower()} {dl['value']:g} {unit}"

_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEAD = PatternFill("solid", fgColor="EEF1F5")
MODES = {"measured": "measured", "design": "from a design", "direct": "entered"}


def _source(it: dict[str, Any]) -> str:
    rs = it["rate_source"]
    if rs["kind"] == "sor":
        return f"{rs['book_title']} {rs['item_code']}".strip()
    if rs["kind"] == "analysis":
        return "rate analysis"
    return "entered"


def build_xlsx(meta: dict[str, str], doc: dict[str, Any], result: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Abstract"
    ws["A1"] = f"Abstract of cost: estimate {meta['calculation']}"
    ws["A1"].font = Font(bold=True, size=14)
    info = [("Project", meta["project"]), ("Job no.", meta["job"]), ("Revision", meta["revision"]), ("Date", meta["date"]),
            ("Prepared", meta["designed"]), ("Issued", meta["checked"])]
    for i, (k, v) in enumerate(info):
        r, c = 2 + i // 2, 1 + (i % 2) * 4
        ws.cell(r, c, k).font = Font(color="5B6675")
        ws.cell(r, c + 1, v).font = Font(bold=True)
    head = ["Item", "Description", "Quantity", "Unit", "Rate (Rs)", "Amount (Rs)", "Rate from", "Quantity"]
    top = 6
    for c, h in enumerate(head, 1):
        cell = ws.cell(top, c, h)
        cell.font, cell.fill, cell.border = Font(bold=True), _HEAD, _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    r = top
    for it, res in zip(doc["items"], result["items"], strict=True):
        r += 1
        row = [res["no"], it["description"], res["quantity"], it["unit"], it["rate"], None, _source(it), MODES[it["quantity_mode"]]]
        for c, v in enumerate(row, 1):
            cell = ws.cell(r, c, v)
            cell.border = _BORDER
            cell.alignment = Alignment(wrap_text=c == 2, vertical="top")
        ws.cell(r, 6, f"=ROUND(C{r}*E{r},2)")  # live: an edited quantity or rate re-prices the abstract
        ws.cell(r, 6).border = _BORDER
        for c in (3, 5, 6):
            ws.cell(r, c).number_format = "#,##0.00" if c != 3 else "#,##0.000"
    first, last = top + 1, r
    r += 1
    ws.cell(r, 2, "Sub-total").font = Font(bold=True)
    ws.cell(r, 6, f"=SUM(F{first}:F{last})" if last >= first else 0).font = Font(bold=True)
    sub = r
    for a in result["abstract"]["additions"]:
        r += 1
        ws.cell(r, 2, f"Add {a['label']} @ {a['pct']:g} percent")
        ws.cell(r, 6, f"=ROUND(F{sub}*{a['pct']}/100,2)")
    r += 1
    ws.cell(r, 2, "Total").font = Font(bold=True)
    ws.cell(r, 6, f"=SUM(F{sub}:F{r - 1})").font = Font(bold=True)
    r += 1
    ws.cell(r, 2, "Say (rounded to the rupee)").font = Font(bold=True)
    ws.cell(r, 6, f"=ROUND(F{r - 1},0)").font = Font(bold=True)
    for rr in range(sub, r + 1):
        ws.cell(rr, 6).number_format = "#,##0.00"
    for col, w in zip("ABCDEFGH", (8, 60, 12, 8, 12, 15, 26, 14), strict=True):
        ws.column_dimensions[col].width = w

    m = wb.create_sheet("Measurements")
    m["A1"] = "Details of measurement"
    m["A1"].font = Font(bold=True, size=14)
    head = ["Item", "Description", "Nos.", "Length (m)", "Breadth (m)", "Depth (m)", "Quantity", "Unit"]
    for c, h in enumerate(head, 1):
        cell = m.cell(3, c, h)
        cell.font, cell.fill, cell.border = Font(bold=True), _HEAD, _BORDER
    r = 3
    for it, res in zip(doc["items"], result["items"], strict=True):
        r += 1
        m.cell(r, 1, res["no"]).font = Font(bold=True)
        m.cell(r, 2, it["description"]).font = Font(bold=True)
        m.cell(r, 2).alignment = Alignment(wrap_text=True)
        start = r + 1
        if it["quantity_mode"] == "measured":
            for ln, q in zip(it["measurements"], res["lines"], strict=True):
                r += 1
                vals = [None, ("Deduct: " if ln["deduct"] else "") + ln["description"], ln["nos"], ln["length"], ln["breadth"], ln["depth"], q, it["unit"]]
                for c, v in enumerate(vals, 1):
                    m.cell(r, c, v).border = _BORDER
            r += 1
            m.cell(r, 2, "Total").font = Font(bold=True)
            m.cell(r, 7, f"=SUM(G{start}:G{r - 1})" if r - 1 >= start else 0).font = Font(bold=True)
        else:
            r += 1
            text = _from_design(it["design"]) if it["quantity_mode"] == "design" and it.get("design") else "Quantity entered"
            m.cell(r, 2, text)
            m.cell(r, 7, res["quantity"]).font = Font(bold=True)
        m.cell(r, 8, it["unit"])
    for col, w in zip("ABCDEFGH", (8, 60, 8, 12, 12, 12, 12, 8), strict=True):
        m.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _money(x: float) -> str:
    return f"{x:,.2f}"


def build_pdf(meta: dict[str, str], doc: dict[str, Any], result: dict[str, Any], status: str, notes: str) -> bytes:
    buf = io.BytesIO()
    width = A4[0] - 30 * mm
    pdf = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=36 * mm, bottomMargin=16 * mm,
                          title=f"{meta['calculation']} - {meta['project']}", author=meta["designed"], subject="Estimate")
    pdf.addPageTemplates([PageTemplate(id="page", frames=[Frame(pdf.leftMargin, pdf.bottomMargin, width, A4[1] - 52 * mm, id="body", leftPadding=0,
                                                                rightPadding=0, topPadding=0, bottomPadding=0)])])
    right = ParagraphStyle("r", parent=BODY, alignment=2)
    s: list[Any] = [Paragraph(f"<b>Estimate: {html.escape(meta['calculation'])}</b>", ParagraphStyle("t", parent=BODY, fontSize=13, leading=17)),
                    Paragraph(("Issued" if status == "issued" else "Draft, not issued") + f". {len(doc['items'])} items.", BODY)]
    ab = result["abstract"]
    s.append(Paragraph("Abstract of cost", H2))
    rows: list[list[Any]] = [["Item", "Description", "Quantity", "Unit", "Rate (Rs)", "Amount (Rs)"]]
    for it, res in zip(doc["items"], result["items"], strict=True):
        src = _source(it)
        rows.append([res["no"], Paragraph(html.escape(it["description"]) + (f'<br/><font size="7" color="#5b6675">{html.escape(src)}</font>'
                                                                            if src != "entered" else ""), BODY),
                     Paragraph(f"{res['quantity']:,.3f}".rstrip("0").rstrip("."), right), it["unit"], Paragraph(_money(it["rate"]), right),
                     Paragraph(_money(res["amount"]), right)])
    rows.append(["", Paragraph("<b>Sub-total</b>", BODY), "", "", "", Paragraph(f"<b>{_money(ab['subtotal'])}</b>", right)])
    for a in ab["additions"]:
        rows.append(["", Paragraph(f"Add {html.escape(a['label'])} @ {a['pct']:g} percent", BODY), "", "", "", Paragraph(_money(a["amount"]), right)])
    rows.append(["", Paragraph("<b>Total</b>", BODY), "", "", "", Paragraph(f"<b>{_money(ab['total'])}</b>", right)])
    rows.append(["", Paragraph("<b>Say (rounded to the rupee)</b>", BODY), "", "", "", Paragraph(f"<b>{_money(ab['rounded'])}</b>", right)])
    s.append(_table(rows, [width * 0.07, width * 0.47, width * 0.11, width * 0.07, width * 0.12, width * 0.16],
                    extra=[("FONT", (0, len(rows) - 2), (-1, -1), BOLD, 8.5)]))
    measured = [(it, res) for it, res in zip(doc["items"], result["items"], strict=True) if it["quantity_mode"] != "direct"]
    if measured:
        s.append(Paragraph("Details of measurement", H2))
        for it, res in measured:
            block: list[Any] = [Paragraph(f"<b>Item {html.escape(res['no'])}</b>: {html.escape(it['description'][:300])}", BODY)]
            if it["quantity_mode"] == "measured":
                mrows: list[list[Any]] = [["Description", "Nos.", "L (m)", "B (m)", "D (m)", "Quantity"]]
                for ln, q in zip(it["measurements"], res["lines"], strict=True):
                    mrows.append([Paragraph(("<i>Deduct:</i> " if ln["deduct"] else "") + html.escape(ln["description"]), BODY), f"{ln['nos']:g}",
                                  *(f"{v:g}" if v is not None else "" for v in (ln["length"], ln["breadth"], ln["depth"])), Paragraph(f"{q:,.2f}", right)])
                mrows.append([Paragraph("<b>Total</b>", BODY), "", "", "", "", Paragraph(f"<b>{res['quantity']:,.2f} {html.escape(it['unit'])}</b>", right)])
                block.append(_table(mrows, [width * 0.42, width * 0.09, width * 0.11, width * 0.11, width * 0.11, width * 0.16]))
            else:
                dl = it["design"]
                block.append(Paragraph(f"{html.escape(_from_design(dl))}, taken as {res['quantity']:g} {html.escape(it['unit'])}"
                                       + (" (the design has changed since)" if res["stale"] else "") + ".", BODY))
            block.append(Spacer(1, 2 * mm))
            s.append(KeepTogether(block))
    if notes.strip():
        s.append(Paragraph("Notes", H2))
        s.append(Paragraph(html.escape(notes).replace("\n", "<br/>"), BODY))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph("Amounts are quantity times rate, to the paisa; additions are percentages of the sub-total; the total is rounded to the "
                       "rupee. Rates are as entered or taken from the schedules and analyses named.", SMALL))
    labels = {"calculation": "Estimate", "designed": "Prepared", "checked": "Issued"}
    pdf.build(s, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, title_block=meta, labels=labels, **k))
    return buf.getvalue()


def build_mb_pdf(meta: dict[str, str], book: dict[str, Any]) -> bytes:
    """The measurement book: the progress of each item against the estimate, then every entry with its lines and its check."""
    buf = io.BytesIO()
    width = A4[0] - 30 * mm
    pdf = BaseDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=36 * mm, bottomMargin=16 * mm,
                          title=f"Measurement book: {meta['calculation']} - {meta['project']}", author=meta["designed"], subject="Measurement book")
    pdf.addPageTemplates([PageTemplate(id="page", frames=[Frame(pdf.leftMargin, pdf.bottomMargin, width, A4[1] - 52 * mm, id="body", leftPadding=0,
                                                                rightPadding=0, topPadding=0, bottomPadding=0)])])
    right = ParagraphStyle("r", parent=BODY, alignment=2)
    entries = book["entries"]
    n_checked = sum(1 for m in entries if m["status"] == "checked")
    s: list[Any] = [Paragraph(f"<b>Measurement book: {html.escape(meta['calculation'])}</b>", ParagraphStyle("t", parent=BODY, fontSize=13, leading=17)),
                    Paragraph(f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, {n_checked} checked.", BODY)]
    s.append(Paragraph("Progress against the estimate", H2))
    rows: list[list[Any]] = [["Item", "Description", "Unit", "Estimated", "Measured", "Checked", "Balance", "Excess", "Value (Rs)"]]
    for it in book["items"]:
        rows.append([it["no"], Paragraph(html.escape(it["description"][:160]) + ("" if it["in_estimate"] else " (not in this revision)"), BODY), it["unit"],
                     *(Paragraph(f"{it[k]:,.2f}", right) for k in ("estimated", "measured", "checked", "balance", "excess")),
                     Paragraph(_money(it["value_measured"]), right)])
    rows.append(["", Paragraph("<b>Total</b>", BODY), "", "", "", "", "", "", Paragraph(f"<b>{_money(book['value_measured'])}</b>", right)])
    s.append(_table(rows, [width * 0.06, width * 0.30, width * 0.06, width * 0.10, width * 0.10, width * 0.10, width * 0.09, width * 0.08,
                           width * 0.11]))
    s.append(Paragraph(f"Value: of the work measured, at the estimate's rates. Of the work checked: Rs {_money(book['value_checked'])}. "
                       f"Beyond the estimated quantities: Rs {_money(book['value_excess'])}.", SMALL))
    if entries:
        s.append(Paragraph("Entries", H2))
        items = {it["item_id"]: it for it in book["items"]}
        for m in entries:
            it = items.get(m["item_id"], {"no": "-", "description": "", "unit": ""})
            head = (f"<b>Entry {m['entry_no']}</b>, {m['measured_on'].strftime('%d %b %Y')}: item {html.escape(it['no'])}, "
                    f"{html.escape(it['description'][:200])}" + (f". <i>{html.escape(m['location'])}</i>" if m["location"] else ""))
            block: list[Any] = [Paragraph(head, BODY)]
            mrows: list[list[Any]] = [["Description", "Nos.", "L (m)", "B (m)", "D (m)", "Quantity"]]
            for ln, q in zip(m["lines"], m["line_quantities"], strict=True):
                mrows.append([Paragraph(("<i>Deduct:</i> " if ln.deduct else "") + html.escape(ln.description), BODY), f"{ln.nos:g}",
                              *(f"{v:g}" if v is not None else "" for v in (ln.length, ln.breadth, ln.depth)), Paragraph(f"{q:,.2f}", right)])
            mrows.append([Paragraph("<b>Total</b>", BODY), "", "", "", "", Paragraph(f"<b>{m['quantity']:,.2f} {html.escape(it['unit'])}</b>", right)])
            block.append(_table(mrows, [width * 0.42, width * 0.09, width * 0.11, width * 0.11, width * 0.11, width * 0.16]))
            checked = (f"checked by {html.escape(m['checked_by_name'])} on {m['checked_at'].strftime('%d %b %Y')}" if m["status"] == "checked"
                       else "not yet checked")
            block.append(Paragraph(f"Measured by {html.escape(m['measured_by_name'])}; {checked}.", SMALL))
            block.append(Spacer(1, 2 * mm))
            s.append(KeepTogether(block))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph("Each line is the number times the dimensions given, to 0.01; a deduction is taken off. Progress is the sum of the "
                       "entries against the estimated quantity of the estimate's current revision.", SMALL))
    labels = {"calculation": "Measurement book", "designed": "Estimate prepared", "checked": "Estimate issued"}
    pdf.build(s, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, title_block=meta, labels=labels, **k))
    return buf.getvalue()
