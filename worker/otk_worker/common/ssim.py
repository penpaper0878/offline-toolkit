"""Structural similarity (SSIM) for ranking compression candidates.

Box-window SSIM (7x7, the scikit-image default) computed with integral
images, on YCbCr so chroma subsampling losses count. Images are compared on a
proxy of at most 1024 px, which is enough to rank encoder settings.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2
_WIN = 7
_WEIGHTS = (0.8, 0.1, 0.1)


def _box_mean(a: np.ndarray, k: int) -> np.ndarray:
    ii = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s / (k * k)


def _ssim_channel(x: np.ndarray, y: np.ndarray) -> float:
    k = min(_WIN, x.shape[0], x.shape[1])
    if k < 2:
        return 1.0 if np.array_equal(x, y) else 0.0
    mx, my = _box_mean(x, k), _box_mean(y, k)
    sxx = _box_mean(x * x, k) - mx * mx
    syy = _box_mean(y * y, k) - my * my
    sxy = _box_mean(x * y, k) - mx * my
    n = k * k
    cov = n / (n - 1)  # sample covariance, as scikit-image does
    sxx, syy, sxy = sxx * cov, syy * cov, sxy * cov
    num = (2 * mx * my + _C1) * (2 * sxy + _C2)
    den = (mx * mx + my * my + _C1) * (sxx + syy + _C2)
    return float(np.mean(num / den))


def _proxy(img: Image.Image, max_side: int) -> Image.Image:
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.getchannel("A"))
        img = bg
    img = img.convert("RGB")
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.Resampling.BOX)
    return img


def ssim(reference: Image.Image, candidate: Image.Image, max_side: int = 1024) -> float:
    if reference.size != candidate.size:
        raise ValueError("SSIM needs images of the same size")
    a = np.asarray(_proxy(reference, max_side).convert("YCbCr"), dtype=np.float64)
    b = np.asarray(_proxy(candidate, max_side).convert("YCbCr"), dtype=np.float64)
    return sum(w * _ssim_channel(a[..., c], b[..., c]) for c, w in enumerate(_WEIGHTS))
