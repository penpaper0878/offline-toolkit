"""Removing things from the picture so the live layers can sit on a clean background.

Each connected part of the mask is filled by the method its surroundings call for:
- flat or gradient surroundings: OpenCV Telea (smooth continuation of the border colours);
- textured surroundings: OpenCV xphoto FSR (frequency-selective reconstruction keeps the texture);
- large regions are filled at reduced resolution and scaled up, so a removed photo leaves a smooth
  continuation of the background instead of streaks.
- plain colour or a smooth gradient around (the commonest case on designed pages): a quadratic surface
  fitted to the surroundings, with grain of the same strength, which continues a gradient exactly;
The method sits behind `fill()`, so a learned inpainter could replace it later.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

TEXTURED_STD = 6.0          # grey-level std of the surrounding ring above which a region counts as textured
SMOOTH_STD = 3.0            # per-channel spread around a fitted smooth surface below which it is a gradient


def paste_mask(full: np.ndarray, mask: np.ndarray, inv: np.ndarray, origin: tuple[float, float]) -> None:
    """OR a mask drawn in a straightened frame (top-left at `origin` of that frame) into `full`.
    `inv` maps frame px -> image px (2x3)."""
    import cv2

    h, w = mask.shape
    ox, oy = origin
    # Frame -> image for the mask's own pixels.
    m = inv.copy()
    m[:, 2] = inv[:, 2] + inv[:, 0] * ox + inv[:, 1] * oy
    if abs(m[0, 1]) < 1e-9 and abs(m[1, 0]) < 1e-9 and abs(m[0, 0] - 1) < 1e-9 and abs(m[1, 1] - 1) < 1e-9:
        x, y = int(round(m[0, 2])), int(round(m[1, 2]))
        H, W = full.shape
        x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
        if x1 > x0 and y1 > y0:
            full[y0:y1, x0:x1] |= mask[y0 - y:y1 - y, x0 - x:x1 - x]
        return
    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64) @ m.T
    H, W = full.shape
    x0, y0 = max(0, int(np.floor(corners[:, 0].min()))), max(0, int(np.floor(corners[:, 1].min())))
    x1, y1 = min(W, int(np.ceil(corners[:, 0].max())) + 1), min(H, int(np.ceil(corners[:, 1].max())) + 1)
    if x1 <= x0 or y1 <= y0:
        return
    shifted = m.copy()
    shifted[:, 2] -= (x0, y0)
    warped = cv2.warpAffine(mask.astype(np.uint8) * 255, shifted, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR)
    full[y0:y1, x0:x1] |= warped > 64


def _ring_std(gray: np.ndarray, region: np.ndarray, known: np.ndarray, width: int) -> float:
    import cv2

    ring = cv2.dilate(region.astype(np.uint8), np.ones((2 * width + 1, 2 * width + 1), np.uint8)) > 0
    ring &= known
    if np.count_nonzero(ring) < 20:
        return 0.0
    # Texture, not gradient: the spread left after fitting a plane to the ring (a gradient is a plane).
    ys, xs = np.nonzero(ring)
    vals = gray[ys, xs].astype(np.float64)
    a = np.column_stack([xs, ys, np.ones_like(xs)]).astype(np.float64)
    coef, *_ = np.linalg.lstsq(a, vals, rcond=None)
    return float(np.std(vals - a @ coef))


def _surface(sub: np.ndarray, reg: np.ndarray, known: np.ndarray, width: int, seed: int,
             limit: float = SMOOTH_STD) -> np.ndarray | None:
    """The region filled with a quadratic surface fitted to the ring around it (plus matching grain), or
    None when the ring is not a smooth surface."""
    import cv2

    ring = cv2.dilate(reg.astype(np.uint8), np.ones((2 * width + 1, 2 * width + 1), np.uint8)) > 0
    ring &= known
    ys, xs = np.nonzero(ring)
    if len(xs) < 60:
        return None
    h, w = reg.shape
    sx, sy = 2.0 / max(1, w), 2.0 / max(1, h)

    def basis(xx, yy):
        u, v = xx * sx - 1, yy * sy - 1
        return np.column_stack([np.ones_like(u), u, v, u * u, u * v, v * v])

    if len(xs) > 20000:
        pick = np.random.default_rng(seed).choice(len(xs), 20000, replace=False)
        xs, ys = xs[pick], ys[pick]
    a = basis(xs.astype(np.float64), ys.astype(np.float64))
    vals = sub[ys, xs].astype(np.float64)
    coef, *_ = np.linalg.lstsq(a, vals, rcond=None)
    resid = vals - a @ coef
    std = resid.std(axis=0)
    if float(std.max()) > limit:
        return None
    ry, rx = np.nonzero(reg)
    est = basis(rx.astype(np.float64), ry.astype(np.float64)) @ coef
    if float(std.mean()) > 0.8:
        est += np.random.default_rng(seed).normal(0.0, 1.0, est.shape) * std
    return np.clip(np.round(est), 0, 255).astype(np.uint8)


def fill(arr: np.ndarray, mask: np.ndarray, *, check: Callable[[], None] = lambda: None) -> tuple[np.ndarray, dict]:
    """`arr` (RGB uint8) with `mask` (bool) filled in. Returns (image, stats).

    Nearby masked pixels (the letters of a word) form one region, and every masked pixel counts as
    unknown while any region is filled, so no ink leaks into a neighbour's fill."""
    import cv2

    out = arr.copy()
    if not mask.any():
        return out, {"regions": 0}
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    H, W = mask.shape
    # Grain of the whole picture (a scan's paper): a surface plus that much grain still counts as smooth.
    from .preprocess import noise_sigma

    limit = max(SMOOTH_STD, 1.6 * noise_sigma(gray))
    m8_all = mask.astype(np.uint8) * 255
    grouped = cv2.dilate(m8_all, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(grouped, connectivity=8)
    used = {"surface": 0, "telea": 0, "fsr": 0, "multiscale": 0}
    telea_mask = np.zeros_like(m8_all)
    for i in range(1, n):
        check()
        x, y, w, h, _ = stats[i]
        region = (labels == i) & mask
        if not region.any():
            continue
        pad = max(10, int(0.3 * max(w, h)))
        X0, Y0, X1, Y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        reg = region[Y0:Y1, X0:X1]
        unknown = mask[Y0:Y1, X0:X1]
        tall = int(np.percentile(np.nonzero(reg)[0], 95) - np.percentile(np.nonzero(reg)[0], 5)) + 1
        textured = _ring_std(gray[Y0:Y1, X0:X1], reg, ~unknown, max(3, tall // 3)) > TEXTURED_STD
        big = min(w, h) > 60 and reg.mean() > 0.35
        sub = out[Y0:Y1, X0:X1]
        um8 = unknown.astype(np.uint8) * 255
        smooth = _surface(sub, reg, ~unknown, max(4, min(16, tall // 2 + 2)), seed=i, limit=limit)
        if smooth is not None:
            sub[reg] = smooth
            used["surface"] += 1
        elif big:
            # Fill at low resolution (smooth, fast), then put back only the masked pixels.
            k = max(2, int(min(w, h) / 24))
            small = cv2.resize(sub, (max(1, sub.shape[1] // k), max(1, sub.shape[0] // k)), interpolation=cv2.INTER_AREA)
            sm = cv2.resize(um8, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST)
            sm = cv2.dilate(sm, np.ones((3, 3), np.uint8))
            small = cv2.inpaint(small, sm, 3, cv2.INPAINT_TELEA)
            filled = cv2.resize(small, (sub.shape[1], sub.shape[0]), interpolation=cv2.INTER_CUBIC)
            edge = cv2.dilate(um8, np.ones((5, 5), np.uint8)) & ~cv2.erode(um8, np.ones((5, 5), np.uint8))
            fine = cv2.inpaint(np.ascontiguousarray(sub), um8, 3, cv2.INPAINT_TELEA)
            filled = np.where((edge > 0)[..., None], fine, filled)
            sub[reg] = filled[reg]
            used["multiscale"] += 1
        elif textured and hasattr(cv2, "xphoto"):
            valid = (~unknown).astype(np.uint8) * 255   # xphoto: non-zero = known pixels
            dst = np.zeros_like(sub)
            cv2.xphoto.inpaint(np.ascontiguousarray(sub), valid, dst, cv2.xphoto.INPAINT_FSR_FAST)
            sub[reg] = dst[reg]
            used["fsr"] += 1
        else:
            telea_mask[Y0:Y1, X0:X1][reg] = 255
            used["telea"] += 1
    if telea_mask.any():
        # One pass for all smooth-background regions (regions filled above are known pixels by now).
        pending = telea_mask > 0
        filled = cv2.inpaint(out, telea_mask, 3, cv2.INPAINT_TELEA)
        out[pending] = filled[pending]
    return out, {"regions": n - 1, **used}
