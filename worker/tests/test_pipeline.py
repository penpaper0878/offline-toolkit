import threading
import zipfile

import numpy as np
import pytest
from PIL import Image

from conftest import jpeg_with_orientation, photo_array, quadrants
from otk_worker.common import metadata
from otk_worker.errors import InputError
from otk_worker.resizer import pipeline
from otk_worker.resizer.settings import validate

PHOTO_240 = {"width": 240, "height": 240, "unit": "px", "dpi": 200, "fit": "crop", "format": "jpeg",
             "sizeRange": {"min": 20, "max": 50, "unit": "KB"}}


def test_settings_validation_lists_problems():
    with pytest.raises(InputError) as exc:
        validate({"width": -1, "height": 10, "unit": "furlong", "dpi": 5000, "fit": "crop", "format": "gif"})
    msg = exc.value.message
    for field in ("width", "unit", "dpi", "format"):
        assert field in msg
    with pytest.raises(InputError):
        validate({**PHOTO_240, "sizeRange": {"min": 60, "max": 50, "unit": "KB"}})
    with pytest.raises(InputError):
        validate({**PHOTO_240, "width": 240.5})
    assert validate(PHOTO_240)["stripMetadata"] is True


def test_photo_preset_end_to_end(tmp_path, photo_file):
    loaded = pipeline.load_cached(str(photo_file))
    result, data = pipeline.process(loaded, None, validate(PHOTO_240))
    assert result["status"] == "ok"
    assert (result["output"]["width"], result["output"]["height"]) == (240, 240)
    assert 20 * 1024 <= len(data) <= 50 * 1024
    rb = metadata.readback(data)
    assert rb["jfifDensity"] == [200, 200] and rb["exifDpi"] == [200.0, 200.0]


def test_physical_units_end_to_end(photo_file):
    s = validate({"width": 3, "height": 3, "unit": "cm", "dpi": 200, "fit": "crop", "format": "png"})
    result, data = pipeline.process(pipeline.load_cached(str(photo_file)), None, s)
    assert (result["output"]["width"], result["output"]["height"]) == (236, 236)
    assert result["size"]["width"]["errorMm"] == pytest.approx(-0.028)
    assert metadata.readback(data)["pngPpm"] == [7874, 7874]


def test_crop_visual_regression(tmp_path):
    """Crop the top-right (green) quadrant exactly: output must be green, exact size and DPI."""
    src = tmp_path / "q.png"
    quadrants(400, 300).save(src)
    s = validate({"width": 100, "height": 75, "unit": "px", "dpi": 300, "fit": "crop", "format": "png"})
    result, data = pipeline.process(pipeline.load_cached(str(src)), {"x": 200, "y": 0, "w": 200, "h": 150}, s)
    from conftest import decode
    out = np.asarray(decode(data).convert("RGB"))
    assert out.shape == (75, 100, 3)
    assert (np.abs(out[4:-4, 4:-4].astype(int) - [0, 255, 0]) <= 2).all()
    assert metadata.readback(data)["dpi"][0] == pytest.approx(300, abs=0.001)


def test_orientation_is_applied_and_reset(tmp_path):
    src = jpeg_with_orientation(tmp_path / "rot.jpg", 6)
    s = validate({"width": 150, "height": 200, "unit": "px", "dpi": 200, "fit": "stretch", "format": "jpeg",
                  "stripMetadata": False})
    result, data = pipeline.process(pipeline.load_cached(str(src)), None, s)
    rb = metadata.readback(data)
    assert (rb["width"], rb["height"]) == (150, 200) and rb["orientation"] == 1
    top_left = Image.open(__import__("io").BytesIO(data)).convert("RGB").getpixel((5, 5))
    assert top_left[2] > 200 and top_left[0] < 60   # blue: the rotation really happened


def test_transparent_png_to_jpeg_warns(tmp_path):
    src = tmp_path / "t.png"
    im = Image.new("RGBA", (50, 50), (255, 0, 0, 0))
    im.paste((255, 0, 0, 255), (10, 10, 40, 40))
    im.save(src)
    s = validate({"width": 50, "height": 50, "unit": "px", "dpi": 200, "fit": "crop", "format": "jpeg",
                  "padColor": "#0000FF"})
    result, data = pipeline.process(pipeline.load_cached(str(src)), None, s)
    assert any("transparency" in w for w in result["warnings"])


def test_batch_names_collisions_zip_and_errors(tmp_path, photo_file):
    out = tmp_path / "out"
    out.mkdir()
    (out / "फोटो photo_240x240.jpg").write_bytes(b"existing file must survive")
    bad = tmp_path / "not-an-image.jpg"
    bad.write_text("nope")
    events = []
    res = pipeline.run_batch({
        "items": [{"path": str(photo_file)}, {"path": str(bad)}, {"path": str(photo_file)}],
        "settings": PHOTO_240, "outputDir": str(out), "zip": True,
    }, events.append)
    statuses = [r["status"] for r in res["results"]]
    assert statuses == ["ok", "error", "ok"]
    assert (out / "फोटो photo_240x240.jpg").read_bytes() == b"existing file must survive"
    names = sorted(p.name for p in out.iterdir())
    assert "फोटो photo_240x240 (1).jpg" in names and "फोटो photo_240x240 (2).jpg" in names
    with zipfile.ZipFile(res["zipPath"]) as zf:
        assert sorted(zf.namelist()) == ["फोटो photo_240x240 (1).jpg", "फोटो photo_240x240 (2).jpg"]
    assert events[-1]["fraction"] == 1.0
    assert res["counts"] == {"ok": 2, "error": 1}


def test_out_of_range_is_not_saved_unless_asked(tmp_path, photo_file):
    s = {**PHOTO_240, "sizeRange": {"max": 0.2, "unit": "KB"}}   # 204 bytes: below any 240x240 JPEG
    res = pipeline.run_batch({"items": [{"path": str(photo_file)}], "settings": s, "outputDir": str(tmp_path / "a")},
                             lambda e: None)
    assert res["results"][0]["status"] == "above_max" and res["results"][0]["outputPath"] is None
    assert not any((tmp_path / "a").iterdir())
    res = pipeline.run_batch({"items": [{"path": str(photo_file)}], "settings": {**s, "saveOutOfRange": True},
                              "outputDir": str(tmp_path / "b")}, lambda e: None)
    assert res["results"][0]["outputPath"]


def test_cancel_mid_batch(tmp_path):
    files = []
    for i in range(5):
        p = tmp_path / f"p{i}.png"
        Image.fromarray(photo_array(600, 400, seed=i)).save(p)
        files.append({"path": str(p)})
    cancel = threading.Event()

    def notify(ev):
        if ev["index"] == 2:
            cancel.set()
    res = pipeline.run_batch({"items": files, "settings": PHOTO_240, "outputDir": str(tmp_path / "o")}, notify, cancel)
    statuses = [r["status"] for r in res["results"]]
    assert statuses[:2] == ["ok", "ok"] and set(statuses[2:]) == {"cancelled"} and len(statuses) == 5
