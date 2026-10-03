"""Stage 2: find every line of text and read it, with word boxes and confidence.

PP-OCR (RapidOCR, ONNX) finds the lines: it is robust on coloured, textured and noisy backgrounds,
and reads Latin and Chinese well. A line is also read with Tesseract when the chosen languages include
another script (Hindi, Arabic, Tamil...) or when PP-OCR is unsure; the more confident reading wins.
Without RapidOCR the page is read by Tesseract alone.
"""

from __future__ import annotations

import logging
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

PPOCR_LANGS = {"eng", "chi_sim", "chi_tra"}


@dataclass
class Word:
    text: str
    box: tuple[float, float, float, float]
    conf: float


@dataclass
class TextLine:
    text: str
    quad: list[list[float]]                    # 4 corners, clockwise from top-left, px
    conf: float                                # 0..1
    engine: str                                # "ppocr" | "tesseract"
    words: list[Word] = field(default_factory=list)

    @property
    def box(self) -> tuple[float, float, float, float]:
        q = np.asarray(self.quad)
        return float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()), float(q[:, 1].max())

    @property
    def angle(self) -> float:
        """Degrees, counter-clockwise positive (text rising to the right)."""
        (x0, y0), (x1, y1) = self.quad[0], self.quad[1]
        return -math.degrees(math.atan2(y1 - y0, x1 - x0))

    @property
    def height(self) -> float:
        q = np.asarray(self.quad)
        return float(np.linalg.norm(q[3] - q[0]))

    def scaled(self, k: float) -> "TextLine":
        return TextLine(self.text, [[x * k, y * k] for x, y in self.quad], self.conf, self.engine,
                        [Word(w.text, tuple(v * k for v in w.box), w.conf) for w in self.words])


_engine = None


def _ppocr():
    global _engine
    if _engine is None:
        from rapidocr import RapidOCR

        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        _engine = RapidOCR(params={"Global.log_level": "critical", "Global.text_score": 0.0})
    return _engine


def ppocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401
        return True
    except Exception:
        return False


def straight_crop(arr: np.ndarray, quad, pad: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """The line cut out and turned horizontal; returns (crop, matrix mapping crop px -> image px)."""
    import cv2

    q = np.asarray(quad, dtype=np.float32)
    w = float(np.linalg.norm(q[1] - q[0]))
    h = float(np.linalg.norm(q[3] - q[0]))
    ux = (q[1] - q[0]) / max(w, 1e-6)
    uy = (q[3] - q[0]) / max(h, 1e-6)
    p = pad * h
    src = np.array([q[0] - ux * p - uy * p, q[1] + ux * p - uy * p, q[3] - ux * p + uy * p], dtype=np.float32)
    W, H = int(round(w + 2 * p)), int(round(h + 2 * p))
    dst = np.array([[0, 0], [W, 0], [0, H]], dtype=np.float32)
    m = cv2.getAffineTransform(src, dst)
    crop = cv2.warpAffine(arr, m, (max(1, W), max(1, H)), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    inv = cv2.invertAffineTransform(m)
    return crop, inv


def _tesseract_line(arr: np.ndarray, quad, langs: list[str], check: Callable[[], None]) -> tuple[str, float, list[Word]]:
    """Read one line with Tesseract (single-line mode) on a straightened, padded, 2x crop."""
    from ..converter import ocr as tocr

    crop, inv = straight_crop(arr, quad, pad=0.25)
    scale = 2.0 if crop.shape[0] < 60 else 1.0
    img = Image.fromarray(crop)
    if scale != 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.Resampling.LANCZOS)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "line.png"
        img.save(p)
        rows = tocr.run_tesseract(p, langs, 300, check, psm=7)
    words, confs = [], []
    for r in rows:
        x0, y0 = float(r["left"]) / scale, float(r["top"]) / scale
        x1, y1 = x0 + float(r["width"]) / scale, y0 + float(r["height"]) / scale
        pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]]) @ inv.T
        c = max(0.0, float(r["conf"])) / 100.0
        words.append(Word(r["text"], (float(pts[:, 0].min()), float(pts[:, 1].min()),
                                      float(pts[:, 0].max()), float(pts[:, 1].max())), c))
        confs.append(c)
    text = " ".join(w.text for w in words)
    return text, (float(np.mean(confs)) if confs else 0.0), words


def _letters(s: str) -> int:
    return sum(ch.isalnum() for ch in s)


def detect(img: Image.Image, langs: list[str], *, check: Callable[[], None] = lambda: None,
           progress: Callable[[float, str], None] = lambda f, m: None) -> list[TextLine]:
    arr = np.asarray(img.convert("RGB"))
    langs = langs or ["eng"]
    other_scripts = [lg for lg in langs if lg not in PPOCR_LANGS]
    if not ppocr_available():
        return _tesseract_page(img, langs, check)
    progress(0.0, "Finding text lines")
    # RapidOCR takes a NumPy array as OpenCV BGR (it converts only files and PIL images).
    res = _ppocr()(np.ascontiguousarray(arr[:, :, ::-1]), return_word_box=True)
    lines: list[TextLine] = []
    boxes = [] if res.boxes is None else list(res.boxes)
    words_by_line = list(res.word_results or [])
    for i, quad in enumerate(boxes):
        check()
        text = (res.txts[i] if res.txts else "") or ""
        conf = float(res.scores[i]) if res.scores is not None else 0.0
        words = []
        if i < len(words_by_line):
            for wt, wc, wq in words_by_line[i]:
                q = np.asarray(wq, dtype=np.float64)
                words.append(Word(wt, (float(q[:, 0].min()), float(q[:, 1].min()), float(q[:, 0].max()),
                                       float(q[:, 1].max())), float(wc)))
        line = TextLine(text=text, quad=np.asarray(quad, dtype=np.float64).tolist(), conf=conf, engine="ppocr",
                        words=words)
        if other_scripts or conf < 0.6:
            t_text, t_conf, t_words = _tesseract_line(arr, line.quad, langs, check)
            # Tesseract wins when it is more confident, or when PP-OCR read nothing useful.
            if t_text and (t_conf > conf or (_letters(text) == 0 and _letters(t_text) > 0)):
                line = TextLine(text=t_text, quad=line.quad, conf=t_conf, engine="tesseract", words=t_words)
        if _letters(line.text) == 0 and line.conf < 0.5:
            continue  # a stray mark, not text
        if not line.words:
            line.words = [Word(line.text, line.box, line.conf)]
        lines.append(line)
        progress((i + 1) / max(1, len(boxes)), f"Reading line {i + 1} of {len(boxes)}")
    if other_scripts:
        # PP-OCR's detector is trained on Latin and Chinese: whether it finds a Devanagari or Arabic line at
        # all depends on colours and size. Tesseract's own line finder, with the chosen languages, fills in.
        progress(1.0, "Looking for lines in other scripts")
        lines = _merge_other_scripts(lines, _tesseract_page(img, langs, check))
    return lines


def _script(text: str) -> str:
    from .fontmatch import script_of

    return script_of(text)


def _overlap(a: tuple, b: tuple) -> float:
    """Intersection over the smaller box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return w * h / max(1.0, small)


def _merge_other_scripts(lines: list[TextLine], extra: list[TextLine]) -> list[TextLine]:
    """Add Tesseract's lines that are in a non-Latin script, replacing what PP-OCR made of the same place
    when that is not a reading in that script (a symbol, a fragment, Latin letters guessed from shapes)."""
    out = list(lines)
    for t in extra:
        script = _script(t.text)
        if script == "latin" or t.conf < 0.5 or _letters(t.text) < 2:
            continue
        hits = [ln for ln in out if _overlap(ln.box, t.box) > 0.3]
        same = [ln for ln in hits if _script(ln.text) == script]
        if same:
            ux0, ux1 = min(ln.box[0] for ln in same), max(ln.box[2] for ln in same)
            spans = (t.box[2] - t.box[0]) >= 0.9 * (ux1 - ux0)
            # Keep PP-OCR's line (re-read by Tesseract) when it is one line as good as the page reading;
            # take the page reading when it joins fragments into one line, or is clearly better.
            if not spans or (len(same) == 1 and same[0].conf >= t.conf - 0.05):
                continue
        out = [ln for ln in out if ln not in hits]
        out.append(t)
    return sorted(out, key=lambda ln: (ln.box[1], ln.box[0]))


def _tesseract_page(img: Image.Image, langs: list[str], check: Callable[[], None]) -> list[TextLine]:
    """Fallback without PP-OCR: Tesseract's own page segmentation."""
    from ..converter import ocr as tocr

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "page.png"
        img.save(p)
        rows = tocr.run_tesseract(p, langs, 300, check, psm=3)
    groups: dict = {}
    for r in rows:
        key = (r["block_num"], r["par_num"], r["line_num"])
        x0, y0 = float(r["left"]), float(r["top"])
        groups.setdefault(key, []).append(Word(r["text"], (x0, y0, x0 + float(r["width"]), y0 + float(r["height"])),
                                               max(0.0, float(r["conf"])) / 100.0))
    lines = []
    for ws in groups.values():
        x0 = min(w.box[0] for w in ws)
        y0 = min(w.box[1] for w in ws)
        x1 = max(w.box[2] for w in ws)
        y1 = max(w.box[3] for w in ws)
        lines.append(TextLine(" ".join(w.text for w in ws), [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                              float(np.mean([w.conf for w in ws])), "tesseract", ws))
    return lines
