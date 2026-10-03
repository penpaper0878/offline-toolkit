"""Closest bundled font for a piece of text, by comparing shapes.

The recognised words are drawn in each candidate font (HarfBuzz shaping through Pillow/raqm), scaled so
the ink heights match, and compared with the ink of the picture: intersection over union of the two
masks after the best alignment within a few pixels. Two passes: every family that covers the script at
regular and bold, then the best few families at every weight they have, upright and italic. The size
(em, px) follows from the scale that matched the heights.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from . import assets

RENDER_SIZE = 96          # px em size used to draw candidates
SHORTLIST = 6


@dataclass
class Candidate:
    family: str
    weight: int
    italic: bool
    score: float          # 0..1, mean IoU
    size: float           # em size in px that reproduces the observed ink height

    def to_dict(self) -> dict:
        return {"family": self.family, "weight": self.weight, "italic": self.italic, "score": round(self.score, 4),
                "size": round(self.size, 2)}


def script_of(text: str) -> str:
    """The dominant script of a string (the names used in fonts.json)."""
    counts: dict[str, int] = {}
    for ch in text:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        for key, script in (("DEVANAGARI", "devanagari"), ("BENGALI", "bengali"), ("GUJARATI", "gujarati"),
                            ("GURMUKHI", "gurmukhi"), ("TAMIL", "tamil"), ("TELUGU", "telugu"), ("KANNADA", "kannada"),
                            ("MALAYALAM", "malayalam"), ("ORIYA", "oriya"), ("ARABIC", "arabic"), ("HEBREW", "hebrew"),
                            ("CJK", "cjk"), ("HIRAGANA", "cjk"), ("KATAKANA", "cjk"), ("HANGUL", "cjk")):
            if name.startswith(key) or key in name.split(" ")[:2]:
                counts[script] = counts.get(script, 0) + 1
                break
        else:
            counts["latin"] = counts.get("latin", 0) + 1
    return max(counts, key=counts.get) if counts else "latin"


def render_mask(text: str, face: assets.FontFace, size: int = RENDER_SIZE) -> tuple[np.ndarray, tuple[int, int, int, int], int]:
    """(ink mask, ink box in the mask, baseline row) of `text` drawn at `size`. See pen_x() for the
    horizontal origin."""
    ft = face.pil(size)
    l, t, r, b = ft.getbbox(text, anchor="ls")
    pad = 4
    w, h = int(r - l) + 2 * pad, int(b - t) + 2 * pad
    img = Image.new("L", (max(1, w), max(1, h)), 0)
    ImageDraw.Draw(img).text((pad - l, pad - t), text, font=ft, fill=255, anchor="ls")
    m = np.asarray(img) > 127
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return m, (0, 0, 0, 0), pad - t
    return m, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1), int(pad - t)


def line_geometry(text: str, face: assets.FontFace) -> dict:
    """Where the ink sits relative to the pen, per em: left side bearing (ink start - pen), ink top above
    the baseline, and the advance width of the whole line."""
    ft = face.pil(RENDER_SIZE)
    l, t, r, b = ft.getbbox(text, anchor="ls")
    m, (x0, y0, x1, y1), base = render_mask(text, face)
    pad = 4
    pen = pad - l
    return {"lsb": (x0 - pen) / RENDER_SIZE, "top": (base - y0) / RENDER_SIZE, "bottom": (y1 - base) / RENDER_SIZE,
            "advance": ft.getlength(text) / RENDER_SIZE, "inkWidth": (x1 - x0) / RENDER_SIZE}


def _iou_aligned(a: np.ndarray, b: np.ndarray, radius: int = 2) -> float:
    """Best IoU of two same-size masks within ±radius px of shift."""
    best = 0.0
    h, w = a.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            aa = a[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)]
            bb = b[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
            inter = np.count_nonzero(aa & bb)
            union = np.count_nonzero(aa | bb)
            if union:
                best = max(best, inter / union)
    return best


@dataclass
class Sample:
    """One line of text as it appears in the picture: its ink (straight, tight) and what it says."""
    text: str
    ink: np.ndarray       # bool mask, tight around the ink


def _size_estimate(by_height: float, oh: int, by_width: float, ow: int) -> float:
    """Combine the size read from the ink height with the one read from the ink width. Small text has
    few rows, and hinting snaps its heights to whole pixels (a 22 px caption can measure 10% short); the
    width spans many more pixels but drifts by a couple of percent between renderers and with tracking.
    Each is weighted by its expected relative error; a large disagreement (letter-spaced text) leaves
    the height alone."""
    if not (0.88 < by_width / by_height < 1.14):
        return by_height
    var_h = (1.0 / oh) ** 2
    var_w = (1.5 / ow) ** 2 + 0.02 ** 2
    return (by_height / var_h + by_width / var_w) / (1 / var_h + 1 / var_w)


def score_face(samples: list[Sample], face: assets.FontFace) -> tuple[float, float]:
    """(mean IoU, em size px) of a face against the samples."""
    import cv2

    scores, sizes = [], []
    for s in samples:
        oh, ow = s.ink.shape
        if oh < 4 or ow < 4:
            continue
        m, (x0, y0, x1, y1), _ = render_mask(s.text, face)
        rh, rw = y1 - y0, x1 - x0
        if rh < 2 or rw < 2:
            continue
        k = oh / rh
        sizes.append(_size_estimate(RENDER_SIZE * k, oh, RENDER_SIZE * ow / rw, ow))
        # Shape: the rendering stretched to the observed box (renderers round glyph advances differently,
        # so a line drawn by another program drifts by a few percent along its length). Width: how far
        # the font's natural width at this height is from the observed width, scored separately.
        scaled = cv2.resize(m[y0:y1, x0:x1].astype(np.uint8) * 255, (ow, oh), interpolation=cv2.INTER_AREA) > 127
        shape = _iou_aligned(s.ink, scaled, radius=max(1, oh // 25))
        ratio = (rw * k) / ow
        width = max(0.0, 1.0 - 2.0 * abs(float(np.log(ratio))))
        scores.append(shape * (0.75 + 0.25 * width) if abs(np.log(ratio)) < 0.04 else shape * width)
    if not scores:
        return 0.0, 0.0
    return float(np.mean(scores)), float(np.median(sizes))


def rendered_coverage(text: str, face: assets.FontFace, size: float) -> float:
    """How much ink `text` puts down at `size` px, in fully covered pixels (rendered 4x, unhinted in effect)."""
    from PIL import Image, ImageDraw

    big = max(8.0, size * 4)
    font = face.pil(big)
    x0, y0, x1, y1 = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font, anchor="ls")
    im = Image.new("L", (int(x1 - x0) + 8, int(y1 - y0) + 8), 0)
    ImageDraw.Draw(im).text((4 - x0, 4 - y0), text, font=font, fill=255, anchor="ls")
    return float(np.asarray(im, np.float64).sum()) / 255.0 * (size / big) ** 2


def pick_weight(family: str, italic: bool, size: float, observed: list[tuple[str, float]]) -> int | None:
    """The weight whose ink coverage matches the observed lines best: [(text, covered pixels)].

    Stroke weight shows directly in how much ink a line puts down; unlike shape overlap it does not
    depend on exact alignment, so it separates neighbouring weights (400 / 500) reliably."""
    best = None
    obs = sum(c for _, c in observed)
    if obs <= 0:
        return None
    for w in assets.weights(family, italic):
        face = assets.face(family, w, italic)
        if face is None or face.italic != italic:
            continue
        ren = sum(rendered_coverage(t, face, size) for t, _ in observed)
        err = abs(float(np.log(max(ren, 1e-6) / obs)))
        if best is None or err < best[0]:
            best = (err, w)
    return best[1] if best else None


def match(samples: list[Sample], script: str = "latin", *, families: list[str] | None = None,
          top: int = 3) -> list[Candidate]:
    """Best `top` candidates, best first."""
    pool = [f["family"] for f in assets.catalogue() if script in f["scripts"]]
    if script == "latin":
        # Noto's per-script families carry the same Latin letters as Noto Sans: one entry is enough.
        pool = [f for f in pool if not (f.startswith("Noto") and _names_script(f))]
    if families:
        pool = [f for f in pool if f in families]
    if not pool:
        pool = [f["family"] for f in assets.catalogue() if "latin" in f["scripts"]]
    first: list[Candidate] = []
    for fam in pool:
        for w, it in ((400, False), (700, False), (400, True)):
            face = assets.face(fam, w, it)
            if face is None or face.italic != it:
                continue
            sc, size = score_face(samples, face)
            first.append(Candidate(fam, face.weight, face.italic, sc, size))
    first.sort(key=lambda c: -c.score)
    shortlist: list[str] = []
    for c in first:
        if c.family not in shortlist:
            shortlist.append(c.family)
        if len(shortlist) >= SHORTLIST:
            break
    second: dict[tuple, Candidate] = {(c.family, c.weight, c.italic): c for c in first}
    for fam in shortlist:
        for italic in (False, True):
            for w in assets.weights(fam, italic):
                face = assets.face(fam, w, italic)
                if face is None or (face.italic != italic):
                    continue
                key = (fam, face.weight, face.italic)
                if key in second:
                    continue
                sc, size = score_face(samples, face)
                second[key] = Candidate(fam, face.weight, face.italic, sc, size)
    # Equal shapes (Noto Sans and Noto Sans Devanagari draw Devanagari identically): prefer the family
    # made for the script.
    ranked = sorted(second.values(), key=lambda c: (-round(c.score, 2), 0 if script in c.family.lower() else 1))
    out: list[Candidate] = []
    for c in ranked:  # one entry per family: the user picks a family, then adjusts weight
        if all(o.family != c.family for o in out):
            out.append(c)
        if len(out) >= top:
            break
    return out


_SCRIPT_WORDS = ("devanagari", "bengali", "gujarati", "gurmukhi", "tamil", "telugu", "kannada", "malayalam",
                 "oriya", "arabic", "naskh", "nastaliq", "hebrew")


def _names_script(family: str) -> bool:
    return any(w in family.lower() for w in _SCRIPT_WORDS)


@lru_cache(maxsize=256)
def metrics(family: str, weight: int = 400, italic: bool = False) -> dict:
    """Vertical metrics (em fractions) used to place baselines: ascent/descent as browsers and LibreOffice
    use them (typographic with USE_TYPO_METRICS, else hhea), line gap, cap and x height."""
    from fontTools.ttLib import TTFont

    face = assets.face(family, weight, italic)
    tt = TTFont(str(face.path), lazy=True)
    upm = tt["head"].unitsPerEm
    os2 = tt["OS/2"] if "OS/2" in tt else None
    hhea = tt["hhea"]
    if os2 is not None and os2.fsSelection & (1 << 7):
        asc, desc, gap = os2.sTypoAscender, -os2.sTypoDescender, os2.sTypoLineGap
    else:
        asc, desc, gap = hhea.ascent, -hhea.descent, hhea.lineGap
    cap = getattr(os2, "sCapHeight", 0) if os2 is not None else 0
    xh = getattr(os2, "sxHeight", 0) if os2 is not None else 0
    return {"ascent": asc / upm, "descent": desc / upm, "lineGap": max(0, gap) / upm,
            "capHeight": (cap or 0.7 * upm) / upm, "xHeight": (xh or 0.5 * upm) / upm}
