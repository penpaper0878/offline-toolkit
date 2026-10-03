"""Stage 4: everything that is not text. Shapes, lines, icons and logos, photos.

With the text already painted out, the background is what is connected to the picture's border
through smooth areas (low gradient); everything else is an element. Each element is then tested in
order:
- a line (long and thin, one colour);
- a native shape: rectangle, rounded rectangle or ellipse, filled or outlined, accepted only when the
  ideal shape covers the element's pixels almost exactly and its inside is one colour;
- a graphic (icon, logo, chart): few colours, sharp edges, which becomes vector paths;
- a photo: everything else, kept as pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Element:
    kind: str                                  # "shape" | "line" | "graphic" | "photo"
    box: tuple[int, int, int, int]             # x0, y0, x1, y1 (px)
    mask: np.ndarray                           # bool, box-sized
    shape: str | None = None                   # rect | rounded | ellipse | line
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float = 0.0
    radius: float = 0.0
    line: tuple[float, float, float, float] | None = None   # x0, y0, x1, y1 for lines
    colors: list[str] = field(default_factory=list)
    score: float = 0.0                         # how well the native shape explains the pixels
    content: np.ndarray | None = None          # inside a filled shape: pixels of other things (an icon)

    @property
    def area(self) -> int:
        return int(self.mask.sum())


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in rgb)
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def background_mask(arr: np.ndarray, *, grad_thresh: float = 9.0) -> np.ndarray:
    """Pixels that belong to the page background: smooth areas connected to the border (or very large)."""
    import cv2

    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)
    gx = cv2.Sobel(lab, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lab, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt((gx ** 2 + gy ** 2).sum(axis=2)) / 4.0
    smooth = (grad < grad_thresh).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(smooth, connectivity=4)
    H, W = smooth.shape
    keep = np.zeros(n, bool)
    areas = stats[:, cv2.CC_STAT_AREA].copy()
    areas[0] = 0
    keep[areas > 0.25 * H * W] = True
    # Smooth areas at the edge are page background when they have the page's colour; a coloured bar or
    # box that reaches the edge (a header, a footer) is an element.
    main = int(np.argmax(areas))
    main_col = np.median(lab[labels == main], axis=0)
    edge = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])).tolist())
    for i in range(1, n):
        if keep[i] or areas[i] < 64:
            continue
        col = np.median(lab[labels == i], axis=0)
        # Enclosed areas of exactly the page colour (between two frame lines, inside an outline) too.
        keep[i] = bool(np.linalg.norm(col - main_col) < (12 if i in edge else 6))
    keep[0] = False
    bg = keep[labels] & (smooth > 0)
    return bg


def _fill_ratio(mask: np.ndarray) -> float:
    return float(mask.mean()) if mask.size else 0.0


def _ideal(shape: str, w: int, h: int, radius: float = 0.0) -> np.ndarray:
    import cv2

    m = np.zeros((h, w), np.uint8)
    if shape == "rect":
        m[:] = 1
    elif shape == "ellipse":
        cv2.ellipse(m, (((w - 1) / 2, (h - 1) / 2), (float(w), float(h)), 0.0), 1, -1)
    elif shape == "rounded":
        r = int(round(max(1.0, min(radius, w / 2, h / 2))))
        cv2.rectangle(m, (r, 0), (w - 1 - r, h - 1), 1, -1)
        cv2.rectangle(m, (0, r), (w - 1, h - 1 - r), 1, -1)
        for cx, cy in ((r, r), (w - 1 - r, r), (r, h - 1 - r), (w - 1 - r, h - 1 - r)):
            cv2.circle(m, (cx, cy), r, 1, -1)
    return m.astype(bool)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    u = np.count_nonzero(a | b)
    return np.count_nonzero(a & b) / u if u else 0.0


def _fit_solid(mask: np.ndarray) -> tuple[str, float, float] | None:
    """Best native shape for a solid mask: (shape, radius, iou)."""
    h, w = mask.shape
    if w < 4 or h < 4:
        return None
    best = None
    for shape in ("rect", "ellipse"):
        s = _iou(mask, _ideal(shape, w, h))
        if best is None or s > best[2]:
            best = (shape, 0.0, s)
    # Rounded rectangle: the radius follows from the missing corner area, (4 - pi) r^2.
    missing = w * h - np.count_nonzero(mask)
    if missing > 0:
        r = float(np.sqrt(missing / (4 - np.pi)))
        if 1.5 <= r < min(w, h) / 2 - 0.5:
            s = _iou(mask, _ideal("rounded", w, h, r))
            if s > best[2]:
                best = ("rounded", r, s)
    return best


def _dominant_colors(pixels: np.ndarray, k: int = 6) -> list[tuple[str, float]]:
    """Main colours (hex, share) by k-means in Lab."""
    import cv2

    if len(pixels) == 0:
        return []
    sample = pixels if len(pixels) <= 20000 else pixels[np.random.default_rng(0).choice(len(pixels), 20000, replace=False)]
    data = sample.astype(np.float32)
    k = min(k, len(np.unique(data, axis=0)))
    if k < 1:
        return []
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(data, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k) / len(labels)
    order = np.argsort(-counts)
    return [(_hex(centers[i]), float(counts[i])) for i in order]


def _colourfulness(pixels: np.ndarray) -> tuple[int, float]:
    """(number of distinct colours after 5-bit quantisation that cover 95% of pixels, mean local variance)."""
    q = (pixels >> 3).astype(np.int32)
    keys = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    _, counts = np.unique(keys, return_counts=True)
    counts = np.sort(counts)[::-1]
    cum = np.cumsum(counts) / counts.sum()
    return int(np.searchsorted(cum, 0.95) + 1), 0.0


def classify(arr: np.ndarray, mask: np.ndarray, box, *, around: np.ndarray | None = None, _strict: bool = False) -> Element:
    """`around`: the Lab colour just outside the element (to tell a filled outline from an empty one)."""
    import cv2

    el = _classify(arr, mask, box, around)
    if el.kind in ("graphic", "photo") and around is not None and not _strict:
        # A faint halo along the edges (resampling or compression ringing) can make a plain line or
        # outline look multicoloured. Without the pixels close to the background colour, look again.
        x0, y0, x1, y1 = box
        lab = cv2.cvtColor(np.ascontiguousarray(arr[y0:y1, x0:x1]), cv2.COLOR_RGB2LAB).astype(np.float32)
        dist = np.linalg.norm(lab - around, axis=2)
        if mask.any():
            strong = mask & (dist >= 0.5 * float(np.percentile(dist[mask], 90)))
            ys, xs = np.nonzero(strong)
            if 0 < len(xs) < 0.97 * np.count_nonzero(mask):
                bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
                again = classify(arr, strong[by0:by1, bx0:bx1], (x0 + bx0, y0 + by0, x0 + bx1, y0 + by1),
                                 around=around, _strict=True)
                if again.kind in ("shape", "line") and again.content is None:
                    return again
    return el


def _classify(arr: np.ndarray, mask: np.ndarray, box, around: np.ndarray | None) -> Element:
    import cv2

    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    sub = arr[y0:y1, x0:x1]
    pixels = sub[mask]
    # Thin and long: a line (or a rule of a table, which the table stage has already taken out).
    if min(w, h) <= max(8, 0.012 * max(arr.shape[:2])) and max(w, h) >= 6 * min(w, h) and _fill_ratio(mask) > 0.8:
        col = _hex(np.median(pixels, axis=0))
        thick = float(np.count_nonzero(mask)) / max(w, h)
        if w >= h:
            yc = y0 + h / 2
            line = (float(x0), yc, float(x1), yc)
        else:
            xc = x0 + w / 2
            line = (xc, float(y0), xc, float(y1))
        return Element("line", box, mask, shape="line", stroke=col, stroke_width=round(thick, 1), line=line, score=1.0)
    # Erode away the anti-aliased rim before judging uniformity.
    core = cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    core_px = sub[core] if core.any() else pixels
    lab = cv2.cvtColor(core_px.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    med = np.median(lab, axis=0)
    spread = np.linalg.norm(lab - med, axis=1)
    off = spread > 14
    uniform = off.mean() < 0.02 if len(off) else True
    # An outline is thin, so resampling or compression shading along its edges is a large share of it;
    # it may vary more (a photo or a picture with a hole is still far more varied).
    ring_uniform = (spread > 22).mean() < 0.2 if len(spread) else True
    filled_mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    holes = _fill_holes(filled_mask) & ~filled_mask
    if uniform and holes.mean() < 0.01:
        fit = _fit_solid(filled_mask)
        if fit and fit[2] >= 0.965:
            shape, r, s = fit
            fill = np.median(core_px, axis=0)
            outer = _fill_holes(filled_mask)
            return Element("shape", box, outer, shape=shape, fill=_hex(fill), radius=round(r, 1), score=round(s, 4),
                           content=_content(sub, outer, fill))
    if ring_uniform and holes.mean() >= 0.2:
        # An outline: the element is a ring around a hole of background colour.
        outer = _fill_holes(filled_mask)
        fit = _fit_solid(outer)
        if fit and fit[2] >= 0.965:
            shape, r, s = fit
            # A ring of width t around a w x h box covers 2t(w + h) - 4t^2 pixels, an elliptic one
            # pi t ((w + h) / 2 - t).
            area, half = float(np.count_nonzero(mask)), (w + h) / 2.0
            a = area if shape != "ellipse" else area * 4.0 / np.pi
            thick = float(half - np.sqrt(max(0.0, half * half - a))) / 2.0
            el = Element("shape", box, mask, shape=shape, stroke=_hex(np.median(core_px, axis=0)),
                         stroke_width=round(thick, 1), radius=round(r, 1), score=round(s, 4))
            # Inside: see-through when it is the colour around the shape, else the shape's fill.
            inner = cv2.erode(holes.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            if around is not None and np.count_nonzero(inner) >= 20:
                ilab = cv2.cvtColor(sub[inner].reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
                imed = np.median(ilab, axis=0)
                flat = (np.linalg.norm(ilab - imed, axis=1) > 10).mean() < 0.05
                if flat and np.linalg.norm(imed - around) > 2.5:
                    el.fill = _hex(np.median(sub[inner], axis=0))
                    el.mask = outer
            return el
    # A filled shape with something on it (an icon on a button): the shape is one colour over most of
    # its area, and the rest becomes elements of their own.
    outer = _fill_holes(filled_mask)
    if w >= 12 and h >= 12 and len(lab) >= 50:
        fit = _fit_solid(outer)
        if fit and fit[2] >= 0.965:
            # Measured over the whole shape (inside included), so a ring around page colour is not a
            # filled shape with "content".
            inside = cv2.erode(outer.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            area_px = sub[inside] if inside.any() else core_px
            alab = cv2.cvtColor(area_px.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
            main = _dominant_colors(area_px, 4)[0][0]
            mlab = cv2.cvtColor(np.array([[[int(main[i:i + 2], 16) for i in (1, 3, 5)]]], np.uint8),
                                cv2.COLOR_RGB2LAB).reshape(3).astype(np.float32)
            near = np.linalg.norm(alab - mlab, axis=1) < 6
            # The main colour must also be the element's own colour, not page colour showing through.
            own = np.linalg.norm(lab - mlab, axis=1) < 6
            if near.mean() >= 0.6 and own.mean() >= 0.5:
                fill = np.median(area_px[near], axis=0)
                shape, r, s = fit
                return Element("shape", box, outer, shape=shape, fill=_hex(fill), radius=round(r, 1),
                               score=round(s, 4), content=_content(sub, outer, fill))
    ncol, _ = _colourfulness(pixels)
    colors = _dominant_colors(pixels, 6)
    top = sum(share for _, share in colors[:4])
    if ncol <= 64 or top >= 0.92:
        return Element("graphic", box, mask, colors=[c for c, share in colors if share >= 0.02])
    return Element("photo", box, mask)


def _half_contrast(strong: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Per pixel, the edge threshold of the nearest distinct part: half the contrast of its core (80th
    percentile of its distance from the background), so a faint hairline next to dark content keeps
    its own edge."""
    import cv2

    n, lab = cv2.connectedComponents(strong.astype(np.uint8), connectivity=8)
    d = dist[strong]
    lv = lab[strong]
    order = np.lexsort((d, lv))
    counts = np.bincount(lv, minlength=n)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    full = np.zeros(n, np.float32)
    has = counts > 0
    idx = (starts + np.floor(0.8 * (counts - 1)).astype(np.int64))[has]
    full[has] = d[order][idx]
    near = cv2.dilate(lab.astype(np.float32), np.ones((5, 5), np.uint8)).astype(np.int64)
    thr = np.maximum(8.0, 0.5 * full[near])
    thr[near == 0] = np.inf
    return thr


def _content(sub: np.ndarray, outer: np.ndarray, fill) -> np.ndarray | None:
    """Pixels well inside a filled shape that are not its fill colour, or None."""
    import cv2

    inner = cv2.erode(outer.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    if not inner.any():
        return None
    lab = cv2.cvtColor(sub, cv2.COLOR_RGB2LAB).astype(np.float32)
    flab = cv2.cvtColor(np.array([[fill]], np.uint8), cv2.COLOR_RGB2LAB).reshape(3).astype(np.float32)
    c = inner & (np.linalg.norm(lab - flab, axis=2) > 14)
    return c if np.count_nonzero(c) >= 20 else None


def _open2(mask: np.ndarray) -> np.ndarray:
    """Opening with a 2x2 square that does not move the mask. OpenCV anchors an even kernel off-centre
    and does not reflect it for dilation, so a plain MORPH_OPEN shifts everything by one pixel."""
    import cv2

    k = np.ones((2, 2), np.uint8)
    return cv2.dilate(cv2.erode(mask.astype(np.uint8), k, anchor=(0, 0)), k, anchor=(1, 1))


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    import cv2

    m = mask.astype(np.uint8)
    h, w = m.shape
    flood = np.pad(m, 1).copy()
    ff = np.zeros((h + 4, w + 4), np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 2)
    return (flood[1:-1, 1:-1] != 2)


def detect(arr: np.ndarray, *, exclude: list[tuple[int, int, int, int]] = (), min_area: int = 60,
           edges: np.ndarray | None = None) -> list[Element]:
    """Elements of a text-free picture. `exclude`: boxes already handled (tables). `edges`: the unsmoothed
    picture when `arr` was smoothed (faint edges, e.g. of a pale shape, are found on it; colours and shape
    tests use `arr`)."""
    import cv2

    H, W = arr.shape[:2]
    bg = background_mask(edges if edges is not None else arr)
    fg = (~bg).astype(np.uint8)
    for x0, y0, x1, y1 in exclude:
        fg[max(0, y0 - 6):y1 + 7, max(0, x0 - 6):x1 + 7] = 0   # a table's own rules and their soft edges
    fg = _open2(fg)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area or area > 0.5 * W * H:
            continue   # specks, or a picture filling the page (that stays the background layer)
        pad = 4
        X0, Y0, X1, Y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
        lab_crop = labels[Y0:Y1, X0:X1]
        coarse = lab_crop == i
        # Its enclosed holes too, but not other elements inside them (a frame within a frame).
        region = _fill_holes(coarse) & ((lab_crop == i) | (lab_crop == 0))
        # The colour around the element is its background; the element is what differs from it.
        ring = (cv2.dilate(region.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & bg[Y0:Y1, X0:X1] & ~region
        wl = lab[Y0:Y1, X0:X1]
        ref = np.median(wl[ring], axis=0) if np.count_nonzero(ring) >= 12 else np.median(
            np.concatenate([wl[0], wl[-1], wl[:, 0], wl[:, -1]]), axis=0)
        dist = np.linalg.norm(wl - ref, axis=2)
        strong = region & (dist > 10)
        if not strong.any():
            continue
        precise = region & (dist > _half_contrast(strong, dist))
        # Drop specks, but keep hairlines (an opening would erase a 1 px outline).
        cn, cl, cs, _ = cv2.connectedComponentsWithStats(precise.astype(np.uint8), connectivity=8)
        precise = (cs[:, cv2.CC_STAT_AREA] >= 6)[cl] & precise
        ys, xs = np.nonzero(precise)
        if len(xs) < min_area:
            continue
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        mask = precise[by0:by1, bx0:bx1]
        box = (int(X0 + bx0), int(Y0 + by0), int(X0 + bx1), int(Y0 + by1))
        el = classify(arr, mask, box, around=ref)
        out.append(el)
        if el.content is not None:
            # Things on the shape that are elements of their own already are not found a second time.
            own = labels[box[1]:box[3], box[0]:box[2]]
            el.content = el.content & ((own == 0) | (own == i))
            if el.content.any():
                out.extend(_inner_elements(arr, el, min_area))
        if el.kind == "photo":
            # A photo keeps its whole rectangle, background-coloured parts included.
            el.mask = region[by0:by1, bx0:bx1] | mask
        elif el.kind == "graphic":
            # Enclosed parts of another colour belong to the graphic too (a white tick inside a badge is
            # close to a cream page but not the page); enclosed page colour stays see-through.
            sub_dist = dist[by0:by1, bx0:bx1]
            holes = _fill_holes(mask) & ~mask
            el.mask = mask | (holes & (sub_dist > 4.0))
            if np.count_nonzero(el.mask) > np.count_nonzero(mask):
                sub = arr[box[1]:box[3], box[0]:box[2]]
                el.colors = [c for c, share in _dominant_colors(sub[el.mask], 6) if share >= 0.02]
    return drop_fringes(out)


def drop_fringes(found: list[Element], band: int = 5) -> list[Element]:
    """Remove thin slivers that hug the outline of a larger element: the halo that compression or resampling
    leaves along an edge (JPEG ringing), not a drawn line. A real rule or frame keeps its distance."""
    big = [e for e in found if min(e.box[2] - e.box[0], e.box[3] - e.box[1]) > 2 * band]
    out = []
    for e in found:
        x0, y0, x1, y1 = e.box
        thin = min(x1 - x0, y1 - y0) <= 4 or e.area < 40
        fringe = False
        if thin:
            for b in big:
                if b is e:
                    continue
                bx0, by0, bx1, by1 = b.box
                inside = bx0 - band <= x0 and x1 <= bx1 + band and by0 - band <= y0 and y1 <= by1 + band
                gap = min(abs(x0 - bx0), abs(x1 - bx1), abs(y0 - by0), abs(y1 - by1))
                if inside and gap <= band:
                    fringe = True
                    break
        if not fringe:
            out.append(e)
    return out


def _inner_elements(arr: np.ndarray, shape: Element, min_area: int) -> list[Element]:
    """The things drawn on a filled shape, each classified against the shape's fill."""
    import cv2

    fill = np.array([int(shape.fill[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
    around = cv2.cvtColor(fill.reshape(1, 1, 3), cv2.COLOR_RGB2LAB).reshape(3).astype(np.float32)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(shape.content.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue   # specks (compression residue around removed text), not an icon
        m = labels[y:y + h, x:x + w] == i
        box = (shape.box[0] + int(x), shape.box[1] + int(y), shape.box[0] + int(x + w), shape.box[1] + int(y + h))
        el = classify(arr, m, box, around=around)
        if el.kind == "shape" and el.content is not None:
            el.content = None   # one level of nesting is enough
        out.append(el)
    return out
