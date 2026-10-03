"""4x super-resolution with Real-ESRGAN (realesr-general-x4v3, ONNX) for small or blurry images.

The image is processed in overlapping tiles, so memory stays flat for any size, and cancel is checked
between tiles. Without the model file (a development copy without scripts/fetch_models.py) the caller
falls back to Lanczos and says so.
"""

from __future__ import annotations

import os
from typing import Callable

import numpy as np
from PIL import Image

from .assets import model_path

MODEL = "realesr-general-x4v3.onnx"
SCALE = 4
_session = None


def available() -> bool:
    return model_path(MODEL) is not None


def _get_session():
    global _session
    if _session is None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) - 1)
        opts.log_severity_level = 3
        _session = ort.InferenceSession(str(model_path(MODEL)), sess_options=opts, providers=["CPUExecutionProvider"])
    return _session


def upscale(img: Image.Image, factor: float, *, tile: int = 192, pad: int = 12,
            check: Callable[[], None] = lambda: None,
            progress: Callable[[float], None] = lambda f: None) -> tuple[Image.Image, str]:
    """Upscale by `factor` (1 < factor <= 4): the network runs at 4x, then the result is resized down.
    Returns (image, method)."""
    w, h = img.size
    target = (max(1, round(w * factor)), max(1, round(h * factor)))
    if not available():
        return img.resize(target, Image.Resampling.LANCZOS), "lanczos"
    sess = _get_session()
    src = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    out = np.zeros((h * SCALE, w * SCALE, 3), dtype=np.float32)
    tiles = [(y, x) for y in range(0, h, tile) for x in range(0, w, tile)]
    for i, (y, x) in enumerate(tiles):
        check()
        y0, x0 = max(0, y - pad), max(0, x - pad)
        y1, x1 = min(h, y + tile + pad), min(w, x + tile + pad)
        patch = src[y0:y1, x0:x1].transpose(2, 0, 1)[None]
        res = sess.run(None, {"input": np.ascontiguousarray(patch)})[0][0].transpose(1, 2, 0)
        # Keep only the tile's own area (the padding exists to give the network context at the edges).
        ty0, tx0 = (y - y0) * SCALE, (x - x0) * SCALE
        th, tw = min(tile, h - y) * SCALE, min(tile, w - x) * SCALE
        out[y * SCALE:y * SCALE + th, x * SCALE:x * SCALE + tw] = res[ty0:ty0 + th, tx0:tx0 + tw]
        progress((i + 1) / len(tiles))
    big = Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))
    if big.size != target:
        big = big.resize(target, Image.Resampling.LANCZOS)
    return big, "realesrgan"
