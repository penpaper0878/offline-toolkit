"""OCR: scans and photos to the OCR model, and the writers that only make sense for scans."""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from PIL import Image as PILImage

from .. import epub, ocr, pdfpages
from ..context import Artifact, StepContext
from ..docmodel import DocModel
from ..engines import EngineFailed
from . import step
from .docmodel_out import load


def _page_sources(ctx: StepContext, src: Artifact, work: Path) -> list[tuple[Path, Path, float, float, bool]]:
    """(image to OCR, image to show, page width pt, page height pt, shown image is the original bytes) per page."""
    if src.format in ("png", "jpeg"):
        img = PILImage.open(src.path)
        dpi, assumed = ocr.effective_dpi(img)
        if assumed:
            ctx.note(f"The image has no usable DPI; {dpi:g} DPI was assumed for the page size.")
        shown = work / ("page0001" + src.path.suffix.lower())
        shutil.copyfile(src.path, shown)
        return [(src.path, shown, img.width / dpi * 72, img.height / dpi * 72, True)]
    import pymupdf

    from .pdf import scanned_extract
    originals = scanned_extract(ctx, src, "jpeg" if _all_jpeg(src.path, ctx) else "png").paths
    out = []
    with pymupdf.open(src.path) as doc:
        if doc.needs_pass:
            doc.authenticate(ctx.password or "")
        for i, page in enumerate(doc):
            ctx.check()
            render = work / f"render{i + 1:04d}.png"
            page.get_pixmap(dpi=300, alpha=False).save(render)
            shown = work / f"page{i + 1:04d}{originals[i].suffix.lower()}"
            shutil.copyfile(originals[i], shown)
            out.append((render, shown, page.rect.width, page.rect.height, True))
    return out


def _all_jpeg(path: Path, ctx: StepContext) -> bool:
    import pikepdf

    with pikepdf.open(path, password=ctx.password or "") as pdf:
        for page in pdf.pages:
            imgs = list(page.images.values())
            if len(imgs) != 1 or imgs[0].get("/Filter") not in ("/DCTDecode",):
                return False
    return True


@step("ocr")
def ocr_step(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    langs = ctx.options.ocr_languages
    work = ctx.folder("ocrmodel")
    pages = _page_sources(ctx, src, work)
    model = DocModel(pages=[], metadata={"title": ctx.source.stem})
    if not ctx.options.ocr:
        ctx.expect("OCR is off, so the text in the image is not recognised; the output holds the picture only.")
    for i, (to_read, shown, w, h, original) in enumerate(pages):
        ctx.progress(i / max(1, len(pages)), f"Recognising text on page {i + 1} of {len(pages)} ({'+'.join(langs)})")
        if ctx.options.ocr:
            op = ocr.ocr_page(to_read, work, langs=langs, dpi=None if src.format in ("png", "jpeg") else 300,
                              check=ctx.check)
            if op.rotated:
                # The shown picture turns with the text, so text and image stay aligned.
                img = PILImage.open(shown)
                turned = img.rotate(-op.rotated, expand=True)
                shown = shown.with_name(shown.stem + "-upright.png")
                turned.save(shown)
                original = False
                if op.rotated in (90, 270):
                    w, h = h, w
            page = ocr.to_page(op, i, w, h, work, image_file=shown.name, keep_original=original)
            for note in (ocr.rotate_note(op, i + 1), ocr.skew_note(op, i + 1)):
                if note:
                    ctx.note(note)
            for wd in op.words:
                if wd.conf < ctx.options.ocr_min_confidence:
                    ctx.low_confidence.append({"page": i + 1, "text": wd.text, "confidence": round(wd.conf, 2)})
            if not op.words:
                ctx.note(f"No text was recognised on page {i + 1}.")
        else:
            from ..docmodel import Image, Page
            img = PILImage.open(shown)
            page = Page(index=i, width=round(w, 2), height=round(h, 2), scanned=True,
                        images=[Image(bbox=[0, 0, round(w, 2), round(h, 2)], file=shown.name, width=img.width,
                                      height=img.height, ext=shown.suffix.lstrip(".").replace("jpg", "jpeg"),
                                      original=original, scan=True)])
        model.pages.append(page)
    if ctx.low_confidence:
        ctx.note(f"{len(ctx.low_confidence)} word(s) were recognised with low confidence "
                 f"(below {ctx.options.ocr_min_confidence:.0%}); they are listed in the report.")
    ctx.expect("Text comes from OCR, which can misread characters; check the low-confidence words.")
    path = model.save(work / "model.json")
    return Artifact("ocrmodel", [path], {"languages": langs})


@step("ocr_txt")
def ocr_txt(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, _ = load(src)
    pages = []
    for p in model.pages:
        lines = []
        done: set[int] = set()
        for blk in p.blocks:
            if blk.table is not None:
                if blk.table not in done:
                    done.add(blk.table)
                    t = p.tables[blk.table]
                    grid = {(c.row, c.col): c.text for c in t.cells}
                    lines.extend("\t".join(grid.get((r, c), "") for c in range(t.cols)).rstrip("\t")
                                 for r in range(t.rows))
                continue
            lines.extend(ln.text.rstrip() for ln in blk.lines)
        pages.append("\n".join(lines))
    out = ctx.path("out.txt")
    out.write_text("\n\f".join(pages) + "\n", encoding="utf-8")
    return Artifact("txt", [out])


@step("ocr_html_exact")
def ocr_html_exact(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """Each page: the page picture with the OCR text laid over it, invisible but selectable."""
    model, mdir = load(src)
    parts = []
    for p in model.pages:
        scan = next((i for i in p.images if i.scan), None)
        if scan is None:
            continue
        svg = pdfpages.image_page_svg(mdir / scan.file, p.width, p.height, model, p.index)
        parts.append(f'<section class="page" id="page-{p.index + 1}">{pdfpages.inline_svg(svg, p.width, p.height)}</section>')
    title = model.metadata.get("title") or ctx.source.stem
    out = ctx.path("out.html")
    out.write_text(
        f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>'
        "body{background:#e8e8e8;margin:0;padding:16px}.page{background:#fff;margin:0 auto 16px;width:max-content}"
        ".page svg{display:block}@media print{body{background:none;padding:0}.page{margin:0;break-after:page}}"
        "</style></head><body>\n" + "\n".join(parts) + "\n</body></html>\n", encoding="utf-8")
    return Artifact("html", [out])


@step("ocr_svg_editable")
def ocr_svg_editable(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """Layered SVG per page: cleaned page picture, then live text (one <text> per line)."""
    import base64

    import cv2
    import numpy as np

    model, mdir = load(src)
    out_dir = ctx.folder("svg")
    paths = []
    for p in model.pages:
        ctx.check()
        scan = next((i for i in p.images if i.scan), None)
        bg = ""
        if scan is not None:
            arr = np.asarray(PILImage.open(mdir / scan.file).convert("RGB")).copy()
            sx, sy = arr.shape[1] / p.width, arr.shape[0] / p.height
            mask = np.zeros(arr.shape[:2], np.uint8)
            for blk in p.blocks:
                for ln in blk.lines:
                    for s in ln.spans:
                        x0, y0, x1, y1 = s.bbox
                        mask[max(0, int(y0 * sy) - 3):int(y1 * sy) + 4, max(0, int(x0 * sx) - 3):int(x1 * sx) + 4] = 255
            clean = cv2.inpaint(arr, mask, 3, cv2.INPAINT_TELEA)
            tmp = mdir / f"p{p.index + 1}-svg-bg.png"
            PILImage.fromarray(clean).save(tmp)
            uri = "data:image/png;base64," + base64.b64encode(tmp.read_bytes()).decode()
            bg = (f'<g id="background"><image x="0" y="0" width="{p.width:.2f}" height="{p.height:.2f}" '
                  f'preserveAspectRatio="none" xlink:href="{uri}"/></g>')
        texts = []
        for blk in p.blocks:
            for ln in blk.lines:
                t = ln.text.strip()
                if not t:
                    continue
                s0 = ln.spans[0]
                x0, y0, x1, y1 = ln.bbox
                base = y1 - 0.2 * (y1 - y0)
                d = ' direction="rtl"' if ln.rtl else ""
                x = x1 if ln.rtl else x0
                texts.append(f'<text x="{x:.2f}" y="{base:.2f}" font-family="Arial, \'Noto Sans\', sans-serif" '
                             f'font-size="{s0.size:.1f}" fill="{s0.color}"{d}>{html.escape(t)}</text>')
        svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
               f'xmlns:xlink="http://www.w3.org/1999/xlink" width="{p.width:.2f}pt" height="{p.height:.2f}pt" '
               f'viewBox="0 0 {p.width:.2f} {p.height:.2f}">{bg}<g id="text">{"".join(texts)}</g></svg>\n')
        path = out_dir / f"{p.index + 1:04d}.svg"
        path.write_text(svg, encoding="utf-8")
        paths.append(path)
    ctx.expect("The recognised text was painted out of the page picture and placed on top as live text in a "
               "generic font.")
    return Artifact("svg", paths)


@step("ocr_fxl_epub")
def ocr_fxl_epub(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mdir = load(src)
    pages = []
    for p in model.pages:
        scan = next((i for i in p.images if i.scan), None)
        if scan is None:
            raise EngineFailed(f"Page {p.index + 1} has no page picture.")
        href = f"images/{scan.file}"
        svg = pdfpages.image_page_svg(mdir / scan.file, p.width, p.height, model, p.index, href=href)
        pages.append(epub.FxlPage(svg=svg, width=p.width * 4 / 3, height=p.height * 4 / 3,
                                  resources=[(href, (mdir / scan.file).read_bytes())]))
    out = ctx.path("out.epub")
    epub.write_fixed_layout(out, pages, title=model.metadata.get("title") or ctx.source.stem)
    return Artifact("epub", [out])
