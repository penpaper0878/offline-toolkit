"""Hit a file-size range at fixed pixel dimensions.

The pixel size is never changed here. The search only varies encoder
settings (quality, chroma subsampling, progressive/baseline, Huffman
optimisation, WEBP lossless, PNG palette), picks the best-looking candidate
inside [min, max] by SSIM, and reports honestly when the range cannot be met:

- above_max: even the smallest encoding is too big. Suggestions list the
  smallest size possible, the largest dimensions that would fit, and a format
  that would fit. Nothing is resized automatically.
- below_min: even the best quality is too small. Optional padding adds a
  comment/text chunk (pixels untouched) to reach the minimum.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Callable

from PIL import Image

from ..common import ssim as ssim_mod
from ..errors import Cancelled
from .encode import EncodeSettings, encode, exact_palette, pad

REFERENCE_QUALITY = 75           # quality used when suggesting dimensions/formats
BIG_IMAGE = 4_000_000            # pixels; above this the search tries fewer variants
PAD_MARGIN = 64                  # bytes above the minimum when padding


@dataclass
class Target:
    min_bytes: int | None = None
    max_bytes: int | None = None

    @property
    def active(self) -> bool:
        return self.min_bytes is not None or self.max_bytes is not None

    def contains(self, n: int) -> bool:
        return (self.min_bytes is None or n >= self.min_bytes) and (self.max_bytes is None or n <= self.max_bytes)


@dataclass
class Options:
    allow_padding: bool = False
    allow_quantize: bool = False
    subsampling: str = "auto"       # auto | 4:4:4 | 4:2:0
    webp_lossless: str = "auto"     # auto | never
    quality: int = 90               # used when there is no target (or no maximum)


@dataclass
class Outcome:
    status: str                     # ok | ok_padded | below_min | above_max | no_target
    data: bytes
    settings: EncodeSettings
    padded_bytes: int = 0
    ssim: float | None = None
    attempts: int = 0
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)


class _Encoder:
    """Caches byte counts per settings; checks for cancellation between encodes."""

    def __init__(self, img: Image.Image, check: Callable[[], None]):
        self.img = img
        self.check = check
        self.sizes: dict[tuple, int] = {}
        self.attempts = 0

    def size(self, s: EncodeSettings) -> int:
        k = s.key()
        if k not in self.sizes:
            self.check()
            self.sizes[k] = len(encode(self.img, s))
            self.attempts += 1
        return self.sizes[k]

    def data(self, s: EncodeSettings) -> bytes:
        self.check()
        return encode(self.img, s)


def _max_quality_under(enc: _Encoder, base: EncodeSettings, hi: int, qmin: int, qmax: int) -> int | None:
    """Highest quality whose size is <= hi (sizes are almost, not strictly, monotonic)."""
    if enc.size(base.with_(quality=qmin)) > hi:
        return None
    if enc.size(base.with_(quality=qmax)) <= hi:
        return qmax
    lo, top = qmin, qmax
    while top - lo > 1:
        mid = (lo + top) // 2
        if enc.size(base.with_(quality=mid)) <= hi:
            lo = mid
        else:
            top = mid
    best = lo
    for q in range(lo + 1, min(lo + 3, qmax) + 1):   # absorb small non-monotonic bumps
        if enc.size(base.with_(quality=q)) <= hi:
            best = q
    return best


def _min_quality_over(enc: _Encoder, base: EncodeSettings, lo_bytes: int, qmin: int, qmax: int) -> int | None:
    """Lowest quality >= qmin whose size is >= lo_bytes."""
    if enc.size(base.with_(quality=qmin)) >= lo_bytes:
        return qmin
    if enc.size(base.with_(quality=qmax)) < lo_bytes:
        return None
    lo, top = qmin, qmax
    while top - lo > 1:
        mid = (lo + top) // 2
        if enc.size(base.with_(quality=mid)) >= lo_bytes:
            top = mid
        else:
            lo = mid
    return top


def _jpeg_configs(img: Image.Image, opts: Options, base: EncodeSettings) -> list[EncodeSettings]:
    if img.mode == "L":
        subs = [None]
    elif opts.subsampling in ("4:4:4", "4:2:0"):
        subs = [opts.subsampling]
    else:
        subs = ["4:4:4", "4:2:0"]
    progs = [True] if img.width * img.height > BIG_IMAGE else [True, False]
    return [base.with_(subsampling=s, progressive=p) for s in subs for p in progs]


def _score(img: Image.Image, data: bytes) -> float:
    with Image.open(io.BytesIO(data)) as dec:
        dec.load()
        ref = img
        if dec.mode == "P":
            dec = dec.convert("RGBA" if "transparency" in dec.info else "RGB")
        if dec.mode != ref.mode:
            dec = dec.convert(ref.mode) if ref.mode in ("RGB", "RGBA", "L", "LA") else dec
        return ssim_mod.ssim(ref, dec)


def _pick_best(enc: _Encoder, cands: list[EncodeSettings]) -> tuple[EncodeSettings, bytes, float | None]:
    best = None
    for c in cands:
        data = enc.data(c)
        score = _score(enc.img, data)
        if best is None or score > best[2] + 1e-9 or (abs(score - best[2]) <= 1e-9 and len(data) < len(best[1])):
            best = (c, data, score)
    return best


def _finish_below_min(enc: _Encoder, s: EncodeSettings, target: Target, opts: Options, fmt_label: str) -> Outcome:
    data = enc.data(s)
    if opts.allow_padding:
        goal = target.min_bytes + PAD_MARGIN
        if target.max_bytes is not None:
            goal = min(goal, target.max_bytes)
        padded = pad(data, s.fmt, max(goal, target.min_bytes))
        return Outcome("ok_padded", padded, s, padded_bytes=len(padded) - len(data), attempts=enc.attempts,
                       message=(f"Even the best quality {fmt_label} is only {len(data):,} bytes, so "
                                f"{len(padded) - len(data):,} bytes of padding were added to reach the minimum. "
                                "The pixels are unchanged."))
    return Outcome("below_min", data, s, attempts=enc.attempts,
                   message=(f"Even the best quality {fmt_label} is {len(data):,} bytes, below the minimum of "
                            f"{target.min_bytes:,} bytes. Turn on 'Pad to minimum size' to add harmless padding, "
                            "or choose larger dimensions."))


# ---------------------------------------------------------------- per format
def _search_lossy(enc: _Encoder, target: Target, opts: Options, configs: list[EncodeSettings],
                  qmin: int, qmax: int) -> tuple[list[EncodeSettings], list[EncodeSettings]]:
    """For each config: best quality under max. Returns (in_range, below_min) candidates."""
    in_range, below = [], []
    for cfg in configs:
        if target.max_bytes is None:
            q0 = max(qmin, min(qmax, opts.quality))
            q = _min_quality_over(enc, cfg, target.min_bytes, q0, qmax) if target.min_bytes else q0
            if q is None:
                below.append(cfg.with_(quality=qmax))
            else:
                in_range.append(cfg.with_(quality=q))
            continue
        q = _max_quality_under(enc, cfg, target.max_bytes, qmin, qmax)
        if q is None:
            continue
        c = cfg.with_(quality=q)
        (in_range if target.contains(enc.size(c)) else below).append(c)
    return in_range, below


def _fit_jpeg(enc: _Encoder, base: EncodeSettings, target: Target, opts: Options) -> Outcome | None:
    configs = _jpeg_configs(enc.img, opts, base)
    in_range, below = _search_lossy(enc, target, opts, configs, 1, 100)
    if not in_range and below:
        # Standard (unoptimised) Huffman tables make the file larger with identical pixels.
        unopt = [c.with_(optimize=False) for c in configs]
        in_range, below2 = _search_lossy(enc, target, opts, unopt, 1, 100)
        below += below2
    if in_range:
        s, data, score = _pick_best(enc, in_range)
        return Outcome("ok", data, s, ssim=score, attempts=enc.attempts)
    if below:
        biggest = max(below, key=enc.size)
        return _finish_below_min(enc, biggest, target, opts, "JPEG")
    return None


def _fit_webp(enc: _Encoder, base: EncodeSettings, target: Target, opts: Options) -> Outcome | None:
    cands_in, cands_below = [], []
    if opts.webp_lossless != "never":
        ll = base.with_(lossless=True)
        n = enc.size(ll)
        if target.contains(n):
            return Outcome("ok", enc.data(ll), ll, ssim=1.0, attempts=enc.attempts)
        if target.max_bytes is None or n <= target.max_bytes:
            cands_below.append(ll)
    in_range, below = _search_lossy(enc, target, opts, [base.with_(lossless=False)], 0, 100)
    cands_in += in_range
    cands_below += below
    if cands_in:
        s, data, score = _pick_best(enc, cands_in)
        return Outcome("ok", data, s, ssim=score, attempts=enc.attempts)
    if cands_below:
        return _finish_below_min(enc, max(cands_below, key=enc.size), target, opts, "WEBP")
    return None


def _fit_png(enc: _Encoder, base: EncodeSettings, target: Target, opts: Options) -> Outcome | None:
    lossless = [base.with_(palette=None)]
    if exact_palette(enc.img) is not None:
        lossless.append(base.with_(palette="exact"))
    smallest = min(lossless, key=enc.size)
    n = enc.size(smallest)
    if target.contains(n):
        return Outcome("ok", enc.data(smallest), smallest, ssim=1.0, attempts=enc.attempts)
    if target.max_bytes is None or n <= target.max_bytes:
        largest = max(lossless, key=enc.size)
        if target.contains(enc.size(largest)):
            return Outcome("ok", enc.data(largest), largest, ssim=1.0, attempts=enc.attempts)
        return _finish_below_min(enc, largest, target, opts, "PNG")
    if not opts.allow_quantize:
        return None
    q = base.with_(palette="quantize")
    if enc.size(q.with_(colors=2)) > target.max_bytes:
        return None
    lo, hi = 2, 256
    if enc.size(q.with_(colors=256)) <= target.max_bytes:
        lo = 256
    else:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if enc.size(q.with_(colors=mid)) <= target.max_bytes:
                lo = mid
            else:
                hi = mid
    chosen = q.with_(colors=lo)
    data = enc.data(chosen)
    out = Outcome("ok", data, chosen, ssim=_score(enc.img, data), attempts=enc.attempts,
                  warnings=[f"Colours reduced to {lo} (lossy) to fit the maximum size, as you allowed."])
    if not target.contains(len(data)):
        below = _finish_below_min(enc, chosen, target, opts, "PNG")
        below.warnings = out.warnings
        return below
    return out


# ---------------------------------------------------------------- suggestions
def _suggest(img: Image.Image, base: EncodeSettings, target: Target, smallest: int,
             check: Callable[[], None]) -> list[dict]:
    """Advice when the maximum cannot be met at these dimensions. Nothing is applied."""
    out: list[dict] = [{"kind": "smallest", "bytes": smallest,
                        "text": f"The smallest possible {base.fmt.upper()} at {img.width}×{img.height} px is {smallest:,} bytes."}]
    hi = target.max_bytes
    ref = base.with_(quality=REFERENCE_QUALITY, lossless=False, palette=None, optimize=True)
    if base.fmt == "png":
        ref = base.with_(palette=None)

    def size_at(scale: float) -> tuple[int, int, int]:
        check()
        w, h = max(1, round(img.width * scale)), max(1, round(img.height * scale))
        small = img.resize((w, h), Image.Resampling.LANCZOS)
        return w, h, len(encode(small, ref))

    # Bisection on the scale factor, starting from a bits-per-pixel estimate.
    lo_s, hi_s, found = 0.0, 1.0, None
    mid = min(0.95, max(1 / max(img.width, img.height), math.sqrt(hi / max(smallest, 1)) * 0.5))
    for _ in range(9):
        w, h, n = size_at(mid)
        if n <= hi:
            found, lo_s = (w, h, n), mid
        else:
            hi_s = mid
        if hi_s - lo_s < 0.01 or max(img.width, img.height) * (hi_s - lo_s) < 2:
            break
        mid = (lo_s + hi_s) / 2
    if found:
        w, h, n = found
        label = "lossless" if base.fmt == "png" else f"quality {REFERENCE_QUALITY}"
        out.append({"kind": "dimensions", "width": w, "height": h, "bytes": n,
                    "text": f"At {w}×{h} px ({label}) the file would be {n:,} bytes, inside your maximum."})
    alternatives = {"jpeg": ["webp"], "png": ["webp", "jpeg"], "webp": []}[base.fmt]
    for fmt in alternatives:
        check()
        src = img
        if fmt == "jpeg" and img.mode in ("RGBA", "LA"):
            from .render import flatten
            src, _ = flatten(img)
        s = EncodeSettings(fmt=fmt, dpi=base.dpi, quality=REFERENCE_QUALITY, meta=base.meta)
        n = len(encode(src, s))
        if n <= hi:
            note = " (transparency would be flattened)" if fmt == "jpeg" and img.mode in ("RGBA", "LA") else ""
            out.append({"kind": "format", "format": fmt, "bytes": n,
                        "text": f"{fmt.upper()} at quality {REFERENCE_QUALITY} would be {n:,} bytes at the same size{note}."})
    return out


def fit(img: Image.Image, base: EncodeSettings, target: Target, opts: Options,
        check: Callable[[], None] = lambda: None) -> Outcome:
    """Encode `img` (already at its final pixel size) to satisfy `target`."""
    enc = _Encoder(img, check)
    if not target.active:
        s = base.with_(quality=opts.quality)
        if base.fmt == "png":
            cands = [base.with_(palette=None)]
            if exact_palette(img) is not None:
                cands.append(base.with_(palette="exact"))
            s = min(cands, key=enc.size)
        elif base.fmt == "jpeg" and img.mode == "RGB" and opts.subsampling in ("4:4:4", "4:2:0"):
            s = s.with_(subsampling=opts.subsampling)
        elif base.fmt == "jpeg" and img.mode == "L":
            s = s.with_(subsampling=None)
        return Outcome("no_target", enc.data(s), s, attempts=enc.attempts + 1)
    if target.min_bytes is not None and target.max_bytes is not None and target.min_bytes > target.max_bytes:
        raise ValueError("The minimum size is larger than the maximum size.")
    fn = {"jpeg": _fit_jpeg, "png": _fit_png, "webp": _fit_webp}[base.fmt]
    outcome = fn(enc, base, target, opts)
    if outcome is not None:
        outcome.attempts = enc.attempts
        return outcome
    # above_max: nothing fits at these dimensions.
    if base.fmt == "jpeg":
        floor = min(_jpeg_configs(img, opts, base), key=lambda c: enc.size(c.with_(quality=1))).with_(quality=1)
    elif base.fmt == "webp":
        floor = base.with_(lossless=False, quality=0)
    else:
        floor = base.with_(palette="quantize", colors=2) if opts.allow_quantize else \
            min([base.with_(palette=None)] + ([base.with_(palette="exact")] if exact_palette(img) else []), key=enc.size)
    data = enc.data(floor)
    suggestions = _suggest(img, base, target, len(data), check)
    hint = "" if base.fmt != "png" or opts.allow_quantize else " PNG is lossless; allowing colour reduction may help."
    return Outcome("above_max", data, floor, attempts=enc.attempts, suggestions=suggestions,
                   message=(f"The maximum of {target.max_bytes:,} bytes cannot be reached at "
                            f"{img.width}×{img.height} px: the smallest possible file is {len(data):,} bytes."
                            f" The dimensions were not changed.{hint}"))


def check_cancel(event) -> Callable[[], None]:
    def _check() -> None:
        if event is not None and event.is_set():
            raise Cancelled()
    return _check
