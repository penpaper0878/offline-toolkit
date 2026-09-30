"""Fit modes: crop-to-fill, fit with padding, stretch.

All coordinates are in source pixels *after* EXIF orientation, as floats so a
crop window can sit between pixels. The crop window always has exactly the
target aspect ratio; the UI locks it, and normalise_crop() enforces it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..errors import InputError

FIT_MODES = ("crop", "pad", "stretch")
UPSCALE_WARN = 2.0


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def box(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass(frozen=True)
class FitPlan:
    mode: str
    target: tuple[int, int]
    crop: Rect | None            # crop mode: source region
    inner: tuple[int, int]       # pad mode: size of the scaled image inside the canvas
    offset: tuple[int, int]      # pad mode: where it sits
    scale: tuple[float, float]   # output px per source px (x, y)
    distortion: float            # stretch mode: relative aspect change (0 = none)

    @property
    def upscale(self) -> float:
        return max(self.scale)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["upscale"] = self.upscale
        return d


def default_crop(src: tuple[int, int], target: tuple[int, int]) -> Rect:
    """Largest centred window with the target aspect ratio."""
    sw, sh = src
    aspect = target[0] / target[1]
    if sw / sh > aspect:
        w, h = sh * aspect, float(sh)
    else:
        w, h = float(sw), sw / aspect
    return Rect((sw - w) / 2, (sh - h) / 2, w, h)


def normalise_crop(rect: dict | Rect | None, src: tuple[int, int], target: tuple[int, int]) -> Rect:
    """Clamp a crop window to the image and force the exact target aspect.

    The window keeps its centre and width; the height follows from the aspect,
    and if that no longer fits, the window shrinks (never distorts).
    """
    if rect is None:
        return default_crop(src, target)
    if isinstance(rect, dict):
        try:
            rect = Rect(float(rect["x"]), float(rect["y"]), float(rect["w"]), float(rect["h"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError("The crop window is invalid.") from exc
    sw, sh = src
    aspect = target[0] / target[1]
    if rect.w <= 0 or rect.h <= 0:
        raise InputError("The crop window has no area.")
    cx, cy = rect.x + rect.w / 2, rect.y + rect.h / 2
    w = min(rect.w, float(sw))
    h = w / aspect
    if h > sh:
        h = float(sh)
        w = h * aspect
    x = min(max(cx - w / 2, 0.0), sw - w)
    y = min(max(cy - h / 2, 0.0), sh - h)
    return Rect(x, y, w, h)


def plan_fit(src: tuple[int, int], target: tuple[int, int], mode: str, crop: dict | Rect | None = None) -> FitPlan:
    if mode not in FIT_MODES:
        raise InputError(f"Unknown fit mode {mode!r}.")
    tw, th = target
    sw, sh = src
    if tw < 1 or th < 1:
        raise InputError("Target size must be at least 1×1 px.")
    if mode == "crop":
        r = normalise_crop(crop, src, target)
        return FitPlan(mode, target, r, target, (0, 0), (tw / r.w, th / r.h), 0.0)
    if mode == "pad":
        s = min(tw / sw, th / sh)
        iw, ih = max(1, min(tw, round(sw * s))), max(1, min(th, round(sh * s)))
        return FitPlan(mode, target, None, (iw, ih), ((tw - iw) // 2, (th - ih) // 2), (iw / sw, ih / sh), 0.0)
    sx, sy = tw / sw, th / sh
    return FitPlan(mode, target, None, target, (0, 0), (sx, sy), sx / sy - 1.0)


def plan_warnings(plan: FitPlan) -> list[str]:
    out: list[str] = []
    if plan.upscale > UPSCALE_WARN:
        out.append(f"The image is enlarged {plan.upscale:.1f}×; it will look soft. A larger source would be better.")
    if plan.mode == "stretch" and abs(plan.distortion) > 0.005:
        out.append(f"Stretch changes the proportions by {plan.distortion * 100:+.1f}%.")
    return out
