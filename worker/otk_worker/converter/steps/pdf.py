"""Steps that read PDFs: extraction, text, page images, SVG, HTML pages, EPUB, PDF/A, pdf2docx, OCR layer."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .. import docmodel, engines, epub, ocr, pdfa, pdfpages
from ..context import Artifact, StepContext
from . import step


def _open(ctx: StepContext, path: Path):
    import pymupdf

    doc = pymupdf.open(path)
    if doc.needs_pass:
        doc.authenticate(ctx.password or "")
    return doc


def _ocr_lines(ctx: StepContext):
    """Callback for docmodel.extract: OCR one rendered page and return its lines (pt coordinates)."""
    def fn(png: Path, size: tuple[float, float]):
        op = ocr.ocr_page(png, png.parent, langs=ctx.options.ocr_languages, dpi=300, check=ctx.check, upright=False)
        page = ocr.to_page(op, 0, size[0], size[1], png.parent, image_file=png.name)
        ctx.low_confidence.extend({"page": None, "text": w.text, "confidence": round(w.conf, 2)}
                                  for w in op.words if w.conf < ctx.options.ocr_min_confidence)
        return [ln for b in page.blocks for ln in b.lines]
    return fn


def extract_model(ctx: StepContext, src: Path) -> tuple[docmodel.DocModel, Path]:
    out_dir = ctx.folder("docmodel")
    use_ocr = ctx.options.ocr and bool(ctx.scanned_pages)
    model = docmodel.extract(src, out_dir, password=ctx.password, scanned=ctx.scanned_pages,
                             ocr_page=_ocr_lines(ctx) if use_ocr else None, check=ctx.check,
                             progress=lambda f, m: ctx.progress(f, m))
    if ctx.scanned_pages and not use_ocr:
        ctx.expect(f"{len(ctx.scanned_pages)} scanned page(s) have no text layer and OCR is off: they stay pictures.")
    for n in model.notes:
        ctx.note(n)
    path = model.save(out_dir / "model.json")
    return model, path


@step("pdf_extract")
def pdf_extract(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    _, path = extract_model(ctx, src.path)
    return Artifact("docmodel", [path])


@step("pdf_text")
def pdf_text(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """Reading-order text; table rows become tab-separated lines; pages end with a form feed."""
    model, _ = extract_model(ctx, src.path)
    pages = []
    for p in model.pages:
        lines: list[str] = []
        done_tables: set[int] = set()
        for blk in p.blocks:
            if blk.table is not None:
                if blk.table in done_tables:
                    continue
                done_tables.add(blk.table)
                t = p.tables[blk.table]
                grid = {(c.row, c.col): c.text for c in t.cells}
                for r in range(t.rows):
                    lines.append("\t".join(grid.get((r, c), "") for c in range(t.cols)).rstrip("\t"))
                continue
            for ln in blk.lines:
                lines.append(ln.text.rstrip())
        pages.append("\n".join(lines))
    out = ctx.path("out.txt")
    out.write_text("\n\f".join(pages) + "\n", encoding="utf-8")
    return Artifact("txt", [out])


@step("pdf_render")
def pdf_render(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """One image per page at the chosen DPI (sRGB)."""
    from PIL import Image as PILImage

    from ...common.imageio import SRGB_ICC

    dpi = ctx.options.dpi
    doc = _open(ctx, src.path)
    out_dir = ctx.folder("pages")
    paths = []
    n = doc.page_count
    for i, page in enumerate(doc):
        ctx.progress(i / max(1, n), f"Rendering page {i + 1} of {n} at {dpi} DPI")
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if target == "jpeg":
            p = out_dir / f"{i + 1:04d}.jpg"
            img.save(p, "JPEG", quality=ctx.options.jpeg_quality, dpi=(dpi, dpi), icc_profile=SRGB_ICC, subsampling=0)
        else:
            p = out_dir / f"{i + 1:04d}.png"
            img.save(p, "PNG", dpi=(dpi, dpi), icc_profile=SRGB_ICC, optimize=False, compress_level=6)
        paths.append(p)
    doc.close()
    if target == "jpeg":
        ctx.expect(f"Pages are JPEG images at quality {ctx.options.jpeg_quality} (lossy).")
    return Artifact(target, paths, {"dpi": dpi})


@step("pdf_svg")
def pdf_svg(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, mpath = extract_model(ctx, src.path)
    if ctx.options.mode == "exact":
        paths = pdfpages.page_svgs(src.path, ctx.folder("svg"), exact=True, model=model, password=ctx.password,
                                   check=ctx.check, progress=ctx.progress)
        return Artifact("svg", paths)
    out_dir = ctx.folder("svg")
    paths = []
    for i in range(len(model.pages)):
        ctx.progress(i / max(1, len(model.pages)), f"Page {i + 1}")
        p = out_dir / f"{i + 1:04d}.svg"
        p.write_text(pdfpages.editable_page_svg(model, i, mpath.parent), encoding="utf-8")
        paths.append(p)
    ctx.expect("Editable SVG uses real text in the PDF's font names; the viewer lays the text out, so line "
               "lengths differ where those fonts are not installed.")
    return Artifact("svg", paths)


@step("pdf_html_pages")
def pdf_html_pages(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    import html

    model, _ = extract_model(ctx, src.path)
    doc = _open(ctx, src.path)
    parts = []
    for i, page in enumerate(doc):
        ctx.progress(i / max(1, doc.page_count), f"Page {i + 1}")
        if page.rotation:
            page.remove_rotation()
        svg = pdfpages.page_svg(page, model, exact=True)
        svg = pdfpages.uniquify_ids(svg, f"p{i + 1}-")
        parts.append(f'<section class="page" id="page-{i + 1}">'
                     f'{pdfpages.inline_svg(svg, page.rect.width, page.rect.height)}</section>')
    doc.close()
    title = model.metadata.get("title") or src.path.stem
    nav = outline_nav(model.toc, ctx)
    out = ctx.path("out.html")
    out.write_text(
        f'<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>'
        "body{background:#e8e8e8;margin:0;padding:16px}.page{background:#fff;margin:0 auto 16px;width:max-content;"
        "box-shadow:0 1px 4px rgba(0,0,0,.3)}.page svg{display:block}"
        "nav.outline{max-width:60em;margin:0 auto 16px;font:14px system-ui,sans-serif}"
        "@media print{body{background:none;padding:0}.page{box-shadow:none;margin:0;break-after:page}nav.outline{display:none}}"
        "</style></head><body>\n" + nav + "\n".join(parts) + "\n</body></html>\n", encoding="utf-8")
    return Artifact("html", [out])


def outline_nav(toc: list, ctx: StepContext) -> str:
    """The PDF's bookmarks as a collapsible list of links to the pages."""
    import html

    if not toc:
        return ""
    items, depth = [], 0
    for level, title, page in ((int(t[0]), str(t[1]), int(t[2])) for t in toc):
        while depth < level:
            items.append("<ul>")
            depth += 1
        while depth > level:
            items.append("</ul>")
            depth -= 1
        items.append(f'<li><a href="#page-{max(1, page)}">{html.escape(title)}</a></li>')
        ctx.added_text.append(title)
    items.extend("</ul>" for _ in range(depth))
    return f'<nav class="outline"><details><summary>Bookmarks</summary>{"".join(items)}</details></nav>\n'



@step("pdf_fxl_epub")
def pdf_fxl_epub(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    model, _ = extract_model(ctx, src.path)
    doc = _open(ctx, src.path)
    pages = []
    for i, page in enumerate(doc):
        ctx.progress(i / max(1, doc.page_count), f"Page {i + 1}")
        if page.rotation:
            page.remove_rotation()
        w, h = page.rect.width * 4 / 3, page.rect.height * 4 / 3
        svg = pdfpages.page_svg(page, model, exact=True)
        pages.append(epub.FxlPage(svg=svg, width=w, height=h))
    doc.close()
    out = ctx.path("out.epub")
    lang = (model.metadata.get("language") or "en").split("-")[0] or "en"
    epub.write_fixed_layout(out, pages, title=model.metadata.get("title") or src.path.stem, language=lang,
                            toc=model.toc)
    return Artifact("epub", [out])


@step("scanned_extract")
def scanned_extract(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """Each page's own image, copied without re-encoding when its format already matches."""
    import pikepdf
    from pikepdf import PdfImage
    from PIL import Image as PILImage

    out_dir = ctx.folder("pages")
    paths: list[Path] = []
    rerendered: list[int] = []
    with pikepdf.open(src.path, password=ctx.password or "") as pdf:
        doc = _open(ctx, src.path)
        for i, page in enumerate(pdf.pages):
            ctx.progress(i / max(1, len(pdf.pages)), f"Page {i + 1}")
            images = list(page.images.values())
            rotate = int(page.obj.get("/Rotate", 0)) % 360
            mupage = doc[i]
            dpi = None
            if len(images) == 1 and rotate == 0:
                pimg = PdfImage(images[0])
                dpi = round(pimg.width / (float(mupage.rect.width) / 72), 2)
                stem = out_dir / f"{i + 1:04d}"
                try:
                    written = Path(pimg.extract_to(fileprefix=str(stem)))
                except Exception:
                    written = None
                if written is not None:
                    ext = written.suffix.lower()
                    if (target == "jpeg" and ext in (".jpg", ".jpeg")) or (target == "png" and ext == ".png"):
                        paths.append(written)
                        continue
                    img = PILImage.open(written)
                    img.load()
                    written.unlink(missing_ok=True)
                    paths.append(_save_as(img, out_dir / f"{i + 1:04d}", target, dpi, ctx))
                    if target == "jpeg":
                        ctx.expect("Page images that were not JPEG were saved as JPEG (lossy).")
                    continue
            # Several images, text, or a rotated page: render the whole page instead.
            rerendered.append(i + 1)
            pix = mupage.get_pixmap(dpi=ctx.options.dpi, alpha=False)
            img = PILImage.frombytes("RGB", (pix.width, pix.height), pix.samples)
            paths.append(_save_as(img, out_dir / f"{i + 1:04d}", target, ctx.options.dpi, ctx))
        doc.close()
    if rerendered:
        ctx.note(f"Page(s) {', '.join(map(str, rerendered))} were rendered at {ctx.options.dpi} DPI because they are "
                 "not a single upright image.")
    return Artifact(target, paths)


def _save_as(img, stem: Path, target: str, dpi, ctx: StepContext) -> Path:
    dpi_t = (dpi, dpi) if dpi else None
    if target == "jpeg":
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        p = stem.with_suffix(".jpg")
        img.save(p, "JPEG", quality=ctx.options.jpeg_quality, **({"dpi": dpi_t} if dpi_t else {}))
    else:
        p = stem.with_suffix(".png")
        img.save(p, "PNG", **({"dpi": dpi_t} if dpi_t else {}))
    return p


@step("pdfa_read")
def pdfa_read(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """PDF/A is PDF. Kept byte-for-byte, or with the PDF/A identification removed on request."""
    out = ctx.path("out.pdf")
    if ctx.options.keep_pdfa_id:
        shutil.copyfile(src.path, out)
        ctx.note("The file is copied unchanged, so it still says it is PDF/A.")
    else:
        pdfa.strip_declaration(src.path, out)
        ctx.expect("The PDF/A identification was removed from the metadata.")
    return Artifact("pdf", [out])


def ocrmypdf(ctx: StepContext, src: Path, out: Path, output_type: str) -> None:
    langs = "+".join(ctx.options.ocr_languages)
    cmd = [sys.executable, "-m", "ocrmypdf", "--output-type", output_type, "--optimize", "0", "--skip-text",
           "-l", langs, "--jobs", "1", "--quiet"]
    if output_type.startswith("pdfa"):
        cmd += ["--pdfa-image-compression", "lossless"]
    cmd += [str(src), str(out)]
    engines.run(cmd, check=ctx.check, timeout=1800, what="OCRmyPDF", ok_codes=(0, 6))
    if not out.exists():
        raise engines.EngineFailed("OCRmyPDF did not produce a file.")


@step("scanned_as_pdf")
def scanned_as_pdf(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    out = ctx.path("out.pdf")
    if ctx.options.ocr:
        ctx.progress(0.05, "Recognising text (OCR)")
        ocrmypdf(ctx, src.path, out, "pdf")
        ctx.note("An invisible OCR text layer was added; the page images are unchanged.")
    else:
        shutil.copyfile(src.path, out)
        ctx.expect("OCR is off, so the pages stay pictures without searchable text.")
    return Artifact("pdf", [out])


@step("gs_pdfa")
def gs_pdfa(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    flavour = pdfa.FLAVOURS[target]
    out = ctx.path(f"out-{flavour}.pdf")
    title = _title(src.path)
    if src.format == "pdf_scanned" and ctx.options.ocr:
        ctx.progress(0.05, "Recognising text (OCR) and writing PDF/A")
        tmp = ctx.path("ocr.pdf")
        ocrmypdf(ctx, src.path, tmp, f"pdfa-{flavour[0]}")
        ctx.note("An invisible OCR text layer was added; the page images are unchanged.")
        v, engine, info = pdfa.make(tmp, out, flavour, ctx.folder("pdfa"), title=title,
                                    source_file=_embed(ctx, flavour), check=ctx.check)
    else:
        ctx.progress(0.05, "Making PDF/A (pikepdf repair first, Ghostscript if needed)")
        v, engine, info = pdfa.make(src.path, out, flavour, ctx.folder("pdfa"), title=title,
                                    source_file=_embed(ctx, flavour), check=ctx.check)
    if engine == "ghostscript":
        ctx.note("The PDF needed Ghostscript to become PDF/A (fonts and page content were rewritten).")
    else:
        ctx.note("PDF/A was reached without rewriting the page content (pikepdf repair).")
    for r in info.get("repairs", []):
        ctx.note(f"PDF/A repair: {r}")
    return Artifact(target, [out], {"pdfa": {"engine": engine, **{k: v_ for k, v_ in info.items() if k != "firstAttempt"}},
                                    "validation": v.to_dict()})


def _embed(ctx: StepContext, flavour: str) -> Path | None:
    if flavour == "3b" and ctx.options.pdfa_embed_source:
        ctx.note(f"The source file {ctx.source.name} is attached inside the PDF/A-3 file.")
        return ctx.source
    return None


def _title(path: Path) -> str:
    try:
        import pymupdf
        with pymupdf.open(path) as d:
            return (d.metadata or {}).get("title") or ""
    except Exception:
        return ""


@step("pdfa_upgrade")
def pdfa_upgrade(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    flavour = pdfa.FLAVOURS[target]
    out = ctx.path(f"out-{flavour}.pdf")
    pdfa.upgrade(src.path, out, flavour)
    if flavour == "3b" and ctx.options.pdfa_embed_source:
        tmp = ctx.path("attached.pdf")
        pdfa.finish(out, tmp, flavour, source_file=ctx.source)
        out = tmp
    ctx.note("Only the PDF/A declaration changed; the content is untouched.")
    return Artifact(target, [out], {"pdfa": {"upgradedFrom": src.format}})


def needs_docmodel_route(path: Path, password: str | None) -> str | None:
    """pdf2docx handles left-to-right, upright text only. Returns the reason to switch, or None."""
    import pymupdf

    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            doc.authenticate(password or "")
        for page in doc:
            if page.rotation:
                return "a rotated page"
            for b in page.get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    dx, dy = ln["dir"]
                    if abs(dy) > 0.01 or dx < 0:
                        return "rotated text"
                    if docmodel.is_rtl("".join(s["text"] for s in ln["spans"])):
                        return "right-to-left text"
    return None


@step("pdf2docx")
def pdf2docx_step(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    reason = needs_docmodel_route(src.path, ctx.password)
    if reason is None and ctx.scanned_pages and ctx.options.ocr:
        reason = "scanned pages that need OCR"
    out = ctx.path("out.docx")
    if reason:
        from .docmodel_out import write_docx_flow

        ctx.note(f"The PDF has {reason}, which pdf2docx cannot rebuild; the document-model route was used instead.")
        model, mpath = extract_model(ctx, src.path)
        write_docx_flow(model, mpath.parent, out, ctx)
        _outline(ctx, out, model.toc)
        return Artifact("docx", [out], {"route": "docmodel_docx"})
    ctx.progress(0.05, "pdf2docx: rebuilding the layout")
    cmd = [sys.executable, "-m", "otk_worker.converter.pdf2docx_cli", str(src.path), str(out)]
    engines.run(cmd, check=ctx.check, timeout=1800 + src.path.stat().st_size / 1_000_000 * 60, what="pdf2docx")
    if not out.exists():
        raise engines.EngineFailed("pdf2docx did not produce a document.")
    import pymupdf
    with pymupdf.open(src.path) as d:
        _outline(ctx, out, d.get_toc(simple=True))
    return Artifact("docx", [out])


def _outline(ctx: StepContext, docx_path: Path, toc: list) -> None:
    from ..docx_post import apply_outline

    if toc:
        placed = apply_outline(docx_path, toc)
        if placed < len(toc):
            ctx.note(f"{len(toc) - placed} of {len(toc)} PDF bookmarks have no matching heading text in the document.")
