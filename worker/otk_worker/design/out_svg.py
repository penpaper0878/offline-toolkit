"""Layered SVG: one group per layer (Inkscape sees them as layers), text kept as real text.

Pictures are embedded, graphics are paths, shapes and tables are native SVG, and the fonts are embedded
as WOFF2 subsets so browsers show the design exactly. (Inkscape ignores embedded fonts; with the fonts
installed it shows the same.)
"""

from __future__ import annotations

import base64
from pathlib import Path
from xml.sax.saxutils import escape

from . import fonts_out, layout


def _a(v) -> str:
    return escape(str(v), {'"': "&quot;"})


def _n(v: float) -> str:
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def font_face_css(scene: dict) -> str:
    rules = []
    for fam, w, it in fonts_out.faces_used(scene):
        path = fonts_out.static_font(fam, w, it)
        if path is None:
            continue
        data = fonts_out.woff2_subset(path, fonts_out.text_used(scene, fam, w, it))
        rules.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:{'italic' if it else 'normal'};"
                     f"src:url(data:font/woff2;base64,{base64.b64encode(data).decode()}) format('woff2');}}")
    return "\n".join(rules)


def _font_attrs(family: str, weight: int, italic: bool, size: float, color: str) -> str:
    return (f'font-family="{_a(family)}" font-weight="{int(weight)}" font-style="{"italic" if italic else "normal"}" '
            f'font-size="{_n(size)}" fill="{_a(color)}"')


def _anchor(align: str, rtl: bool) -> str:
    a = {"left": "start", "justify": "start", "center": "middle", "right": "end"}.get(align, "start")
    if rtl and a != "middle":
        a = "end" if a == "start" else "start"
    return a


def _text(lines, baselines, anchor_x, align, rtl, attrs, underline=False) -> str:
    deco = ' text-decoration="underline"' if underline else ""
    direction = ' direction="rtl"' if rtl else ""
    spans = "".join(f'<tspan x="{_n(anchor_x)}" y="{_n(b)}">{escape(t)}</tspan>' for t, b in zip(lines, baselines))
    return f'<text xml:space="preserve" text-anchor="{_anchor(align, rtl)}"{direction}{deco} {attrs}>{spans}</text>'


def layer_svg(lyr: dict, project: Path) -> str:
    t = lyr["type"]
    x, y, w, h = lyr["box"]
    if t == "image":
        return (f'<image x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}" preserveAspectRatio="none" '
                f'href="{layout.data_uri(project / lyr["asset"])}"/>')
    if t == "shape":
        stroke = (f' stroke="{_a(lyr["stroke"])}" stroke-width="{_n(lyr["strokeWidth"])}"'
                  if lyr.get("stroke") and lyr.get("strokeWidth") else "")
        fill = f' fill="{_a(lyr["fill"])}"' if lyr.get("fill") else ' fill="none"'
        if lyr["shape"] == "line":
            x0, y0, x1, y1 = layout.line_points(lyr)
            return (f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" stroke="{_a(lyr.get("stroke") or "#000000")}" '
                    f'stroke-width="{_n(lyr.get("strokeWidth") or 1)}"/>')
        ox, oy, ow, oh, r = layout.shape_outline(lyr)
        if lyr["shape"] == "ellipse":
            return f'<ellipse cx="{_n(ox + ow / 2)}" cy="{_n(oy + oh / 2)}" rx="{_n(ow / 2)}" ry="{_n(oh / 2)}"{fill}{stroke}/>'
        rr = f' rx="{_n(r)}" ry="{_n(r)}"' if lyr["shape"] == "rounded" and r > 0 else ""
        return f'<rect x="{_n(ox)}" y="{_n(oy)}" width="{_n(ow)}" height="{_n(oh)}"{rr}{fill}{stroke}/>'
    if t == "vector":
        sx, sy = layout.vector_scale(lyr)
        paths = "".join(f'<path d="{_a(p["d"])}" fill="{_a(p["fill"])}"/>' for p in lyr["paths"])
        return f'<g transform="translate({_n(x)} {_n(y)}) scale({sx:.5f} {sy:.5f})">{paths}</g>'
    if t == "text":
        st = lyr["style"]
        g = layout.text_geometry(lyr)
        attrs = _font_attrs(st["family"], st["weight"], st["italic"], st["size"], st["color"])
        return _text(g["lines"], g["baselines"], g["anchor"], g["align"], g["rtl"], attrs, st.get("underline", False))
    if t == "table":
        st, border = lyr["style"], lyr["border"]
        parts = []
        for cell, (x0, y0, x1, y1) in layout.table_cells(lyr):
            if cell.get("fill"):
                parts.append(f'<rect x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" height="{_n(y1 - y0)}" fill="{_a(cell["fill"])}"/>')
        for x0, y0, x1, y1 in layout.cell_edges(lyr):
            parts.append(f'<line x1="{_n(x0)}" y1="{_n(y0)}" x2="{_n(x1)}" y2="{_n(y1)}" stroke="{_a(border["color"])}" '
                         f'stroke-width="{_n(border["width"])}" stroke-linecap="square"/>')
        for cell, box in layout.table_cells(lyr):
            if not cell["text"]:
                continue
            g = layout.cell_text(lyr, cell, box)
            attrs = _font_attrs(st["family"], cell.get("weight", 400), cell.get("italic", False), st["size"],
                                cell.get("color") or st["color"])
            parts.append(_text(g["lines"], g["baselines"], g["anchor"], g["align"], False, attrs))
        return "".join(parts)
    return ""


def write(scene: dict, project: Path, out: Path, *, embed_fonts: bool = True) -> Path:
    W, H = scene["page"]["width"], scene["page"]["height"]
    k, _ = layout.page_scale(scene, max_in=1000)
    css = font_face_css(scene) if embed_fonts else ""
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n'
             f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
             f'width="{_n(W * k)}pt" height="{_n(H * k)}pt" viewBox="0 0 {W} {H}">',
             f'<title>{escape(scene["source"].get("name", "Design"))}</title>']
    if css:
        parts.append(f"<defs><style>{css}</style></defs>")
    parts.append(f'<rect width="{W}" height="{H}" fill="{_a(scene["page"].get("background", "#ffffff"))}"/>')
    for lyr in layout.visible_layers(scene):
        body = layer_svg(lyr, project)
        if not body:
            continue
        x, y, w, h = lyr["box"]
        extra = ""
        if lyr.get("rotation"):
            extra += f' transform="rotate({_n(lyr["rotation"])} {_n(x + w / 2)} {_n(y + h / 2)})"'
        if lyr.get("opacity", 1.0) < 0.999:
            extra += f' opacity="{_n(lyr["opacity"])}"'
        parts.append(f'<g id="{_a(lyr["id"])}" inkscape:groupmode="layer" inkscape:label="{_a(lyr["name"])}"{extra}>'
                     f"{body}</g>")
    parts.append("</svg>\n")
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
