"""Image -> editable design: runs the stages and assembles the scene.

1. prepare: orientation, straightening, denoising (preprocess)
2. text: lines, words and confidence (textdetect); small text is read on a super-resolved copy
3. text removal: the ink of every line is painted out (inpaint)
4. tables: ruled grids with text in them (tables)
5. elements: shapes, lines, graphics and photos on the text-free picture (elements)
6. typography: paragraphs, alignment, spacing and the closest bundled font (textstyle, fontmatch)
7. background: everything that became a layer is removed from the picture
8. layers: photos cropped from the original pixels, graphics traced to paths, the scene written

Stages 1-2 are cached in the project folder by the source's hash and the options, so analysing again
(other languages, other font choices) skips the slow parts that did not change.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from .. import __version__
from . import elements as el_mod
from . import fontmatch, inpaint, preprocess, scene as sc, superres, tables as tbl_mod, textdetect, textstyle, vectorize

SMALL_TEXT_PX = 20          # detected line height below which text is read on an upscaled copy
LOW_CONFIDENCE = 0.80


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


# The cache holds plain PNG and JSON only, so opening a project folder can never run code from it.

def _cached_prepared(cache: Path, key: str, build: Callable[[], preprocess.Prepared]) -> preprocess.Prepared:
    meta, png, orig = cache / f"{key}.json", cache / f"{key}.png", cache / f"{key}-original.png"
    if meta.exists() and png.exists() and orig.exists():
        try:
            d = json.loads(meta.read_text(encoding="utf-8"))
            return preprocess.Prepared(image=Image.open(png).convert("RGB"), original=Image.open(orig).convert("RGB"),
                                       dpi=d["dpi"], dpi_assumed=d["dpiAssumed"], rotation=d["rotation"],
                                       noise=d["noise"], denoised=d["denoised"], notes=d["notes"])
        except (OSError, ValueError, KeyError):
            pass
    prep = build()
    cache.mkdir(parents=True, exist_ok=True)
    prep.image.save(png)
    prep.original.save(orig)
    meta.write_text(json.dumps({"dpi": prep.dpi, "dpiAssumed": prep.dpi_assumed, "rotation": prep.rotation,
                                "noise": prep.noise, "denoised": prep.denoised, "notes": prep.notes}), encoding="utf-8")
    return prep


def _cached_lines(cache: Path, key: str, build: Callable[[], list[textdetect.TextLine]]) -> list[textdetect.TextLine]:
    p = cache / f"{key}.json"
    if p.exists():
        try:
            return [textdetect.TextLine(d["text"], d["quad"], d["conf"], d["engine"],
                                        [textdetect.Word(w["text"], tuple(w["box"]), w["conf"]) for w in d["words"]])
                    for d in json.loads(p.read_text(encoding="utf-8"))]
        except (OSError, ValueError, KeyError):
            pass
    lines = build()
    cache.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([{"text": ln.text, "quad": [[float(x), float(y)] for x, y in ln.quad], "conf": float(ln.conf),
                              "engine": ln.engine, "words": [{"text": w.text, "box": [float(v) for v in w.box],
                                                              "conf": float(w.conf)} for w in ln.words]}
                             for ln in lines], ensure_ascii=False), encoding="utf-8")
    return lines


def _cached_upscale(cache: Path, key: str, build: Callable[[], tuple[Image.Image, str]]) -> tuple[Image.Image, str]:
    png, meta = cache / f"{key}.png", cache / f"{key}.json"
    if png.exists() and meta.exists():
        try:
            return Image.open(png).convert("RGB"), json.loads(meta.read_text(encoding="utf-8"))["method"]
        except (OSError, ValueError, KeyError):
            pass
    img, method = build()
    cache.mkdir(parents=True, exist_ok=True)
    img.save(png)
    meta.write_text(json.dumps({"method": method}), encoding="utf-8")
    return img, method


def analyze(source: str | Path, project: Path, *, langs: list[str] | None = None, upscale: str = "auto",
            deskew: bool = True, denoise: bool = True, check: Callable[[], None] = lambda: None,
            progress: Callable[[float, str], None] = lambda f, m: None) -> dict:
    """Analyse `source` into `project` (assets/, cache/, scene.json). Returns the scene."""
    import cv2

    t0 = time.monotonic()
    source = Path(source)
    project.mkdir(parents=True, exist_ok=True)
    assets_dir = project / "assets"
    assets_dir.mkdir(exist_ok=True)
    cache = project / "cache"
    langs = langs or ["eng"]
    src_hash = _sha(source)
    notes: list[str] = []
    timings: dict[str, float] = {}

    def stage(name: str, frac: float, msg: str):
        check()
        progress(frac, msg)
        timings[name] = time.monotonic()

    # 1. prepare ------------------------------------------------------------------------------
    stage("prepare", 0.02, "Preparing the picture")
    prep = _cached_prepared(cache, f"prep-{src_hash}-{int(deskew)}{int(denoise)}",
                   lambda: preprocess.prepare(str(source), deskew=deskew, denoise=denoise))
    notes += prep.notes
    if prep.dpi_assumed:
        notes.append(f"The picture has no resolution information; {prep.dpi:.0f} DPI is assumed for physical sizes.")
    prep.original.save(assets_dir / "original.png")
    prep.image.save(assets_dir / "prepared.png")
    arr = np.asarray(prep.image)
    H, W = arr.shape[:2]

    # 2. text ---------------------------------------------------------------------------------
    stage("text", 0.08, "Reading the text")
    key = f"text-{src_hash}-{int(deskew)}{int(denoise)}-{'+'.join(langs)}"
    lines = _cached_lines(cache, key + "-1x", lambda: textdetect.detect(prep.image, langs, check=check))
    factor, method = 1.0, None
    heights = [ln.height for ln in lines]
    small = bool(heights) and float(np.median(heights)) < SMALL_TEXT_PX
    if upscale == "always" or (upscale == "auto" and (small or (not heights and max(W, H) < 700))):
        factor = float(min(4, max(2, round(30 / max(4.0, float(np.median(heights)) if heights else 15.0)))))
    analysis = prep.image
    if factor > 1:
        stage("superres", 0.15, f"Enlarging {factor:.0f}x for small text")
        big = _cached_upscale(cache, f"sr-{src_hash}-{int(deskew)}{int(denoise)}-{factor:g}",
                      lambda: superres.upscale(prep.image, factor, check=check))
        analysis, method = big
        lines = [ln.scaled(1 / factor) for ln in _cached_lines(cache, key + f"-{factor:g}x",
                 lambda: textdetect.detect(analysis, langs, check=check))]
        notes.append(f"Small text was read on a copy enlarged {factor:.0f}x "
                     f"({'Real-ESRGAN' if method == 'realesrgan' else 'Lanczos'}).")
    big_arr = np.asarray(analysis)

    # 3. text removal ----------------------------------------------------------------------------
    stage("removal", 0.30, "Removing the text from the background")
    big_lines = [ln.scaled(factor) for ln in lines] if factor > 1 else lines
    inks = {id(ln): textstyle.line_ink(big_arr, bl) for ln, bl in zip(lines, big_lines)}
    text_mask_big = np.zeros(big_arr.shape[:2], bool)
    for li in inks.values():
        if li is not None:
            inpaint.paste_mask(text_mask_big, li.ink, li.inv, li.ink_origin)
    text_mask = text_mask_big if factor == 1 else cv2.resize(text_mask_big.astype(np.uint8), (W, H),
                                                             interpolation=cv2.INTER_AREA) > 0
    hs = [li.height / factor for li in inks.values() if li is not None]
    r = max(2, int(round(0.1 * float(np.median(hs))))) if hs else 2
    text_mask = cv2.dilate(text_mask.astype(np.uint8), np.ones((2 * r + 1, 2 * r + 1), np.uint8)) > 0
    clean, fill_stats = inpaint.fill(arr, text_mask, check=check)
    Image.fromarray(clean).save(cache / "notext.png")

    # 4. tables -----------------------------------------------------------------------------------
    stage("tables", 0.42, "Looking for tables")
    tables, rest = tbl_mod.detect(arr, clean, lines)

    # 5. elements --------------------------------------------------------------------------------
    stage("elements", 0.50, "Finding shapes, icons and photos")
    elements = el_mod.detect(clean, exclude=[t.box for t in tables])
    containers = [tuple(map(float, e.box)) for e in elements if e.kind == "shape" and e.fill]
    guides = [tuple(map(float, e.box)) for e in elements if e.kind == "line" and e.line[1] == e.line[3]]

    # 6. typography -----------------------------------------------------------------------------
    stage("typography", 0.58, "Matching fonts")
    # Font matching reads the (possibly enlarged) picture; geometry is scaled back afterwards.
    # Colours are measured on the original pixels: enlarging sharpens strokes and darkens them.
    blocks = textstyle.build_blocks(big_arr, [ln.scaled(factor) if factor > 1 else ln for ln in rest],
                                    containers=[tuple(v * factor for v in c) for c in containers],
                                    guides=[tuple(v * factor for v in g) for g in guides], check=check,
                                    progress=lambda f, m: progress(0.58 + 0.22 * f, m),
                                    color_source=(arr, factor) if factor > 1 else None)

    # 7. background ---------------------------------------------------------------------------
    stage("background", 0.82, "Cleaning the background")
    removal = np.zeros((H, W), bool)
    for e in elements:
        x0, y0, x1, y1 = e.box
        m = e.mask if e.kind != "photo" else np.ones_like(e.mask)
        removal[y0:y1, x0:x1] |= m
    for t in tables:
        x0, y0, x1, y1 = (int(v) for v in t.box)
        removal[max(0, y0 - 3):y1 + 4, max(0, x0 - 3):x1 + 4] = True
    removal = cv2.dilate(removal.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    background, bg_stats = inpaint.fill(clean, removal, check=check)
    Image.fromarray(background).save(assets_dir / "background.png")
    page_bg = _hex(np.median(background.reshape(-1, 3), axis=0))

    # 8. layers -------------------------------------------------------------------------------
    stage("layers", 0.88, "Building the layers")
    scene = sc.new_scene(W, H, source={
        "name": source.name, "sha256": src_hash, "width": prep.original.width, "height": prep.original.height,
        "dpi": round(prep.dpi, 2), "dpiAssumed": prep.dpi_assumed, "rotation": prep.rotation,
        "denoised": prep.denoised, "noise": round(prep.noise, 2), "upscale": factor, "upscaleMethod": method,
        "languages": langs, "app": __version__})
    scene["page"]["background"] = page_bg
    scene["assets"] = {"original": "assets/original.png", "prepared": "assets/prepared.png",
                       "background": "assets/background.png"}
    layers = scene["layers"]
    layers.append(sc.layer("image", "background", "Background", (0, 0, W, H), asset="assets/background.png",
                           role="background", locked=True))
    counters: dict[str, int] = {}

    def nid(prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}{counters[prefix]}"

    photos = [e for e in elements if e.kind == "photo"]
    shapes = [e for e in elements if e.kind == "shape"]
    lines_ = [e for e in elements if e.kind == "line"]
    graphics = [e for e in elements if e.kind == "graphic"]
    jpeg_source = source.suffix.lower() in (".jpg", ".jpeg")
    # Bottom to top: larger boxes first, so a card lies under the photo and icon placed on it; text last.
    def box_area(item) -> float:
        x0, y0, x1, y1 = item.box
        return -(x1 - x0) * (y1 - y0)

    stack = sorted(list(elements) + list(tables), key=box_area)
    traced = 0
    for item in stack:
        if isinstance(item, tbl_mod.Table):
            layers.append(_table_layer(item, nid("table")))
            continue
        e = item
        x0, y0, x1, y1 = e.box
        if e.kind == "photo":
            lid = nid("photo")
            crop = Image.fromarray(arr[y0:y1, x0:x1])
            if e.mask.all():
                name = f"assets/{lid}.{'jpg' if jpeg_source else 'png'}"
                crop.save(project / name, quality=95) if jpeg_source else crop.save(project / name)
            else:
                name = f"assets/{lid}.png"
                rgba = np.dstack([arr[y0:y1, x0:x1], (e.mask * 255).astype(np.uint8)])
                Image.fromarray(rgba, "RGBA").save(project / name)
            layers.append(sc.layer("image", lid, f"Photo {counters['photo']}", (x0, y0, x1 - x0, y1 - y0),
                                   asset=name, kind="photo", source={"box": [x0, y0, x1, y1]}))
        elif e.kind == "shape":
            lid = nid("shape")
            label = {"rect": "Rectangle", "rounded": "Rounded rectangle", "ellipse": "Ellipse"}.get(e.shape, "Shape")
            layers.append(sc.layer("shape", lid, label, (x0, y0, x1 - x0, y1 - y0), shape=e.shape, fill=e.fill,
                                   stroke=e.stroke, strokeWidth=e.stroke_width, radius=e.radius,
                                   source={"fit": e.score}))
        elif e.kind == "line":
            lid = nid("line")
            lx0, ly0, lx1, ly1 = e.line
            layers.append(sc.layer("shape", lid, "Line", (x0, y0, x1 - x0, y1 - y0), shape="line", fill=None,
                                   stroke=e.stroke, strokeWidth=e.stroke_width,
                                   points=[round(lx0 - x0, 2), round(ly0 - y0, 2), round(lx1 - x0, 2),
                                           round(ly1 - y0, 2)]))
        else:
            check()
            traced += 1
            progress(0.88 + 0.08 * traced / max(1, len(graphics)), f"Tracing graphic {traced} of {len(graphics)}")
            lid = nid("graphic")
            paths = vectorize.trace(arr, e.mask, e.box)
            crop_name = f"assets/{lid}-pixels.png"
            Image.fromarray(np.dstack([arr[y0:y1, x0:x1], (e.mask * 255).astype(np.uint8)]), "RGBA").save(
                project / crop_name)
            layers.append(sc.layer("vector", lid, f"Graphic {counters['graphic']}", (x0, y0, x1 - x0, y1 - y0),
                                   paths=paths, colors=e.colors, source={"pixels": crop_name}))
    for blk in blocks:
        layers.append(_text_layer(blk, nid("text"), factor, scene["lowConfidence"]))
    scene["notes"] = notes
    scene["limits"] = _limits(blocks, tables, elements, langs, factor)
    timings["end"] = time.monotonic()
    names = list(timings)
    scene["stats"] = {"seconds": round(timings["end"] - t0, 2),
                      "stages": {n: round(timings[names[i + 1]] - timings[n], 2) for i, n in enumerate(names[:-1])},
                      "textLines": len(lines), "textLayers": len(blocks), "tables": len(tables),
                      "shapes": len(shapes) + len(lines_), "graphics": len(graphics), "photos": len(photos),
                      "inpaint": {"text": fill_stats, "elements": bg_stats}}
    progress(0.98, "Saving the design")
    sc.save(scene, project / "scene.json")
    progress(1.0, "Done")
    return scene


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _text_layer(blk: textstyle.TextBlock, lid: str, factor: float, low: list) -> dict:
    """A paragraph as a text layer: box, typography, and the words with their confidence."""
    from . import assets

    k = 1.0 / factor
    face = assets.face(blk.family, blk.weight, blk.italic)
    size = blk.size * k
    met = fontmatch.metrics(blk.family, blk.weight, blk.italic)
    lh = blk.line_height
    pens, advs, bases = [], [], []
    for li in blk.lines:
        g = fontmatch.line_geometry(li.line.text.strip() or " ", face) if face else {"lsb": 0, "advance": 0.5}
        # Straight frame: ink start minus the first glyph's side bearing is where the pen starts.
        pens.append((li.x0 - g["lsb"] * blk.size) * k)
        advs.append(g["advance"] * blk.size * k)
        bases.append(li.baseline * k)
    first = blk.lines[0]
    if blk.angle == 0.0:
        ox, oy = first.inv[0, 2] * k, first.inv[1, 2] * k
        pens = [p + li.inv[0, 2] * k for p, li in zip(pens, blk.lines)]
        bases = [b + li.inv[1, 2] * k for b, li in zip(bases, blk.lines)]
    width = max(advs) * 1.02 + 2
    if blk.align == "center":
        cx = float(np.median([p + a / 2 for p, a in zip(pens, advs)]))
        x = cx - width / 2
    elif blk.align == "right":
        x = max(p + a for p, a in zip(pens, advs)) - width
    else:
        x = min(pens)
    asc, desc = met["ascent"] * size, met["descent"] * size
    y = bases[0] - asc
    h = asc + (len(blk.lines) - 1) * lh * size + desc
    rotation = 0.0
    if blk.angle != 0.0:
        # Single rotated line: its box was measured in the straightened frame; turn it into place.
        cxf, cyf = (x + width / 2) * factor, (y + h / 2) * factor
        c = np.array([cxf, cyf, 1.0]) @ first.inv.T
        x, y = c[0] * k - width / 2, c[1] * k - h / 2
        rotation = -blk.angle
    words, flagged = [], []
    for li in blk.lines:
        for w in li.line.words:
            bx = [round(v * k, 1) for v in w.box]
            words.append({"text": w.text, "box": bx, "conf": round(w.conf, 3)})
            if w.conf < LOW_CONFIDENCE:
                flagged.append(len(words) - 1)
                low.append({"layer": lid, "text": w.text, "conf": round(w.conf, 3)})
    lyr = sc.layer("text", lid, (blk.lines[0].line.text[:40] or "Text"), (x, y, width, h), text=blk.text,
                   style={"family": blk.family, "weight": int(blk.weight), "italic": bool(blk.italic),
                          "size": round(size, 2), "color": blk.color, "align": blk.align,
                          "lineHeight": round(lh, 3), "underline": False},
                   baseline=round(asc, 2),
                   lines=[{"text": li.line.text, "width": round(a, 2)} for li, a in zip(blk.lines, advs)],
                   words=words, lowConfidence=flagged, script=blk.script, confidence=round(blk.conf, 3),
                   fontCandidates=[{**c.to_dict(), "size": round(c.size * k, 2)} for c in blk.candidates],
                   engine=blk.lines[0].line.engine)
    lyr["rotation"] = round(rotation, 2)
    return lyr


def _table_layer(t: tbl_mod.Table, lid: str) -> dict:
    x0, y0, x1, y1 = t.box
    cells = [{"row": c.row, "col": c.col, "rowSpan": c.row_span, "colSpan": c.col_span, "text": c.text,
              "fill": c.fill, "weight": c.weight, "italic": c.italic, "align": c.align, "valign": c.valign}
             for c in sorted(t.cells, key=lambda c: (c.row, c.col))]
    return sc.layer("table", lid, f"Table ({t.rows} x {t.cols})", (x0, y0, x1 - x0, y1 - y0),
                    colWidths=[round(b - a, 2) for a, b in zip(t.xs, t.xs[1:])],
                    rowHeights=[round(b - a, 2) for a, b in zip(t.ys, t.ys[1:])],
                    border={"color": t.border_color, "width": t.border_width},
                    style={"family": t.family, "size": round(t.size, 2), "color": t.color},
                    cells=cells, fontCandidates=[c.to_dict() for c in t.candidates])


def _limits(blocks, tables, elements, langs, factor) -> list[dict]:
    out = [{"id": "general", "text": "Handwriting, heavily decorative or distorted lettering and text on curves "
            "cannot be rebuilt as live text; check those areas in the overlay and fix them by hand."}]
    weak = [b for b in blocks if b.candidates and b.candidates[0].score < 0.55]
    if weak:
        out.append({"id": "font-uncertain", "text": f"{len(weak)} text layer(s) have no close match among the "
                    "bundled fonts (decorative, script or unusual lettering). The nearest font is used; pick "
                    "another from the suggestions or the font list."})
    if any(b.script == "cjk" for b in blocks):
        out.append({"id": "cjk", "text": "Chinese, Japanese and Korean fonts are not bundled; that text uses "
                    "the fonts installed in Windows."})
    def overlaps(a, b) -> bool:
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    k = 1.0 / factor
    if any(overlaps(tuple(v * k for v in blk.box), e.box) for blk in blocks for e in elements if e.kind == "photo"):
        out.append({"id": "text-on-photo", "text": "Where text sat on a photo, the background under it is "
                    "filled in by estimation and can show smudges."})
    if any(e.kind == "graphic" and len(e.colors) > 6 for e in elements):
        out.append({"id": "gradients", "text": "Gradients and shading in graphics become flat colour bands "
                    "when traced; the original pixels are kept with each graphic."})
    if factor > 1:
        out.append({"id": "small-text", "text": "The text is small; recognition and font sizes are less "
                    "certain. Check the highlighted words."})
    return out
