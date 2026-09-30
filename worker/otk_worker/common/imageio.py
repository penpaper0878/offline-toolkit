"""Loading images for editing: EXIF orientation, HEIC, colour management, odd modes.

Every conversion that changes pixel values (colour profile to sRGB, 16-bit to
8-bit, CMYK to RGB, multi-page to first page) is reported as a warning, never
applied silently.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from ..errors import InputError, UnsupportedFormat

MAX_PIXELS = 300_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

INPUT_EXTENSIONS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG",
    ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP", ".dib": "BMP",
    ".tif": "TIFF", ".tiff": "TIFF",
    ".heic": "HEIF", ".heif": "HEIF", ".hif": "HEIF",
}

try:  # HEIC/HEIF decoding (decode-only build, see docs/ENGINES.md)
    import pi_heif

    pi_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the environment
    HEIF_AVAILABLE = False

_SRGB = ImageCms.createProfile("sRGB")
SRGB_ICC = ImageCms.ImageCmsProfile(_SRGB).tobytes()


@dataclass
class Loaded:
    image: Image.Image                 # oriented, sRGB, mode L / LA / RGB / RGBA
    path: str
    source_format: str
    file_size: int
    original_size: tuple[int, int]     # as stored, before orientation
    orientation: int                   # EXIF orientation that was applied (1 = none)
    dpi: tuple[float, float] | None
    exif: Image.Exif | None
    icc: bytes | None                  # original profile bytes
    icc_name: str | None
    colour_converted: bool             # pixels were converted to sRGB
    xmp: bytes | None
    comment: bytes | None
    has_iptc: bool
    frames: int
    warnings: list[str] = field(default_factory=list)

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    @property
    def has_alpha(self) -> bool:
        return self.image.mode in ("LA", "RGBA")

    def info_dict(self) -> dict:
        return {
            "path": self.path,
            "format": self.source_format,
            "fileSize": self.file_size,
            "width": self.image.width,
            "height": self.image.height,
            "originalWidth": self.original_size[0],
            "originalHeight": self.original_size[1],
            "orientation": self.orientation,
            "dpi": list(self.dpi) if self.dpi else None,
            "mode": self.image.mode,
            "hasAlpha": self.has_alpha,
            "iccName": self.icc_name,
            "colourConverted": self.colour_converted,
            "hasExif": bool(self.exif),
            "hasXmp": bool(self.xmp),
            "hasIptc": self.has_iptc,
            "frames": self.frames,
            "warnings": list(self.warnings),
        }


def _profile_name(icc: bytes) -> str | None:
    try:
        return ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc))).strip() or None
    except Exception:
        return None


def _is_srgb(name: str | None) -> bool:
    return bool(name) and "srgb" in name.lower().replace(" ", "").replace("-", "")


def _to_8bit(img: Image.Image, warnings: list[str]) -> Image.Image:
    """16-bit and float greyscale to 8-bit, scaling instead of clipping."""
    arr = np.asarray(img)
    peak = float(arr.max(initial=0))
    if img.mode.startswith("I;16") or (img.mode == "I" and peak > 255):
        top = 65535.0 if img.mode.startswith("I;16") or peak <= 65535 else peak
        arr = np.clip(arr.astype(np.float64) / top * 255.0 + 0.5, 0, 255).astype(np.uint8)
        warnings.append("16-bit image reduced to 8 bits per channel (outputs are 8-bit).")
    elif img.mode == "F":
        lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        scale = 255.0 / (hi - lo) if hi > lo else 0.0
        arr = np.clip((arr - lo) * scale + 0.5, 0, 255).astype(np.uint8)
        warnings.append("Floating-point image scaled to 8 bits per channel.")
    else:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "L")


def _normalise_mode(img: Image.Image, warnings: list[str]) -> Image.Image:
    mode = img.mode
    if mode in ("L", "LA", "RGB", "RGBA"):
        return img
    if mode == "1":
        return img.convert("L")
    if mode in ("P", "PA"):
        has_alpha = mode == "PA" or "transparency" in img.info
        return img.convert("RGBA" if has_alpha else "RGB")
    if mode in ("I", "F") or mode.startswith("I;16"):
        return _to_8bit(img, warnings)
    if mode == "La":
        return img.convert("LA")
    if mode == "RGBa":
        return img.convert("RGBA")
    if mode == "RGBX":
        return img.convert("RGB")
    try:
        converted = img.convert("RGBA" if "A" in mode else "RGB")
    except Exception as exc:  # pragma: no cover - exotic modes
        raise UnsupportedFormat(f"Image mode {mode} is not supported.") from exc
    warnings.append(f"Image mode {mode} converted to {converted.mode}.")
    return converted


def _to_srgb(img: Image.Image, icc: bytes | None, warnings: list[str]) -> tuple[Image.Image, bool]:
    """Convert to sRGB when the image carries a non-sRGB profile (or is CMYK)."""
    name = _profile_name(icc) if icc else None
    if img.mode == "CMYK":
        if icc:
            try:
                src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                out = ImageCms.profileToProfile(img, src, _SRGB, outputMode="RGB",
                                                renderingIntent=ImageCms.Intent.PERCEPTUAL)
                warnings.append(f"CMYK image converted to sRGB using its profile ({name or 'embedded'}).")
                return out, True
            except Exception:
                pass
        warnings.append("CMYK image without a usable colour profile: converted to RGB, colours are approximate.")
        return img.convert("RGB"), True
    if not icc or _is_srgb(name) or img.mode not in ("RGB", "RGBA", "L", "LA"):
        return img, False
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        if img.mode in ("L", "LA"):
            return img, False  # grey profiles: keep grey values (gamma differences are negligible here)
        alpha = img.getchannel("A") if img.mode == "RGBA" else None
        rgb = img.convert("RGB")
        out = ImageCms.profileToProfile(rgb, src, _SRGB, outputMode="RGB",
                                        renderingIntent=ImageCms.Intent.PERCEPTUAL)
        if alpha is not None:
            out.putalpha(alpha)
        warnings.append(f"Colours converted from {name or 'the embedded profile'} to sRGB.")
        return out, True
    except Exception:
        warnings.append(f"Could not read the colour profile ({name or 'unknown'}); colours kept as they are.")
        return img, False


def open_image(path: str | os.PathLike, draft_to: int | None = None) -> Loaded:
    """Open, orient and colour-normalise an image.

    draft_to: when set, JPEGs are decoded at reduced scale (for previews only).
    """
    p = Path(path)
    if not p.is_file():
        raise InputError(f"File not found: {p.name}")
    ext = p.suffix.lower()
    if ext in (".heic", ".heif", ".hif") and not HEIF_AVAILABLE:
        raise UnsupportedFormat("HEIC support is not installed.")
    warnings: list[str] = []
    try:
        img = Image.open(p)
    except UnidentifiedImageError as exc:
        raise UnsupportedFormat(f"{p.name} is not an image this app can read (JPG, PNG, WEBP, BMP, TIFF, HEIC).") from exc
    except Image.DecompressionBombError as exc:
        raise InputError(f"{p.name} is larger than {MAX_PIXELS // 1_000_000} megapixels.") from exc
    except OSError as exc:
        raise InputError(f"{p.name} is damaged or incomplete: {exc}") from exc
    fmt = (img.format or INPUT_EXTENSIONS.get(ext, "")).upper()
    if fmt == "MPO":
        fmt = "JPEG"
    frames = getattr(img, "n_frames", 1) or 1
    if frames > 1:
        warnings.append(f"The file has {frames} pages/frames; only the first is used.")
    info = dict(img.info)
    icc = info.get("icc_profile")
    xmp = info.get("xmp") or info.get("XML:com.adobe.xmp")
    if isinstance(xmp, str):
        xmp = xmp.encode("utf-8")
    comment = info.get("comment")
    if isinstance(comment, str):
        comment = comment.encode("utf-8")
    has_iptc = fmt == "JPEG" and any(name == "APP13" for name, _ in getattr(img, "applist", []) or [])
    dpi = info.get("dpi")
    dpi = (float(dpi[0]), float(dpi[1])) if dpi and dpi[0] and dpi[1] else None
    exif = img.getexif()
    orientation = int(exif.get(0x0112, 1) or 1)
    original_size = img.size
    if draft_to and fmt == "JPEG":
        img.draft("RGB", (draft_to, draft_to))
    try:
        img.load()
    except OSError as exc:
        raise InputError(f"{p.name} is damaged or incomplete: {exc}") from exc
    try:
        oriented = ImageOps.exif_transpose(img)
    except Exception:
        oriented = img
        if orientation != 1:
            warnings.append("Could not apply the EXIF orientation; the image is shown as stored.")
            orientation = 1
    if oriented is None:  # pragma: no cover - Pillow returns None only with in_place=True
        oriented = img
    converted_img, converted = _to_srgb(oriented, icc, warnings)
    final = _normalise_mode(converted_img, warnings)
    return Loaded(
        image=final, path=str(p), source_format=fmt, file_size=p.stat().st_size,
        original_size=original_size, orientation=orientation if orientation in range(1, 9) else 1,
        dpi=dpi, exif=exif if len(exif) else None, icc=icc, icc_name=_profile_name(icc) if icc else None,
        colour_converted=converted, xmp=xmp, comment=comment, has_iptc=has_iptc,
        frames=frames, warnings=warnings,
    )


def save_preview(loaded: Loaded, out_path: str | os.PathLike, max_side: int = 2048) -> dict:
    """Downscaled copy for the UI (PNG when transparent, JPEG otherwise)."""
    img = loaded.image
    scale = min(1.0, max_side / max(img.size))
    if scale < 1.0:
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if loaded.has_alpha:
        out = out.with_suffix(".png")
        img.save(out, "PNG", compress_level=1)
    else:
        out = out.with_suffix(".jpg")
        img.convert("RGB").save(out, "JPEG", quality=90)
    return {"path": str(out), "width": img.width, "height": img.height, "scale": scale}
