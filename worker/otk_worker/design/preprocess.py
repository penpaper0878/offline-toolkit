"""Stage 1: open the picture, straighten it when the evidence is clear, and remove sensor noise.

- Orientation from EXIF; colour to sRGB; transparency flattened onto white (noted).
- Skew: the projection-profile angle (±5°) is applied only when it sharpens the text rows clearly
  (a poster with diagonal art keeps its angle).
- Noise: estimated per image (Immerkær); denoising runs only above a threshold and scales with it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from ..common import imageio


@dataclass
class Prepared:
    image: Image.Image                 # RGB, straightened and denoised: what the layers sit on
    original: Image.Image              # RGB as opened (oriented), for the overlay check
    dpi: float
    dpi_assumed: bool
    rotation: float = 0.0              # degrees applied (counter-clockwise positive)
    noise: float = 0.0                 # estimated sigma (0..255)
    denoised: bool = False
    notes: list[str] = field(default_factory=list)


def load(path: str) -> tuple[Image.Image, float, bool, list[str]]:
    loaded = imageio.open_image(path)
    notes = list(loaded.warnings)
    img = loaded.image
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.getchannel("A"))
        img = bg
        notes.append("The picture has transparent areas; they are shown on white.")
    img = img.convert("RGB")
    dpi = loaded.dpi[0] if loaded.dpi and 50 <= loaded.dpi[0] <= 1200 else None
    return img, float(dpi or 96.0), dpi is None, notes


def noise_sigma(gray: np.ndarray) -> float:
    """Immerkær's fast noise estimate (sigma in grey levels), ignoring strong edges."""
    import cv2

    g = gray.astype(np.float64)
    kernel = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float64)
    lap = cv2.filter2D(g, -1, kernel)[1:-1, 1:-1]
    edges = cv2.Canny(gray, 60, 160)[1:-1, 1:-1] > 0
    edges = cv2.dilate(edges.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    vals = np.abs(lap[~edges])
    if vals.size < 100:
        return 0.0
    return float(math.sqrt(math.pi / 2) * vals.mean() / 6.0)


def skew(gray: np.ndarray) -> tuple[float, float]:
    """(angle, gain): the rotation (counter-clockwise positive) that levels the text rows, and how much
    sharper the rows are than without it."""
    import cv2

    h, w = gray.shape
    scale = min(1.0, 1000 / max(h, w))
    small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if bw.mean() < 0.5 or bw.mean() > 128:
        return 0.0, 1.0
    center = (bw.shape[1] / 2, bw.shape[0] / 2)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(bw, m, (bw.shape[1], bw.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)
        return float(np.var(rot.sum(axis=1, dtype=np.float64)))

    base = score(0.0) or 1.0
    best = max(np.arange(-5.0, 5.01, 0.5), key=score)
    fine = max(np.arange(best - 0.5, best + 0.51, 0.1), key=score)
    return round(float(fine), 2), score(fine) / base


def rotate(img: Image.Image, angle: float) -> Image.Image:
    """Rotate about the centre, same canvas size; the uncovered corners repeat the nearest edge."""
    import cv2

    arr = np.asarray(img)
    h, w = arr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return Image.fromarray(cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE))


def prepare(path: str, *, deskew: bool = True, denoise: bool = True) -> Prepared:
    import cv2

    img, dpi, assumed, notes = load(path)
    prep = Prepared(image=img, original=img, dpi=dpi, dpi_assumed=assumed, notes=notes)
    gray = np.asarray(img.convert("L"))
    if deskew:
        angle, gain = skew(gray)
        if 0.3 <= abs(angle) <= 5.0 and gain >= 1.3:
            prep.image = rotate(img, angle)
            prep.rotation = angle
            notes.append(f"Straightened by {abs(angle):.1f}°.")
    prep.noise = noise_sigma(np.asarray(prep.image.convert("L")))
    if denoise and prep.noise >= 4.0:
        h = float(min(15.0, max(3.0, prep.noise * 1.1)))
        arr = cv2.fastNlMeansDenoisingColored(np.asarray(prep.image), None, h, h, 7, 21)
        prep.image = Image.fromarray(arr)
        prep.denoised = True
        notes.append(f"Noise removed (estimated level {prep.noise:.0f}).")
    return prep
