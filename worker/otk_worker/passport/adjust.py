"""Photo adjustments for the person, in a fixed order, from slider values (-100..100 unless noted).

1. exposure (stops x 0.02: 100 = +2 EV, applied in linear light)   2. brightness (midtone gamma)
3. contrast (around mid grey)                                       4. highlights / shadows (tone masks)
5. warmth (blue <-> amber) and tint (green <-> magenta)              6. saturation and vibrance
7. noise reduction (0..100), red-eye (in the irises), skin smoothing (0..100, face skin only)
8. sharpness (0..100, unsharp mask)

Auto enhance and auto white balance return slider values, so you see and can change what they did.
Retouching (skin smoothing) is off unless asked for; many authorities refuse retouched photos.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from . import face as F


WARMTH_RANGE = 0.30          # +-100 warmth = red and blue gains +-30% (in linear light)
TINT_RANGE = 0.25            # +-100 tint = green gain -+25%


@dataclass
class Adjust:
    exposure: float = 0
    brightness: float = 0
    contrast: float = 0
    highlights: float = 0
    shadows: float = 0
    warmth: float = 0
    tint: float = 0
    saturation: float = 0
    vibrance: float = 0
    denoise: float = 0
    sharpness: float = 0
    redEye: bool = False
    skinSmoothing: float = 0

    @staticmethod
    def parse(d: dict | None) -> "Adjust":
        a = Adjust()
        for f in fields(Adjust):
            if d and f.name in d and d[f.name] is not None:
                v = d[f.name]
                setattr(a, f.name, bool(v) if f.type in (bool, "bool") else float(np.clip(float(v), -100, 100)))
        return a

    @property
    def identity(self) -> bool:
        return self == Adjust()


def _to_linear(v: np.ndarray) -> np.ndarray:
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _to_srgb(v: np.ndarray) -> np.ndarray:
    v = np.clip(v, 0, 1)
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * np.power(v, 1 / 2.4) - 0.055)


def _luma(v: np.ndarray) -> np.ndarray:
    return v[..., 0] * 0.2126 + v[..., 1] * 0.7152 + v[..., 2] * 0.0722


def skin_mask(shape: tuple[int, int], points: np.ndarray) -> np.ndarray:
    """Face skin (0..1): inside the face outline, without eyes, brows and lips, softened."""
    import cv2

    h, w = shape
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.round(points[list(F.FACE_OVAL)]).astype(np.int32)], 255)
    for idx in (F.EYE_L_RING, F.EYE_R_RING, F.BROW_L, F.BROW_R, F.LIPS):
        poly = np.round(points[list(idx)]).astype(np.int32)
        cv2.fillPoly(m, [cv2.convexHull(poly)], 0)
        cv2.polylines(m, [cv2.convexHull(poly)], True, 0, max(1, int(w / 150)))
    k = max(3, int(min(h, w) / 60) | 1)
    return cv2.GaussianBlur(m, (k, k), 0).astype(np.float32) / 255.0


def _red_eye(v: np.ndarray, points: np.ndarray) -> np.ndarray:
    import cv2

    h, w = v.shape[:2]
    out = v.copy()
    for c, ring in ((F.IRIS_L, range(469, 473)), (F.IRIS_R, range(474, 478))):
        centre = points[c]
        r = float(np.mean([np.linalg.norm(points[i] - centre) for i in ring])) * 1.1
        m = np.zeros((h, w), np.float32)
        cv2.circle(m, (int(round(centre[0])), int(round(centre[1]))), max(1, int(round(r))), 1.0, -1, cv2.LINE_AA)
        red = out[..., 0]
        gb = np.maximum(out[..., 1], out[..., 2])
        redness = np.clip((red - gb * 1.4) / np.maximum(red, 1e-3), 0, 1) * m
        out[..., 0] = red * (1 - redness) + ((out[..., 1] + out[..., 2]) / 2) * redness
    return out


def apply(img: np.ndarray, a: Adjust, points: np.ndarray | None = None) -> np.ndarray:
    """`img` RGB float32 0..1 (H, W, 3); `points` the face landmarks in its coordinates (or None)."""
    import cv2

    v = img.astype(np.float32)
    if a.identity:
        return v
    if a.exposure:
        v = _to_srgb(_to_linear(v) * 2.0 ** (a.exposure / 50.0)).astype(np.float32)
    if a.brightness:
        v = np.power(np.clip(v, 0, 1), 2.0 ** (-a.brightness / 100.0)).astype(np.float32)
    if a.contrast:
        k = 1 + a.contrast / 100.0 * (0.8 if a.contrast > 0 else 1.0)
        v = 0.5 + (v - 0.5) * k
    if a.highlights or a.shadows:
        y = np.clip(_luma(v), 0, 1)[..., None]
        if a.shadows:
            v = v + (a.shadows / 100.0) * 0.35 * (1 - y) ** 2 * (1 - v if a.shadows > 0 else v)
        if a.highlights:
            v = v + (a.highlights / 100.0) * 0.35 * y ** 2 * (1 - v if a.highlights > 0 else v)
    if a.warmth or a.tint:
        lin = _to_linear(np.clip(v, 0, 1))
        wk, tk = a.warmth / 100.0 * WARMTH_RANGE, a.tint / 100.0 * TINT_RANGE
        gains = np.array([1 + wk + tk / 2, 1 - tk, 1 - wk + tk / 2], np.float32)
        v = _to_srgb(lin * gains).astype(np.float32)
    if a.saturation or a.vibrance:
        y = _luma(v)[..., None]
        chroma = v - y
        k = 1 + a.saturation / 100.0
        if a.vibrance:
            sat = np.clip((v.max(-1) - v.min(-1))[..., None], 0, 1)
            k = k + (a.vibrance / 100.0) * (1 - sat) * 0.8
        v = y + chroma * k
    v = np.clip(v, 0, 1).astype(np.float32)
    if a.denoise > 0:
        u8 = (v * 255 + 0.5).astype(np.uint8)
        hval = 2 + a.denoise / 100.0 * 10
        v = cv2.fastNlMeansDenoisingColored(u8, None, hval, hval, 5, 15).astype(np.float32) / 255.0
    if a.redEye and points is not None:
        v = _red_eye(v, points)
    if a.skinSmoothing > 0 and points is not None:
        m = skin_mask(v.shape[:2], points)[..., None] * (a.skinSmoothing / 100.0) * 0.6
        d = max(3, int(min(v.shape[:2]) / 120))
        smooth = cv2.bilateralFilter(v, d * 2 + 1, 0.06, d * 2)
        v = v * (1 - m) + smooth * m
    if a.sharpness > 0:
        sigma = max(0.6, min(v.shape[:2]) / 600)
        blur = cv2.GaussianBlur(v, (0, 0), sigma)
        v = v + (v - blur) * (a.sharpness / 100.0) * 1.2
    return np.clip(v, 0, 1).astype(np.float32)


def auto_enhance(img: np.ndarray, points: np.ndarray | None, person: np.ndarray | None = None) -> dict:
    """Exposure, contrast, shadows and vibrance that bring the face to a normal brightness and range."""
    region = np.ones(img.shape[:2], np.float32)
    if points is not None:
        region = skin_mask(img.shape[:2], points)
    elif person is not None:
        region = person
    sel = region > 0.5
    if sel.sum() < 50:
        sel = np.ones(img.shape[:2], bool)
    y = _luma(img)[sel]
    lo, mid, hi = np.percentile(y, [2, 50, 98])
    # Face mid-tones around 0.55 (skin of every tone stays in its own range; this only moves the average).
    exposure = float(np.clip(50 * np.log2(max(0.55, 1e-3) / max(mid, 1e-3)) * 0.6, -60, 60))
    contrast = float(np.clip((0.75 - (hi - lo)) * 60, -20, 30))
    yall = _luma(img)
    shadows = float(np.clip((0.06 - np.percentile(yall, 5)) * 300, 0, 35))
    sat = (img.max(-1) - img.min(-1))[sel].mean()
    vibrance = float(np.clip((0.18 - sat) * 150, 0, 25))
    return {"exposure": round(exposure), "contrast": round(contrast), "shadows": round(shadows), "vibrance": round(vibrance)}


NEUTRAL_CHROMA = 0.12     # (max - min) / max of a pixel that can serve as a grey reference
WB_LIMIT = 45             # largest correction from scattered pale pixels (a wrong guess must not ruin skin)


def auto_white_balance(img: np.ndarray, background: np.ndarray | None = None) -> dict:
    """Warmth and tint that make the neutral parts of the photo grey: the background when it is near
    neutral already (a white or grey wall), otherwise the bright, nearly colourless pixels (a white shirt,
    the whites of the eyes, a pale wall). Without any, nothing changes (a red curtain is not grey)."""
    v = np.clip(img, 0, 1)
    mx = v.max(-1)
    chroma = (mx - v.min(-1)) / np.maximum(mx, 1e-3)
    lin = _to_linear(v)
    sel = None
    limit = WB_LIMIT
    if background is not None and (background > 0.5).sum() > 200:
        bgsel = background > 0.5
        if float(chroma[bgsel].mean()) < NEUTRAL_CHROMA * 1.5:
            sel, limit = bgsel, 100       # a near-neutral background is a reliable grey: full range
    if sel is None:
        y = _luma(v)
        cand = (chroma < NEUTRAL_CHROMA) & (y > np.percentile(y, 50)) & (mx < 0.98)
        if cand.sum() < max(50, 0.005 * cand.size):
            return {"warmth": 0, "tint": 0}
        sel = cand
    px = lin[sel]
    r, g, b = (max(float(px[:, i].mean()), 1e-4) for i in range(3))
    # The gains (1 + wk + tk/2, 1 - tk, 1 - wk + tk/2) must be proportional to (1/r, 1/g, 1/b):
    # with gains = l * (1/r, 1/g, 1/b), the three add up to 3, so l = 3 / (1/r + 1/g + 1/b).
    lam = 3 / (1 / r + 1 / g + 1 / b)
    tk = 1 - lam / g
    wk = lam * (1 / r - 1 / b) / 2
    return {"warmth": round(float(np.clip(wk / WARMTH_RANGE * 100, -limit, limit))),
            "tint": round(float(np.clip(tk / TINT_RANGE * 100, -limit, limit)))}
