"""Editable HTML: one self-contained page, every layer an absolutely placed element.

Text and table cells can be edited in the browser (contenteditable), fonts are embedded (WOFF2 subsets
covering the text plus basic Latin, so typing new words keeps the font), pictures are embedded, shapes
and graphics are inline SVG. The page scales to the window; printing gives the design at its size.

CSS places a line's baseline half the leading plus the font's ascent below the line box top; the text
block's top is set so that the first baseline lands where the scene has it.
"""

from __future__ import annotations

import base64
from pathlib import Path
from xml.sax.saxutils import escape

from . import fonts_out, layout, out_svg

_BASIC = "".join(chr(c) for c in range(32, 127)) + "‘’“”–—…•€£₹©®™°±×÷"


def _n(v: float) -> str:
    return out_svg._n(v)


def _font_css(scene: dict) -> str:
    rules = []
    for fam, w, it in fonts_out.faces_used(scene):
        path = fonts_out.static_font(fam, w, it)
        if path is None:
            continue
        data = fonts_out.woff2_subset(path, fonts_out.text_used(scene, fam, w, it) + _BASIC)
        rules.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:{'italic' if it else 'normal'};"
                     f"font-display:block;src:url(data:font/woff2;base64,{base64.b64encode(data).decode()}) format('woff2')}}")
    return "\n".join(rules)


def _box_style(lyr: dict, x: float, y: float, w: float, h: float) -> str:
    st = f"left:{_n(x)}px;top:{_n(y)}px;width:{_n(w)}px;height:{_n(h)}px;"
    if lyr.get("rotation"):
        st += f"transform:rotate({_n(lyr['rotation'])}deg);"
    if lyr.get("opacity", 1.0) < 0.999:
        st += f"opacity:{_n(lyr['opacity'])};"
    return st


def _font_style(family: str, weight: int, italic: bool, size: float, color: str) -> str:
    return (f"font-family:'{family}';font-weight:{int(weight)};font-style:{'italic' if italic else 'normal'};"
            f"font-size:{_n(size)}px;color:{color};")


def _text_div(lyr: dict) -> str:
    st = lyr["style"]
    x, y, w, h = lyr["box"]
    g = layout.text_geometry(lyr)
    size, pitch = g["size"], g["pitch"]
    # First baseline = top + (pitch - (ascent + descent) * size) / 2 + ascent * size.
    top = g["baselines"][0] - (pitch - (g["ascent"] + g["descent"]) * size) / 2 - g["ascent"] * size
    align = {"justify": "left"}.get(g["align"], g["align"])
    css = (_box_style(lyr, x, top, w, max(h, pitch * len(g["lines"]))) + _font_style(st["family"], st["weight"],
           st["italic"], size, st["color"]) + f"line-height:{_n(pitch)}px;text-align:{align};")
    if st.get("underline"):
        css += "text-decoration:underline;"
    direction = ' dir="rtl"' if g["rtl"] else ""
    body = "<br>".join(escape(t) for t in g["lines"])
    return f'<div class="t" id="{escape(lyr["id"])}" contenteditable="true"{direction} style="{css}">{body}</div>'


def _table(lyr: dict) -> str:
    st, border = lyr["style"], lyr["border"]
    x, y, w, h = lyr["box"]
    xs, ys = layout.table_grid(lyr)
    pad = lyr.get("padding") or [6, 2, 6, 2]
    cols = "".join(f'<col style="width:{_n(b - a)}px">' for a, b in zip(xs, xs[1:]))
    rows: dict[int, list[str]] = {}
    covered = set()
    for c in lyr["cells"]:
        for r in range(c["row"], c["row"] + c.get("rowSpan", 1)):
            for k in range(c["col"], c["col"] + c.get("colSpan", 1)):
                if (r, k) != (c["row"], c["col"]):
                    covered.add((r, k))
    for c in sorted(lyr["cells"], key=lambda c: (c["row"], c["col"])):
        if (c["row"], c["col"]) in covered:
            continue
        m = layout.metrics(st["family"], int(c.get("weight", 400)), bool(c.get("italic", False)))
        lh = (m["ascent"] + m["descent"] + m["lineGap"]) * st["size"]
        span = (f' rowspan="{c["rowSpan"]}"' if c.get("rowSpan", 1) > 1 else "") + (
            f' colspan="{c["colSpan"]}"' if c.get("colSpan", 1) > 1 else "")
        css = (_font_style(st["family"], c.get("weight", 400), c.get("italic", False), st["size"], c.get("color") or st["color"])
               + f"line-height:{_n(lh)}px;text-align:{c.get('align', 'left')};vertical-align:{c.get('valign', 'middle')};"
               + f"padding:{_n(pad[1])}px {_n(pad[2])}px {_n(pad[3])}px {_n(pad[0])}px;")
        if c.get("fill"):
            css += f"background:{c['fill']};"
        text = "<br>".join(escape(t) for t in c["text"].split("\n")) if c["text"] else ""
        rows.setdefault(c["row"], []).append(f'<td{span} contenteditable="true" style="{css}">{text}</td>')
    trs = "".join(f'<tr style="height:{_n(b - a)}px">{"".join(rows.get(i, []))}</tr>' for i, (a, b) in enumerate(zip(ys, ys[1:])))
    bw = border["width"]
    return (f'<table class="tb" id="{escape(lyr["id"])}" style="{_box_style(lyr, x, y, w, h)}'
            f'--bw:{_n(bw)}px;--bc:{border["color"]}"><colgroup>{cols}</colgroup>{trs}</table>')


def _svg_box(lyr: dict, inner: str) -> str:
    x, y, w, h = lyr["box"]
    return (f'<svg class="g" id="{escape(lyr["id"])}" style="{_box_style(lyr, x, y, w, h)}" viewBox="{_n(x)} {_n(y)} {_n(w)} {_n(h)}" '
            f'overflow="visible">{inner}</svg>')


def write(scene: dict, project: Path, out: Path) -> Path:
    W, H = scene["page"]["width"], scene["page"]["height"]
    body = []
    for lyr in layout.visible_layers(scene):
        t = lyr["type"]
        x, y, w, h = lyr["box"]
        if t == "image":
            body.append(f'<img class="i" id="{escape(lyr["id"])}" alt="{escape(lyr["name"])}" style="{_box_style(lyr, x, y, w, h)}" '
                        f'src="{layout.data_uri(project / lyr["asset"])}">')
        elif t in ("shape", "vector"):
            body.append(_svg_box(lyr, out_svg.layer_svg(lyr, project)))
        elif t == "text":
            body.append(_text_div(lyr))
        elif t == "table":
            body.append(_table(lyr))
    title = escape(scene["source"].get("name", "Design"))
    k, _ = layout.page_scale(scene, max_in=1000)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{_font_css(scene)}
html,body{{margin:0;background:#888;}}
#wrap{{width:{W}px;height:{H}px;transform-origin:0 0;}}
#page{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:{scene["page"].get("background", "#ffffff")};}}
#page>*{{position:absolute;box-sizing:border-box;margin:0;transform-origin:50% 50%;}}
.t{{white-space:pre;outline:none;padding:0;}}
.t:focus,td:focus{{outline:1px dashed #2f6feb;}}
.tb{{border-collapse:collapse;table-layout:fixed;}}
.tb td{{border:var(--bw) solid var(--bc);box-sizing:border-box;white-space:pre;overflow:hidden;outline:none;}}
.i{{object-fit:fill;}}
@page{{size:{_n(W * k)}pt {_n(H * k)}pt;margin:0}}
@media print{{html,body{{background:none}}#wrap{{transform:none!important;width:auto;height:auto}}#page{{zoom:{_n(k / 0.75)}}}}}
</style></head>
<body><div id="wrap"><div id="page">
{chr(10).join(body)}
</div></div>
<script>
(function () {{
  var wrap = document.getElementById('wrap');
  function fit() {{
    var s = Math.min(1, (window.innerWidth - 16) / {W});
    wrap.style.transform = 'scale(' + s + ')';
    wrap.style.margin = s < 1 ? '8px' : '8px auto';
    document.body.style.height = ({H} * s + 16) + 'px';
  }}
  window.addEventListener('resize', fit); fit();
}})();
</script>
</body></html>
"""
    out.write_text(html, encoding="utf-8")
    return out
