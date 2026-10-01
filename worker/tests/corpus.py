"""Sample documents for the converter tests (and the samples/ folder).

Every sample carries the same kinds of content the verification checks look
for: headings, English with Markdown-like characters (* # _), Hindi
(Devanagari) and Arabic lines, a hyperlink, a table with merged cells and a
leading-zero code ('001234'), a picture, and bookmarks where the format has
them. Formats that need an engine to create (DOC/XLS/PPT via LibreOffice) are
skipped when the engine is missing.
"""

from __future__ import annotations

import base64
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TITLE = "Quarterly Report"
EN = "Sales rose *sharply* in Q3 # while costs_fell by 4.5 percent."
HI = "नमस्ते दुनिया यह हिंदी पाठ है"
AR = "مرحبا بالعالم هذا نص عربي"
LINK = "https://example.com/report"
TABLE = [["Region", "Code", "Amount"], ["North", "001234", "3.50"], ["South", "004321", "12.25"]]
PASSWORD = "secret-123"


def _font(size: int, name: str = "DejaVuSans.ttf") -> ImageFont.ImageFont:
    for cand in (f"/usr/share/fonts/truetype/dejavu/{name}", f"C:/Windows/Fonts/{'arial.ttf'}", name):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def picture(path: Path, size=(320, 200)) -> Path:
    """A small photo-like picture (gradient + shapes) used inside documents."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (40 + x * 180 // w, 90 + y * 120 // h, 200 - x * 100 // w)
    d = ImageDraw.Draw(img)
    d.ellipse((w // 3, h // 4, w // 3 + 90, h // 4 + 90), fill=(250, 210, 60))
    d.rectangle((20, h - 60, 120, h - 20), fill=(30, 30, 30))
    img.save(path, dpi=(150, 150))
    return path


OCR_LINES = [TITLE, "Sales rose sharply in the third quarter", "while costs fell by 4.5 percent."]


def text_page_image(path: Path, dpi: int = 300, fmt: str = "PNG", table: bool = True) -> Path:
    """A half-letter page of clear black-on-white English text and a ruled table with a merged header (OCR input)."""
    w, h = int(5.8 * dpi), int(5.2 * dpi)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    big, body = _font(int(dpi * 0.28)), _font(int(dpi * 0.16))
    x, y = int(dpi * 0.5), int(dpi * 0.4)
    for i, line in enumerate(OCR_LINES):
        f = big if i == 0 else body
        d.text((x, y), line, fill="black", font=f)
        y += int(f.size * 1.6)
    if table:
        y += int(dpi * 0.25)
        col_w, row_h = int(dpi * 1.4), int(dpi * 0.36)
        rows = [["Regional amounts"]] + TABLE
        lw = max(2, dpi // 100)
        for r_i, row in enumerate(rows):
            top = y + r_i * row_h
            if len(row) == 1:
                d.rectangle((x, top, x + 3 * col_w, top + row_h), outline="black", width=lw)
                d.text((x + int(dpi * 0.08), top + int(dpi * 0.08)), row[0], fill="black", font=body)
                continue
            for c_i, val in enumerate(row):
                left = x + c_i * col_w
                d.rectangle((left, top, left + col_w, top + row_h), outline="black", width=lw)
                d.text((left + int(dpi * 0.08), top + int(dpi * 0.08)), val, fill="black", font=body)
    img.save(path, fmt, dpi=(dpi, dpi), **({"quality": 95} if fmt == "JPEG" else {}))
    return path


def make_docx(path: Path, pic: Path) -> Path:
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm

    doc = Document()
    doc.core_properties.title = TITLE
    doc.add_heading(TITLE, level=1)
    doc.add_paragraph(EN)
    p = doc.add_paragraph()
    r = p.add_run(HI)
    r.font.name = "Noto Sans Devanagari"
    r._r.rPr.rFonts.set(qn("w:cs"), "Noto Sans Devanagari")  # Word sets the complex-script font for Hindi
    p = doc.add_paragraph()
    p.paragraph_format.alignment = 2
    p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
    r = p.add_run(AR)
    r._r.get_or_add_rPr().append(OxmlElement("w:rtl"))
    doc.add_heading("Details", level=2)
    p = doc.add_paragraph("See the full report at ")
    rid = p.part.relate_to(LINK, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink")
    h.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = LINK
    run.append(t)
    h.append(run)
    p._p.append(h)
    table = doc.add_table(rows=4, cols=3)
    table.style = "Table Grid"
    merged = table.cell(0, 0).merge(table.cell(0, 2))
    merged.text = "Regional amounts"
    for r_i, row in enumerate(TABLE, start=1):
        for c_i, val in enumerate(row):
            table.cell(r_i, c_i).text = val
    doc.add_paragraph("A picture of the office:")
    doc.add_picture(str(pic), width=Cm(6))
    doc.save(path)
    return path


def make_xlsx(path: Path) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws["A1"] = "Regional amounts"
    ws.merge_cells("A1:C1")
    for r_i, row in enumerate(TABLE, start=2):
        for c_i, val in enumerate(row, start=1):
            cell = ws.cell(row=r_i, column=c_i)
            if c_i == 3 and r_i > 2:
                cell.value = float(val)
                cell.number_format = "0.00"
            else:
                cell.value = val
                if c_i == 2:
                    cell.number_format = "@"
    ws["B5"] = "Total"
    ws["C5"] = "=SUM(C3:C4)"
    ws["C5"].number_format = "0.00"
    ws["D3"] = 0.125
    ws["D3"].number_format = "0.0%"
    ws2 = wb.create_sheet("Notes")
    ws2["A1"] = HI
    ws2["A2"] = EN
    wb.save(path)
    return path


def make_pptx(path: Path, pic: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Cm, Pt

    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = TITLE
    s1.placeholders[1].text = "Third quarter"
    s2 = prs.slides.add_slide(prs.slide_layouts[1])
    s2.shapes.title.text = "Highlights"
    body = s2.placeholders[1].text_frame
    body.text = EN
    body.add_paragraph().text = HI
    r = body.add_paragraph().add_run()
    r.text = "Full report"
    r.hyperlink.address = LINK
    s2.notes_slide.notes_text_frame.text = "Speaker notes: mention the 4.5 percent."
    s3 = prs.slides.add_slide(prs.slide_layouts[5])
    s3.shapes.title.text = "Amounts"
    gt = s3.shapes.add_table(4, 3, Cm(2), Cm(4), Cm(14), Cm(5)).table
    gt.cell(0, 0).merge(gt.cell(0, 2))
    gt.cell(0, 0).text = "Regional amounts"
    for r_i, row in enumerate(TABLE, start=1):
        for c_i, val in enumerate(row):
            gt.cell(r_i, c_i).text = val
            for p in gt.cell(r_i, c_i).text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(14)
    s3.shapes.add_picture(str(pic), Cm(17), Cm(4), width=Cm(6))
    prs.save(path)
    return path


def html_text(pic_rel: str = "office.png") -> str:
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in TABLE[1:])
    head = "".join(f"<th>{c}</th>" for c in TABLE[0])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{TITLE}</title>
<style>body{{font-family:'Noto Sans',sans-serif}} table{{border-collapse:collapse}} td,th{{border:1px solid #444;padding:4px}}</style>
</head><body>
<h1>{TITLE}</h1>
<p>{EN.replace('*', '&#42;')}</p>
<p lang="hi">{HI}</p>
<p dir="rtl" lang="ar">{AR}</p>
<h2>Details</h2>
<p>See the full report at <a href="{LINK}">{LINK}</a></p>
<table><tr><th colspan="3">Regional amounts</th></tr><tr>{head}</tr>{rows}</table>
<p>A picture of the office:</p>
<p><img src="{pic_rel}" alt="office" width="320" height="200"></p>
<p><img src="https://example.com/remote-logo.png" alt="remote logo"></p>
</body></html>
"""


def make_html(path: Path, pic: Path) -> Path:
    if pic.resolve() != (path.parent / "office.png").resolve():
        shutil.copy(pic, path.parent / "office.png")
    path.write_text(html_text("office.png"), encoding="utf-8")
    return path


def make_txt(path: Path) -> Path:
    lines = [TITLE, "", EN, "# not a heading", "_not italic_ and **not bold**", "Tab\tseparated\tvalues",
             HI, AR, "", "Line after a blank line."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_svg(path: Path, pic: Path) -> Path:
    data = base64.b64encode(pic.read_bytes()).decode()
    path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="600" height="400" viewBox="0 0 600 400">
  <title>{TITLE}</title>
  <rect x="0" y="0" width="600" height="400" fill="#ffffff"/>
  <rect x="20" y="20" width="560" height="60" fill="#1f4e79"/>
  <text x="40" y="62" font-family="DejaVu Sans, sans-serif" font-size="28" fill="#ffffff">{TITLE}</text>
  <circle cx="480" cy="250" r="70" fill="#f2b632" stroke="#333333" stroke-width="3"/>
  <path d="M 40 300 C 120 200, 200 380, 300 280" fill="none" stroke="#c00000" stroke-width="4"/>
  <text x="40" y="140" font-family="DejaVu Sans, sans-serif" font-size="18" fill="#000000">Sales rose sharply in Q3</text>
  <text x="40" y="180" font-family="Noto Sans Devanagari, sans-serif" font-size="18" fill="#000000">{HI}</text>
  <a xlink:href="{LINK}"><text x="40" y="220" font-family="DejaVu Sans, sans-serif" font-size="16" fill="#0563c1">Full report</text></a>
  <image x="330" y="110" width="96" height="60" xlink:href="data:image/png;base64,{data}"/>
</svg>
""", encoding="utf-8")
    return path


def make_pdf(path: Path, pic: Path) -> Path:
    """Born-digital PDF with real fonts, a ruled table, a picture, a link and bookmarks (PyMuPDF Story)."""
    import pymupdf

    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in TABLE[1:])
    head = "".join(f"<th>{c}</th>" for c in TABLE[0])
    html = f"""<h1>{TITLE}</h1><p>{EN}</p><h2>Details</h2><p>See the full report at <a href="{LINK}">{LINK}</a></p>
<table border="1" style="border-collapse: collapse"><tr><th colspan="3">Regional amounts</th></tr><tr>{head}</tr>{rows}</table>
<p>A picture of the office:</p><img src="office.png" width="240" height="150"/>"""
    css = "h1 {font-size: 20pt} p, td, th {font-size: 11pt} td, th {padding: 3pt; border: 1px solid black}"
    arch = pymupdf.Archive(str(pic.parent))
    story = pymupdf.Story(html=html, user_css=css, archive=arch)
    # PyMuPDF's DocumentWriter keeps its file open until the object is freed, and Windows cannot replace an
    # open file, so the story goes to its own file and the finished document is saved under the real name.
    story_pdf = path.with_suffix(".story.pdf")
    writer = pymupdf.DocumentWriter(str(story_pdf))
    mediabox = pymupdf.paper_rect("a4")
    where = mediabox + (56, 56, -56, -56)
    more = True
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    del writer
    doc = pymupdf.open(story_pdf)
    # Second page, so page counts and bookmarks have something to check.
    page = doc.new_page(width=mediabox.width, height=mediabox.height)
    page.insert_text((72, 100), "Appendix", fontsize=18, fontname="helv")
    page.insert_text((72, 130), "Figures are unaudited.", fontsize=11, fontname="helv")
    first = doc[0]
    for rect in first.search_for(LINK):
        first.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": LINK})
    doc.set_toc([[1, TITLE, 1], [2, "Details", 1], [1, "Appendix", 2]])
    doc.set_metadata({"title": TITLE, "author": "Offline Toolkit tests"})
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    try:
        story_pdf.unlink()
    except OSError:
        pass
    return path


def make_scanned_pdf(path: Path, page_png: Path) -> Path:
    import img2pdf

    path.write_bytes(img2pdf.convert(str(page_png)))
    return path


def make_epub(path: Path, pic: Path) -> Path:
    """Minimal valid reflowable EPUB 3 with two chapters, a picture and a nav."""
    def xhtml(title: str, body: str) -> str:
        return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" '
                f'xmlns:epub="http://www.idpf.org/2007/ops" lang="en"><head><meta charset="utf-8"/><title>{title}</title>'
                f'<link rel="stylesheet" href="style.css"/></head><body>{body}</body></html>')
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in TABLE)
    ch1 = xhtml("Chapter 1", f"<h1>{TITLE}</h1><p>{EN}</p><p lang=\"hi\">{HI}</p><p><a href=\"{LINK}\">{LINK}</a></p>")
    ch2 = xhtml("Chapter 2", f"<h1>Details</h1><table>{rows}</table><p><img src=\"office.png\" alt=\"office\"/></p>")
    nav = xhtml("Contents", '<nav epub:type="toc"><ol><li><a href="ch1.xhtml">Quarterly Report</a></li>'
                            '<li><a href="ch2.xhtml">Details</a></li></ol></nav>')
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">urn:uuid:5b1f0c3e-6a39-4f5e-9d0c-0e8b8a1f2c11</dc:identifier>
<dc:title>{TITLE}</dc:title><dc:language>en</dc:language><meta property="dcterms:modified">2026-09-30T00:00:00Z</meta></metadata>
<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/><item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
<item id="css" href="style.css" media-type="text/css"/><item id="img" href="office.png" media-type="image/png"/></manifest>
<spine><itemref idref="ch1"/><itemref idref="ch2"/></spine></package>"""
    container = ('<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/ch1.xhtml", ch1, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/ch2.xhtml", ch2, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", "body{font-family:serif} table{border-collapse:collapse} td{border:1px solid}",
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/office.png", pic.read_bytes(), compress_type=zipfile.ZIP_STORED)
    return path


def encrypt_pdf(src: Path, dst: Path) -> Path:
    import pikepdf

    with pikepdf.open(src) as pdf:
        pdf.save(dst, encryption=pikepdf.Encryption(user=PASSWORD, owner=PASSWORD + "-owner", R=6))
    return dst


def encrypt_office(src: Path, dst: Path) -> Path:
    from msoffcrypto.format.ooxml import OOXMLFile

    with open(src, "rb") as fin, open(dst, "wb") as fout:
        OOXMLFile(fin).encrypt(PASSWORD, fout)
    return dst


def legacy_via_lo(src: Path, out_dir: Path, filt: str) -> Path | None:
    """DOC/XLS/PPT samples: saved by LibreOffice from the OOXML sample."""
    try:
        from otk_worker.converter import libreoffice
        return libreoffice.convert(src, out_dir, filt)
    except Exception:
        return None


def build(out: Path, *, legacy: bool = True, pdfa: bool = True) -> dict[str, Path]:
    """Create every sample in `out`; returns {name: path}."""
    out.mkdir(parents=True, exist_ok=True)
    pic = picture(out / "office.png")
    s: dict[str, Path] = {"picture": pic}
    s["docx"] = make_docx(out / "report.docx", pic)
    s["xlsx"] = make_xlsx(out / "sales.xlsx")
    s["pptx"] = make_pptx(out / "slides.pptx", pic)
    s["html"] = make_html(out / "page.html", pic)
    s["txt"] = make_txt(out / "notes.txt")
    s["svg"] = make_svg(out / "drawing.svg", pic)
    s["pdf"] = make_pdf(out / "document.pdf", pic)
    s["png"] = text_page_image(out / "scan-page.png")
    s["jpeg"] = text_page_image(out / "scan-photo.jpg", dpi=200, fmt="JPEG", table=False)
    s["pdf_scanned"] = make_scanned_pdf(out / "scanned.pdf", s["png"])
    s["epub"] = make_epub(out / "book.epub", pic)
    s["pdf_encrypted"] = encrypt_pdf(s["pdf"], out / "locked.pdf")
    s["docx_encrypted"] = encrypt_office(s["docx"], out / "locked.docx")
    if legacy and shutil.which("soffice"):
        from otk_worker.converter import libreoffice as lo
        for key, src, filt in (("doc", s["docx"], lo.DOC), ("xls", s["xlsx"], lo.XLS), ("ppt", s["pptx"], lo.PPT)):
            got = legacy_via_lo(src, out, filt)
            if got:
                s[key] = got
        try:  # born-digital PDF with Hindi and Arabic text, as Word/LibreOffice users produce them
            got = lo.convert(s["docx"], out / "lo-pdf", lo.pdf_filter("writer"))
            s["pdf_lo"] = got.rename(out / "report-lo.pdf")
            (out / "lo-pdf").rmdir()
        except Exception:
            pass
        if pdfa:
            try:
                got = lo.convert(s["docx"], out / "pdfa", lo.pdf_filter("writer", pdfa=2))
                s["pdfa2b"] = got.rename(out / "archived-2b.pdf")
                (out / "pdfa").rmdir()
            except Exception:
                pass
    return s


if __name__ == "__main__":  # python -m tests.corpus <dir>
    import sys

    for k, v in build(Path(sys.argv[1] if len(sys.argv) > 1 else "samples")).items():
        print(f"{k:14s} {v}")
