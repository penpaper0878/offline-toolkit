import numpy as np
import pytest
from PIL import Image

from conftest import FIXTURES, jpeg_with_orientation, quadrants
from otk_worker.common import imageio
from otk_worker.errors import InputError, UnsupportedFormat


@pytest.mark.parametrize("orientation,size,top_left", [
    (1, (400, 300), (255, 0, 0)),     # as stored
    (3, (400, 300), (255, 255, 0)),   # rotated 180: bottom-right yellow comes to top-left
    (6, (300, 400), (0, 0, 255)),     # rotated 90 CW: bottom-left blue comes to top-left
    (8, (300, 400), (0, 255, 0)),     # rotated 90 CCW: top-right green comes to top-left
])
def test_exif_orientation_applied(tmp_path, orientation, size, top_left):
    p = jpeg_with_orientation(tmp_path / f"o{orientation}.jpg", orientation)
    loaded = imageio.open_image(p)
    assert loaded.size == size
    assert loaded.orientation == orientation
    px = loaded.image.getpixel((10, 10))
    assert all(abs(a - b) <= 6 for a, b in zip(px, top_left))


def test_heic(tmp_path):
    loaded = imageio.open_image(FIXTURES / "quadrants.heic")
    assert loaded.source_format == "HEIF"
    assert loaded.size == (64, 48)
    r, g, b = loaded.image.getpixel((5, 5))
    assert r > 240 and 100 < g < 150


def test_formats_and_modes(tmp_path):
    base = quadrants(64, 48)
    base.save(tmp_path / "a.bmp")
    base.save(tmp_path / "a.webp", quality=90)
    base.convert("CMYK").save(tmp_path / "cmyk.jpg")
    pal = base.convert("P", palette=Image.Palette.ADAPTIVE, colors=4)
    pal.info["transparency"] = 0
    pal.save(tmp_path / "pal.png", transparency=0)
    Image.fromarray((np.arange(64 * 48, dtype=np.uint16).reshape(48, 64) * 20)).save(tmp_path / "g16.png")
    frames = [quadrants(32, 32), quadrants(32, 32).rotate(90)]
    frames[0].save(tmp_path / "multi.tif", save_all=True, append_images=frames[1:])

    assert imageio.open_image(tmp_path / "a.bmp").image.mode == "RGB"
    assert imageio.open_image(tmp_path / "a.webp").source_format == "WEBP"
    cmyk = imageio.open_image(tmp_path / "cmyk.jpg")
    assert cmyk.image.mode == "RGB" and any("CMYK" in w for w in cmyk.warnings)
    assert imageio.open_image(tmp_path / "pal.png").image.mode == "RGBA"
    g16 = imageio.open_image(tmp_path / "g16.png")
    assert g16.image.mode == "L" and any("16-bit" in w for w in g16.warnings)
    assert g16.image.getextrema()[1] > 200   # scaled, not clipped to a flat 255
    multi = imageio.open_image(tmp_path / "multi.tif")
    assert multi.frames == 2 and any("first" in w for w in multi.warnings)


def test_srgb_profile_is_not_converted(tmp_path):
    p = tmp_path / "srgb.jpg"
    quadrants(40, 30).save(p, icc_profile=imageio.SRGB_ICC)
    loaded = imageio.open_image(p)
    assert not loaded.colour_converted and loaded.icc


def test_bad_inputs(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    with pytest.raises(UnsupportedFormat):
        imageio.open_image(tmp_path / "notes.txt")
    with pytest.raises(InputError):
        imageio.open_image(tmp_path / "missing.jpg")
    broken = tmp_path / "broken.jpg"
    data = (tmp_path / "x.jpg")
    quadrants().save(data)
    broken.write_bytes(data.read_bytes()[:400])
    with pytest.raises((InputError, UnsupportedFormat)):
        imageio.open_image(broken)


def test_preview(tmp_path, photo_file):
    loaded = imageio.open_image(photo_file, draft_to=256)
    prev = imageio.save_preview(loaded, tmp_path / "prev", 256)
    assert max(prev["width"], prev["height"]) <= 256
