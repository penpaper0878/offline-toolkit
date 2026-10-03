"""Open photos and per-crop analysis, cached in the worker (the UI sends parameters, never pixels).

A session is one opened photo: its EXIF-oriented sRGB pixels and a pyramid of halvings, so any output is
sampled from a level at most twice its own resolution (no aliasing when a 50 MP photo becomes a 413 px
passport photo). Analysis is per crop: the cropped picture at up to 1600 px on the long side, its faces,
the person matte and the top of the hair. Up to three sessions and eight analyses are kept.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..common import imageio
from ..errors import InputError
from . import face as F
from . import geometry as G

ANALYSE_SIDE = 1600
MAX_SESSIONS = 3
MAX_ANALYSES = 8


@dataclass
class Session:
    id: str
    path: str
    rgb: np.ndarray
    warnings: list[str]
    meta: dict
    _pyramid: list[np.ndarray] = field(default_factory=list)
    analyses: "OrderedDict[tuple, Analysis]" = field(default_factory=OrderedDict)

    @property
    def size(self) -> tuple[int, int]:
        return self.rgb.shape[1], self.rgb.shape[0]

    def level(self, n: int) -> np.ndarray:
        import cv2

        if not self._pyramid:
            self._pyramid.append(self.rgb)
        while len(self._pyramid) <= n:
            prev = self._pyramid[-1]
            if min(prev.shape[:2]) < 32:
                break
            self._pyramid.append(cv2.pyrDown(prev))
        return self._pyramid[min(n, len(self._pyramid) - 1)]


@dataclass
class Analysis:
    crop: G.Crop
    k: float                          # analysis px per cropped px
    image: np.ndarray                 # the cropped picture at analysis size (RGB uint8)
    faces: F.Faces
    alpha: np.ndarray | None          # person matte at analysis size (uint8), None without a person
    hair: np.ndarray | None           # top of the hair (analysis px)
    hair_cut: bool                    # the hair reaches the picture's edge

    def to_cropped(self, pts) -> np.ndarray:
        return np.atleast_2d(np.asarray(pts, dtype=float)) / self.k


_lock = threading.RLock()
_sessions: "OrderedDict[str, Session]" = OrderedDict()


def warp(sess: Session, out_to_src: np.ndarray, size: tuple[int, int], *, quality: bool = True,
         border_value=(0, 0, 0)) -> np.ndarray:
    """Sample the source through `out_to_src` (continuous output -> source map) into `size` (w, h)."""
    import cv2

    ratio = G.source_per_output(out_to_src)
    n = 0
    while ratio / (2 ** n) > 2.0:
        n += 1
    src = sess.level(n)
    k = src.shape[1] / sess.rgb.shape[1]
    a = G.compose(G.scaling(k), out_to_src)
    return cv2.warpAffine(src, G.to_cv(a), size, flags=(cv2.INTER_LANCZOS4 if quality else cv2.INTER_LINEAR) | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=border_value)


def coverage(sess: Session, out_to_src: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """1 where an output pixel's centre falls inside the photo, 0 outside (float32)."""
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w]
    pts = np.stack([xs.ravel() + 0.5, ys.ravel() + 0.5], 1)
    s = G.apply(out_to_src, pts)
    W, H = sess.size
    inside = (s[:, 0] >= 0) & (s[:, 0] <= W) & (s[:, 1] >= 0) & (s[:, 1] <= H)
    return inside.reshape(h, w).astype(np.float32)


def open_photo(path: str) -> Session:
    p = Path(path)
    if not p.is_file():
        raise InputError("That photo was not found.")
    st = p.stat()
    sid = hashlib.sha256(f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    with _lock:
        if sid in _sessions:
            _sessions.move_to_end(sid)
            return _sessions[sid]
    loaded = imageio.open_image(str(p))
    img = loaded.image
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    if "A" in img.getbands():
        from PIL import Image

        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        img = bg
    rgb = np.asarray(img.convert("RGB"))
    sess = Session(sid, str(p), np.ascontiguousarray(rgb), list(loaded.warnings),
                   {"format": loaded.source_format, "width": rgb.shape[1], "height": rgb.shape[0],
                    "dpi": list(loaded.dpi) if loaded.dpi else None, "orientation": loaded.orientation,
                    "fileSize": loaded.file_size})
    with _lock:
        _sessions[sid] = sess
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return sess


def get(sid: str) -> Session:
    with _lock:
        s = _sessions.get(sid)
    if s is None:
        raise InputError("This photo is no longer open; open it again.")
    return s


def _crop_key(c: G.Crop) -> tuple:
    return (round(c.cx, 2), round(c.cy, 2), round(c.w, 2), round(c.h, 2), round(c.angle, 3), c.flipH, c.flipV)


def analyse(sess: Session, crop: G.Crop, check=lambda: None) -> Analysis:
    from . import matte

    key = _crop_key(crop)
    with _lock:
        if key in sess.analyses:
            sess.analyses.move_to_end(key)
            return sess.analyses[key]
    cw, ch = crop.size
    k = min(1.0, ANALYSE_SIDE / max(cw, ch))
    size = (max(1, round(cw * k)), max(1, round(ch * k)))
    # analysis px -> cropped px -> source px
    out_to_src = G.compose(G.crop_map(crop), G.scaling(1 / k))
    image = warp(sess, out_to_src, size, quality=False, border_value=(255, 255, 255))
    check()
    faces = F.detect(image)
    check()
    alpha = matte.person_matte(image, faces.main.box if faces.main else None)   # None: no person
    hair, cut = (None, False)
    if faces.main is not None and alpha is not None:
        hair, cut = F.hair_top(alpha, faces.main)
    an = Analysis(crop, k, image, faces, alpha, hair, cut)
    with _lock:
        sess.analyses[key] = an
        while len(sess.analyses) > MAX_ANALYSES:
            sess.analyses.popitem(last=False)
    return an
