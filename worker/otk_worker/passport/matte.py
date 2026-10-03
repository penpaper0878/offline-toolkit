"""The person matte for passport photos, and colour clean-up at its edge.

MediaPipe's selfie segmenter gives a soft person mask at 256 px. GrabCut on the photo's own colours sharpens
its edge, but only inside a narrow band around the mask's outline: beyond the band the background is fixed,
so GrabCut cannot grow into a background area of similar colour (a window, a wall the colour of hair).
A guided filter then gives soft, hair-following edges (design.cutout._feather).

Edge colours: a soft edge pixel mixes the person with the old background (a red curtain leaves a red rim
on a white background). `decontaminate` gives edge pixels the colour of the nearby person instead.
"""

from __future__ import annotations

import numpy as np

from ..design import cutout

BAND = 0.025            # GrabCut decides only this far (share of the long side) around the mask outline


HEAD_CROP = 2.8         # side of the head close-up, in face heights


def _probability(rgb: np.ndarray, face_box: tuple[float, float, float, float] | None) -> np.ndarray | None:
    """Person probability; around the head from a close-up, where the 256 px model sees the head large."""
    import cv2

    prob = cutout.person_probability(rgb)
    if prob is None or face_box is None:
        return prob
    h, w = rgb.shape[:2]
    x, y, bw, bh = face_box
    side = HEAD_CROP * max(bw, bh)
    cx, cy = x + bw / 2, y + bh * 0.35            # a little above the face centre: room for the hair
    x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x1, y1 = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
    if x1 - x0 < 32 or y1 - y0 < 32 or (x1 - x0) * (y1 - y0) > 0.6 * w * h:
        return prob                                # the head is large already
    close = cutout.person_probability(np.ascontiguousarray(rgb[y0:y1, x0:x1]))
    if close is None:
        return prob
    # Blend the close-up in, fading out over the outer 10% of the crop so no seam shows.
    ramp = np.ones((y1 - y0, x1 - x0), np.float32)
    f = max(2, int(0.1 * min(x1 - x0, y1 - y0)))
    for i in range(f):
        v = (i + 1) / (f + 1)
        if y0 > 0:
            ramp[i, :] = np.minimum(ramp[i, :], v)
        if y1 < h:
            ramp[-1 - i, :] = np.minimum(ramp[-1 - i, :], v)
        if x0 > 0:
            ramp[:, i] = np.minimum(ramp[:, i], v)
        if x1 < w:
            ramp[:, -1 - i] = np.minimum(ramp[:, -1 - i], v)
    out = prob.copy()
    out[y0:y1, x0:x1] = prob[y0:y1, x0:x1] * (1 - ramp) + close * ramp
    return out


def _feather(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Soft edges that follow the photo, tighter than the general cut-out (a passport edge is crisp)."""
    import cv2

    src = mask.astype(np.float32)
    try:
        r = max(1, int(round(max(rgb.shape[:2]) / 700)))
        soft = cv2.ximgproc.guidedFilter(rgb.astype(np.float32) / 255.0, src, r, 4e-5)
    except (AttributeError, cv2.error):
        soft = cv2.GaussianBlur(src, (0, 0), 0.7)
    return (np.clip(soft, 0.0, 1.0) * 255).astype(np.uint8)


def person_matte(rgb: np.ndarray, face_box: tuple[float, float, float, float] | None = None) -> np.ndarray | None:
    """Person matte (uint8 0..255) for an RGB photo, or None when no person is found. With the main face's
    box (x, y, w, h), the head is segmented again from a close-up."""
    import cv2

    prob = _probability(rgb, face_box)
    if prob is None or float((prob > 0.5).mean()) < 0.02:
        return None
    h, w = rgb.shape[:2]
    core = (prob > 0.5).astype(np.uint8)
    b = max(3, int(round(BAND * max(h, w))))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * b + 1, 2 * b + 1))
    near = cv2.dilate(core, k).astype(bool)
    inner = cv2.erode(core, k).astype(bool)
    seed = np.full((h, w), cv2.GC_BGD, np.uint8)
    seed[near] = cv2.GC_PR_BGD
    seed[core.astype(bool)] = cv2.GC_PR_FGD
    seed[inner | (prob > 0.95)] = cv2.GC_FGD
    fg = cutout._grabcut(rgb, seed)
    # Keep the parts that touch the model's confident core (drops islands GrabCut adds in the band).
    n, labels = cv2.connectedComponents(fg.astype(np.uint8), connectivity=8)
    if n > 2:
        sure = prob > 0.9
        keep = np.zeros(n, bool)
        keep[np.unique(labels[sure & fg])] = True
        keep[0] = False
        fg = keep[labels]
    fg |= prob > 0.9
    return _feather(rgb, fg)


def decontaminate(img: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Edge pixels (0 < alpha < 0.95) take the colour of the nearby solid person pixels.
    `img` float RGB 0..1, `alpha` float 0..1, same size."""
    import cv2

    solid = (alpha >= 0.95).astype(np.float32)
    if solid.sum() < 10:
        return img
    edge = (alpha > 0.001) & (alpha < 0.95)
    if not edge.any():
        return img
    out = img.copy()
    sigma = max(1.5, max(img.shape[:2]) / 250)
    est = np.zeros_like(img)
    filled = np.zeros(img.shape[:2], bool)
    # Normalised convolution, wider passes for pixels far from solid ones.
    for s in (sigma, sigma * 3, sigma * 9):
        wsum = cv2.GaussianBlur(solid, (0, 0), s)
        num = cv2.GaussianBlur(img * solid[..., None], (0, 0), s)
        ok = (wsum > 1e-3) & ~filled
        est[ok] = num[ok] / wsum[ok][:, None]
        filled |= ok
    sel = edge & filled
    out[sel] = est[sel]
    return out
