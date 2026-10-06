"""Module 4: passport photos. Geometry, face measurement (metamorphic: a turned, scaled, shifted or mirrored
photo must measure the same face), automatic fitting against every shipped spec, background, adjustments,
exports with exact pixels and DPI, and print sheets."""

from __future__ import annotations

import json
import math
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from otk_worker.design import assets
from otk_worker.passport import adjust as A
from otk_worker.passport import export as E
from otk_worker.passport import geometry as G
from otk_worker.passport import render as R
from otk_worker.passport import session as S

ROOT = Path(__file__).resolve().parents[2]
FACES = Path(__file__).parent / "fixtures" / "faces"
SPECS = {s["id"]: s for s in json.loads((ROOT / "resources/defaults/presets/passport-specs.json").read_text())["specs"]}
PAPERS = {p["id"]: p for p in json.loads((ROOT / "resources/defaults/presets/paper-sizes.json").read_text())["papers"]}
needs_models = pytest.mark.skipif(assets.model_path("face_landmarks_detector.tflite") is None or assets.model_path("selfie_segmenter.tflite") is None,
                                  reason="face or person models missing: run scripts/fetch_models.py")
CTX = types.SimpleNamespace(cancel_event=None, progress=lambda *a: None)


# ------------------------------------------------------------------ geometry
def test_crop_map_round_trip_and_centre():
    c = G.Crop(500, 400, 300, 200, 17.5, True, False)
    m = G.crop_map(c)
    assert np.allclose(G.apply(m, [[150, 100]]), [[500, 400]])
    pts = np.random.default_rng(1).uniform(-50, 400, (20, 2))
    assert np.allclose(G.apply(G.invert(m), G.apply(m, pts)), pts)
    # Mirroring swaps the cropped picture's left and right edges in the source.
    left, right = G.apply(G.crop_map(G.Crop(500, 400, 300, 200)), [[0, 100], [300, 100]])
    fl, fr = G.apply(G.crop_map(G.Crop(500, 400, 300, 200, 0, True)), [[0, 100], [300, 100]])
    assert np.allclose(left, fr) and np.allclose(right, fl)


@pytest.mark.parametrize("angle", [-45, -30, -7.5, 0, 3, 20, 45])
def test_straightening_zooms_so_no_blank_corners(angle):
    c = G.fit_inside(G.Crop(600, 400, 1200, 800, angle), 1200, 800)
    assert G.corners_inside(c, 1200, 800)
    assert c.w / c.h == pytest.approx(1.5)
    # As large as possible: 1% bigger no longer fits (unless nothing was turned).
    bigger = G.Crop(c.cx, c.cy, c.w * 1.01, c.h * 1.01, angle)
    assert angle == 0 or not G.corners_inside(bigger, 1200, 800)


def test_pixel_convention_exact():
    """A crop of a chart lands exactly where the maths says (pixel centres at i + 0.5)."""
    import cv2

    img = np.zeros((40, 60, 3), np.uint8)
    img[10:20, 30:40] = 255                        # white square, x 30..40, y 10..20
    sess = S.Session("t", "", img, [], {})
    # Crop 20 x 20 centred on the square's centre (35, 15), no turn: the square fills x 5..15 of the crop.
    crop = G.Crop(35, 15, 20, 20)
    out = S.warp(sess, G.crop_map(crop), (20, 20), quality=False)
    assert out[5:15, 5:15].min() == 255 and out[:5].max() == 0 and out[:, :5].max() == 0 and out[15:].max() == 0
    # Mirrored: still symmetric about the centre; turned 90 degrees: still the same square.
    out2 = S.warp(sess, G.crop_map(G.Crop(35, 15, 20, 20, 90, True)), (20, 20), quality=False)
    assert (out2[5:15, 5:15] == 255).all() and out2[:4].max() == 0
    del cv2


def test_place_map_and_output_px():
    spec = R.Spec.parse(SPECS["uk-passport"])
    assert spec.px == (413, 531)
    info = spec.size_info()
    assert info["errorMm"] == pytest.approx([-0.033, -0.042], abs=0.001)
    assert R.Spec.parse(SPECS["us-passport"]).px == (600, 600)
    assert R.Spec.parse(SPECS["canada-passport"]).px == (591, 827)
    assert R.Spec.parse({**SPECS["uk-passport"], "dpi": 600}).px == (827, 1063)
    p = G.Place(0.5, 0.5, 2.0 / 531, 10)          # 2 output px per cropped px
    m = G.place_map(p, (200, 300), (413, 531))
    assert np.allclose(G.apply(m, [[206.5, 265.5]]), [[100, 150]])
    assert G.source_per_output(m) == pytest.approx(0.5)


def test_maps_match_the_shared_vectors():
    """tests/vectors/passport.json is also checked by src/shared/passport.test.ts (the editor's maths)."""
    v = json.loads((ROOT / "tests/vectors/passport.json").read_text())
    for c in v["cropMap"]:
        assert np.allclose(G.apply(G.crop_map(G.Crop.parse(c["crop"], 1, 1)), c["points"]), c["expect"], atol=1e-6)
    for f in v["fitInside"]:
        got = G.fit_inside(G.Crop.parse(f["crop"], 1, 1), *f["size"]).to_dict()
        assert all(abs(got[k] - f["expect"][k]) < 1e-6 for k in ("cx", "cy", "w", "h"))
    for pm in v["placeMap"]:
        m = G.place_map(G.Place.parse(pm["place"]), tuple(pm["crop"]), tuple(pm["out"]))
        assert np.allclose(G.apply(m, pm["points"]), pm["expect"], atol=1e-6)
    for sp in v["specPx"]:
        assert list(R.Spec.parse({**sp["spec"], "head": {"min": 1, "max": 2, "crown": "hair"}}).px) == sp["expect"]


# ------------------------------------------------------------------ faces (metamorphic)
def _rotated(img: np.ndarray, deg: float) -> np.ndarray:
    return np.asarray(Image.fromarray(img).rotate(-deg, Image.Resampling.BICUBIC, expand=True, fillcolor=(235, 235, 235)))


@pytest.fixture(scope="module")
def photos():
    return {n: np.asarray(Image.open(FACES / f"{n}.jpg").convert("RGB")) for n in ("portrait-souza", "astronaut-collins")}


@needs_models
@pytest.mark.parametrize("name", ["portrait-souza", "astronaut-collins"])
def test_face_measurements_follow_rotation_scale_and_mirror(photos, name):
    from otk_worker.passport import face as F

    img = photos[name]
    base = F.detect(img).main
    assert base is not None and F.detect(img).count == 1
    eye_d = np.linalg.norm(base.eye_right - base.eye_left)
    for deg in (-8, 6):
        f = F.detect(_rotated(img, deg)).main
        assert f.tilt - base.tilt == pytest.approx(deg, abs=0.8), (name, deg)
    small = np.asarray(Image.fromarray(img).resize((img.shape[1] * 3 // 5, img.shape[0] * 3 // 5), Image.Resampling.LANCZOS))
    f = F.detect(small).main
    assert np.linalg.norm(f.eye_right - f.eye_left) / eye_d == pytest.approx(0.6, rel=0.03)
    assert np.linalg.norm(f.chin - base.chin * 0.6) < eye_d * 0.6 * 0.08
    mir = F.detect(np.ascontiguousarray(img[:, ::-1])).main
    w = img.shape[1]
    assert abs((w - mir.eye_right[0]) - base.eye_left[0]) < eye_d * 0.05
    assert min(base.eye_openness()) > 0.18


@needs_models
def test_a_close_up_face_is_found_whole(photos):
    """A head-and-shoulders crop of a 50 MP photo is analysed at 1600 px, where the face is about 750 px high. YuNet
    split such a face into two partial boxes (one face counted twice, measured from the lower half)."""
    from otk_worker.passport import face as F

    img = photos["portrait-souza"]
    base = F.detect(img).main
    crop = img[70:660, 175:633]                                       # the wizard's first crop, as at 820 px
    big = np.asarray(Image.fromarray(crop).resize((1244, 1600), Image.Resampling.BICUBIC))
    found = F.detect(big)
    assert found.count == 1
    k = 1600 / crop.shape[0]
    f = found.main
    eye_d = np.linalg.norm(base.eye_right - base.eye_left) * k
    assert np.linalg.norm(f.chin - (base.chin - (175, 70)) * k) < eye_d * 0.08
    assert np.linalg.norm(f.eye_left - (base.eye_left - (175, 70)) * k) < eye_d * 0.05


@needs_models
def test_models_give_the_same_results_from_several_threads(photos):
    """The worker answers requests on several threads (a render and an auto adjust can overlap). The shared
    OpenCV models must not mix up their inputs: before they were locked this failed with a cv2.error."""
    from concurrent.futures import ThreadPoolExecutor

    from otk_worker.design import cutout
    from otk_worker.passport import face as F

    imgs = [photos["portrait-souza"], photos["astronaut-collins"]]
    chins = [F.detect(i).main.chin for i in imgs]
    probs = [cutout.person_probability(i).mean() for i in imgs]
    with ThreadPoolExecutor(8) as ex:
        for _ in range(3):
            faces = [(k, ex.submit(F.detect, imgs[k])) for k in [0, 1] * 4]
            people = [(k, ex.submit(cutout.person_probability, imgs[k])) for k in [0, 1] * 4]
            for k, f in faces:
                assert np.linalg.norm(f.result().main.chin - chins[k]) < 0.5
            for k, f in people:
                assert abs(f.result().mean() - probs[k]) < 1e-4


@needs_models
def test_no_face_in_a_landscape():
    from otk_worker.passport import face as F

    rng = np.random.default_rng(3)
    img = (np.clip(rng.normal(0.5, 0.15, (300, 400, 3)), 0, 1) * 255).astype(np.uint8)
    assert F.detect(img).count == 0


# ------------------------------------------------------------------ fitting
def _open(path) -> S.Session:
    return S.open_photo(str(path))


@needs_models
@pytest.mark.parametrize("spec_id", sorted(SPECS))
def test_autofit_meets_every_spec(spec_id, tmp_path):
    sess = _open(FACES / "portrait-souza.jpg")
    spec = R.Spec.parse(SPECS[spec_id])
    res = R.render(sess, G.Crop.full(*sess.size), None, spec, background={"mode": "replace", "color": "#FFFFFF"})
    assert res.image.shape[:2] == spec.px[::-1]
    hints = {h["id"]: h for h in res.hints}
    for key in ("face", "head", "centre", "level", "eyes", "background"):
        assert hints[key]["level"] == "ok", (spec_id, hints[key])
    for key in ("eyeLine", "top", "bottom", "headWidth"):
        if key in hints:
            assert hints[key]["level"] == "ok", (spec_id, hints[key])
    head = res.measures["head"]
    assert head == pytest.approx((spec.head["min"] + spec.head["max"]) / 2, rel=0.002)


@needs_models
def test_autofit_is_the_same_for_a_turned_and_shifted_original(photos, tmp_path):
    """Turn the portrait 7 degrees and pad it: after auto fit, the eyes, chin and crown land on the same
    output pixels (within 1.5 px of a 413 x 531 photo)."""
    img = photos["portrait-souza"]
    p1 = tmp_path / "a.png"
    Image.fromarray(img).save(p1)
    turned = _rotated(img, 7)
    padded = np.full((turned.shape[0] + 120, turned.shape[1] + 80, 3), 235, np.uint8)
    padded[60:60 + turned.shape[0], 30:30 + turned.shape[1]] = turned
    p2 = tmp_path / "b.png"
    Image.fromarray(padded).save(p2)
    spec = R.Spec.parse(SPECS["uk-passport"])
    out = []
    for p in (p1, p2):
        sess = _open(p)
        res = R.render(sess, G.Crop.full(*sess.size), None, spec)
        out.append(res.measures)
    for k in ("crown", "chin"):
        assert np.linalg.norm(np.subtract(out[0][k], out[1][k])) < 1.5, (k, out[0][k], out[1][k])
    assert abs(out[0]["eyeLine"] - out[1]["eyeLine"]) < 0.15        # mm
    assert abs(out[1]["eyeTilt"]) < 0.5


@needs_models
def test_hints_flag_a_small_or_offset_photo():
    sess = _open(FACES / "astronaut-collins.jpg")                     # 512 px: too few pixels for 600 DPI
    spec = R.Spec.parse({**SPECS["uk-passport"], "dpi": 600})
    res = R.render(sess, G.Crop.full(*sess.size), None, spec)
    hints = {h["id"]: h for h in res.hints}
    assert hints["resolution"]["level"] == "bad"
    # Move the photo far off centre by hand: centring and frame coverage complain.
    fit = res.measures["place"]
    res2 = R.render(sess, G.Crop.full(*sess.size), G.Place(fit["x"] + 1.2, fit["y"], fit["scale"], fit["angle"]), spec)
    h2 = {h["id"]: h for h in res2.hints}
    assert h2["centre"]["level"] == "bad" and h2["frame"]["level"] == "bad"


@needs_models
def test_frame_hint_only_complains_when_the_person_is_cut():
    bg = {"mode": "replace", "color": "#FFFFFF", "feather": 1}
    spec = R.Spec.parse(SPECS["uk-passport"])
    # The portrait's hair nearly touches the top of the photo: the fitted frame reaches above the photo,
    # but only background is missing there, and the new background fills it.
    sess = _open(FACES / "portrait-souza.jpg")
    res = R.render(sess, G.Crop(403.7, 294.4, 457.8, 588.7, 0.0, False, False), None, spec, background=bg)
    h = {x["id"]: x for x in res.hints}
    assert res.measures["uncovered"] > 0.02 and res.measures["personCut"] == 0
    assert h["frame"]["level"] == "ok"
    # Kept background: the empty strip shows, so it is a fault.
    res_keep = R.render(sess, G.Crop(403.7, 294.4, 457.8, 588.7, 0.0, False, False), None, spec)
    assert {x["id"]: x for x in res_keep.hints}["frame"]["level"] == "bad"
    # Zoomed out and moved up: the bottom edge of the photo runs through the shoulders inside the frame.
    sess2 = _open(FACES / "astronaut-collins.jpg")
    fit = R.render(sess2, G.Crop.full(*sess2.size), None, spec, background=bg).measures["place"]
    cut = R.render(sess2, G.Crop.full(*sess2.size), G.Place(fit["x"], fit["y"] - 1.0, fit["scale"] * 0.6, fit["angle"]), spec, background=bg)
    hc = {x["id"]: x for x in cut.hints}
    assert cut.measures["personCut"] > 0.5
    assert hc["frame"]["level"] == "bad" and "cut off" in hc["frame"]["label"]


@needs_models
def test_the_crop_limits_what_is_shown():
    # A narrow (35 x 45) crop sized for a square US photo: the photo continues beside the crop, but what the
    # crop leaves out is not shown; it gets the background colour, and the cut shoulders are reported.
    sess = _open(FACES / "portrait-souza.jpg")
    crop = G.Crop(403.7, 294.4, 457.8, 588.7, 0.0, False, False)
    spec = R.Spec.parse(SPECS["us-passport"])
    res = R.render(sess, crop, None, spec, background={"mode": "keep"})
    out_to_crop, out_to_src = R.maps(None, G.Place(**res.measures["place"]), spec, crop)
    cov = S.coverage(sess, out_to_src, spec.px, (out_to_crop, (crop.w, crop.h)))
    assert (cov == 0).mean() > 0.03
    assert (res.image[cov == 0] == 255).all()                    # white, not the photo
    assert {h["id"]: h for h in res.hints}["frame"]["level"] == "bad"
    rep = R.render(sess, crop, None, spec, background={"mode": "replace", "color": "#FFFFFF", "feather": 1})
    assert rep.measures["personCut"] > 0.1
    assert {h["id"]: h for h in rep.hints}["frame"]["level"] == "bad"


@needs_models
def test_crown_and_chin_corrections_are_used():
    sess = _open(FACES / "portrait-souza.jpg")
    crop = G.Crop.full(*sess.size)
    spec = R.Spec.parse(SPECS["us-passport"])
    an = S.analyse(sess, crop)
    m = R.measure(an, "hair")
    lower_crown = (m.crown + np.array([0, 40])).tolist()
    m2 = R.measure(an, "hair", {"crown": lower_crown})
    assert m2.crown_from == "corrected" and m2.crown[1] == pytest.approx(m.crown[1] + 40)
    place = R.autofit(m, crop, spec)
    res = R.render(sess, crop, place, spec, overrides={"crown": lower_crown})
    assert res.measures["crownFrom"] == "corrected"
    assert res.measures["head"] < R.render(sess, crop, place, spec).measures["head"]


# ------------------------------------------------------------------ background and matte
@needs_models
def test_background_replaced_and_no_background_patches():
    sess = _open(FACES / "portrait-souza.jpg")
    spec = R.Spec.parse(SPECS["us-passport"])
    res = R.render(sess, G.Crop.full(*sess.size), None, spec, background={"mode": "replace", "color": "#3366CC", "feather": 1})
    img = res.image.astype(int)
    W, H = spec.px
    m = res.measures
    # The top corners and the band beside the head (where the flag and window were) are the new colour.
    for x, y in ((5, 5), (W - 6, 5), (int(m["crown"][0] + 0.32 * W), int(m["crown"][1] + 0.12 * H)),
                 (int(m["crown"][0] - 0.32 * W), int(m["crown"][1] + 0.12 * H))):
        assert np.abs(img[y, x] - [0x33, 0x66, 0xCC]).max() <= 6, (x, y, img[y, x])
    # The face itself is untouched.
    cx = int((m["crown"][0] + m["chin"][0]) / 2)
    cy = int(m["chin"][1] - 0.3 * (m["chin"][1] - m["crown"][1]))
    assert np.abs(img[cy, cx] - [0x33, 0x66, 0xCC]).max() > 60


@needs_models
def test_brush_strokes_restore_and_erase():
    sess = _open(FACES / "astronaut-collins.jpg")
    crop = G.Crop.full(*sess.size)
    spec = R.Spec.parse(SPECS["uk-passport"])
    bg = {"mode": "replace", "color": "#FFFFFF", "feather": 0}
    base = R.render(sess, crop, None, spec, background=bg)
    place = G.Place.parse(base.measures["place"])
    # Erase a disk in the middle of the face (source px 225, 140), then restore part of the background.
    erased = R.render(sess, crop, place, spec, background=bg,
                      strokes=[{"mode": "erase", "radius": 12, "hardness": 1, "points": [[225, 140]]}])
    out_pt = G.apply(G.invert(G.compose(G.crop_map(crop), G.place_map(place, (crop.w, crop.h), spec.px))), [[225, 140]])[0]
    x, y = (int(v) for v in out_pt)
    assert (erased.image[y, x] >= 250).all() and not (base.image[y, x] >= 250).all()
    restored = R.render(sess, crop, place, spec, background=bg,
                        strokes=[{"mode": "restore", "radius": 15, "hardness": 1, "points": [[30, 30], [60, 30]]}])
    p = G.apply(G.invert(G.compose(G.crop_map(crop), G.place_map(place, (crop.w, crop.h), spec.px))), [[45, 30]])[0]
    px, py = int(p[0]), int(p[1])
    if 0 <= px < spec.px[0] and 0 <= py < spec.px[1]:
        assert not (restored.image[py, px] >= 250).all()


# ------------------------------------------------------------------ adjustments
def test_adjustments_identity_and_ranges():
    img = np.random.default_rng(0).uniform(0, 1, (40, 50, 3)).astype(np.float32)
    assert np.array_equal(A.apply(img, A.Adjust()), img)
    for k in ("exposure", "brightness", "contrast", "highlights", "shadows", "warmth", "tint", "saturation", "vibrance"):
        hi, lo = A.apply(img, A.Adjust.parse({k: 100})), A.apply(img, A.Adjust.parse({k: -100}))
        assert 0 <= hi.min() and hi.max() <= 1 and not np.allclose(hi, lo), k
    assert A.apply(img, A.Adjust.parse({"exposure": 50})).mean() > img.mean()
    assert A.apply(img, A.Adjust.parse({"exposure": -50})).mean() < img.mean()


def test_auto_white_balance_neutralises_a_grey_wall_and_ignores_a_red_one():
    for cast in ((1.06, 1, 0.92), (0.94, 1.03, 1.05)):
        g = np.full((60, 60, 3), 0.75, np.float32) * np.array(cast, np.float32)
        out = A.apply(g, A.Adjust.parse(A.auto_white_balance(g, np.ones((60, 60), np.float32))))[0, 0]
        assert out.max() - out.min() < 0.01, (cast, out)
    red = np.full((60, 60, 3), [0.7, 0.15, 0.15], np.float32)
    assert A.auto_white_balance(red, np.ones((60, 60), np.float32)) == {"warmth": 0, "tint": 0}


def test_red_eye_only_inside_the_iris():
    img = np.full((100, 200, 3), 0.8, np.float32)
    pts = np.zeros((478, 2))
    for c, (x, y) in ((468, (60, 50)), (473, (140, 50))):
        pts[c] = (x, y)
        for i, (dx, dy) in enumerate(((6, 0), (0, 6), (-6, 0), (0, -6))):
            pts[c + 1 + i] = (x + dx, y + dy)
        img[y - 4:y + 5, x - 4:x + 5] = (0.8, 0.1, 0.1)
    img[10:20, 10:20] = (0.8, 0.1, 0.1)                 # red outside the eyes stays red
    out = A.apply(img, A.Adjust.parse({"redEye": True}), pts)
    assert out[50, 60, 0] < 0.3 and out[50, 140, 0] < 0.3
    assert out[15, 15, 0] == pytest.approx(0.8)


# ------------------------------------------------------------------ single photo export
@needs_models
@pytest.mark.parametrize("fmt", ["jpeg", "png", "pdf"])
def test_single_photo_exact_size_and_dpi(fmt, tmp_path):
    import pymupdf

    from otk_worker.passport import api

    o = api.open_photo({"path": str(FACES / "portrait-souza.jpg"), "previewDir": str(tmp_path)}, CTX)
    out = tmp_path / f"photo.{'jpg' if fmt == 'jpeg' else fmt}"
    res = api.export_photo({"id": o["id"], "spec": SPECS["uk-passport"], "previewDir": str(tmp_path), "format": fmt,
                            "path": str(out), "background": {"mode": "replace", "color": "#DCDCDC"}}, CTX)
    assert out.is_file() and res["px"] == [413, 531]
    if fmt == "pdf":
        page = pymupdf.open(out)[0]
        assert (page.rect.width / 72 * 25.4, page.rect.height / 72 * 25.4) == pytest.approx((35, 45), abs=0.001)
    else:
        im = Image.open(out)
        assert im.size == (413, 531) and tuple(round(v) for v in im.info["dpi"]) == (300, 300)


@needs_models
def test_single_photo_file_size_limit(tmp_path):
    from otk_worker.passport import api

    o = api.open_photo({"path": str(FACES / "portrait-souza.jpg"), "previewDir": str(tmp_path)}, CTX)
    out = tmp_path / "small.jpg"
    res = api.export_photo({"id": o["id"], "spec": SPECS["india-passport"], "previewDir": str(tmp_path), "format": "jpeg",
                            "path": str(out), "sizeLimit": {"min": 10, "max": 30, "unit": "KB"}}, CTX)
    assert 10 * 1024 <= out.stat().st_size <= 30 * 1024 and res["compression"]["status"] in ("ok", "ok_padded")
    assert Image.open(out).size == (413, 531)


# ------------------------------------------------------------------ print sheets
@pytest.mark.parametrize("paper,photo,expect", [
    ("4x6", (35, 45), (3, 2)), ("4x6", (50.8, 50.8), (2, 1)), ("5x7", (35, 45), (3, 3)),
    ("a4", (35, 45), (6, 5)), ("a5", (35, 45), (4, 3)), ("letter", (50.8, 50.8), (5, 3)), ("a4", (50, 70), (4, 3)),
])
def test_auto_fill_counts(paper, photo, expect):
    lay = E.layout({"paper": PAPERS[paper], "auto": True, "margins": 4, "gutter": 2}, photo)
    assert (lay.rows, lay.cols) == expect and lay.fits
    pw, ph = lay.paper
    for x, y in lay.cells:
        assert x >= 4 - 1e-9 and y >= 4 - 1e-9 and x + photo[0] <= pw - 4 + 1e-9 and y + photo[1] <= ph - 4 + 1e-9


def test_grid_overflow_is_reported_and_blocks_export(tmp_path):
    lay = E.layout({"paper": PAPERS["4x6"], "rows": 5, "cols": 5, "margins": 5, "gutter": 2}, (35, 45))
    assert not lay.fits and len(lay.problems) == 2 and "at most 2 fit" in lay.problems[0]
    lay2 = E.layout({"paper": PAPERS["4x6"], "rows": 1, "cols": 3, "margins": 5, "gutter": 2, "orientation": "landscape"}, (35, 45))
    assert lay2.paper == pytest.approx((152.4, 101.6)) and lay2.fits


def test_cut_marks_never_cross_a_photo():
    lay = E.layout({"paper": PAPERS["a4"], "auto": True, "margins": 6, "gutter": 3}, (35, 45))
    segs = E._mark_segments(lay)
    assert segs
    for x0, y0, x1, y1 in segs:
        for cx, cy in lay.cells:
            inside_x = max(x0, x1) > cx + 1e-6 and min(x0, x1) < cx + 35 - 1e-6
            inside_y = max(y0, y1) > cy + 1e-6 and min(y0, y1) < cy + 45 - 1e-6
            assert not (inside_x and inside_y)


def test_copies_for_several_people():
    lay = E.layout({"paper": PAPERS["4x6"], "auto": True, "margins": 4, "gutter": 2}, (35, 45))
    cells, notes = E.assign(lay, [{"copies": 2}, {"copies": 2}, {"copies": None}])
    assert cells == [0, 0, 1, 1, 2, 2] and not notes
    cells, notes = E.assign(lay, [{"copies": 5}, {"copies": 3}])
    assert cells.count(0) == 5 and cells.count(1) == 1 and notes


@needs_models
@pytest.mark.parametrize("fmt,dpi", [("pdf", 300), ("png", 300), ("jpeg", 600)])
def test_sheet_exports(fmt, dpi, tmp_path):
    import pymupdf

    from otk_worker.passport import api

    o = api.open_photo({"path": str(FACES / "portrait-souza.jpg"), "previewDir": str(tmp_path)}, CTX)
    o2 = api.open_photo({"path": str(FACES / "astronaut-collins.jpg"), "previewDir": str(tmp_path)}, CTX)
    spec = SPECS["uk-passport"]
    photos = [{"kind": "current", "id": o["id"], "spec": spec, "previewDir": str(tmp_path), "copies": 4,
               "background": {"mode": "replace", "color": "#DCDCDC"}},
              {"kind": "current", "id": o2["id"], "spec": spec, "previewDir": str(tmp_path), "copies": None,
               "background": {"mode": "replace", "color": "#DCDCDC"}}]
    out = tmp_path / f"sheet.{'jpg' if fmt == 'jpeg' else fmt}"
    res = api.sheet({"photos": photos, "layout": {"paper": PAPERS["a5"], "auto": True, "margins": 5, "gutter": 2},
                     "format": fmt, "dpi": dpi, "path": str(out), "previewDir": str(tmp_path), "cutMarks": True}, CTX)
    assert res["counts"] == [4, 8] and res["layout"]["count"] == 12
    if fmt == "pdf":
        doc = pymupdf.open(out)
        page = doc[0]
        assert (page.rect.width / 72 * 25.4, page.rect.height / 72 * 25.4) == pytest.approx((148, 210), abs=0.01)
        refs = doc.get_page_images(0)
        assert len(refs) == 12 and len({r[0] for r in refs}) == 2          # each person embedded once
        for info in page.get_image_info():
            r = info["bbox"]
            assert ((r[2] - r[0]) / 72 * 25.4, (r[3] - r[1]) / 72 * 25.4) == pytest.approx((35, 45), abs=0.01)
    else:
        im = Image.open(out)
        assert im.size == (round(148 / 25.4 * dpi), round(210 / 25.4 * dpi))
        assert tuple(round(v) for v in im.info["dpi"]) == (dpi, dpi)


def test_sheet_refuses_an_overflowing_grid(tmp_path):
    from otk_worker.errors import InputError
    from otk_worker.passport import api

    img = tmp_path / "p.png"
    Image.new("RGB", (413, 531), (200, 200, 200)).save(img)
    with pytest.raises(InputError, match="does not fit"):
        api.sheet({"photos": [{"kind": "file", "path": str(img), "widthMm": 35, "heightMm": 45}],
                   "layout": {"paper": PAPERS["4x6"], "rows": 4, "cols": 4, "margins": 5, "gutter": 2},
                   "format": "pdf", "path": str(tmp_path / "x.pdf"), "previewDir": str(tmp_path)}, CTX)


def test_sheet_trims_another_photo_of_a_different_shape(tmp_path):
    import pymupdf

    from otk_worker.passport import api

    # A square photo with a red square in the middle, stored sideways (EXIF orientation 6 = turn 90° clockwise).
    img = Image.new("RGB", (600, 400), (40, 90, 200))
    img.paste((220, 30, 30), (250, 150, 350, 250))
    path = tmp_path / "other.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    img.save(path, quality=95, exif=exif)
    out = tmp_path / "s.pdf"
    res = api.sheet({"photos": [{"kind": "file", "path": str(path), "widthMm": 35, "heightMm": 45, "copies": None}],
                     "layout": {"paper": PAPERS["4x6"], "auto": True, "margins": 4, "gutter": 2},
                     "format": "pdf", "path": str(out), "previewDir": str(tmp_path)}, CTX)
    assert any("top and bottom are trimmed" in n for n in res["notes"])
    doc = pymupdf.open(out)
    xref = doc.get_page_images(0)[0][0]
    pix = pymupdf.Pixmap(doc, xref)
    # Upright 400 × 600, trimmed to 35:45 (400 × 514) around the middle: not stretched.
    assert (pix.width, pix.height) == (400, 514)
    arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)
    ys, xs = np.nonzero((arr[..., 0] > 150) & (arr[..., 2] < 100))
    assert abs((xs.max() - xs.min()) - (ys.max() - ys.min())) <= 3        # the red square is still square
    assert abs((ys.min() + ys.max()) / 2 - 257) <= 3                      # and still in the middle
