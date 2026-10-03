"""Icons, logos and simple graphics to vector paths (vtracer), with one fill colour per path.

The element's pixels go to vtracer with everything outside its mask transparent, so only the graphic
is traced. vtracer's SVG is reduced to plain absolute path data (M, L, C, Q, Z) in the layer's own
coordinates, which the editor, SVG, PPTX (custGeom) and DOCX writers all draw the same way.
"""

from __future__ import annotations

import io
import re

import numpy as np
from PIL import Image

_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def parse_path(d: str, dx: float = 0.0, dy: float = 0.0) -> list[tuple]:
    """SVG path data -> absolute segments [("M", x, y), ("L", x, y), ("C", x1, y1, x2, y2, x, y),
    ("Q", x1, y1, x, y), ("Z",)], translated by (dx, dy). Arcs are not produced by vtracer."""
    toks = _TOKEN.findall(d)
    out: list[tuple] = []
    i, cmd = 0, None
    cx = cy = sx = sy = 0.0
    last_ctrl = None

    def num():
        nonlocal i
        v = float(toks[i])
        i += 1
        return v

    while i < len(toks):
        if toks[i].isalpha():
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                out.append(("Z",))
                cx, cy = sx, sy
                last_ctrl = None
                continue
        if cmd is None:
            break
        rel = cmd.islower()
        c = cmd.upper()
        if c == "M":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            out.append(("M", x + dx, y + dy))
            cx, cy, sx, sy = x, y, x, y
            cmd = "l" if rel else "L"       # following pairs are line-tos
            last_ctrl = None
        elif c == "L":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            out.append(("L", x + dx, y + dy))
            cx, cy = x, y
            last_ctrl = None
        elif c == "H":
            x = num()
            x = cx + x if rel else x
            out.append(("L", x + dx, cy + dy))
            cx = x
            last_ctrl = None
        elif c == "V":
            y = num()
            y = cy + y if rel else y
            out.append(("L", cx + dx, y + dy))
            cy = y
            last_ctrl = None
        elif c == "C":
            x1, y1, x2, y2, x, y = (num() for _ in range(6))
            if rel:
                x1, y1, x2, y2, x, y = cx + x1, cy + y1, cx + x2, cy + y2, cx + x, cy + y
            out.append(("C", x1 + dx, y1 + dy, x2 + dx, y2 + dy, x + dx, y + dy))
            last_ctrl = (x2, y2)
            cx, cy = x, y
        elif c == "S":
            x2, y2, x, y = (num() for _ in range(4))
            if rel:
                x2, y2, x, y = cx + x2, cy + y2, cx + x, cy + y
            x1, y1 = (2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]) if last_ctrl else (cx, cy)
            out.append(("C", x1 + dx, y1 + dy, x2 + dx, y2 + dy, x + dx, y + dy))
            last_ctrl = (x2, y2)
            cx, cy = x, y
        elif c == "Q":
            x1, y1, x, y = (num() for _ in range(4))
            if rel:
                x1, y1, x, y = cx + x1, cy + y1, cx + x, cy + y
            out.append(("Q", x1 + dx, y1 + dy, x + dx, y + dy))
            last_ctrl = (x1, y1)
            cx, cy = x, y
        elif c == "T":
            x, y = num(), num()
            if rel:
                x, y = cx + x, cy + y
            x1, y1 = (2 * cx - last_ctrl[0], 2 * cy - last_ctrl[1]) if last_ctrl else (cx, cy)
            out.append(("Q", x1 + dx, y1 + dy, x + dx, y + dy))
            last_ctrl = (x1, y1)
            cx, cy = x, y
        else:
            i += 1
    return out


def to_d(segs: list[tuple], precision: int = 2) -> str:
    def f(v: float) -> str:
        s = f"{v:.{precision}f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s

    parts = []
    for s in segs:
        parts.append(s[0] + (" " + " ".join(f(v) for v in s[1:]) if len(s) > 1 else ""))
    return " ".join(parts)


def trace(arr: np.ndarray, mask: np.ndarray, box: tuple[int, int, int, int], *, detail: str = "normal") -> list[dict]:
    """Paths of one graphic, in coordinates relative to `box`'s top-left: [{"d": ..., "fill": "#rrggbb"}]."""
    import vtracer

    x0, y0, x1, y1 = box
    rgba = np.dstack([arr[y0:y1, x0:x1], (mask * 255).astype(np.uint8)])
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    params = {"fine": dict(filter_speckle=2, color_precision=7, layer_difference=8),
              "normal": dict(filter_speckle=4, color_precision=6, layer_difference=16),
              "simple": dict(filter_speckle=8, color_precision=4, layer_difference=32)}[detail]
    svg = vtracer.convert_raw_image_to_svg(buf.getvalue(), img_format="png", colormode="color", hierarchical="stacked",
                                           mode="spline", corner_threshold=60, length_threshold=4.0, max_iterations=10,
                                           splice_threshold=45, path_precision=3, **params)
    paths = []
    for m in re.finditer(r'<path\s+d="([^"]+)"\s+fill="(#[0-9A-Fa-f]{6})"(?:\s+transform="translate\(([-\d.]+),([-\d.]+)\)")?', svg):
        d, fill, tx, ty = m.group(1), m.group(2).lower(), float(m.group(3) or 0), float(m.group(4) or 0)
        segs = parse_path(d, tx, ty)
        if segs:
            paths.append({"d": to_d(segs), "fill": fill})
    return paths
