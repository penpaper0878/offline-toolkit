import io
import json
from pathlib import Path

import pytest
from PIL import Image

from imagegen import photo_array, quadrants  # noqa: F401  (re-exported for the tests)
from conftest_converter import samples  # noqa: F401  (session fixture for the converter tests)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def vectors() -> dict:
    with open(ROOT / "tests" / "vectors" / "units.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def photo() -> Image.Image:
    return Image.fromarray(photo_array())


@pytest.fixture
def photo_file(tmp_path) -> Path:
    p = tmp_path / "फोटो photo.jpg"   # Unicode name on purpose
    Image.fromarray(photo_array()).save(p, quality=95)
    return p


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
