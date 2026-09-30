"""Deterministic test images. No pytest import, so the bundled Python can use it too."""

import numpy as np
from PIL import Image


def photo_array(w: int = 1200, h: int = 900, seed: int = 1) -> np.ndarray:
    """Deterministic photo-like content: smooth gradients, edges and mild noise."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, w)[None, :, None]
    y = np.linspace(0, 1, h)[:, None, None]
    base = np.concatenate([x * 200 + 30 * np.sin(y * 20),
                           y * 180 + 40 * np.cos(x * 15),
                           (x + y) * 100], axis=2)
    base[h // 3: h // 2, w // 4: w // 2] = [240, 240, 240]  # a hard-edged block
    return (base + rng.normal(0, 12, (h, w, 3))).clip(0, 255).astype(np.uint8)


def quadrants(w: int = 400, h: int = 300) -> Image.Image:
    """Four solid colours: TL red, TR green, BL blue, BR yellow."""
    arr = np.zeros((h, w, 3), np.uint8)
    arr[: h // 2, : w // 2] = (255, 0, 0)
    arr[: h // 2, w // 2:] = (0, 255, 0)
    arr[h // 2:, : w // 2] = (0, 0, 255)
    arr[h // 2:, w // 2:] = (255, 255, 0)
    return Image.fromarray(arr)
