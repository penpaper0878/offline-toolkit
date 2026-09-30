import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def vectors() -> dict:
    with open(ROOT / "tests" / "vectors" / "units.json", encoding="utf-8") as fh:
        return json.load(fh)


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


@pytest.fixture
def photo() -> Image.Image:
    return Image.fromarray(photo_array())


@pytest.fixture
def photo_file(tmp_path) -> Path:
    p = tmp_path / "फोटो photo.jpg"   # Unicode name on purpose
    Image.fromarray(photo_array()).save(p, quality=95)
    return p


def quadrants(w: int = 400, h: int = 300) -> Image.Image:
    """Four solid colours: TL red, TR green, BL blue, BR yellow."""
    arr = np.zeros((h, w, 3), np.uint8)
    arr[: h // 2, : w // 2] = (255, 0, 0)
    arr[: h // 2, w // 2:] = (0, 255, 0)
    arr[h // 2:, : w // 2] = (0, 0, 255)
    arr[h // 2:, w // 2:] = (255, 255, 0)
    return Image.fromarray(arr)


def jpeg_with_orientation(path: Path, orientation: int, img: Image.Image | None = None) -> Path:
    img = img or quadrants()
    exif = Image.Exif()
    exif[0x0112] = orientation
    img.save(path, "JPEG", quality=95, exif=exif)
    return path


def decode(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im
