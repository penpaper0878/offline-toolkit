"""Bar bending schedule as an Excel workbook (schedule sheet and a summary by diameter)."""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_THIN = Side(style="thin", color="C9D0D9")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_HEAD = PatternFill("solid", fgColor="EEF1F5")


def build_bbs_xlsx(meta: dict[str, str], bbs: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BBS"
    ws["A1"] = "Bar bending schedule"
    ws["A1"].font = Font(bold=True, size=14)
    info = [("Project", meta["project"]), ("Job no.", meta["job"]), ("Member", bbs["member"]), ("Calculation", meta["calculation"]),
            ("Revision", meta["revision"]), ("Designed", meta["designed"]), ("Checked", meta["checked"]), ("Date", meta["date"])]
    for i, (k, v) in enumerate(info):
        r, c = 2 + i // 2, 1 + (i % 2) * 4
        ws.cell(r, c, k).font = Font(color="5B6675")
        ws.cell(r, c + 1, v).font = Font(bold=True)

    head = ["Mark", "Description", "Shape", "Dia (mm)", "Nos.", "A (mm)", "B (mm)", "Hook (mm)", "Cutting length (mm)", "Total length (m)",
            "Unit mass (kg/m)", "Mass (kg)", "Cutting length formula"]
    top = 7
    for c, h in enumerate(head, 1):
        cell = ws.cell(top, c, h)
        cell.font, cell.fill, cell.border = Font(bold=True), _HEAD, _BORDER
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    r = top
    for it in bbs["items"]:
        r += 1
        d = it["dims"]
        row = [it["mark"], it["description"], it["shape"], it["dia"], it["count"], d.get("A"), d.get("B"), d.get("hook"), it["cutting_length_mm"],
               None, it["unit_weight_kg_m"], None, it["formula"]]
        for c, v in enumerate(row, 1):
            ws.cell(r, c, v).border = _BORDER
        # Totals are live formulas so an edited count or length re-prices the schedule.
        ws.cell(r, 10, f"=ROUND(E{r}*I{r}/1000,3)")
        ws.cell(r, 12, f"=ROUND(J{r}*K{r},2)")
        ws.cell(r, 11).number_format = "0.0000"
    first, last = top + 1, r
    r += 1
    ws.cell(r, 2, "Total").font = Font(bold=True)
    ws.cell(r, 10, f"=SUM(J{first}:J{last})").font = Font(bold=True)
    ws.cell(r, 12, f"=SUM(L{first}:L{last})").font = Font(bold=True)
    for c in range(1, len(head) + 1):
        ws.cell(r, c).border = _BORDER
    r += 2
    for note in bbs["notes"]:
        ws.cell(r, 1, note).font = Font(color="5B6675", italic=True)
        r += 1
    for c, w in enumerate([7, 38, 26, 9, 7, 10, 10, 10, 13, 12, 11, 11, 60], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(top + 1, 1)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    sm = wb.create_sheet("Summary")
    for c, h in enumerate(["Dia (mm)", "Total length (m)", "Mass (kg)"], 1):
        cell = sm.cell(1, c, h)
        cell.font, cell.fill, cell.border = Font(bold=True), _HEAD, _BORDER
    for i, row in enumerate(bbs["summary"], 2):
        for c, v in enumerate([row["dia"], row["length_m"], row["weight_kg"]], 1):
            sm.cell(i, c, v).border = _BORDER
    end = 1 + len(bbs["summary"])
    sm.cell(end + 1, 1, "Total").font = Font(bold=True)
    sm.cell(end + 1, 3, f"=SUM(C2:C{end})").font = Font(bold=True)
    for c, w in enumerate([12, 18, 14], 1):
        sm.column_dimensions[get_column_letter(c)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
