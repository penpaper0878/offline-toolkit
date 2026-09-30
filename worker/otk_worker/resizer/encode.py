"""Encoders for JPEG, PNG and WEBP, plus harmless padding to reach a minimum size.

Every encode is deterministic for the same settings, so the size search can
cache byte counts and re-encode the winner at the end.
"""

from __future__ import annotations

import io
import struct
import threading
import zlib
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image, ImageFile, features
from PIL.PngImagePlugin import PngInfo

FORMATS = ("jpeg", "png", "webp")
EXTENSIONS = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}
PIL_FORMAT = {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
_MAXBLOCK_LOCK = threading.Lock()
LOSSLESS_EFFORT = 80
PADDING_TEXT = b"Padding added by Offline Toolkit to reach the requested minimum file size. Pixels are unchanged. "


@dataclass(frozen=True)
class Meta:
    exif: bytes | None = None
    icc: bytes | None = None
    xmp: bytes | None = None
    comment: bytes | None = None


@dataclass(frozen=True)
class EncodeSettings:
    fmt: str
    dpi: tuple[float, float]
    quality: int = 90
    subsampling: str | None = "4:2:0"   # JPEG only; None for greyscale
    progressive: bool = True            # JPEG only
    optimize: bool = True               # JPEG Huffman optimisation / PNG max compression
    lossless: bool = False              # WEBP only
    method: int = 6                     # WEBP effort 0-6
    palette: str | None = None          # PNG: None, "exact" (lossless) or "quantize"
    colors: int = 256                   # PNG quantize colours
    meta: Meta = field(default_factory=Meta)

    def key(self) -> tuple:
        return (self.fmt, self.quality, self.subsampling, self.progressive, self.optimize,
                self.lossless, self.method, self.palette, self.colors)

    def describe(self) -> dict:
        d: dict = {"format": self.fmt}
        if self.fmt == "jpeg":
            d.update(quality=self.quality, subsampling=self.subsampling, progressive=self.progressive,
                     optimizedHuffman=self.optimize)
        elif self.fmt == "webp":
            d.update(lossless=self.lossless, quality=None if self.lossless else self.quality, method=self.method)
        else:
            d.update(palette=self.palette, colors=self.colors if self.palette else None)
        return d

    def with_(self, **kw) -> "EncodeSettings":
        return replace(self, **kw)


def exact_palette(img: Image.Image) -> Image.Image | None:
    """Lossless palette version when the image has at most 256 distinct colours."""
    if img.mode not in ("RGB", "RGBA", "L", "LA"):
        return None
    rgba = np.asarray(img.convert("RGBA"))
    flat = rgba.reshape(-1, 4)
    view = flat.view(np.dtype((np.void, 4))).ravel()
    uniq, inverse = np.unique(view, return_inverse=True)
    if len(uniq) > 256:
        return None
    colours = uniq.view(np.uint8).reshape(-1, 4)
    pal = Image.fromarray(inverse.reshape(img.height, img.width).astype(np.uint8), "P")
    palette = colours[:, :3].reshape(-1).tolist()
    pal.putpalette(palette + [0] * (768 - len(palette)))
    alphas = colours[:, 3]
    if (alphas < 255).any():
        pal.info["transparency"] = bytes(alphas.tolist())
    return pal


def quantize(img: Image.Image, colors: int) -> Image.Image:
    has_alpha = img.mode in ("RGBA", "LA")
    src = img.convert("RGBA" if has_alpha else "RGB")
    if features.check_feature("libimagequant"):
        method = Image.Quantize.LIBIMAGEQUANT
    else:
        method = Image.Quantize.FASTOCTREE if has_alpha else Image.Quantize.MEDIANCUT
    return src.quantize(colors=colors, method=method, dither=Image.Dither.FLOYDSTEINBERG)


def encode(img: Image.Image, s: EncodeSettings) -> bytes:
    buf = io.BytesIO()
    m = s.meta
    if s.fmt == "jpeg":
        if img.mode not in ("RGB", "L"):
            raise ValueError(f"JPEG needs RGB or L, got {img.mode}")
        kw: dict = dict(quality=s.quality, optimize=s.optimize, progressive=s.progressive,
                        dpi=(round(s.dpi[0]), round(s.dpi[1])))
        if img.mode == "RGB" and s.subsampling:
            kw["subsampling"] = s.subsampling
        if m.exif:
            kw["exif"] = m.exif
        if m.icc:
            kw["icc_profile"] = m.icc
        if m.xmp:
            kw["xmp"] = m.xmp
        if m.comment:
            kw["comment"] = m.comment
        try:
            img.save(buf, "JPEG", **kw)
        except OSError:
            # Pillow sizes the optimised/progressive output buffer at 1-2 bytes per
            # pixel; near-random images at high quality need more. Retry once with
            # a buffer big enough for any JPEG of this size.
            buf = io.BytesIO()
            with _MAXBLOCK_LOCK:
                saved = ImageFile.MAXBLOCK
                ImageFile.MAXBLOCK = max(saved, 4 * img.width * img.height + (1 << 20))
                try:
                    img.save(buf, "JPEG", **kw)
                finally:
                    ImageFile.MAXBLOCK = saved
    elif s.fmt == "png":
        out = img
        if s.palette == "exact":
            out = exact_palette(img) or img
        elif s.palette == "quantize":
            out = quantize(img, s.colors)
        info = PngInfo()
        if m.xmp:
            info.add_itxt("XML:com.adobe.xmp", m.xmp.decode("utf-8", "replace"))
        if m.comment:
            info.add_text("Comment", m.comment.decode("utf-8", "replace"))
        kw = dict(optimize=s.optimize, dpi=s.dpi, pnginfo=info)
        if m.exif:
            kw["exif"] = m.exif
        if m.icc:
            kw["icc_profile"] = m.icc
        if out.mode == "P" and "transparency" in out.info:
            kw["transparency"] = out.info["transparency"]
        out.save(buf, "PNG", **kw)
    elif s.fmt == "webp":
        src = img if img.mode in ("RGB", "RGBA") else img.convert("RGBA" if img.mode == "LA" else "RGB")
        # In lossless mode libwebp reads `quality` as compression effort; 80 is
        # within a percent or two of 100 and many times faster.
        kw = dict(quality=LOSSLESS_EFFORT if s.lossless else s.quality, method=s.method, lossless=s.lossless)
        if m.exif:
            kw["exif"] = m.exif
        if m.icc:
            kw["icc_profile"] = m.icc
        if m.xmp:
            kw["xmp"] = m.xmp
        src.save(buf, "WEBP", **kw)
    else:
        raise ValueError(f"unknown format {s.fmt!r}")
    return buf.getvalue()


# ---------------------------------------------------------------- padding
def _jpeg_pad(data: bytes, extra: int) -> bytes:
    """Insert COM segments after the APPn segments (JFIF stays first)."""
    if extra < 5:
        extra = 5
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF and 0xE0 <= data[pos + 1] <= 0xEF:
        pos += 2 + struct.unpack(">H", data[pos + 2:pos + 4])[0]
    segments = bytearray()
    remaining = extra
    while remaining > 0:
        seg_total = min(remaining, 65535 + 2)
        if 0 < remaining - seg_total < 5:   # keep the last segment big enough to exist
            seg_total = remaining - 5
        payload = seg_total - 4
        body = (PADDING_TEXT * (payload // len(PADDING_TEXT) + 1))[:payload]
        segments += b"\xff\xfe" + struct.pack(">H", payload + 2) + body
        remaining -= seg_total
    return data[:pos] + bytes(segments) + data[pos:]


def _png_pad(data: bytes, extra: int) -> bytes:
    """Insert a tEXt chunk just before IEND."""
    key = b"Comment\x00"
    payload_len = max(1, extra - 12 - len(key))
    text = key + (PADDING_TEXT * (payload_len // len(PADDING_TEXT) + 1))[:payload_len]
    chunk = struct.pack(">I", len(text)) + b"tEXt" + text + struct.pack(">I", zlib.crc32(b"tEXt" + text) & 0xFFFFFFFF)
    iend = data.rfind(b"IEND") - 4
    return data[:iend] + chunk + data[iend:]


def _webp_pad(data: bytes, extra: int) -> bytes:
    """Append an unknown chunk (allowed in the extended VP8X format) and fix the RIFF size."""
    if data[12:16] != b"VP8X":
        raise ValueError("WEBP padding needs the extended format")
    payload = max(2, extra - 8)
    payload += payload % 2
    chunk = b"OTKP" + struct.pack("<I", payload) + (PADDING_TEXT * (payload // len(PADDING_TEXT) + 1))[:payload]
    out = bytearray(data + chunk)
    out[4:8] = struct.pack("<I", len(out) - 8)
    return bytes(out)


def pad(data: bytes, fmt: str, target_bytes: int) -> bytes:
    """Grow `data` to at least `target_bytes` without touching the image data."""
    extra = target_bytes - len(data)
    if extra <= 0:
        return data
    fn = {"jpeg": _jpeg_pad, "png": _png_pad, "webp": _webp_pad}[fmt]
    out = fn(data, extra)
    # Chunk overheads may leave us a few bytes short; top up once.
    if len(out) < target_bytes:
        out = fn(data, extra + (target_bytes - len(out)))
    return out
