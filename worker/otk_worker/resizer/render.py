"""Apply a FitPlan with Lanczos resampling (alpha premultiplied, so edges don't darken)."""

from __future__ import annotations

from PIL import Image

from .geometry import FitPlan

_PREMULTIPLIED = {"RGBA": "RGBa", "LA": "La"}


def parse_color(value: str) -> tuple[int, int, int, int]:
    """'#RRGGBB' or '#RRGGBBAA' -> RGBA tuple."""
    v = value.strip().lstrip("#")
    if len(v) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in v):
        raise ValueError(f"Colour must look like #RRGGBB or #RRGGBBAA, got {value!r}")
    r, g, b = int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    a = int(v[6:8], 16) if len(v) == 8 else 255
    return r, g, b, a


def _resize(img: Image.Image, size: tuple[int, int], box: tuple[float, float, float, float] | None = None) -> Image.Image:
    pre = _PREMULTIPLIED.get(img.mode)
    work = img.convert(pre) if pre else img
    src_w = (box[2] - box[0]) if box else img.width
    src_h = (box[3] - box[1]) if box else img.height
    gap = 3.0 if src_w >= size[0] * 3 and src_h >= size[1] * 3 else None
    out = work.resize(size, Image.Resampling.LANCZOS, box=box, reducing_gap=gap)
    return out.convert(img.mode) if pre else out


def render(img: Image.Image, plan: FitPlan, pad_color: str = "#FFFFFF") -> Image.Image:
    if plan.mode == "crop":
        return _resize(img, plan.target, plan.crop.box())
    if plan.mode == "stretch":
        return _resize(img, plan.target)
    # pad
    r, g, b, a = parse_color(pad_color)
    inner = _resize(img, plan.inner)
    grey = r == g == b and img.mode in ("L", "LA")
    needs_alpha = inner.mode in ("RGBA", "LA") or a < 255
    mode = ("LA" if grey else "RGBA") if needs_alpha else ("L" if grey else "RGB")
    fill = ((r, a) if mode == "LA" else r) if grey else ((r, g, b, a) if mode == "RGBA" else (r, g, b))
    canvas = Image.new(mode, plan.target, fill)
    piece = inner.convert(mode) if inner.mode != mode else inner
    if piece.mode in ("RGBA", "LA"):
        canvas.alpha_composite(piece, dest=plan.offset) if mode == "RGBA" else canvas.paste(piece, plan.offset, piece)
    else:
        canvas.paste(piece, plan.offset)
    return canvas


def flatten(img: Image.Image, color: str = "#FFFFFF") -> tuple[Image.Image, bool]:
    """Composite transparency onto a solid colour. Returns (image, had_transparency)."""
    if img.mode not in ("RGBA", "LA"):
        return img, False
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return img.convert("RGB" if img.mode == "RGBA" else "L"), False
    r, g, b, _ = parse_color(color)
    if img.mode == "LA" and r == g == b:
        bg = Image.new("L", img.size, r)
        bg.paste(img.getchannel("L"), mask=alpha)
        return bg, True
    bg = Image.new("RGB", img.size, (r, g, b))
    bg.paste(img.convert("RGBA"), mask=alpha)
    return bg, True
