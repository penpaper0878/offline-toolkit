"""DPI and metadata for output files.

- JPEG: JFIF APP0 density (whole DPI) + EXIF X/YResolution (exact rational).
- PNG:  pHYs (whole pixels per metre); EXIF only when metadata is kept.
- WEBP: has no density field, so a small EXIF block carries X/YResolution.

"Strip metadata" removes camera, GPS, XMP, comments and profiles but always
keeps the resolution tags, because the DPI is part of what the user asked for.
"""

from __future__ import annotations

import io
import re
from fractions import Fraction

from PIL import ExifTags, Image
from PIL.TiffImagePlugin import IFDRational

from . import units

TAG_ORIENTATION = 0x0112
TAG_XRES, TAG_YRES, TAG_RES_UNIT = 0x011A, 0x011B, 0x0128
TAG_MAKERNOTE = 0x927C
TAG_PIXEL_X, TAG_PIXEL_Y = 0xA002, 0xA003
_POINTER_TAGS = {0x8769, 0x8825, 0xA005, 0x014A}  # Exif, GPS, Interop, SubIFDs
_THUMBNAIL_TAGS = {0x0201, 0x0202, 0x0103}


def rational(value: float) -> IFDRational:
    frac = Fraction(value).limit_denominator(100000)
    return IFDRational(frac.numerator, frac.denominator)


def build_exif(source: Image.Exif | None, keep: bool, dpi: tuple[float, float],
               size: tuple[int, int], warnings: list[str]) -> Image.Exif:
    """EXIF for the output: resolution always; the rest of the source only if keep=True.

    The source's thumbnail (IFD1) is never copied because it shows the old
    crop, and orientation is reset to 1 because pixels are already upright.
    """
    out = Image.Exif()
    if keep and source:
        for tag, value in source.items():
            if tag in _POINTER_TAGS or tag in _THUMBNAIL_TAGS:
                continue
            out[tag] = value
        exif_ifd = dict(source.get_ifd(ExifTags.IFD.Exif))
        if TAG_MAKERNOTE in exif_ifd:
            exif_ifd.pop(TAG_MAKERNOTE)
            warnings.append("Camera maker notes were not carried over (their internal offsets break when rewritten).")
        exif_ifd.pop(ExifTags.IFD.Interop, None)
        if exif_ifd:
            exif_ifd[TAG_PIXEL_X] = size[0]
            exif_ifd[TAG_PIXEL_Y] = size[1]
            target = out.get_ifd(ExifTags.IFD.Exif)
            target.update(exif_ifd)
        gps = dict(source.get_ifd(ExifTags.IFD.GPSInfo))
        if gps:
            out.get_ifd(ExifTags.IFD.GPSInfo).update(gps)
        if TAG_ORIENTATION in out:
            out[TAG_ORIENTATION] = 1
    out[TAG_XRES] = rational(dpi[0])
    out[TAG_YRES] = rational(dpi[1])
    out[TAG_RES_UNIT] = 2  # inches
    return out


_XMP_ORIENTATION = re.compile(rb'(tiff:Orientation\s*=\s*["\'])\d(["\'])|(<tiff:Orientation>)\d(</tiff:Orientation>)')


def clean_xmp(xmp: bytes | None) -> bytes | None:
    """Reset tiff:Orientation inside XMP so viewers don't rotate upright pixels again."""
    if not xmp:
        return None
    return _XMP_ORIENTATION.sub(lambda m: (m.group(1) or m.group(3)) + b"1" + (m.group(2) or m.group(4)), xmp)


def readback(data: bytes) -> dict:
    """What a reader sees in an encoded file: size, format and every place DPI is stored."""
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        exif = im.getexif()
        out: dict = {
            "format": im.format,
            "width": im.width,
            "height": im.height,
            "mode": im.mode,
            "bytes": len(data),
            "dpi": [float(v) for v in im.info["dpi"]] if "dpi" in im.info else None,
            "exifDpi": None,
            "jfifDensity": None,
            "pngPpm": None,
            "orientation": int(exif.get(TAG_ORIENTATION, 1) or 1),
            "hasIcc": "icc_profile" in im.info,
            "hasExif": len(exif) > 0,
        }
        if TAG_XRES in exif and TAG_YRES in exif:
            out["exifDpi"] = [float(exif[TAG_XRES]), float(exif[TAG_YRES])]
        if im.format == "JPEG" and im.info.get("jfif_unit") == 1:
            out["jfifDensity"] = list(im.info.get("jfif_density", ()))
        if im.format == "PNG" and "dpi" in im.info:
            out["pngPpm"] = [units.png_phys(float(v)) for v in im.info["dpi"]]
    return out
