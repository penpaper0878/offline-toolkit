"""Stage 3: the look of the text. Ink and colour per line, lines grouped into paragraphs, alignment and
line spacing, the closest bundled font, and exact baselines.

Ink: inside a line's (straightened) box the background is the colour of the box border; ink is what is
clearly different from it, cut at half the contrast of the stroke cores (where a pixel is half covered).
The text colour is the median of the stroke cores, so anti-aliased edges do not wash it out. The weight
comes from how much ink a line puts down compared with each weight of the matched family.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import assets, fontmatch
from .textdetect import TextLine, straight_crop


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _rgb(hex_color: str) -> np.ndarray:
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def color_distance(a: str, b: str) -> float:
    import cv2

    lab = cv2.cvtColor(np.array([[_rgb(a), _rgb(b)]], dtype=np.uint8), cv2.COLOR_RGB2LAB).astype(np.float64)
    return float(np.linalg.norm(lab[0, 0] - lab[0, 1]))


@dataclass
class LineInk:
    line: TextLine
    angle: float                              # degrees ccw applied to the layer (0 for level text)
    ink: np.ndarray                           # tight bool mask in the straightened line frame
    ink_origin: tuple[float, float]           # straight-frame position of the mask's top-left
    inv: np.ndarray                           # straight frame -> image (2x3)
    color: str
    background: str
    box: tuple[float, float, float, float]    # ink box in the image (axis-aligned)
    baseline: float = 0.0                     # straight-frame y of the baseline (set after font matching)
    x0: float = 0.0                           # straight-frame x of the ink start / end
    x1: float = 0.0

    @property
    def height(self) -> float:
        return float(self.ink.shape[0])


def _ink(crop: np.ndarray) -> tuple[np.ndarray, str, str]:
    import cv2

    b = max(1, min(crop.shape[:2]) // 12)
    border = np.concatenate([crop[:b].reshape(-1, 3), crop[-b:].reshape(-1, 3),
                             crop[:, :b].reshape(-1, 3), crop[:, -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    dist = np.linalg.norm(lab - bg_lab, axis=2)
    d8 = np.clip(dist * (255.0 / max(1.0, dist.max())), 0, 255).astype(np.uint8)
    thr, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    rough = d8 > max(thr, 255.0 * 12 / max(1.0, dist.max()))
    # Otsu leans toward the larger class (the background), which makes strokes look bolder. The ink
    # boundary is where a pixel is half covered: half the distance of the stroke cores.
    if rough.any():
        full = float(np.percentile(dist[rough], 80))
        mask = dist > max(6.0, 0.5 * full)
    else:
        mask = rough
    if mask.any():
        core = mask & (dist >= np.percentile(dist[mask], 60))
        color = np.median(crop[core if core.any() else mask], axis=0)
    else:
        color = np.array([0, 0, 0])
    return mask, _hex(color), _hex(bg)


def line_ink(arr: np.ndarray, line: TextLine, bounds: tuple[float, float, float, float] | None = None) -> LineInk | None:
    """The ink of one line. `bounds` (x0, y0, x1, y1) limits the crop, e.g. to the inside of a table cell."""
    q = np.asarray(line.quad)
    w = float(np.linalg.norm(q[1] - q[0]))
    h = float(np.linalg.norm(q[3] - q[0]))
    angle = line.angle
    # Detectors give short words a few degrees of tilt; only a long line can show a real rotation.
    if bounds is not None or abs(angle) < 2.0 or (w / max(h, 1) < 4 and abs(angle) < 8):
        angle = 0.0
        x0, y0, x1, y1 = line.box
        quad = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    else:
        quad = line.quad
    pad = 0.12
    if angle == 0.0:
        # Level text: an exact pixel crop. Resampling would blur strokes and (bicubic) overshoot colours.
        x0, y0, x1, y1 = line.box
        p = int(round(pad * (y1 - y0)))
        H, W = arr.shape[:2]
        ix0, iy0 = max(0, int(np.floor(x0)) - p), max(0, int(np.floor(y0)) - p)
        ix1, iy1 = min(W, int(np.ceil(x1)) + p), min(H, int(np.ceil(y1)) + p)
        if bounds is not None:
            ix0, iy0 = max(ix0, int(np.ceil(bounds[0]))), max(iy0, int(np.ceil(bounds[1])))
            ix1, iy1 = min(ix1, int(np.floor(bounds[2]))), min(iy1, int(np.floor(bounds[3])))
            if ix1 - ix0 < 4 or iy1 - iy0 < 4:
                return None
        crop = arr[iy0:iy1, ix0:ix1]
        inv = np.array([[1.0, 0.0, ix0], [0.0, 1.0, iy0]])
    else:
        crop, inv = straight_crop(arr, quad, pad=pad)
    if crop.size == 0:
        return None
    mask, color, bg = _ink(crop)
    ys, xs = np.nonzero(mask)
    if len(xs) < 4:
        return None
    ty0, ty1, tx0, tx1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
    tight = mask[ty0:ty1, tx0:tx1]
    pts = np.array([[tx0, ty0, 1], [tx1, ty0, 1], [tx1, ty1, 1], [tx0, ty1, 1]], dtype=np.float64) @ inv.T
    box = (float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max()))
    return LineInk(line=line, angle=angle, ink=tight, ink_origin=(float(tx0), float(ty0)), inv=inv,
                   color=color, background=bg, box=box, x0=float(tx0), x1=float(tx1))


def coverage(arr: np.ndarray, li: LineInk) -> float:
    """The line's ink in fully covered pixels: each pixel near the strokes counts by how far its colour
    lies from the background toward the text colour."""
    import cv2

    from .textdetect import straight_crop

    if li.angle == 0.0:
        ix0, iy0 = int(li.inv[0, 2]), int(li.inv[1, 2])
        ox, oy = int(li.ink_origin[0]), int(li.ink_origin[1])
        h, w = li.ink.shape
        x0, y0 = ix0 + ox - 2, iy0 + oy - 2
        crop = arr[max(0, y0):y0 + h + 4, max(0, x0):x0 + w + 4]
        m = np.zeros(crop.shape[:2], bool)
        sy, sx = max(0, y0) - y0, max(0, x0) - x0
        m[2 - sy:2 - sy + h, 2 - sx:2 - sx + w] = li.ink[:m.shape[0] - 2 + sy, :m.shape[1] - 2 + sx]
    else:
        crop, _ = straight_crop(arr, li.line.quad, pad=0.12)
        m = np.zeros(crop.shape[:2], bool)
        ox, oy = int(li.ink_origin[0]), int(li.ink_origin[1])
        h, w = li.ink.shape
        m[oy:oy + h, ox:ox + w] = li.ink[:max(0, m.shape[0] - oy), :max(0, m.shape[1] - ox)]
    if crop.size == 0 or not m.any():
        return 0.0
    near = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2LAB).astype(np.float32)
    bl = cv2.cvtColor(np.array([[_rgb(li.background)]], np.uint8), cv2.COLOR_RGB2LAB).reshape(3).astype(np.float32)
    fl = cv2.cvtColor(np.array([[_rgb(li.color)]], np.uint8), cv2.COLOR_RGB2LAB).reshape(3).astype(np.float32)
    ax = fl - bl
    den = float(ax @ ax)
    if den < 1.0:
        return 0.0
    cov = np.clip(((lab - bl) @ ax) / den, 0.0, 1.0)
    return float(cov[near].sum())


def to_image(li: LineInk, x: float, y: float) -> tuple[float, float]:
    p = np.array([x, y, 1.0]) @ li.inv.T
    return float(p[0]), float(p[1])


@dataclass
class TextBlock:
    lines: list[LineInk]
    align: str = "left"
    line_height: float = 1.2                  # baseline-to-baseline / em size
    family: str = "Noto Sans"
    weight: int = 400
    italic: bool = False
    size: float = 16.0
    color: str = "#000000"
    script: str = "latin"
    candidates: list[fontmatch.Candidate] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(li.line.text for li in self.lines)

    @property
    def angle(self) -> float:
        return self.lines[0].angle

    @property
    def box(self) -> tuple[float, float, float, float]:
        return (min(li.box[0] for li in self.lines), min(li.box[1] for li in self.lines),
                max(li.box[2] for li in self.lines), max(li.box[3] for li in self.lines))

    @property
    def conf(self) -> float:
        return float(np.mean([li.line.conf for li in self.lines]))


def _same_paragraph(a: LineInk, b: LineInk) -> bool:
    """b directly below a, same look, edges lined up."""
    if a.angle or b.angle:
        return False
    ha, hb = a.box[3] - a.box[1], b.box[3] - b.box[1]
    la, lb = a.line.height, b.line.height
    if max(la, lb) / max(1.0, min(la, lb)) > 1.3:
        return False
    if color_distance(a.color, b.color) > 18:
        return False
    gap = b.box[1] - a.box[3]
    if gap < -0.2 * min(ha, hb) or gap > 1.1 * max(la, lb):
        return False
    tol = 0.6 * max(la, lb)
    left = abs(a.box[0] - b.box[0]) < tol
    right = abs(a.box[2] - b.box[2]) < tol
    center = abs((a.box[0] + a.box[2]) / 2 - (b.box[0] + b.box[2]) / 2) < tol
    overlap = min(a.box[2], b.box[2]) - max(a.box[0], b.box[0]) > 0
    return overlap and (left or right or center)


def group(lines: list[LineInk]) -> list[list[LineInk]]:
    lines = sorted(lines, key=lambda li: (li.box[1] + li.box[3]) / 2)
    blocks: list[list[LineInk]] = []
    for li in lines:
        for blk in blocks:
            if _same_paragraph(blk[-1], li):
                blk.append(li)
                break
        else:
            blocks.append([li])
    return blocks


def _alignment(blk: TextBlock, page_w: float, containers: list[tuple[float, float, float, float]],
               guides: list[tuple[float, float, float, float]] = ()) -> str:
    lefts = np.array([li.box[0] for li in blk.lines])
    rights = np.array([li.box[2] for li in blk.lines])
    centers = (lefts + rights) / 2
    tol = 0.25 * blk.size
    if len(blk.lines) >= 2:
        spread = {"left": np.ptp(lefts), "center": np.ptp(centers), "right": np.ptp(rights)}
        if len(blk.lines) >= 3 and np.ptp(lefts) < tol and np.ptp(rights[:-1]) < tol and rights[-1] < rights[:-1].min() - tol:
            return "justify"
        return min(spread, key=spread.get)
    cx = float(centers[0])
    bx0, by0, bx1, by1 = blk.box
    for x0, y0, x1, y1 in containers:  # a single line centred in a button or box
        if x0 <= bx0 and bx1 <= x1 and y0 <= by0 and by1 <= y1 and abs(cx - (x0 + x1) / 2) < 0.04 * (x1 - x0) + 2:
            return "center"
    lh = by1 - by0
    for x0, y0, x1, y1 in guides:      # a caption centred under (or over) a rule, as on a signature line
        near = by0 - y1 < 2 * lh and y0 - by1 < 2 * lh and (by0 >= y1 - 1 or by1 <= y0 + 1)
        if near and x0 - 2 <= bx0 and bx1 <= x1 + 2 and abs(cx - (x0 + x1) / 2) < 0.04 * (x1 - x0) + 2:
            return "center"
    return "center" if abs(cx - page_w / 2) < 0.015 * page_w + 2 else "left"


def build_blocks(arr: np.ndarray, lines: list[TextLine], *, containers=(), guides=(), families: list[str] | None = None,
                 color_source: tuple[np.ndarray, float] | None = None, check=lambda: None,
                 progress=lambda f, m: None) -> list[TextBlock]:
    """Paragraphs with their typography. `color_source` (picture, factor): read colours from this
    picture instead, `arr` being it enlarged by `factor`."""
    inks = [li for li in (line_ink(arr, ln) for ln in lines) if li is not None]
    # Ink coverage per line for the weight, on the original pixels like the colour.
    src, k = color_source if color_source is not None else (arr, 1.0)
    cover: dict[int, float] = {}
    for li in inks:
        small = li if color_source is None else line_ink(src, li.line.scaled(1.0 / k))
        if small is not None:
            li.color, li.background = small.color, small.background
            cover[id(li)] = coverage(src, small)
    blocks = []
    groups = group(inks)
    for gi, members in enumerate(groups):
        check()
        progress(gi / max(1, len(groups)), f"Matching fonts ({gi + 1} of {len(groups)})")
        blk = TextBlock(lines=members)
        blk.script = fontmatch.script_of(blk.text)
        samples = _samples(blk)
        blk.candidates = fontmatch.match(samples, blk.script, families=families) if samples else []
        if blk.candidates:
            best = blk.candidates[0]
            blk.family, blk.weight, blk.italic, blk.size = best.family, best.weight, best.italic, best.size
        else:
            blk.size = float(np.median([li.height for li in members])) / 0.72
        cols = np.array([_rgb(li.color) for li in members])
        blk.color = _hex(np.median(cols, axis=0))
        blocks.append(blk)
    if not families:
        _harmonise(blocks)
    for blk in blocks:
        if blk.candidates:
            obs = [(li.line.text.strip(), cover[id(li)]) for li in blk.lines[:4] if id(li) in cover and li.line.text.strip()]
            w = fontmatch.pick_weight(blk.family, blk.italic, blk.size / k, obs) if obs else None
            if w is not None and w != blk.weight:
                blk.weight = w
                face = assets.face(blk.family, w, blk.italic)
                if face is not None:
                    blk.size = fontmatch.score_face(_samples(blk), face)[1] or blk.size
        _baselines(blk)
        if len(blk.lines) >= 2:
            ys = [to_image(li, 0, li.baseline)[1] for li in blk.lines]
            blk.line_height = float(np.median(np.diff(ys))) / blk.size
        else:
            m = fontmatch.metrics(blk.family, blk.weight, blk.italic)
            blk.line_height = round(m["ascent"] + m["descent"] + m["lineGap"], 3)
        blk.align = _alignment(blk, arr.shape[1], list(containers), list(guides))
    return blocks


def _samples(blk: TextBlock) -> list[fontmatch.Sample]:
    longest = sorted(blk.lines, key=lambda li: -len(li.line.text))[:3]
    return [fontmatch.Sample(li.line.text.strip(), li.ink) for li in longest if li.line.text.strip()]


SHORT_TEXT = 14          # characters; below this a font match rests on few letters
COHERENCE_MARGIN = 0.03


def _harmonise(blocks: list[TextBlock]) -> None:
    """Designs use few typefaces. A short label whose best match is a family found nowhere else on the
    page, while a family that the longer text uses fits it almost as well, takes that family."""
    used: dict[str, int] = {}
    for b in blocks:
        n = len(b.text.replace("\n", ""))
        if n >= 16 and b.candidates and b.candidates[0].score >= 0.5:
            used[b.family] = used.get(b.family, 0) + n
    for b in blocks:
        if not b.candidates or b.family in used or len(b.text) > SHORT_TEXT:
            continue
        samples = _samples(b)
        best = None
        for fam in sorted(used, key=lambda f: -used[f]):
            if b.script not in (assets.family(fam) or {}).get("scripts", []):
                continue
            for w in assets.weights(fam, b.italic):
                face = assets.face(fam, w, b.italic)
                if face is None or face.italic != b.italic:
                    continue
                sc, size = fontmatch.score_face(samples, face)
                if best is None or sc > best.score:
                    best = fontmatch.Candidate(fam, w, b.italic, sc, size)
        if best is not None and best.score >= b.candidates[0].score - COHERENCE_MARGIN:
            b.family, b.weight, b.size = best.family, best.weight, best.size
            b.candidates = [best] + [c for c in b.candidates if c.family != best.family][:3]


def _baselines(blk: TextBlock) -> None:
    """Each line's baseline in its straight frame: the matched font, drawn at the matched size, lined up
    with the observed ink by its top edge."""
    face = assets.face(blk.family, blk.weight, blk.italic)
    for li in blk.lines:
        if face is None or not li.line.text.strip():
            li.baseline = li.ink_origin[1] + li.ink.shape[0]
            continue
        m, (x0, y0, x1, y1), base = fontmatch.render_mask(li.line.text.strip(), face)
        k = li.ink.shape[0] / max(1, (y1 - y0))
        li.baseline = li.ink_origin[1] + (base - y0) * k
