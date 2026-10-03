"""Module 3 building blocks, each against a known answer."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from otk_worker.design import assets

HAVE_FONTS = (assets.fonts_dir() / "fonts.json").is_file()
HAVE_MODELS = assets.model_path("selfie_segmenter.tflite") is not None
needs_fonts = pytest.mark.skipif(not HAVE_FONTS, reason="bundled fonts missing: run scripts/fetch_fonts.py")
needs_models = pytest.mark.skipif(not HAVE_MODELS, reason="bundled models missing: run scripts/fetch_models.py")


# ------------------------------------------------------------------ vector paths
def test_path_parser_makes_relative_and_shorthand_commands_absolute():
    from otk_worker.design.vectorize import parse_path, to_d

    segs = parse_path("M10 10 l5 0 v5 h-5 z m20 0 c0 0 5 0 5 5 s5 5 5 0 Q40 0 45 5 T55 5", dx=1, dy=2)
    assert segs[0] == ("M", 11, 12)
    assert segs[1] == ("L", 16, 12)
    assert segs[2] == ("L", 16, 17)
    assert segs[3] == ("L", 11, 17)
    assert segs[4] == ("Z",)
    assert segs[5] == ("M", 31, 12)                       # relative to the closed subpath's start
    assert segs[6] == ("C", 31, 12, 36, 12, 36, 17)
    assert segs[7] == ("C", 36, 22, 41, 22, 41, 17)       # S: first control mirrors the previous one
    assert segs[9] == ("Q", 51, 12, 56, 7)                # T: control mirrored from Q (45,5)->(50,10)... absolute + offset
    assert to_d([("M", 1.005, 2), ("L", 3.1, -0.001), ("Z",)]) == "M 1 2 L 3.1 0 Z"


# ------------------------------------------------------------------ fonts for the exports
def test_office_names_keep_regular_and_bold_in_the_family():
    from otk_worker.design.fonts_out import office_name

    assert office_name("Inter", 400, False) == ("Inter", False, False)
    assert office_name("Inter", 700, True) == ("Inter", True, True)
    assert office_name("Inter", 600, False) == ("Inter SemiBold", False, False)
    assert office_name("Lato", 280, False) == ("Lato Light", False, False)


@needs_fonts
def test_static_instance_of_a_variable_font_is_named_for_office(tmp_path, monkeypatch):
    from fontTools.ttLib import TTFont

    from otk_worker.design import fonts_out

    monkeypatch.setenv("OTK_CACHE", str(tmp_path))
    path = fonts_out.static_font("Inter", 600, False)
    tt = TTFont(str(path))
    assert "fvar" not in tt
    assert tt["name"].getDebugName(1) == "Inter SemiBold"
    assert tt["name"].getDebugName(2) == "Regular"
    assert tt["name"].getDebugName(16) == "Inter"
    assert tt["name"].getDebugName(17) == "SemiBold"
    assert tt["OS/2"].usWeightClass == 600
    bold = TTFont(str(fonts_out.static_font("Lora", 700, False)))
    assert bold["name"].getDebugName(1) == "Lora" and bold["name"].getDebugName(2) == "Bold"
    assert bold["OS/2"].fsSelection & (1 << 5) and bold["head"].macStyle & 1


@needs_fonts
def test_woff2_subset_and_docx_obfuscation(tmp_path, monkeypatch):
    from fontTools.ttLib import TTFont

    from otk_worker.design import fonts_out

    monkeypatch.setenv("OTK_CACHE", str(tmp_path))
    path = fonts_out.static_font("Noto Sans Devanagari", 400, False)
    data = fonts_out.woff2_subset(path, "नमस्ते")
    assert data[:4] == b"wOF2"
    sub = TTFont(io.BytesIO(data))
    assert len(sub.getGlyphOrder()) < len(TTFont(str(path)).getGlyphOrder())
    assert "GSUB" in sub          # conjuncts still shape
    raw = path.read_bytes()
    key = "{6C3A7E2B-1D2F-4A5B-9C8D-0E1F2A3B4C5D}"
    hidden = fonts_out.obfuscate(raw, key)
    assert hidden[:32] != raw[:32] and hidden[32:] == raw[32:]
    assert fonts_out.obfuscate(hidden, key) == raw


# ------------------------------------------------------------------ layout shared with the editor
@needs_fonts
def test_text_and_cell_geometry_match_the_editor_rules():
    from otk_worker.design import layout

    lyr = {"box": [100, 50, 300, 80], "text": "One\nTwo", "style": {"family": "Lato", "weight": 400, "italic": False,
           "size": 20, "color": "#000", "align": "center", "lineHeight": 1.5, "underline": False}}
    m = layout.metrics("Lato", 400, False)
    g = layout.text_geometry(lyr)
    assert g["baselines"] == pytest.approx([50 + m["ascent"] * 20, 50 + m["ascent"] * 20 + 30])
    assert g["anchor"] == 250
    table = {"box": [0, 0, 200, 100], "colWidths": [50, 50], "rowHeights": [25, 25], "border": {"color": "#000", "width": 2},
             "padding": [6, 2, 6, 2], "style": {"family": "Lato", "size": 10, "color": "#000"},
             "cells": [{"row": 0, "col": 0, "rowSpan": 1, "colSpan": 1, "text": "A", "align": "right", "valign": "middle"}]}
    xs, ys = layout.table_grid(table)
    assert xs == [0, 100, 200] and ys == [0, 50, 100]
    cg = layout.cell_text(table, table["cells"][0], (0, 0, 100, 50))
    assert cg["anchor"] == 100 - 1 - 6
    assert cg["baselines"][0] == pytest.approx(25 - (m["ascent"] + m["descent"]) * 10 / 2 + m["ascent"] * 10)


# ------------------------------------------------------------------ project file
def _scene(asset="assets/a.png") -> dict:
    return {"format": "otk-design", "version": 1, "source": {"name": "x.png", "width": 10, "height": 10, "dpi": 96},
            "page": {"width": 10, "height": 10, "background": "#ffffff"},
            "layers": [{"id": "background", "type": "image", "name": "Background", "box": [0, 0, 10, 10], "rotation": 0,
                        "visible": True, "locked": True, "opacity": 1, "asset": asset, "role": "background"}],
            "notes": [], "limits": [], "lowConfidence": []}


def test_otkd_round_trip_and_hostile_files(tmp_path):
    from otk_worker.design import project
    from otk_worker.errors import InputError

    src = tmp_path / "p1"
    (src / "assets").mkdir(parents=True)
    Image.new("RGB", (10, 10), "red").save(src / "assets" / "a.png")
    scene = _scene()
    project.save(src, scene)
    out = project.pack(src, scene, tmp_path / "d.otkd")
    opened = project.unpack(out, tmp_path / "p2")
    assert opened == scene and (tmp_path / "p2" / "assets" / "a.png").is_file()

    # An entry that would land outside the project folder is refused.
    bad = tmp_path / "bad.otkd"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("mimetype", "otk-design")
        z.writestr("scene.json", json.dumps(scene))
        z.writestr("assets/../../evil.txt", "x")
    with pytest.raises(InputError, match="unexpected entry"):
        project.unpack(bad, tmp_path / "p3")
    assert not (tmp_path / "evil.txt").exists()
    # A layer pointing outside its project is refused, too.
    with pytest.raises(InputError, match="outside the design"):
        project.save(src, _scene("../../etc/passwd"))


# ------------------------------------------------------------------ shapes and lines
def test_elements_rebuild_native_shapes_with_their_colours():
    from otk_worker.design import elements

    img = Image.new("RGB", (900, 500), (250, 247, 240))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 240, 160), fill=(30, 90, 168))                       # filled rectangle
    d.rounded_rectangle((300, 40, 560, 160), radius=24, fill=(200, 40, 60))   # rounded
    d.ellipse((620, 40, 860, 160), fill=(255, 215, 194))                      # ellipse
    d.rectangle((40, 220, 300, 380), outline=(139, 30, 63), width=5)          # outline only
    d.line((360, 300, 860, 300), fill=(68, 68, 68), width=4)                  # rule
    d.rectangle((20, 420, 880, 480), outline=(122, 92, 30), width=3)          # frame ...
    d.rectangle((30, 430, 870, 470), outline=(201, 167, 74), width=2)         # ... inside a frame
    found = elements.detect(np.asarray(img))
    shapes = sorted((e for e in found if e.kind in ("shape", "line")), key=lambda e: (e.box[1], e.box[0]))
    kinds = [(e.kind, e.shape) for e in shapes]
    assert kinds == [("shape", "rect"), ("shape", "rounded"), ("shape", "ellipse"), ("shape", "rect"), ("line", "line"),
                     ("shape", "rect"), ("shape", "rect")], kinds
    rect, rounded, ellipse, outline, line, frame, inner = shapes
    assert rect.fill == "#1e5aa8" and rect.box == (40, 40, 241, 161)
    assert rounded.radius == pytest.approx(24, abs=2.5)
    assert ellipse.fill == "#ffd7c2"
    assert outline.fill is None and outline.stroke == "#8b1e3f" and outline.stroke_width == pytest.approx(5, abs=0.3)
    assert line.stroke == "#444444" and line.stroke_width == pytest.approx(4, abs=0.5)
    assert frame.stroke_width == pytest.approx(3, abs=0.3) and inner.stroke_width == pytest.approx(2, abs=0.3)


def test_icon_on_a_button_becomes_its_own_layer():
    from otk_worker.design import elements

    img = Image.new("RGB", (400, 200), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((50, 50, 350, 150), radius=16, fill=(47, 111, 235))
    d.polygon([(90, 80), (130, 100), (90, 120)], fill=(255, 220, 0))   # a play icon on the button
    found = elements.detect(np.asarray(img))
    button = next(e for e in found if e.kind == "shape")
    assert button.shape == "rounded" and button.fill == "#2f6feb"
    icon = [e for e in found if e is not button]
    assert len(icon) == 1 and icon[0].box[0] >= 85 and icon[0].box[2] <= 135


# ------------------------------------------------------------------ inpainting
def test_gradient_background_is_continued_exactly():
    from otk_worker.design import inpaint

    h, w = 300, 400
    yy, xx = np.mgrid[0:h, 0:w]
    grad = np.dstack([200 + 0.1 * xx, 180 + 0.15 * yy, 160 + 0.05 * (xx + yy)]).clip(0, 255).astype(np.uint8)
    mask = np.zeros((h, w), bool)
    mask[100:200, 120:300] = True
    damaged = grad.copy()
    damaged[mask] = (20, 20, 20)
    out, stats = inpaint.fill(damaged, mask)
    assert stats["surface"] == 1
    assert np.abs(out[mask].astype(int) - grad[mask].astype(int)).max() <= 2


# ------------------------------------------------------------------ cut-out
def test_subject_cutout_on_a_plain_backdrop():
    from otk_worker.design import cutout

    img = Image.new("RGB", (320, 240), (235, 235, 235))
    ImageDraw.Draw(img).ellipse((100, 60, 220, 180), fill=(200, 30, 30))
    res = cutout.cutout(np.asarray(img), "subject")
    assert res.method == "subject"
    kept = res.alpha > 127
    truth = np.zeros_like(kept)
    yy, xx = np.mgrid[0:240, 0:320]
    truth[((xx - 160) / 60.0) ** 2 + ((yy - 120) / 60.0) ** 2 <= 1] = True
    iou = (kept & truth).sum() / (kept | truth).sum()
    assert iou > 0.9


@needs_models
def test_person_mode_refuses_a_picture_without_a_person():
    from otk_worker.design import cutout

    img = np.full((200, 200, 3), 240, np.uint8)
    with pytest.raises(ValueError, match="No person"):
        cutout.cutout(img, "person")


# ------------------------------------------------------------------ typography
@needs_fonts
def test_weight_from_ink_coverage(tmp_path):
    from otk_worker.design import assets as A, fontmatch, textdetect, textstyle

    for weight in (400, 600, 700):
        face = A.face("Inter", weight)
        img = Image.new("RGB", (900, 120), "white")
        ImageDraw.Draw(img).text((20, 85), "Quarterly results and plans", font=face.pil(48), fill="#202020", anchor="ls")
        arr = np.asarray(img)
        ys, xs = np.nonzero(arr.min(axis=2) < 200)
        quad = [[xs.min() - 4, ys.min() - 4], [xs.max() + 4, ys.min() - 4], [xs.max() + 4, ys.max() + 4], [xs.min() - 4, ys.max() + 4]]
        li = textstyle.line_ink(arr, textdetect.TextLine("Quarterly results and plans", quad, 0.99, "ppocr", []))
        got = fontmatch.pick_weight("Inter", False, 48, [("Quarterly results and plans", textstyle.coverage(arr, li))])
        assert got == weight


def test_unreadable_lines_are_recognised():
    from otk_worker.design.pipeline import _readable
    from otk_worker.design.textdetect import TextLine

    def line(text, w, h=50, conf=0.6):
        return TextLine(text, [[0, 0], [w, 0], [w, h], [0, h]], conf, "ppocr", [])

    assert not _readable(line("#", 500))                  # a whole line read as one symbol
    assert not _readable(line("  ", 300))
    assert not _readable(line("-- .", 400))
    assert not _readable(line("ab", 600, conf=0.4))
    assert _readable(line("Day", 60, h=26))               # a short word in a table cell
    assert _readable(line("36", 30, h=28))
    assert _readable(line("Summer Music Festival", 900, h=60, conf=0.99))
