"""RPC handlers for the passport module (registered in otk_worker.api)."""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from ..errors import InputError
from . import adjust as A
from . import export as E
from . import geometry as G
from . import render as R
from . import session as S


def _dir(params: dict) -> Path:
    d = Path(params["previewDir"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(img: np.ndarray | Image.Image, folder: Path, stem: str, fmt: str = "png") -> str:
    im = img if isinstance(img, Image.Image) else Image.fromarray(img)
    path = folder / f"{stem}-{uuid.uuid4().hex[:10]}.{'jpg' if fmt == 'jpeg' else fmt}"
    if fmt == "jpeg":
        im.convert("RGB").save(path, "JPEG", quality=90)
    else:
        im.save(path, "PNG", compress_level=1)
    return str(path)


def _ctx(params: dict) -> tuple[S.Session, G.Crop]:
    sess = S.get(params["id"])
    return sess, G.Crop.parse(params.get("crop"), *sess.size)


def open_photo(params: dict, ctx) -> dict:
    sess = S.open_photo(params["path"])
    w, h = sess.size
    k = min(1.0, int(params.get("maxSide", 2048)) / max(w, h))
    prev = Image.fromarray(sess.rgb)
    if k < 1:
        prev = prev.resize((max(1, round(w * k)), max(1, round(h * k))), Image.Resampling.LANCZOS, reducing_gap=3.0)
    return {"id": sess.id, "path": sess.path, "width": w, "height": h, "meta": sess.meta, "warnings": sess.warnings,
            "preview": {"path": _save(prev, _dir(params), "photo", "jpeg"), "width": prev.width, "height": prev.height, "scale": prev.width / w}}


def _face_info(an: S.Analysis, spec: dict | None, overrides: dict | None) -> dict | None:
    f = an.faces.main
    if f is None:
        return None
    m = R.measure(an, (spec or {}).get("head", {}).get("crown", "hair"), overrides)
    c = lambda p: [round(float(p[0]), 2), round(float(p[1]), 2)]  # noqa: E731
    pts = an.to_cropped(f.points)
    return {"eyes": [c(pts[468]), c(pts[473])], "chin": c(m.chin), "crown": c(m.crown), "crownFrom": m.crown_from,
            "hair": c(m.hair) if m.hair is not None else None, "hairCut": an.hair_cut, "skull": c(m.skull),
            "centre": c(m.centre), "tilt": round(m.tilt, 2), "width": round(m.width, 2),
            "openness": [round(v, 3) for v in m.openness],
            "outline": [c(pts[i]) for i in (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379,
                                             378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
                                             162, 21, 54, 103, 67, 109)]}


def analyze(params: dict, ctx) -> dict:
    from ..resizer import compress

    sess, crop = _ctx(params)
    an = S.analyse(sess, crop, compress.check_cancel(ctx.cancel_event))
    folder = _dir(params)
    out = {"faces": an.faces.count, "face": _face_info(an, params.get("spec"), params.get("overrides")),
           "cropSize": [crop.w, crop.h], "analysisScale": an.k,
           "image": {"path": _save(an.image, folder, "cropped", "jpeg"), "width": an.image.shape[1], "height": an.image.shape[0]},
           "person": an.alpha is not None}
    if an.alpha is not None:
        out["matte"] = {"path": _save(an.alpha, folder, "matte"), "width": an.alpha.shape[1], "height": an.alpha.shape[0]}
    return out


def autofit(params: dict, ctx) -> dict:
    sess, crop = _ctx(params)
    spec = R.Spec.parse(params["spec"])
    an = S.analyse(sess, crop)
    m = R.measure(an, spec.head["crown"], params.get("overrides"))
    if m is None:
        raise InputError("No face was found, so the photo cannot be fitted automatically. Place it by hand.")
    return {"place": R.autofit(m, crop, spec).to_dict()}


def _render(params: dict, spec: R.Spec, ctx, before: bool = False) -> R.Result:
    from ..resizer import compress

    sess, crop = _ctx(params)
    return R.render(sess, crop, G.Place.parse(params.get("place")), spec, background=params.get("background"),
                    strokes=params.get("strokes"), adjust=params.get("adjust"), overrides=params.get("overrides"),
                    upscale=bool(params.get("upscale")), before=before, check=compress.check_cancel(ctx.cancel_event))


def render(params: dict, ctx) -> dict:
    spec = R.Spec.parse(params["spec"])
    res = _render(params, spec, ctx, before=bool(params.get("before")))
    folder = _dir(params)
    out = {"image": {"path": _save(res.image, folder, "photo"), "width": res.image.shape[1], "height": res.image.shape[0]},
           "hints": res.hints, "measures": res.measures}
    if res.before is not None:
        out["before"] = {"path": _save(res.before, folder, "before"), "width": res.before.shape[1], "height": res.before.shape[0]}
    return out


def auto(params: dict, ctx) -> dict:
    """Slider values for auto enhance ("enhance") or auto white balance ("whiteBalance")."""
    spec = R.Spec.parse(params["spec"])
    p = dict(params)
    p["adjust"] = None
    p["background"] = {"mode": "keep"}
    res = _render(p, spec, ctx)
    sess, crop = _ctx(params)
    an = S.analyse(sess, crop)
    m = R.measure(an, spec.head["crown"], params.get("overrides"))
    img = res.image.astype(np.float32) / 255.0
    pts = None
    if m is not None:
        out_to_crop = G.place_map(G.Place.parse(res.measures["place"]), (crop.w, crop.h), spec.px)
        pts = G.apply(G.invert(out_to_crop), m.points)
    if params.get("kind") == "whiteBalance":
        bg = None
        if an.alpha is not None:
            import cv2

            out_to_an = G.compose(G.scaling(an.k), G.place_map(G.Place.parse(res.measures["place"]), (crop.w, crop.h), spec.px))
            a = cv2.warpAffine(an.alpha.astype(np.float32) / 255, G.to_cv(out_to_an), spec.px,
                               flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=1.0)
            bg = (a < 0.05).astype(np.float32)
        return {"adjust": A.auto_white_balance(img, bg)}
    return {"adjust": A.auto_enhance(img, pts)}


def export_photo(params: dict, ctx) -> dict:
    from ..resizer import compress

    spec = R.Spec.parse(params["spec"])
    res = _render(params, spec, ctx)
    size_mm = (E.to_mm(spec.width, spec.unit), E.to_mm(spec.height, spec.unit))
    out = E.save_photo(res.image, size_mm, spec.dpi, params["format"], params["path"], params.get("sizeLimit"),
                       compress.check_cancel(ctx.cancel_event))
    out["hints"] = res.hints
    return out


def _sheet_images(params: dict, dpi: float, ctx) -> tuple[list[Image.Image], tuple[float, float], list[str]]:
    """The photos for a sheet, each rendered (or resampled) for `dpi`, and the cell size in mm."""
    notes: list[str] = []
    imgs: list[Image.Image] = []
    cell = None
    for i, ph in enumerate(params["photos"]):
        if ph.get("kind") == "file":
            im = Image.open(ph["path"])
            im.load()
            w_mm, h_mm = float(ph["widthMm"]), float(ph["heightMm"])
            if cell is None:
                cell = (w_mm, h_mm)
            if abs(im.width / im.height - cell[0] / cell[1]) > 0.01 * cell[0] / cell[1]:
                notes.append(f"Photo {i + 1} has a different shape ({im.width}×{im.height} px); it is stretched to fit the cell.")
            imgs.append(im.convert("RGB"))
            continue
        spec_d = dict(ph["spec"])
        spec_d["dpi"] = dpi
        spec = R.Spec.parse(spec_d)
        if cell is None:
            cell = (E.to_mm(spec.width, spec.unit), E.to_mm(spec.height, spec.unit))
        res = _render(ph, spec, ctx)
        imgs.append(Image.fromarray(res.image))
    if cell is None:
        raise InputError("Add a photo to the sheet first.")
    return imgs, cell, notes


def sheet(params: dict, ctx) -> dict:
    fmt = params.get("format", "preview")
    dpi = float(params.get("dpi", 300)) if fmt in ("png", "jpeg", "pdf", "html") else float(params.get("previewDpi", 60))
    imgs, cell, notes = _sheet_images(params, dpi if fmt != "pdf" else max(dpi, 300), ctx)
    lay = E.layout(params["layout"], cell)
    cells, more = E.assign(lay, [{"copies": ph.get("copies")} for ph in params["photos"]])
    notes += more
    out = {"layout": lay.to_dict(), "assignment": cells, "notes": notes,
           "counts": [sum(1 for c in cells if c == i) for i in range(len(imgs))]}
    borders, marks = bool(params.get("borders")), bool(params.get("cutMarks", True))
    if fmt != "preview" and not lay.fits:
        raise InputError("The grid does not fit on the paper: " + " ".join(lay.problems))
    if fmt == "preview":
        im = E.sheet_raster(lay, imgs, cells, dpi, borders=borders, cut_marks=marks)
        out["image"] = {"path": _save(im, _dir(params), "sheet", "jpeg"), "width": im.width, "height": im.height}
    elif fmt == "pdf":
        data = E.sheet_pdf(lay, imgs, cells, borders=borders, cut_marks=marks)
        E._atomic_write(Path(params["path"]), data)
        out.update(path=params["path"], bytes=len(data))
    elif fmt in ("png", "jpeg"):
        im = E.sheet_raster(lay, imgs, cells, dpi, borders=borders, cut_marks=marks)
        from ..resizer.encode import EncodeSettings, encode

        data = encode(im, EncodeSettings(fmt=fmt, dpi=(dpi, dpi), quality=95, subsampling="4:4:4" if fmt == "jpeg" else None))
        E._atomic_write(Path(params["path"]), data)
        out.update(path=params["path"], bytes=len(data), px=[im.width, im.height], dpi=dpi)
    elif fmt == "html":
        folder = _dir(params)
        paths = [_save(im, folder, f"print{i}") for i, im in enumerate(imgs)]
        out["images"] = paths
        out["html"] = E.sheet_html(lay, ["{{IMG%d}}" % i for i in range(len(paths))], cells, borders=borders, cut_marks=marks)
    else:
        raise InputError(f"Unknown sheet format: {fmt}")
    return out
