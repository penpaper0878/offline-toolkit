"""Image steps: PNG/JPEG to PDF (lossless), PNG <-> JPEG, SVG rasterising (resvg), images embedded in SVG."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image as PILImage

from .. import engines, htmlprep, ocr, pdfpages
from ..context import Artifact, StepContext
from ..docmodel import DocModel
from . import step


def _hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


@step("img2pdf")
def img2pdf_step(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """Lossless: JPEG bytes are copied as they are; the page size comes from the image DPI."""
    import img2pdf

    img = PILImage.open(src.path)
    dpi, assumed = ocr.effective_dpi(img)
    path = src.path
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        flat = PILImage.new("RGB", img.size, _hex_rgb(ctx.options.background))
        flat.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        path = ctx.path("flattened.png")
        flat.save(path, dpi=(dpi, dpi))
        ctx.expect(f"Transparent areas were flattened onto {ctx.options.background} (PDF pages are opaque).")
    layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi)) if assumed else None
    if assumed:
        ctx.note(f"The image has no usable DPI; {dpi:g} DPI was assumed for the page size.")
    out = ctx.path("out.pdf")
    kwargs = {"layout_fun": layout} if layout else {}
    out.write_bytes(img2pdf.convert(str(path), rotation=img2pdf.Rotation.ifvalid, **kwargs))
    return Artifact("pdf_scanned", [out], {"dpi": dpi})


@step("raster_convert")
def raster_convert(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    from ...common.imageio import open_image

    loaded = open_image(str(src.path))
    img = loaded.image
    dpi = img.info.get("dpi") or loaded.info_dict().get("dpi")
    icc = img.info.get("icc_profile")
    kw: dict = {}
    if dpi:
        kw["dpi"] = tuple(float(x) for x in (dpi if isinstance(dpi, (tuple, list)) else (dpi, dpi)))
    if icc:
        kw["icc_profile"] = icc
    if target == "jpeg":
        if img.mode in ("RGBA", "LA", "PA", "P"):
            rgba = img.convert("RGBA")
            if rgba.getextrema()[3][0] < 255:
                ctx.expect(f"Transparent areas were flattened onto {ctx.options.background} (JPEG has no transparency).")
            flat = PILImage.new("RGB", img.size, _hex_rgb(ctx.options.background))
            flat.paste(rgba, mask=rgba.split()[-1])
            img = flat
        elif img.mode not in ("RGB", "L", "CMYK"):
            img = img.convert("RGB")
        out = ctx.path("out.jpg")
        img.save(out, "JPEG", quality=ctx.options.jpeg_quality, subsampling=0 if ctx.options.jpeg_quality >= 90 else 2, **kw)
        ctx.expect(f"JPEG is lossy (quality {ctx.options.jpeg_quality}).")
    else:
        if img.mode == "CMYK":
            img = img.convert("RGB")
            ctx.expect("CMYK colours were converted to RGB (PNG has no CMYK).")
        out = ctx.path("out.png")
        img.save(out, "PNG", **kw)
    if loaded.orientation not in (None, 1):
        ctx.note("The EXIF orientation was applied to the pixels.")
    return Artifact(target, [out])


def render_svg(ctx: StepContext, svg: Path, out: Path, *, dpi: int) -> Path:
    exe = engines.require("resvg")
    cmd = [exe, "--dpi", str(dpi), "--zoom", f"{dpi / 96:.6f}", "--shape-rendering", "geometricPrecision",
           "--text-rendering", "geometricPrecision", "--image-rendering", "optimizeQuality"]
    fonts = engines.engines_dir() / "fonts"
    if fonts.is_dir():
        cmd += ["--use-fonts-dir", str(fonts)]
    cmd += [str(svg), str(out)]
    engines.run(cmd, check=ctx.check, timeout=300, what="resvg", cwd=str(svg.parent))
    img = PILImage.open(out)
    img.load()
    img.save(out, "PNG", dpi=(dpi, dpi))  # record the DPI (lossless re-save)
    return out


def complex_script_text(svg: Path) -> bool:
    """Indic, Arabic or Hebrew text, which resvg does not always shape correctly."""
    from .. import textutil
    from .web import svg_text_lines

    return any(textutil.script_of(t) not in (None, "cjk", "thai") for t in svg_text_lines(svg, visible_only=True))


@step("resvg")
def resvg_step(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    out = ctx.path("out.png")
    if complex_script_text(src.path):
        # Chromium shapes Indic and Arabic text correctly; print the drawing and render the page.
        from .pdf import pdf_render
        from .web import chromium_pdf

        ctx.note("The drawing has Indic/Arabic/Hebrew text, so Chromium drew it instead of resvg (correct shaping).")
        pdf = chromium_pdf(ctx, src, "pdf")
        pages = pdf_render(ctx, pdf, "png")
        return Artifact("png", [pages.path], {"dpi": ctx.options.dpi, "engine": "chromium"})
    render_svg(ctx, src.path, out, dpi=ctx.options.dpi)
    return Artifact("png", [out], {"dpi": ctx.options.dpi})


@step("raster_svg_embed")
def raster_svg_embed(ctx: StepContext, src: Artifact, target: str) -> Artifact:
    """The original image bytes at physical size, with an invisible OCR text layer when OCR is on."""
    out_dir = ctx.folder("svg")
    pages: list[tuple[Path, float, float]] = []
    if src.format == "pdf_scanned":
        from .pdf import scanned_extract
        imgs = scanned_extract(ctx, src, "png")
        import pymupdf
        with pymupdf.open(src.path) as doc:
            for img_path, page in zip(imgs.paths, doc):
                pages.append((img_path, page.rect.width, page.rect.height))
    else:
        img = PILImage.open(src.path)
        dpi, assumed = ocr.effective_dpi(img)
        if assumed:
            ctx.note(f"The image has no usable DPI; {dpi:g} DPI was assumed for its physical size.")
        pages.append((src.path, img.width / dpi * 72, img.height / dpi * 72))
    paths = []
    for i, (img_path, w, h) in enumerate(pages):
        ctx.progress(i / max(1, len(pages)), f"Page {i + 1}")
        model = None
        if ctx.options.ocr:
            op = ocr.ocr_page(img_path, ctx.folder("ocr"), langs=ctx.options.ocr_languages, dpi=None, check=ctx.check,
                              upright=False)
            page = ocr.to_page(op, 0, w, h, ctx.folder("ocr"))
            model = DocModel(pages=[page])
        svg = pdfpages.image_page_svg(img_path, w, h, model, 0)
        p = out_dir / f"{i + 1:04d}.svg"
        p.write_text(svg, encoding="utf-8")
        paths.append(p)
    if ctx.options.ocr:
        ctx.note("An invisible OCR text layer makes the text searchable and selectable.")
    return Artifact("svg", paths)


def copy_as(src: Path, dest: Path) -> Path:
    shutil.copyfile(src, dest)
    return dest


def svg_size(path: Path) -> tuple[float, float]:
    return htmlprep.svg_size_pt(path)
