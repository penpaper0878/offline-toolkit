"""Crop and placement as exact affine maps (all coordinates continuous: a pixel's centre is at i + 0.5).

Crop (step 2), in source pixels: the frame is a w x h rectangle centred at (cx, cy). The picture is turned
clockwise by `angle` degrees and mirrored (`flipH`, `flipV`) under the frame. A point d in the cropped
picture (origin at its top-left corner) comes from the source point

    s = C + R(-angle) . F . (d - (w/2, h/2))

R(t) turns clockwise on screen (y down); F mirrors the axes that are flipped.

Placement (step 3), relative to the output frame (W x H px), so it survives a change of DPI or preset:
the cropped picture's centre sits at (x*W, y*H), scaled by `scale*H` output px per cropped px and turned
clockwise by `angle`. A point o of the output comes from the cropped point

    d = (w/2, h/2) + R(-angle) . (o - (x*W, y*H)) / (scale*H)

src/shared/passport.ts implements the same maps for the editor; tests/vectors/passport.json checks both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Crop:
    cx: float
    cy: float
    w: float
    h: float
    angle: float = 0.0
    flipH: bool = False
    flipV: bool = False

    @staticmethod
    def full(width: int, height: int) -> "Crop":
        return Crop(width / 2, height / 2, float(width), float(height))

    @staticmethod
    def parse(d: dict | None, width: int, height: int) -> "Crop":
        if not d:
            return Crop.full(width, height)
        return Crop(float(d["cx"]), float(d["cy"]), float(d["w"]), float(d["h"]), float(d.get("angle", 0.0)),
                    bool(d.get("flipH", False)), bool(d.get("flipV", False)))

    @property
    def size(self) -> tuple[int, int]:
        return max(1, round(self.w)), max(1, round(self.h))

    def to_dict(self) -> dict:
        return {"cx": float(self.cx), "cy": float(self.cy), "w": float(self.w), "h": float(self.h),
                "angle": float(self.angle), "flipH": self.flipH, "flipV": self.flipV}


@dataclass(frozen=True)
class Place:
    x: float = 0.5
    y: float = 0.5
    scale: float = 0.0          # output px per cropped px, divided by the output height
    angle: float = 0.0

    @staticmethod
    def parse(d: dict | None) -> "Place | None":
        if not d:
            return None
        return Place(float(d["x"]), float(d["y"]), float(d["scale"]), float(d.get("angle", 0.0)))

    def to_dict(self) -> dict:
        return {"x": float(self.x), "y": float(self.y), "scale": float(self.scale), "angle": float(self.angle)}


def rot(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, -s], [s, c]])


def affine(lin: np.ndarray, off) -> np.ndarray:
    return np.c_[lin, np.asarray(off, dtype=float)]


def compose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a after b (2x3 each): x -> a(b(x))."""
    return np.c_[a[:, :2] @ b[:, :2], a[:, :2] @ b[:, 2] + a[:, 2]]


def invert(a: np.ndarray) -> np.ndarray:
    li = np.linalg.inv(a[:, :2])
    return np.c_[li, -li @ a[:, 2]]


def apply(a: np.ndarray, pts) -> np.ndarray:
    p = np.atleast_2d(np.asarray(pts, dtype=float))
    return p @ a[:, :2].T + a[:, 2]


def scaling(k: float) -> np.ndarray:
    return np.array([[k, 0.0, 0.0], [0.0, k, 0.0]])


def crop_map(c: Crop) -> np.ndarray:
    """Cropped picture -> source."""
    f = np.diag([-1.0 if c.flipH else 1.0, -1.0 if c.flipV else 1.0])
    lin = rot(-c.angle) @ f
    return affine(lin, np.array([c.cx, c.cy]) - lin @ np.array([c.w / 2, c.h / 2]))


def place_map(p: Place, crop_wh: tuple[float, float], out_wh: tuple[int, int]) -> np.ndarray:
    """Output -> cropped picture."""
    W, H = out_wh
    k = p.scale * H
    lin = rot(-p.angle) / k
    return affine(lin, np.array(crop_wh, dtype=float) / 2 - lin @ np.array([p.x * W, p.y * H]))


def to_cv(a: np.ndarray) -> np.ndarray:
    """A continuous map (destination -> source) as OpenCV's inverse map between pixel indices."""
    shift = np.array([0.5, 0.5])
    return np.c_[a[:, :2], a[:, :2] @ shift + a[:, 2] - shift].astype(np.float64)


def source_per_output(a: np.ndarray) -> float:
    """Source pixels per output pixel (geometric mean of the axes) for an output -> source map."""
    return math.sqrt(abs(np.linalg.det(a[:, :2])))


def corners_inside(c: Crop, width: int, height: int, tol: float = 1e-6) -> bool:
    pts = apply(crop_map(c), [[0, 0], [c.w, 0], [c.w, c.h], [0, c.h]])
    return bool(((pts[:, 0] >= -tol) & (pts[:, 0] <= width + tol) & (pts[:, 1] >= -tol) & (pts[:, 1] <= height + tol)).all())


def fit_inside(c: Crop, width: int, height: int) -> Crop:
    """The largest crop with the same centre direction, ratio and angle whose corners are all inside the
    picture (automatic zoom when straightening, so no blank corners appear)."""
    r = rot(-c.angle)
    hw, hh = c.w / 2, c.h / 2
    # Half-extents of the turned frame along the picture's axes.
    ex = abs(r[0, 0]) * hw + abs(r[0, 1]) * hh
    ey = abs(r[1, 0]) * hw + abs(r[1, 1]) * hh
    k = min(1.0, (width / 2) / ex if ex else 1.0, (height / 2) / ey if ey else 1.0)
    w, h = c.w * k, c.h * k
    ex, ey = ex * k, ey * k
    cx = min(max(c.cx, ex), width - ex)
    cy = min(max(c.cy, ey), height - ey)
    return Crop(float(cx), float(cy), float(w), float(h), c.angle, c.flipH, c.flipV)
