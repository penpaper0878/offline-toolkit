"""Cut-outs: the subject of a photo on a transparent background.

People: MediaPipe's selfie segmenter (Apache-2.0, bundled) gives a soft person mask at 256 x 256. It is
scaled to the photo and its edge refined with GrabCut on the photo's own colours, then feathered with
a guided filter so hair and soft edges keep partial transparency.
Anything else: GrabCut alone, seeded with the photo's border as background and its middle as probably
foreground. That suits a product or logo on a plain backdrop; busy scenes need hand touch-up, which
the editor offers by restoring or erasing with a brush.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import assets

MODEL = "selfie_segmenter.tflite"
SIZE = 256
WORK = 900          # GrabCut runs on a copy at most this many px on the long side


@dataclass
class Cutout:
    alpha: np.ndarray       # uint8, photo-sized
    method: str             # "person" | "subject"
    coverage: float         # share of the photo kept


_net = None


def _segmenter():
    global _net
    if _net is None:
        import cv2

        path = assets.model_path(MODEL)
        if path is None:
            return None
        _net = cv2.dnn.readNetFromTFLite(str(path))
    return _net


def person_probability(rgb: np.ndarray) -> np.ndarray | None:
    """Per-pixel probability (0..1) that a pixel shows a person, or None without the model."""
    import cv2

    net = _segmenter()
    if net is None:
        return None
    h, w = rgb.shape[:2]
    side = max(h, w)
    top, left = (side - h) // 2, (side - w) // 2
    square = cv2.copyMakeBorder(rgb, top, side - h - top, left, side - w - left, cv2.BORDER_REPLICATE)
    small = cv2.resize(square, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    net.setInput(cv2.dnn.blobFromImage(small, 1.0, (SIZE, SIZE), swapRB=False))
    prob = net.forward()[0, 0]
    prob = cv2.resize(prob, (side, side), interpolation=cv2.INTER_LINEAR)
    return np.clip(prob[top:top + h, left:left + w], 0.0, 1.0)


def _grabcut(rgb: np.ndarray, seed: np.ndarray, iterations: int = 4) -> np.ndarray:
    """GrabCut from a seed (cv2.GC_* labels), run on a reduced copy; returns a bool mask at full size."""
    import cv2

    h, w = rgb.shape[:2]
    k = min(1.0, WORK / max(h, w))
    small = cv2.resize(rgb, (max(1, int(w * k)), max(1, int(h * k))), interpolation=cv2.INTER_AREA) if k < 1 else rgb
    s = cv2.resize(seed, (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST) if k < 1 else seed.copy()
    if not ((s == cv2.GC_FGD) | (s == cv2.GC_PR_FGD)).any() or not ((s == cv2.GC_BGD) | (s == cv2.GC_PR_BGD)).any():
        return (seed == cv2.GC_FGD) | (seed == cv2.GC_PR_FGD)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(np.ascontiguousarray(small[:, :, ::-1]), s, None, bgd, fgd, iterations, cv2.GC_INIT_WITH_MASK)
    fg = ((s == cv2.GC_FGD) | (s == cv2.GC_PR_FGD)).astype(np.uint8)
    if k < 1:
        fg = cv2.resize(fg * 255, (w, h), interpolation=cv2.INTER_LINEAR) > 127
    return fg.astype(bool)


def _feather(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Soft edges that follow the photo: a guided filter of the hard mask, guided by the photo."""
    import cv2

    src = mask.astype(np.float32)
    try:
        r = max(2, int(round(max(rgb.shape[:2]) / 300)))
        soft = cv2.ximgproc.guidedFilter(rgb.astype(np.float32) / 255.0, src, r, 1e-4)
    except (AttributeError, cv2.error):
        soft = cv2.GaussianBlur(src, (0, 0), 1.0)
    return (np.clip(soft, 0.0, 1.0) * 255).astype(np.uint8)


def _largest_parts(mask: np.ndarray, keep_share: float = 0.05) -> np.ndarray:
    """Drop small islands (specks GrabCut keeps in the background)."""
    import cv2

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 2:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool)
    keep[1:] = areas >= keep_share * areas.max()
    return keep[labels]


def cutout(rgb: np.ndarray, mode: str = "auto") -> Cutout:
    """Cut the subject out of `rgb` (H x W x 3 uint8). `mode`: "auto", "person" or "subject"."""
    import cv2

    h, w = rgb.shape[:2]
    prob = person_probability(rgb) if mode in ("auto", "person") else None
    person = prob is not None and float((prob > 0.5).mean()) >= 0.02
    if person:
        seed = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
        seed[prob > 0.5] = cv2.GC_PR_FGD
        seed[prob > 0.9] = cv2.GC_FGD
        seed[prob < 0.05] = cv2.GC_BGD
        method = "person"
    else:
        if mode == "person":
            raise ValueError("No person was found in this photo. Try the general subject cut-out.")
        seed = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
        b = max(2, int(0.02 * min(h, w)))
        seed[:b], seed[-b:], seed[:, :b], seed[:, -b:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
        seed[int(h * 0.2):int(h * 0.8), int(w * 0.2):int(w * 0.8)] = cv2.GC_PR_FGD
        method = "subject"
    fg = _largest_parts(_grabcut(rgb, seed))
    if person:
        # GrabCut follows colour edges; keep what the model is sure of even where colours are alike.
        fg |= prob > 0.9
    alpha = _feather(rgb, fg)
    return Cutout(alpha=alpha, method=method, coverage=float((alpha > 127).mean()))
