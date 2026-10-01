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
    el = (f'<text x="{x:.2f}" y="{base:.2f}" font-size="{size:.2f}" textLength="{width:.2f}" '
          f'lengthAdjust="spacingAndGlyphs" fill="none" stroke="none"{rtl}{rot}>{html.escape(text)}</text>')
    link = next((s.link for s in ln.spans if s.link), None)
    if link:
        el = f'<a href="{html.escape(link, quote=True)}" xlink:href="{html.escape(link, quote=True)}">{el}</a>'
    return el


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


def _path_d(ops) -> str:
    parts = []
    for op in ops:
        k = op[0]
        if k == "m":
            parts.append(f"M{op[1]:.2f} {op[2]:.2f}")
        elif k == "l":
            parts.append(f"L{op[1]:.2f} {op[2]:.2f}")
        elif k == "c":
            parts.append(f"C{op[1]:.2f} {op[2]:.2f} {op[3]:.2f} {op[4]:.2f} {op[5]:.2f} {op[6]:.2f}")
        elif k == "h":
            parts.append("Z")
    return " ".join(parts)


def editable_page_svg(model: DocModel, page_index: int, mdir: Path) -> str:
    """A page as editable SVG: vector paths, pictures, and real <text> per line (the viewer shapes the text)."""
    from . import fontnames

    p = model.pages[page_index]
    layers = [(i.z, "img", i) for i in p.images] + [(s.z, "shape", s) for s in p.shapes]
    layers.sort(key=lambda t: t[0])
    body = []
    for _, kind, obj in layers:
        if kind == "img":
            x0, y0, x1, y1 = obj.bbox
            data = (mdir / obj.file).read_bytes()
            mime = "image/jpeg" if obj.ext in ("jpeg", "jpg") else "image/png"
            body.append(f'<image x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
                        f'preserveAspectRatio="none" xlink:href="data:{mime};base64,{base64.b64encode(data).decode()}"/>')
        else:
            sh = obj
            attrs = [f'd="{_path_d(sh.ops)}"', f'fill="{sh.fill}"' if sh.fill else 'fill="none"']
            if sh.fill and sh.fill_opacity < 1:
                attrs.append(f'fill-opacity="{sh.fill_opacity:.3f}"')
            if sh.even_odd:
                attrs.append('fill-rule="evenodd"')
            if sh.stroke:
                attrs += [f'stroke="{sh.stroke}"', f'stroke-width="{max(sh.width, 0.1):.2f}"',
                          f'stroke-linecap="{("butt", "round", "square")[min(2, sh.cap)]}"',
                          f'stroke-linejoin="{("miter", "round", "bevel")[min(2, sh.join)]}"']
                if sh.stroke_opacity < 1:
                    attrs.append(f'stroke-opacity="{sh.stroke_opacity:.3f}"')
                if sh.dashes:
                    attrs.append(f'stroke-dasharray="{" ".join(f"{d:.2f}" for d in sh.dashes)}"')
            body.append(f"<path {' '.join(attrs)}/>")
    for blk in p.blocks:
        for ln in blk.lines:
            spans = [s for s in ln.spans if s.text]
            if not spans or not ln.text.strip():
                continue
            base = spans[0].origin[1] if len(spans[0].origin) == 2 else ln.bbox[3] - 0.2 * (ln.bbox[3] - ln.bbox[1])
            x = ln.bbox[2] if ln.rtl else ln.bbox[0]
            rot = ""
            if abs(ln.angle) > 0.5:
                cx, cy = (ln.bbox[0] + ln.bbox[2]) / 2, (ln.bbox[1] + ln.bbox[3]) / 2
                rot = f' transform="rotate({-ln.angle:.2f} {cx:.2f} {cy:.2f})"'
            tspans = []
            for s in spans:
                fam, bold, italic = fontnames.split(s.font)
                generic = "monospace" if s.mono else ("serif" if s.serif else "sans-serif")
                style = [f"font-family=\"'{html.escape(fam, quote=True)}', {generic}\"", f'font-size="{s.size:.2f}"']
                if s.bold or bold:
                    style.append('font-weight="bold"')
                if s.italic or italic:
                    style.append('font-style="italic"')
                if s.color != "#000000":
                    style.append(f'fill="{s.color}"')
                if ln.conf is not None:
                    style.append('fill="none" stroke="none"')
                t = f"<tspan {' '.join(style)}>{html.escape(s.text)}</tspan>"
                if s.link:
                    t = f'<a href="{html.escape(s.link, quote=True)}" xlink:href="{html.escape(s.link, quote=True)}">{t}</a>'
                tspans.append(t)
            d = ' direction="rtl" unicode-bidi="embed"' if ln.rtl else ""
            body.append(f'<text x="{x:.2f}" y="{base:.2f}" xml:space="preserve"{d}{rot}>{"".join(tspans)}</text>')
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="{p.width:.2f}pt" height="{p.height:.2f}pt" '
            f'viewBox="0 0 {p.width:.2f} {p.height:.2f}">\n' + "\n".join(body) + "\n</svg>\n")


def points_units(svg_text: str) -> str:
    """MuPDF writes width="612" height="792" (user units are points); say so, so viewers use the real size."""
    import re as _re

    def fix(m):
        tag = m.group(0)
        tag = _re.sub(r'\bwidth="([0-9.]+)"', r'width="\1pt"', tag, count=1)
        return _re.sub(r'\bheight="([0-9.]+)"', r'height="\1pt"', tag, count=1)
    return _re.sub(r"<svg\b[^>]*>", fix, svg_text, count=1)
