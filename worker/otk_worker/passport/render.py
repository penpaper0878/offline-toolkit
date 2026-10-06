"""Measure, fit and render a passport photo.

All parameters come from the editor: crop (step 2), placement (step 3), background, brush strokes,
adjustments and optional corrections of the crown and chin markers. The photo is sampled once from the
original pixels (see session.warp), adjusted, and laid on the background colour through the person matte.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..common.units import round_px
from . import adjust as A
from . import geometry as G
from . import session as S

PER_UNIT = {"mm": 25.4, "cm": 2.54, "in": 1.0}


# ------------------------------------------------------------------ spec
@dataclass
class Spec:
    width: float
    height: float
    unit: str
    dpi: float
    head: dict
    eyeLine: dict | None = None
    topMargin: dict | None = None
    bottomMargin: dict | None = None
    headWidth: dict | None = None

    @staticmethod
    def parse(d: dict) -> "Spec":
        return Spec(float(d["width"]), float(d["height"]), d["unit"], float(d["dpi"]), d["head"], d.get("eyeLine"),
                    d.get("topMargin"), d.get("bottomMargin"), d.get("headWidth"))

    @property
    def ppu(self) -> float:
        """Output pixels per spec unit."""
        return self.dpi / PER_UNIT[self.unit]

    @property
    def px(self) -> tuple[int, int]:
        return max(1, round_px(self.width * self.ppu)), max(1, round_px(self.height * self.ppu))

    def size_info(self) -> dict:
        w, h = self.px
        mm = 25.4 / self.dpi
        return {"px": [w, h], "dpi": self.dpi, "unit": self.unit, "size": [self.width, self.height],
                "errorMm": [round(w * mm - self.width * 25.4 / PER_UNIT[self.unit], 3),
                            round(h * mm - self.height * 25.4 / PER_UNIT[self.unit], 3)]}


def _mid(r: dict | None) -> float | None:
    if not r:
        return None
    lo, hi = r.get("min"), r.get("max")
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    return lo if lo is not None else hi


# ------------------------------------------------------------------ measurements (cropped px)
@dataclass
class Measures:
    chin: np.ndarray
    crown: np.ndarray
    hair: np.ndarray | None
    skull: np.ndarray
    eyes: np.ndarray            # (2, 2)
    centre: np.ndarray          # face midline point at eye height
    up: np.ndarray
    width: float                # cheek to cheek
    tilt: float
    openness: tuple[float, float]
    points: np.ndarray          # all landmarks
    hair_cut: bool
    crown_from: str             # "hair" | "skull" | "hair (estimated)" | "corrected"


def measure(an: S.Analysis, crown_ref: str, overrides: dict | None = None) -> Measures | None:
    f = an.faces.main
    if f is None:
        return None
    pts = an.to_cropped(f.points)
    hair = an.to_cropped(an.hair)[0] if an.hair is not None else None
    skull = an.to_cropped(f.skull_top(an.hair))[0]
    if crown_ref == "hair":
        crown, src = (hair, "hair") if hair is not None and not an.hair_cut else (skull, "hair (estimated)")
    else:
        crown, src = skull, "skull"
    chin = pts[152]
    ov = overrides or {}
    if ov.get("crown"):
        crown, src = np.array(ov["crown"], dtype=float), "corrected"
    if ov.get("chin"):
        chin = np.array(ov["chin"], dtype=float)
    eyes = np.stack([pts[468], pts[473]])
    centre = (pts[234] + pts[454]) / 2
    return Measures(chin, crown, hair, skull, eyes, centre, f.up, float(np.linalg.norm(pts[454] - pts[234])),
                    f.tilt, f.eye_openness(), pts, an.hair_cut, src)


# ------------------------------------------------------------------ auto fit
def autofit(m: Measures, crop: G.Crop, spec: Spec) -> G.Place:
    W, H = spec.px
    ppu = spec.ppu
    angle = -m.tilt                                         # level the eyes
    head_c = float(np.dot(m.crown - m.chin, m.up))          # cropped px along the face's up axis
    target = (_mid(spec.head) or spec.height * 0.75) * ppu
    s = target / max(head_c, 1e-6)                          # output px per cropped px
    cw, ch = crop.w, crop.h
    r = G.rot(angle)

    def out(p):  # cropped point -> output, with the picture's centre at the origin
        return s * (r @ (np.asarray(p, dtype=float) - np.array([cw / 2, ch / 2])))

    centre_o, crown_o, chin_o, eye_o = out(m.centre), out(m.crown), out(m.chin), out(m.eyes.mean(0))
    x = W / 2 - centre_o[0]
    if spec.eyeLine:
        y = (H - _mid(spec.eyeLine) * ppu) - eye_o[1]
    elif spec.topMargin:
        y = _mid(spec.topMargin) * ppu - crown_o[1]
    else:
        head_o = chin_o[1] - crown_o[1]
        y = (H - head_o) * 0.42 - crown_o[1]                # a little more room below the chin than above
    if spec.bottomMargin and spec.bottomMargin.get("min") is not None:
        limit = H - spec.bottomMargin["min"] * ppu
        if chin_o[1] + y > limit:
            y = limit - chin_o[1]
    return G.Place(x / W, y / H, s / H, angle)


# ------------------------------------------------------------------ maps
def maps(an_or_crop, place: G.Place, spec: Spec, crop: G.Crop):
    """(output -> cropped, output -> source)."""
    out_to_crop = G.place_map(place, (crop.w, crop.h), spec.px)
    return out_to_crop, G.compose(G.crop_map(crop), out_to_crop)


# ------------------------------------------------------------------ hints
def _level(ok: bool, warn: bool) -> str:
    return "ok" if ok else ("warn" if warn else "bad")


def _fmt(v: float, unit: str) -> str:
    return f"{v:.2f} in" if unit == "in" else f"{v:.1f} mm" if unit == "mm" else f"{v:.2f} cm"


def hints(an: S.Analysis, m: Measures | None, place: G.Place, spec: Spec, crop: G.Crop, *,
          src_per_out: float, uncovered: float, background: dict, upscaled: bool, out: np.ndarray | None,
          person: np.ndarray | None, person_cut: int = 0) -> tuple[list[dict], dict]:
    W, H = spec.px
    ppu = spec.ppu
    unit = spec.unit
    res: list[dict] = []
    measures: dict = {}
    n = an.faces.count
    res.append({"id": "face", "level": _level(n == 1, n > 1),
                "label": "Face found" if n == 1 else ("No face found" if n == 0 else f"{n} faces found"),
                "detail": "" if n == 1 else ("Measure by hand: drag the crown and chin markers." if n == 0
                                             else "Only the largest face is measured. A passport photo shows one person.")})
    if m is not None:
        crop_to_out = G.invert(G.place_map(place, (crop.w, crop.h), spec.px))
        P = lambda p: G.apply(crop_to_out, p)[0]  # noqa: E731
        chin, crown, centre = P(m.chin), P(m.crown), P(m.centre)
        eyes = G.apply(crop_to_out, m.eyes)
        up = np.array([0.0, -1.0])
        head = float(np.dot(crown - chin, up)) / ppu
        lo, hi = spec.head["min"], spec.head["max"]
        span = hi - lo
        measures.update(head=round(head, 3), headPercent=round(100 * head / spec.height, 1),
                        crownFrom=m.crown_from, crown=[round(float(v), 1) for v in crown],
                        chin=[round(float(v), 1) for v in chin])
        res.append({"id": "head", "level": _level(lo <= head <= hi, lo - span * 0.25 <= head <= hi + span * 0.25),
                    "label": f"Head {_fmt(head, unit)} ({100 * head / spec.height:.0f}% of the height)",
                    "detail": f"Allowed {_fmt(lo, unit)}–{_fmt(hi, unit)}, chin to {'top of the hair' if spec.head['crown'] == 'hair' else 'top of the head (not the hair)'}."
                              + (" The crown is estimated: the hair is cut off at the top of the photo." if m.crown_from == "hair (estimated)" else "")
                              + (" Crown or chin corrected by hand." if m.crown_from == "corrected" else "")})
        off = (float(centre[0]) - W / 2) / ppu
        tol = spec.width * 0.02
        measures["offCentre"] = round(off, 3)
        res.append({"id": "centre", "level": _level(abs(off) <= tol, abs(off) <= tol * 2.5),
                    "label": "Centred" if abs(off) <= tol else f"Off centre by {_fmt(abs(off), unit)}",
                    "detail": "The face midline should be in the middle of the photo."})
        d = eyes[1] - eyes[0]
        tilt = math.degrees(math.atan2(d[1], d[0]))
        measures["eyeTilt"] = round(tilt, 2)
        res.append({"id": "level", "level": _level(abs(tilt) < 2, abs(tilt) < 4),
                    "label": "Eyes level" if abs(tilt) < 2 else f"Eyes tilted {abs(tilt):.1f}°",
                    "detail": "Use Auto fit, or turn the photo, until the eyes are level (within 2°)."})
        eye_line = (H - float(eyes[:, 1].mean())) / ppu
        measures["eyeLine"] = round(eye_line, 3)
        if spec.eyeLine:
            elo, ehi = spec.eyeLine.get("min", 0), spec.eyeLine.get("max", spec.height)
            res.append({"id": "eyeLine", "level": _level(elo <= eye_line <= ehi, elo - 0.05 * spec.height <= eye_line <= ehi + 0.05 * spec.height),
                        "label": f"Eye line {_fmt(eye_line, unit)} from the bottom",
                        "detail": f"Allowed {_fmt(elo, unit)}–{_fmt(ehi, unit)}."})
        top = float(crown[1]) / ppu
        bottom = (H - float(chin[1])) / ppu
        measures.update(topMargin=round(top, 3), bottomMargin=round(bottom, 3))
        if spec.topMargin:
            tlo, thi = spec.topMargin.get("min", 0), spec.topMargin.get("max", spec.height)
            res.append({"id": "top", "level": _level(tlo <= top <= thi, tlo - 1 <= top <= thi + 1),
                        "label": f"Space above the head {_fmt(top, unit)}", "detail": f"Allowed {_fmt(tlo, unit)}–{_fmt(thi, unit)}."})
        elif top < 0:
            res.append({"id": "top", "level": "warn", "label": "The top of the head is outside the photo",
                        "detail": "Most authorities want the whole head in the photo."})
        if spec.bottomMargin and spec.bottomMargin.get("min") is not None:
            res.append({"id": "bottom", "level": _level(bottom >= spec.bottomMargin["min"], bottom >= spec.bottomMargin["min"] - 1),
                        "label": f"Space below the chin {_fmt(bottom, unit)}", "detail": f"At least {_fmt(spec.bottomMargin['min'], unit)}."})
        if spec.headWidth:
            hw = m.width * place.scale * H / ppu
            measures["headWidth"] = round(hw, 3)
            wlo, whi = spec.headWidth.get("min", 0), spec.headWidth.get("max", spec.width)
            res.append({"id": "headWidth", "level": _level(wlo <= hw <= whi, wlo - 1 <= hw <= whi + 1),
                        "label": f"Face width {_fmt(hw, unit)}", "detail": f"Allowed {_fmt(wlo, unit)}–{_fmt(whi, unit)} (cheek to cheek)."})
        ear = min(m.openness)
        measures["eyeOpenness"] = round(ear, 3)
        res.append({"id": "eyes", "level": _level(ear >= 0.18, ear >= 0.12),
                    "label": "Eyes open" if ear >= 0.18 else ("Eyes narrow" if ear >= 0.12 else "Eyes look closed"),
                    "detail": "Eyes must be open and clearly visible."})
    enl = 1 / max(src_per_out, 1e-9)
    measures["sourcePixelsPerOutput"] = round(src_per_out, 3)
    if upscaled:
        res.append({"id": "resolution", "level": "warn", "label": f"Enlarged {enl:.1f}× with AI upscaling",
                    "detail": "Upscaling invents detail. Many authorities refuse altered photos; use a sharper original if you can."})
    else:
        res.append({"id": "resolution", "level": _level(enl <= 1.0, enl <= 1.6),
                    "label": "Resolution: enough pixels" if enl <= 1.0 else f"Enlarged {enl:.1f}× (too few pixels)",
                    "detail": "Each output pixel comes from at least one photo pixel." if enl <= 1.0 else "The print may look soft. Use a larger original, or try AI upscaling."})
    measures["uncovered"] = round(uncovered, 4)
    measures["personCut"] = round(person_cut / W, 4)
    if uncovered > 0.002:
        if background.get("mode") == "replace" and person is not None and person_cut < 0.02 * W:
            # Only background is missing there, and the new background fills it seamlessly.
            res.append({"id": "frame", "level": "ok", "label": f"{uncovered * 100:.1f}% of the frame filled with the background colour",
                        "detail": "The photo or the crop does not reach that edge of the frame, but only background is missing there."})
        elif background.get("mode") == "replace" and person is not None:
            res.append({"id": "frame", "level": "warn" if person_cut < 0.1 * W else "bad",
                        "label": "The person is cut off by the edge of the photo or the crop",
                        "detail": "Zoom in, move the photo, or crop more loosely (step 2), so the head and shoulders are not cut inside the frame."})
        else:
            res.append({"id": "frame", "level": "bad", "label": f"{uncovered * 100:.1f}% of the frame is outside the photo or the crop",
                        "detail": "Zoom in, move the photo, or crop more loosely (step 2), so the photo fills the frame (empty parts get the background colour)."})
    if background.get("mode") == "replace":
        res.append({"id": "background", "level": "ok" if an.alpha is not None else "bad",
                    "label": f"Background replaced ({background.get('color', '#FFFFFF')})" if an.alpha is not None else "No person found to cut out",
                    "detail": "" if an.alpha is not None else "The background cannot be replaced; keep the original."})
    elif out is not None and person is not None:
        bgm = person < 0.05
        if bgm.sum() > 100:
            y = out[..., :3].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            sd = float(y[bgm].std())
            measures["backgroundSpread"] = round(sd, 2)
            res.append({"id": "background", "level": _level(sd < 8, sd < 16),
                        "label": "Background plain" if sd < 8 else "Background uneven",
                        "detail": "Authorities want a plain, evenly lit background. Replacing it helps."})
    if out is not None and m is not None:
        crop_to_out = G.invert(G.place_map(place, (crop.w, crop.h), spec.px))
        sm = A.skin_mask(out.shape[:2], G.apply(crop_to_out, m.points))
        sel = sm > 0.5
        if sel.sum() > 50:
            px = out[sel][:, :3]
            clipped = float(((px >= 254).any(1) | (px <= 1).all(1)).mean())
            measures["faceClipped"] = round(clipped, 4)
            res.append({"id": "exposure", "level": _level(clipped < 0.01, clipped < 0.05),
                        "label": "Exposure fine" if clipped < 0.01 else f"{clipped * 100:.0f}% of the face is burnt out or black",
                        "detail": "Lower the exposure or highlights so the face keeps detail."})
    return res, measures


# ------------------------------------------------------------------ render
@dataclass
class Result:
    image: np.ndarray           # RGB uint8 at the spec's pixel size
    before: np.ndarray | None
    hints: list[dict]
    measures: dict


def _strokes_mask(an: S.Analysis, strokes: list[dict]) -> np.ndarray | None:
    """Restore (+1) / erase (-1) paint in analysis px from strokes stored in source px."""
    import cv2

    if not strokes or an.alpha is None:
        return None
    h, w = an.alpha.shape
    src_to_an = G.compose(G.scaling(an.k), G.invert(G.crop_map(an.crop)))
    zoom = an.k
    m = an.alpha.astype(np.float32) / 255.0
    for st in strokes:
        pts = G.apply(src_to_an, st.get("points") or [])
        if len(pts) == 0:
            continue
        r = max(1.0, float(st.get("radius", 10)) * zoom)
        canvas = np.zeros((h, w), np.uint8)
        poly = np.round(pts * 4).astype(np.int32)
        if len(poly) == 1:
            cv2.circle(canvas, tuple(int(v) for v in poly[0]), int(round(r * 4)), 255, -1, cv2.LINE_AA, shift=2)
        else:
            cv2.polylines(canvas, [poly], False, 255, max(1, int(round(r * 2))), cv2.LINE_AA, shift=2)
            for p in (poly[0], poly[-1]):
                cv2.circle(canvas, tuple(int(v) for v in p), int(round(r * 4)), 255, -1, cv2.LINE_AA, shift=2)
        soft = 1.0 - float(st.get("hardness", 0.6))
        paint = canvas.astype(np.float32) / 255.0
        if soft > 0.01:
            sig = max(0.5, r * soft * 0.5)
            paint = cv2.GaussianBlur(paint, (0, 0), sig)
        if st.get("mode") == "erase":
            m = m * (1 - paint)
        else:
            m = np.maximum(m, paint)
    return m


def render(sess: S.Session, crop: G.Crop, place: G.Place | None, spec: Spec, *, background: dict | None = None,
           strokes: list[dict] | None = None, adjust: dict | None = None, overrides: dict | None = None,
           upscale: bool = False, before: bool = False, check=lambda: None) -> Result:
    import cv2

    background = background or {"mode": "keep"}
    an = S.analyse(sess, crop, check)
    m = measure(an, spec.head["crown"], overrides)
    if place is None:
        place = autofit(m, crop, spec) if m is not None else G.Place(0.5, 0.5, spec.px[1] / max(crop.h, 1) / spec.px[1], 0.0)
    W, H = spec.px
    out_to_crop, out_to_src = maps(an, place, spec, crop)
    src_per_out = G.source_per_output(out_to_src)
    upscaled = False
    if upscale and src_per_out < 0.95:
        person_rgb, upscaled = _upscaled(sess, crop, out_to_src, (W, H), check)
    else:
        person_rgb = S.warp(sess, out_to_src, (W, H), quality=True)
    check()
    cover = S.coverage(sess, out_to_src, (W, H), (out_to_crop, (crop.w, crop.h)))
    uncovered = float(1 - cover.mean())
    pts_out = None
    if m is not None:
        pts_out = G.apply(G.invert(out_to_crop), m.points)
    img = person_rgb.astype(np.float32) / 255.0
    adj = A.Adjust.parse(adjust)
    img = A.apply(img, adj, pts_out)
    # Matte in output px.
    alpha_out = None
    person_cut = 0
    if an.alpha is not None:
        mat = _strokes_mask(an, strokes or [])
        mat = mat if mat is not None else an.alpha.astype(np.float32) / 255.0
        out_to_an = G.compose(G.scaling(an.k), out_to_crop)
        alpha_out = cv2.warpAffine(mat.astype(np.float32), G.to_cv(out_to_an), (W, H),
                                   flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        feather = float(background.get("feather", 1.0))
        if feather > 0:
            alpha_out = cv2.GaussianBlur(alpha_out, (0, 0), feather * W / 600)
        alpha_out = np.clip(alpha_out, 0, 1)
        if uncovered > 0:
            # Length (px) of the photo's edge inside the frame that runs through the person: a visible cut.
            inside = (cover > 0.5).astype(np.uint8)
            edge = (inside > 0) & (cv2.erode(inside, np.ones((3, 3), np.uint8)) == 0)
            person_cut = int((edge & (alpha_out > 0.5)).sum())
        alpha_out = alpha_out * cover
    if background.get("mode") == "replace" and alpha_out is not None:
        from .matte import decontaminate

        col = np.array([int(background.get("color", "#FFFFFF")[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
        img = decontaminate(img, alpha_out)
        img = img * alpha_out[..., None] + col * (1 - alpha_out[..., None])
    elif uncovered > 0:
        col = np.array([int(background.get("color", "#FFFFFF")[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255
        img = img * cover[..., None] + col * (1 - cover[..., None])
    out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    hs, ms = hints(an, m, place, spec, crop, src_per_out=src_per_out, uncovered=uncovered, background=background,
                   upscaled=upscaled, out=out, person=alpha_out, person_cut=person_cut)
    ms["place"] = place.to_dict()
    ms["size"] = spec.size_info()
    bef = None
    if before:
        bef = person_rgb if uncovered == 0 else (person_rgb * cover[..., None] + 255 * (1 - cover[..., None])).astype(np.uint8)
    return Result(out, bef, hs, ms)


_up_cache: dict = {}


def _upscaled(sess: S.Session, crop: G.Crop, out_to_src: np.ndarray, size: tuple[int, int], check) -> tuple[np.ndarray, bool]:
    """Real-ESRGAN (x4) on the part of the photo the frame shows, then sampled like the original."""
    import cv2

    from ..design import superres

    W, H = size
    corners = G.apply(out_to_src, [[0, 0], [W, 0], [W, H], [0, H]])
    x0, y0 = np.floor(corners.min(0)).astype(int) - 4
    x1, y1 = np.ceil(corners.max(0)).astype(int) + 4
    sw, sh = sess.size
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(sw, x1), min(sh, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return S.warp(sess, out_to_src, size), False
    key = (sess.id, x0, y0, x1, y1)
    big = _up_cache.get(key)
    if big is None:
        from PIL import Image

        if not superres.available():
            return S.warp(sess, out_to_src, size), False
        big_img, method = superres.upscale(Image.fromarray(sess.rgb[y0:y1, x0:x1]), 4, check=check)
        if method == "lanczos":
            return S.warp(sess, out_to_src, size), False
        big = np.asarray(big_img.convert("RGB"))
        _up_cache.clear()
        _up_cache[key] = big
    k = big.shape[1] / (x1 - x0)
    a = G.compose(G.affine(np.eye(2) * k, [-x0 * k, -y0 * k]), out_to_src)
    return cv2.warpAffine(big, G.to_cv(a), size, flags=cv2.INTER_LANCZOS4 | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0)), True
