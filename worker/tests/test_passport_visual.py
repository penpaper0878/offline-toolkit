"""Visual regression tests for Module 4: the crop, the sized passport photo and the print sheet, compared
with reviewed reference pictures (tests/golden/passport), plus their exact pixel sizes and DPI.

A change that moves, scales, recolours or re-cuts the result fails here. After an intended change, look
at the new pictures and replace the references:  OTK_UPDATE_GOLDEN=1 npm run test:py -- -k visual
"""

from __future__ import annotations

import json
import os
import threading
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from otk_worker.common.ssim import ssim
from otk_worker.design import assets
from otk_worker.passport import geometry as G
from otk_worker.passport import render as R
from otk_worker.passport import session as S

ROOT = Path(__file__).resolve().parents[2]
FACES = Path(__file__).parent / "fixtures" / "faces"
GOLD = Path(__file__).parent / "golden" / "passport"
UPDATE = os.environ.get("OTK_UPDATE_GOLDEN") == "1"
SPECS = {s["id"]: s for s in json.loads((ROOT / "resources/defaults/presets/passport-specs.json").read_text())["specs"]}
PAPERS = {p["id"]: p for p in json.loads((ROOT / "resources/defaults/presets/paper-sizes.json").read_text())["papers"]}
CTX = types.SimpleNamespace(cancel_event=threading.Event())

# The first crop the app makes for this portrait (head and shoulders, UK shape).
PORTRAIT_CROP = G.Crop(403.7, 294.4, 457.8, 588.7, 0.0, False, False)
WHITE = {"mode": "replace", "color": "#FFFFFF", "feather": 1}

needs_models = pytest.mark.skipif(
    not all((assets.models_dir() / f).is_file() for f in ("face_detection_yunet_2023mar.onnx", "face_landmarks_detector.tflite",
                                                          "selfie_segmenter.tflite")),
    reason="face and segmentation models not fetched (python scripts/fetch_models.py)")


def _compare(name: str, img: Image.Image, min_ssim: float, max_side: int = 1024, info: dict | None = None) -> float:
    """Compare with the reference picture; `info` (measurements) is stored next to it and shown on failure."""
    path = GOLD / f"{name}.png"
    meta = path.with_suffix(".json")
    if UPDATE:
        GOLD.mkdir(parents=True, exist_ok=True)
        img.save(path, optimize=True)
        if info is not None:
            meta.write_text(json.dumps(info, indent=1, sort_keys=True) + "\n")
        return 1.0
    if not path.is_file():
        pytest.fail(f"No reference picture {path.name}; create it with OTK_UPDATE_GOLDEN=1 and review it.")
    ref = Image.open(path).convert("RGB")
    assert ref.size == img.size, f"{name}: {img.size} instead of {ref.size}"
    s = ssim(ref, img.convert("RGB"), max_side)
    if s < min_ssim:
        # For review (ignored by git, uploaded by CI): the new picture and the difference, 4x amplified.
        img.save(path.with_name(f"{name}.actual.png"))
        diff = np.abs(np.asarray(ref, np.int16) - np.asarray(img.convert("RGB"), np.int16)).max(2)
        Image.fromarray(np.clip(diff * 4, 0, 255).astype(np.uint8)).save(path.with_name(f"{name}.diff.png"))
        was = json.loads(meta.read_text()) if meta.is_file() else None
        pytest.fail(f"{name}: SSIM {s:.4f} < {min_ssim} against the reference (saved {name}.actual.png and .diff.png)\n"
                    f"  now:       {json.dumps(info, sort_keys=True)}\n  reference: {json.dumps(was, sort_keys=True)}")
    return s


def _measures(m: dict) -> dict:
    keep = ("head", "headPercent", "crownFrom", "crown", "chin", "eyeLine", "topMargin", "bottomMargin", "eyeTilt",
            "uncovered", "personCut", "place")
    r = lambda v: [r(x) for x in v] if isinstance(v, list) else ({k: r(x) for k, x in v.items()} if isinstance(v, dict)  # noqa: E731
                                                                 else float(f"{v:.6g}") if isinstance(v, float) else v)
    return {k: r(m[k]) for k in keep if k in m}


def test_crop_matches_the_reference():
    # Turned 3°, mirrored, 400 × 520 px at one source pixel per output pixel.
    sess = S.open_photo(str(FACES / "portrait-souza.jpg"))
    crop = G.Crop(410.0, 300.0, 400.0, 520.0, 3.0, True, False)
    assert G.corners_inside(crop, *sess.size)
    out = S.warp(sess, G.crop_map(crop), (400, 520))
    assert out.shape == (520, 400, 3)
    _compare("crop-3deg-mirrored", Image.fromarray(out), 0.995)


@needs_models
@pytest.mark.parametrize("spec_id,px", [("uk-passport", (413, 531)), ("us-passport", (600, 600))])
def test_passport_photo_matches_the_reference(spec_id, px, tmp_path):
    from otk_worker.passport import api
    from otk_worker.common.metadata import readback

    o = api.open_photo({"path": str(FACES / "portrait-souza.jpg"), "previewDir": str(tmp_path)}, CTX)
    spec = SPECS[spec_id]
    crop = PORTRAIT_CROP if spec_id == "uk-passport" else G.Crop(403.7, 294.4, 588.7, 588.7, 0.0, False, False)
    out = tmp_path / "photo.png"
    res = api.export_photo({"id": o["id"], "crop": crop.to_dict(), "spec": spec, "background": WHITE, "format": "png",
                            "path": str(out), "previewDir": str(tmp_path)}, CTX)
    assert tuple(res["px"]) == px and res["dpi"] == 300
    rb = readback(out.read_bytes())
    assert (rb["width"], rb["height"]) == px
    im = Image.open(out)
    assert tuple(round(v) for v in im.info["dpi"]) == (300, 300)
    # The head sits inside the spec's range, and the picture matches the reference.
    rr = R.render(S.get(o["id"]), crop, None, R.Spec.parse(spec), background=WHITE)
    _compare(f"photo-{spec_id}", im.convert("RGB"), 0.97, info=_measures(rr.measures))
    h = {x["id"]: x for x in rr.hints}
    assert h["head"]["level"] == "ok" and h["centre"]["level"] == "ok" and h["frame"]["level"] == "ok"


@needs_models
def test_print_sheet_matches_the_reference(tmp_path):
    from otk_worker.passport import api

    o = api.open_photo({"path": str(FACES / "portrait-souza.jpg"), "previewDir": str(tmp_path)}, CTX)
    out = tmp_path / "sheet.png"
    res = api.sheet({"photos": [{"kind": "current", "id": o["id"], "crop": PORTRAIT_CROP.to_dict(), "spec": SPECS["uk-passport"],
                                 "background": WHITE, "previewDir": str(tmp_path), "copies": None}],
                     "layout": {"paper": PAPERS["4x6"], "orientation": "portrait", "auto": True, "margins": 4, "gutter": 2, "center": True},
                     "format": "png", "dpi": 300, "path": str(out), "previewDir": str(tmp_path), "cutMarks": True}, CTX)
    assert res["layout"]["rows"] * res["layout"]["cols"] == res["layout"]["count"] == 6
    im = Image.open(out)
    assert im.size == (1200, 1800) and tuple(round(v) for v in im.info["dpi"]) == (300, 300)
    # The cut marks stay in the margins: nothing is printed at the very edge of the paper (printers cannot print there).
    arr = np.asarray(im.convert("L"))
    for edge in (arr[:8], arr[-8:], arr[:, :8], arr[:, -8:]):
        assert (edge == 255).all()
    _compare("sheet-4x6-uk", im.convert("RGB"), 0.97)
