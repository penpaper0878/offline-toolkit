"""PDF pages as SVG: exact (glyph outlines + an invisible, selectable text layer) or editable (<text>)."""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Callable

from .docmodel import DocModel, Line


def _overlay_line(ln: Line) -> str:
    text = ln.text.strip()
    if not text:
        return ""
    x0, y0, x1, y1 = ln.bbox
    size = max(s.size for s in ln.spans) or (y1 - y0)
    base = max((s.origin[1] for s in ln.spans if len(s.origin) == 2), default=y1 - 0.2 * (y1 - y0))
    width = max(0.5, x1 - x0)
    rtl = ' direction="rtl" unicode-bidi="embed"' if ln.rtl else ""
    x = x1 if ln.rtl else x0
    rot = ""
    if abs(ln.angle) > 0.5:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rot = f' transform="rotate({-ln.angle:.2f} {cx:.2f} {cy:.2f})"'
        width = max(width, y1 - y0)
    return (f'<text x="{x:.2f}" y="{base:.2f}" font-size="{size:.2f}" textLength="{width:.2f}" '
            f'lengthAdjust="spacingAndGlyphs" fill="#000" fill-opacity="0"{rtl}{rot}>{html.escape(text)}</text>')


def text_layer(model: DocModel, page_index: int) -> str:
    p = model.pages[page_index]
    lines = [_overlay_line(ln) for b in p.blocks for ln in b.lines]
    return '<g class="text-layer" font-family="sans-serif">' + "".join(x for x in lines if x) + "</g>"


def page_svg(page, model: DocModel | None, *, exact: bool) -> str:
    """One page as a standalone SVG document (units: PDF points)."""
    svg = page.get_svg_image(text_as_path=exact)
    if exact and model is not None:
        layer = text_layer(model, page.number)
        svg = svg[: svg.rfind("</svg>")] + layer + "\n</svg>\n"
    return svg


def page_svgs(pdf_path: Path, out_dir: Path, *, exact: bool, model: DocModel | None, password: str | None = None,
              check: Callable[[], None] = lambda: None,
              progress: Callable[[float, str], None] = lambda f, m: None) -> list[Path]:
    import pymupdf

    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    if doc.needs_pass:
        doc.authenticate(password or "")
    paths = []
    for i, page in enumerate(doc):
        check()
        progress(i / max(1, doc.page_count), f"Page {i + 1} of {doc.page_count}")
        if page.rotation:
            page.remove_rotation()
        p = out_dir / f"{i + 1:04d}.svg"
        p.write_text(page_svg(page, model, exact=exact), encoding="utf-8")
        paths.append(p)
    doc.close()
    return paths


def inline_svg(svg_text: str, width_pt: float, height_pt: float) -> str:
    """An SVG document ready to be placed inside HTML (no XML prolog, sized in pt, unique ids)."""
    s = re.sub(r"^<\?xml[^>]*>\s*", "", svg_text.strip())
    s = re.sub(r"<svg\b", f'<svg style="width:{width_pt:.2f}pt;height:{height_pt:.2f}pt"', s, count=1)
    return s


def uniquify_ids(svg_text: str, prefix: str) -> str:
    """Several SVGs in one HTML page must not share ids (clip paths, glyph outlines)."""
    ids = set(re.findall(r'\bid="([^"]+)"', svg_text))
    if not ids:
        return svg_text

    def fix_id(m):
        return f'id="{prefix}{m.group(1)}"'

    out = re.sub(r'\bid="([^"]+)"', fix_id, svg_text)
    out = re.sub(r'url\(#([^)]+)\)', lambda m: f"url(#{prefix}{m.group(1)})" if m.group(1) in ids else m.group(0), out)
    out = re.sub(r'(xlink:href|href)="#([^"]+)"',
                 lambda m: f'{m.group(1)}="#{prefix}{m.group(2)}"' if m.group(2) in ids else m.group(0), out)
    return out


def image_page_svg(image_path: Path, width_pt: float, height_pt: float, model: DocModel | None, page_index: int,
                   *, href: str | None = None) -> str:
    """A scan page: the original image bytes at physical size plus the invisible OCR text layer."""
    if href is None:
        ext = image_path.suffix.lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        href = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode()}"
    layer = text_layer(model, page_index) if model is not None else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" '
            f'width="{width_pt:.2f}pt" height="{height_pt:.2f}pt" viewBox="0 0 {width_pt:.2f} {height_pt:.2f}">'
            f'<image x="0" y="0" width="{width_pt:.2f}" height="{height_pt:.2f}" preserveAspectRatio="none" '
            f'xlink:href="{html.escape(href, quote=True)}"/>{layer}</svg>\n')
