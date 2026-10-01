"""Writers for the document model (born-digital PDF pages and OCR results).

exact    = every page keeps its size; text, pictures and vector shapes sit at
           their original positions (a text box per line).
editable = reflowed: headings, paragraphs, native tables and pictures, or a
           text box per paragraph and native tables on slides.
OCR text (lines with a confidence) is invisible over the page image in exact
mode, and visible in editable mode where the page image is left out.
"""

from __future__ import annotations

import base64
import html
import re
from collections import Counter
from pathlib import Path

from .. import fontnames, ooxml
from ..context import Artifact, StepContext
from ..docmodel import Block, DocModel, Line, Page, Span, Table, is_rtl, scale_page
from ..flow import Item, build as build_flow
from . import step

WORD_MAX_PT = 22 * 72          # Word's largest page side
SLIDE_MIN_PT, SLIDE_MAX_PT = 72, 56 * 72


def load(art: Artifact) -> tuple[DocModel, Path]:
    return DocModel.load(art.path), art.path.parent


def _is_ocr(line: Line) -> bool:
    return line.conf is not None


def _visible_images(page: Page, mode: str):
    """Scan images are shown in exact mode; in editable mode OCR text replaces them."""
    has_ocr_text = any(_is_ocr(ln) for b in page.blocks for ln in b.lines)
    for img in page.images:
        if img.scan and mode == "editable" and has_ocr_text:
            continue
        yield img


def _line_box(line: Line, slack: float = 1.12) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = line.bbox
    w = (x1 - x0) * slack + 2
    if line.rtl:
        return x1 - w, y0, x1, y1 + 0.15 * (y1 - y0)
    return x0, y0, x0 + w, y1 + 0.15 * (y1 - y0)


def _rotated_box(line: Line) -> tuple[tuple[float, float, float, float], float]:
    """Unrotated text box (centred on the line's bounding box) and its angle."""
    import math

    x0, y0, x1, y1 = line.bbox
    a = math.radians(line.angle)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    size = max(sp.size for sp in line.spans) * 1.25
    bw, bh = x1 - x0, y1 - y0
    length = (bw - size * s) / c if c >= s else (bh - size * c) / max(s, 1e-6)
    length = max(length, size) * 1.1
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (cx - length / 2, cy - size / 2, cx + length / 2, cy + size / 2), line.angle


# ------------------------------------------------------------------ PPTX
def _slide_size(model: DocModel, ctx: StepContext) -> tuple[float, float]:
    sizes = Counter((round(p.width, 1), round(p.height, 1)) for p in model.pages)
    w, h = sizes.most_common(1)[0][0] if sizes else (720.0, 540.0)
    s = 1.0
    if max(w, h) > SLIDE_MAX_PT:
        s = SLIDE_MAX_PT / max(w, h)
    if min(w, h) * s < SLIDE_MIN_PT:
        s = SLIDE_MIN_PT / min(w, h)
    if s != 1.0:
        ctx.expect(f"Pages were scaled by {s:.3f} to fit PowerPoint's slide size limits (1–56 inches).")
    return w * s, h * s


def write_pptx(model: DocModel, mdir: Path, out: Path, mode: str, ctx: StepContext) -> Path:
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation()
    sw, sh = _slide_size(model, ctx)
    prs.slide_width, prs.slide_height = Emu(ooxml.emu(sw)), Emu(ooxml.emu(sh))
    blank = prs.slide_layouts[6]
    scaled = 0
    for p in model.pages:
        ctx.check()
        if abs(p.width - sw) > 0.5 or abs(p.height - sh) > 0.5:
            s = min(sw / p.width, sh / p.height)
            scale_page(p, s, (sw - p.width * s) / 2, (sh - p.height * s) / 2)
            scaled += 1
        slide = prs.slides.add_slide(blank)
        _pptx_page(slide, p, mdir, mode)
    if scaled:
        ctx.expect(f"{scaled} page(s) of a different size were scaled to fit the slide size.")
    prs.core_properties.title = model.metadata.get("title") or ""
    prs.save(out)
    return out


def _table_rules(shape, tables: list[Table]) -> bool:
    b = shape.bbox
    for t in tables:
        tb = t.bbox
        if b[0] >= tb[0] - 2 and b[1] >= tb[1] - 2 and b[2] <= tb[2] + 2 and b[3] <= tb[3] + 2:
            return True
    return False


def _pptx_page(slide, p: Page, mdir: Path, mode: str) -> None:
    from pptx.util import Emu

    native_tables = mode == "editable" and bool(p.tables)
    layers = []
    for img in _visible_images(p, mode):
        layers.append((img.z, "img", img))
    for sh in p.shapes:
        if native_tables and _table_rules(sh, p.tables):
            continue
        layers.append((sh.z, "shape", sh))
    layers.sort(key=lambda t: t[0])
    for _, kind, obj in layers:
        if kind == "img":
            x0, y0, x1, y1 = obj.bbox
            slide.shapes.add_picture(str(mdir / obj.file), Emu(ooxml.emu(x0)), Emu(ooxml.emu(y0)),
                                     Emu(max(1, ooxml.emu(x1 - x0))), Emu(max(1, ooxml.emu(y1 - y0))))
        else:
            ooxml.pptx_add_shape(slide, obj)
    if mode == "exact":
        for blk in p.blocks:
            for ln in blk.lines:
                _pptx_line(slide, ln)
    else:
        placed: set[int] = set()
        for blk in p.blocks:
            if blk.table is not None:
                if blk.table not in placed:
                    placed.add(blk.table)
                    _pptx_table(slide, p.tables[blk.table], p, mode)
                continue
            _pptx_block(slide, blk)
        for ti, t in enumerate(p.tables):
            if ti not in placed:
                _pptx_table(slide, t, p, mode)


def _pptx_line(slide, ln: Line) -> None:
    spans = [s for s in ln.spans if s.text]
    if not spans:
        return
    invisible = _is_ocr(ln)
    if abs(ln.angle) > 0.5:
        box, angle = _rotated_box(ln)
        ooxml.pptx_text_box(slide, [spans], box, wrap=False, rtl=ln.rtl, angle=angle, invisible=invisible)
    else:
        ooxml.pptx_text_box(slide, [spans], _line_box(ln), wrap=False, rtl=ln.rtl, invisible=invisible)


def _para_spans(blk: Block) -> list[Span]:
    from ..flow import _block_spans
    return _block_spans(blk)


def _pptx_block(slide, blk: Block) -> None:
    spans = [s for s in _para_spans(blk) if s.text]
    if not spans:
        return
    x0, y0, x1, y1 = blk.bbox
    rtl = any(ln.rtl for ln in blk.lines)
    single = len(blk.lines) == 1
    box = (x0, y0, x0 + (x1 - x0) * (1.12 if single else 1.04) + 2, y1 + 0.2 * (y1 - y0) / max(1, len(blk.lines)))
    if rtl:
        w = box[2] - box[0]
        box = (x1 - w, y0, x1, box[3])
    ooxml.pptx_text_box(slide, [spans], box, wrap=not single, rtl=rtl)


def _cell_spans(p: Page, table_index: int, cell) -> list[Span]:
    spans: list[Span] = []
    for blk in p.blocks:
        if blk.table != table_index:
            continue
        for ln in blk.lines:
            cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
            if cell.bbox[0] - 0.5 <= cx <= cell.bbox[2] + 0.5 and cell.bbox[1] - 0.5 <= cy <= cell.bbox[3] + 0.5:
                if spans and not spans[-1].text.endswith((" ", "-")):
                    spans.append(Span(**{**ln.spans[0].__dict__, "text": " ", "link": None}))
                spans.extend(s for s in ln.spans if s.text)
    return spans


def _pptx_table(slide, t: Table, p: Page, mode: str) -> None:
    from pptx.oxml.ns import qn
    from pptx.util import Emu

    ti = p.tables.index(t)
    x0, y0, x1, y1 = t.bbox
    gf = slide.shapes.add_table(t.rows, t.cols, Emu(ooxml.emu(x0)), Emu(ooxml.emu(y0)),
                                Emu(ooxml.emu(x1 - x0)), Emu(ooxml.emu(y1 - y0)))
    tbl = gf.table
    tblpr = tbl._tbl.tblPr
    for a in ("firstRow", "bandRow"):
        tblpr.set(a, "0")
    style = tblpr.find(qn("a:tableStyleId"))
    if style is None:
        from pptx.oxml import parse_xml
        style = parse_xml(f'<a:tableStyleId {ooxml.XMLNS}/>')
        tblpr.append(style)
    style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # "No Style, Table Grid": plain black grid
    for c in range(t.cols):
        tbl.columns[c].width = Emu(max(1, ooxml.emu(t.xs[c + 1] - t.xs[c])))
    for r in range(t.rows):
        tbl.rows[r].height = Emu(max(1, ooxml.emu(t.ys[r + 1] - t.ys[r])))
    for cell in t.cells:
        target = tbl.cell(cell.row, cell.col)
        if cell.rowspan > 1 or cell.colspan > 1:
            target.merge(tbl.cell(cell.row + cell.rowspan - 1, cell.col + cell.colspan - 1))
        target.margin_left = target.margin_right = Emu(ooxml.emu(2))
        target.margin_top = target.margin_bottom = Emu(ooxml.emu(1))
        spans = _cell_spans(p, ti, cell)
        tf = target.text_frame
        para = tf.paragraphs[0]
        for sp in spans:
            run = para.add_run()
            run.text = sp.text
            ooxml.pptx_run_props(run, sp)


@step("docmodel_pptx", "ocr_pptx_exact", "ocr_pptx_editable")
def to_pptx(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    mode = ctx.options.mode
    if src.format == "ocrmodel" and mode == "editable":
        _use_clean_backgrounds(model, mdir, ctx)
        ctx.expect_check("images", "Each page picture became a cleaned background with live text on top.")
    out = ctx.path("out.pptx")
    write_pptx(model, mdir, out, mode, ctx)
    if mode == "exact" and any(p.tables for p in model.pages):
        ctx.expect_check("tables", "Exact slides draw tables as ruled lines with positioned text (use Editable "
                                   "for PowerPoint tables).")
    return Artifact("pptx", [out])


def _use_clean_backgrounds(model: DocModel, mdir: Path, ctx: StepContext) -> None:
    """Editable slides from a scan: the page picture with the recognised text painted out, behind live text."""
    import cv2
    import numpy as np
    from PIL import Image as PILImage

    for p in model.pages:
        scans = [i for i in p.images if i.scan]
        if not scans:
            continue
        img = scans[0]
        arr = np.asarray(PILImage.open(mdir / img.file).convert("RGB")).copy()
        sx, sy = arr.shape[1] / p.width, arr.shape[0] / p.height
        mask = np.zeros(arr.shape[:2], np.uint8)
        for blk in p.blocks:
            for ln in blk.lines:
                if ln.conf is None:
                    continue
                for s in ln.spans:
                    x0, y0, x1, y1 = s.bbox
                    mask[max(0, int(y0 * sy) - 3):int(y1 * sy) + 4, max(0, int(x0 * sx) - 3):int(x1 * sx) + 4] = 255
        clean = cv2.inpaint(arr, mask, 3, cv2.INPAINT_TELEA)
        name = f"p{p.index + 1}-background.png"
        PILImage.fromarray(clean).save(mdir / name)
        img.file, img.scan, img.original = name, False, False
        # Figures are already part of the background picture.
        p.images = [i for i in p.images if i is img]
        # Tables stay native, drawn without a grid of their own (the background has the lines).
    ctx.expect("Recognised text was painted out of the page picture and placed as live text boxes on top.")


# ------------------------------------------------------------------ DOCX (exact: positioned)
def write_docx_exact(model: DocModel, mdir: Path, out: Path, ctx: StepContext) -> Path:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import parse_xml
    from docx.shared import Emu

    doc = Document()
    body = doc.element.body
    for p_el in list(body):
        if p_el.tag.endswith("}p"):
            body.remove(p_el)
    links: dict[str, str] = {}
    current = None
    for p in model.pages:
        ctx.check()
        s = 1.0
        if max(p.width, p.height) > WORD_MAX_PT:
            s = WORD_MAX_PT / max(p.width, p.height)
            scale_page(p, s)
            ctx.expect(f"Page {p.index + 1} was scaled by {s:.3f} (Word pages are at most 22 inches).")
        size = (round(p.width, 1), round(p.height, 1))
        new_section = current is not None and size != current
        if new_section:
            doc.add_section(WD_SECTION.NEW_PAGE)
        if current is None or new_section:
            sec = doc.sections[-1]
            sec.page_width, sec.page_height = Emu(ooxml.emu(p.width)), Emu(ooxml.emu(p.height))
            sec.orientation = 1 if p.width > p.height else 0
            for m in ("left_margin", "right_margin", "top_margin", "bottom_margin", "header_distance", "footer_distance"):
                setattr(sec, m, Emu(0))
        para = doc.add_paragraph()
        pf = para.paragraph_format
        pf.space_before = pf.space_after = Emu(0)
        pf.line_spacing = Emu(ooxml.emu(1))
        if current is not None and not new_section:
            pf.page_break_before = True
        current = size
        runs: list[str] = []
        layers = [(i.z, "img", i) for i in p.images] + [(sh.z, "shape", sh) for sh in p.shapes]
        layers.sort(key=lambda t: t[0])
        for z, kind, obj in layers:
            if kind == "img":
                rid, _ = doc.part.get_or_add_image(str(mdir / obj.file))
                runs.append(ooxml.docx_picture_run(rid, tuple(obj.bbox), z=10 + z * 2, behind=True))
            else:
                runs.append(ooxml.docx_shape_run(obj, z=10 + z * 2))
        top = 10 + 2 * (max((t[0] for t in layers), default=0) + 1)
        for blk in p.blocks:
            for ln in blk.lines:
                spans = [sp for sp in ln.spans if sp.text]
                if not spans:
                    continue
                invisible = _is_ocr(ln)
                run_xml = []
                for sp in spans:
                    rid = None
                    if sp.link:
                        rid = links.get(sp.link) or doc.part.relate_to(sp.link, RT.HYPERLINK, is_external=True)
                        links[sp.link] = rid
                    run_xml.append(ooxml.docx_run_xml(sp, rtl=ln.rtl, invisible=invisible, rid=rid))
                par_xml = ooxml.docx_para_xml("".join(run_xml), rtl=ln.rtl)
                if abs(ln.angle) > 0.5:
                    box, angle = _rotated_box(ln)
                else:
                    box, angle = _line_box(ln), 0.0
                # OCR text goes under the page picture: searchable and selectable, never seen twice.
                z = 4 if invisible else top
                runs.append(ooxml.docx_textbox_run([par_xml], box, z=z, behind=invisible, rot=angle))
                top += 1
        for r in runs:
            para._p.append(parse_xml(r))
    doc.core_properties.title = model.metadata.get("title") or ""
    doc.save(out)
    return out


@step("docmodel_docx_exact", "ocr_docx_exact")
def to_docx_exact(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    out = ctx.path("out.docx")
    write_docx_exact(model, mdir, out, ctx)
    ctx.expect_check("bookmarks", "Exact pages are built from positioned text boxes; Word's navigation pane "
                                  "does not list headings inside text boxes, so bookmarks and headings are not kept.")
    if any(p.tables for p in model.pages):
        ctx.expect_check("tables", "Exact pages draw tables as ruled lines with positioned text (use Editable for "
                                   "Word tables).")
    return Artifact("docx", [out])


# ------------------------------------------------------------------ DOCX (editable: reflowed)
def _docx_add_runs(doc, par, spans: list[Span], rtl: bool, links: dict, keep_size: bool = True) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import parse_xml

    for sp in spans:
        if not sp.text:
            continue
        rid = None
        if sp.link:
            rid = links.get(sp.link) or doc.part.relate_to(sp.link, RT.HYPERLINK, is_external=True)
            links[sp.link] = rid
        xml = ooxml.docx_run_xml(sp, rtl=rtl, rid=rid)
        if not keep_size:
            xml = re.sub(r'<w:sz w:val="\d+"/><w:szCs w:val="\d+"/>', "", xml)
        wrapped = parse_xml(f'<w:p {ooxml.XMLNS}>{xml}</w:p>')
        for child in list(wrapped):
            par._p.append(child)


def write_docx_flow(model: DocModel, mdir: Path, out: Path, ctx: StepContext, items: list[Item] | None = None) -> Path:
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.shared import Emu, Pt

    doc = Document()
    if model.pages:
        p0 = model.pages[0]
        sec = doc.sections[0]
        w, h = min(p0.width, WORD_MAX_PT), min(p0.height, WORD_MAX_PT)
        sec.page_width, sec.page_height = Emu(ooxml.emu(w)), Emu(ooxml.emu(h))
        left = min((b.bbox[0] for p in model.pages for b in p.blocks), default=72)
        margin = max(18.0, min(72.0, left))
        for m in ("left_margin", "right_margin"):
            setattr(sec, m, Emu(ooxml.emu(margin)))
        for m in ("top_margin", "bottom_margin"):
            setattr(sec, m, Emu(ooxml.emu(min(72.0, margin))))
        text_width = w - 2 * margin
    else:
        text_width = 468.0
    links: dict[str, str] = {}
    items = items if items is not None else build_flow(model, include_scans=True)
    pending_break = False
    for it in items:
        ctx.check()
        if it.kind == "page":
            pending_break = True
            continue
        if it.kind in ("heading", "para", "list"):
            if it.kind == "heading":
                par = doc.add_heading(level=it.level)
            else:
                par = doc.add_paragraph()
            if it.rtl:
                par._p.get_or_add_pPr().insert(0, OxmlElement("w:bidi"))
            _docx_add_runs(doc, par, it.spans, it.rtl, links)
        elif it.kind == "table":
            par = None
            _docx_table(doc, it.table, model.pages[it.page], links)
        elif it.kind == "image":
            img = it.image
            width = min(text_width, img.bbox[2] - img.bbox[0])
            doc.add_picture(str(mdir / img.file), width=Pt(max(1.0, width)))
            par = doc.paragraphs[-1]
        else:
            continue
        if pending_break:
            target = par if par is not None else None
            if target is not None:
                target.paragraph_format.page_break_before = True
            else:
                tbl = doc.tables[-1]._tbl
                brk = doc.add_paragraph()
                brk.paragraph_format.page_break_before = True
                tbl.addprevious(brk._p)
            pending_break = False
    doc.core_properties.title = model.metadata.get("title") or ""
    doc.save(out)
    return out


def _docx_table(doc, t: Table, page: Page, links: dict) -> None:
    from docx.shared import Emu

    ti = page.tables.index(t) if t in page.tables else -1
    table = doc.add_table(rows=t.rows, cols=t.cols)
    table.style = "Table Grid"
    table.autofit = False
    for c in range(t.cols):
        w = Emu(max(1, ooxml.emu(t.xs[c + 1] - t.xs[c])))
        for r in range(t.rows):
            table.cell(r, c).width = w
    for cell in t.cells:
        target = table.cell(cell.row, cell.col)
        if cell.rowspan > 1 or cell.colspan > 1:
            target = target.merge(table.cell(cell.row + cell.rowspan - 1, cell.col + cell.colspan - 1))
        spans = _cell_spans(page, ti, cell) if ti >= 0 else []
        par = target.paragraphs[0]
        if spans:
            _docx_add_runs(doc, par, spans, is_rtl("".join(s.text for s in spans)), links)
        elif cell.text:
            par.add_run(cell.text)


@step("docmodel_docx", "ocr_docx_editable")
def to_docx_flow(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    out = ctx.path("out.docx")
    items = build_flow(model, include_scans=src.format != "ocrmodel")
    if src.format == "ocrmodel":
        ctx.expect_check("images", "The page pictures were replaced by the recognised text, tables and cropped figures.")
    write_docx_flow(model, mdir, out, ctx, items)
    if model.toc:
        from ..docx_post import apply_outline
        apply_outline(out, model.toc)
    return Artifact("docx", [out])


# ------------------------------------------------------------------ HTML (semantic)
def _span_html(sp: Span, body_color: str = "#000000") -> str:
    t = html.escape(sp.text)
    fam, bold, italic = fontnames.split(sp.font)
    if sp.bold or bold:
        t = f"<b>{t}</b>"
    if sp.italic or italic:
        t = f"<i>{t}</i>"
    if sp.color and sp.color.lower() not in (body_color, "#000000") and not sp.link:
        t = f'<span style="color:{sp.color}">{t}</span>'
    if sp.link:
        t = f'<a href="{html.escape(sp.link, quote=True)}">{t}</a>'
    return t


def _data_uri(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif"}.get(ext, "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def write_html(model: DocModel, mdir: Path, out: Path, ctx: StepContext, items: list[Item] | None = None) -> Path:
    items = items if items is not None else build_flow(model)
    title = model.metadata.get("title") or next((it.text for it in items if it.kind == "heading"), "") or "Document"
    parts = []
    open_list = None
    for it in items:
        ctx.check()
        if it.kind != "list" and open_list:
            parts.append(f"</{open_list}>")
            open_list = None
        d = ' dir="rtl"' if it.rtl else ""
        if it.kind == "page":
            parts.append('<hr class="page-break">')
        elif it.kind == "heading":
            parts.append(f"<h{it.level}{d}>{''.join(_span_html(s) for s in it.spans)}</h{it.level}>")
        elif it.kind == "para":
            parts.append(f"<p{d}>{''.join(_span_html(s) for s in it.spans)}</p>")
        elif it.kind == "list":
            tag = "ol" if it.ordered else "ul"
            if open_list != tag:
                if open_list:
                    parts.append(f"</{open_list}>")
                parts.append(f'<{tag} class="source-marked">')
                open_list = tag
            parts.append(f"<li{d}>{''.join(_span_html(s) for s in it.spans)}</li>")
        elif it.kind == "table":
            parts.append(_html_table(it.table, model.pages[it.page]))
        elif it.kind == "image":
            img = it.image
            w, h = img.bbox[2] - img.bbox[0], img.bbox[3] - img.bbox[1]
            parts.append(f'<figure><img src="{_data_uri(mdir / img.file)}" alt="" '
                         f'style="width:{w:.1f}pt;height:{h:.1f}pt"></figure>')
    if open_list:
        parts.append(f"</{open_list}>")
    lang = model.metadata.get("language") or ""
    doc = (f'<!DOCTYPE html>\n<html{f" lang={html.escape(lang)}" if lang else ""}><head><meta charset="utf-8">'
           f"<title>{html.escape(title)}</title><style>"
           "body{font-family:'Noto Sans',Arial,sans-serif;line-height:1.4;max-width:52em;margin:2em auto;padding:0 1em}"
           "table{border-collapse:collapse;margin:1em 0}td,th{border:1px solid #666;padding:3px 6px;vertical-align:top}"
           "figure{margin:1em 0}img{max-width:100%;height:auto}hr.page-break{border:0;border-top:1px dashed #aaa;margin:2em 0}"
           "ul.source-marked,ol.source-marked{list-style:none;padding-left:0}"
           "</style></head><body>\n" + "\n".join(parts) + "\n</body></html>\n")
    out.write_text(doc, encoding="utf-8")
    return out


def _html_table(t: Table, page: Page) -> str:
    ti = page.tables.index(t) if t in page.tables else -1
    grid: dict[tuple[int, int], str] = {}
    for cell in t.cells:
        spans = _cell_spans(page, ti, cell) if ti >= 0 else []
        content = "".join(_span_html(s) for s in spans) if spans else html.escape(cell.text)
        attrs = (f' rowspan="{cell.rowspan}"' if cell.rowspan > 1 else "") + (f' colspan="{cell.colspan}"' if cell.colspan > 1 else "")
        grid[(cell.row, cell.col)] = f"<td{attrs}>{content}</td>"
    rows = []
    for r in range(t.rows):
        rows.append("<tr>" + "".join(grid[(r, c)] for c in range(t.cols) if (r, c) in grid) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


@step("docmodel_html", "ocr_html_editable")
def to_html(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    out = ctx.path("out.html")
    if src.format == "ocrmodel":
        ctx.expect_check("images", "The page pictures were replaced by the recognised text, tables and cropped figures.")
    write_html(model, mdir, out, ctx, build_flow(model, include_scans=src.format != "ocrmodel"))
    return Artifact("html", [out])


# ------------------------------------------------------------------ XLSX
_PLAIN_NUMBER = re.compile(r"^-?(0|[1-9]\d{0,14})(\.\d{1,10})?$")


def typed_value(text: str):
    """Conservative typing: only plain numbers become numbers ('001234', '1,234', dates stay text)."""
    t = text.strip()
    if t != text or not _PLAIN_NUMBER.match(t):
        return text, "@" if text else None
    if "." in t:
        decimals = len(t.split(".")[1])
        return float(t), "0." + "0" * decimals
    return int(t), "0"


def write_cell(ws, row: int, col: int, text: str):
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    value, fmt = typed_value(text)
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("�", value)
    c = ws.cell(row=row, column=col, value=value)
    if fmt:
        c.number_format = fmt
        if fmt == "@":
            c.data_type = "s"
    return c


def set_link(cell, url: str | None) -> None:
    """Excel holds one hyperlink per cell; the first link in the cell's text is kept."""
    if url and cell.hyperlink is None:
        cell.hyperlink = url
        cell.style = "Hyperlink"


def first_link(spans) -> str | None:
    return next((s.link for s in spans if getattr(s, "link", None)), None)


def safe_sheet_title(title: str, used: set[str]) -> str:
    t = re.sub(r"[\[\]:*?/\\]", "_", title).strip("'")[:31] or "Sheet"
    base, n = t, 2
    while t.lower() in used:
        suffix = f" ({n})"
        t = base[: 31 - len(suffix)] + suffix
        n += 1
    used.add(t.lower())
    return t


def write_xlsx(model: DocModel, mdir: Path, out: Path, ctx: StepContext, mode: str) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment

    wb = Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    n = 0
    text_rows: list[tuple[int, str, str | None]] = []
    for p in model.pages:
        for ti, t in enumerate(p.tables):
            ctx.check()
            n += 1
            ws = wb.create_sheet(safe_sheet_title(f"Table {n} (page {p.index + 1})", used))
            for cell in t.cells:
                spans = _cell_spans(p, ti, cell)
                text = "".join(s.text for s in spans) if spans else cell.text
                c = write_cell(ws, cell.row + 1, cell.col + 1, text)
                set_link(c, first_link(spans))
                c.alignment = Alignment(wrap_text=True, vertical="top")
                if cell.rowspan > 1 or cell.colspan > 1:
                    ws.merge_cells(start_row=cell.row + 1, start_column=cell.col + 1,
                                   end_row=cell.row + cell.rowspan, end_column=cell.col + cell.colspan)
            from openpyxl.utils import get_column_letter
            for c in range(t.cols):
                ws.column_dimensions[get_column_letter(c + 1)].width = max(4.0, (t.xs[c + 1] - t.xs[c]) / 5.25)
        for blk in p.blocks:
            if blk.table is None and blk.text.strip():
                text_rows.append((p.index + 1, blk.text, first_link([s for ln in blk.lines for s in ln.spans])))
    if text_rows or not wb.sheetnames:
        ws = wb.create_sheet(safe_sheet_title("Text", used), 0 if not wb.sheetnames else len(wb.sheetnames))
        ws.append(["Page", "Text"])
        for page_no, text, link in text_rows:
            ws.append([page_no, None])
            c = write_cell(ws, ws.max_row, 2, text)
            set_link(c, link)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions["B"].width = 100
        ctx.added_text.extend(["Page", "Text"])
        ctx.added_text.extend(str(pn) for pn, _, _ in text_rows)
    if mode == "exact":
        _original_sheet(wb, model, mdir, used)
    wb.save(out)
    return out


def _original_sheet(wb, model: DocModel, mdir: Path, used: set[str]) -> None:
    """Exact mode for scans: an 'Original' sheet shows each page picture for comparison."""
    from openpyxl.drawing.image import Image as XLImage

    scans = [(p, i) for p in model.pages for i in p.images if i.scan]
    if not scans:
        return
    ws = wb.create_sheet(safe_sheet_title("Original", used))
    row = 1
    for p, img in scans:
        pic = XLImage(str(mdir / img.file))
        scale = min(1.0, 900 / max(1, pic.width))
        pic.width, pic.height = int(pic.width * scale), int(pic.height * scale)
        ws.add_image(pic, f"A{row}")
        row += int(pic.height / 20) + 2


@step("docmodel_xlsx", "ocr_xlsx")
def to_xlsx(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    out = ctx.path("out.xlsx")
    write_xlsx(model, mdir, out, ctx, ctx.options.mode)
    ctx.expect("Tables are on their own sheets and the other text is on the 'Text' sheet, so the reading order changes.")
    return Artifact("xlsx", [out])
