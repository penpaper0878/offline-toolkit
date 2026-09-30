"""One image and batch processing for the resizer.

Every output is decoded again before it is written and checked for its exact
pixel size, so a size or dimension mistake can never be saved silently.
"""

from __future__ import annotations

import os
import threading
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from ..common import imageio, metadata, units
from ..common.paths import render_name, unique_path, write_atomic
from ..errors import Cancelled, ToolkitError
from . import compress, geometry, render
from .encode import EXTENSIONS, EncodeSettings, Meta
from .settings import validate

WRITABLE = {"ok", "ok_padded", "no_target"}
_cache_lock = threading.Lock()
_cache: "OrderedDict[tuple, imageio.Loaded]" = OrderedDict()
CACHE_ITEMS = 2


def load_cached(path: str) -> imageio.Loaded:
    """Keep the last two full-resolution images so repeated previews are fast."""
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    loaded = imageio.open_image(path)
    with _cache_lock:
        _cache[key] = loaded
        while len(_cache) > CACHE_ITEMS:
            _cache.popitem(last=False)
    return loaded


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def size_target(settings: dict, base: int = 1024) -> compress.Target:
    rng = settings.get("sizeRange")
    if not rng:
        return compress.Target()
    unit = rng["unit"]
    lo = units.bytes_from(rng["min"], unit, base) if rng.get("min") not in (None, 0) else None
    hi = units.bytes_from(rng["max"], unit, base) if rng.get("max") is not None else None
    return compress.Target(lo, hi)


def _stored_dpi(fmt: str, dpi: tuple[float, float]) -> dict:
    if fmt == "jpeg":
        return {"jfif": [units.jfif_density(dpi[0]), units.jfif_density(dpi[1])], "exif": list(dpi)}
    if fmt == "png":
        ppm = [units.png_phys(dpi[0]), units.png_phys(dpi[1])]
        return {"pngPpm": ppm, "pngDpi": [units.png_phys_dpi(p) for p in ppm]}
    return {"exif": list(dpi)}


def process(loaded: imageio.Loaded, crop: dict | None, settings: dict, *, size_base: int = 1024,
            check: Callable[[], None] = lambda: None) -> tuple[dict, bytes]:
    """Resize + encode one image. Returns (result, encoded bytes)."""
    s = settings
    size = units.resolve_size(s["width"], s["height"], s["unit"], s["dpi"], fit_dpi=s["fitDpi"])
    target_px = size.px
    warnings = list(loaded.warnings)
    plan = geometry.plan_fit(loaded.size, target_px, s["fit"], crop)
    warnings += geometry.plan_warnings(plan)
    check()
    img = render.render(loaded.image, plan, s["padColor"])
    fmt = s["format"]
    if fmt == "jpeg":
        img, flattened = render.flatten(img, s["padColor"])
        if flattened:
            warnings.append(f"JPEG has no transparency: transparent areas were filled with {s['padColor']}.")
    keep = not s["stripMetadata"]
    exif = metadata.build_exif(loaded.exif, keep, size.dpi, target_px, warnings).tobytes()
    icc = None
    if keep:
        icc = imageio.SRGB_ICC if loaded.colour_converted else loaded.icc
        if loaded.has_iptc:
            warnings.append("IPTC data (captions/keywords in APP13) is not carried over.")
    meta = Meta(exif=exif, icc=icc, xmp=metadata.clean_xmp(loaded.xmp) if keep else None,
                comment=loaded.comment if keep else None)
    pixels = target_px[0] * target_px[1]
    base = EncodeSettings(fmt=fmt, dpi=size.dpi, quality=s["quality"], meta=meta,
                          method=6 if pixels <= compress.BIG_IMAGE else 4)
    target = size_target(s, size_base)
    opts = compress.Options(allow_padding=s["allowPadding"], allow_quantize=s["allowQuantize"],
                            subsampling=s["subsampling"], webp_lossless=s["webpLossless"], quality=s["quality"])
    outcome = compress.fit(img, base, target, opts, check)
    warnings += outcome.warnings

    # Independent check of what was actually produced.
    rb = metadata.readback(outcome.data)
    if (rb["width"], rb["height"]) != target_px:
        raise ToolkitError(f"Internal check failed: produced {rb['width']}×{rb['height']} px instead of "
                           f"{target_px[0]}×{target_px[1]} px. Nothing was saved.", code="verify_failed")
    stored = _stored_dpi(fmt, size.dpi)
    if s["fitDpi"] and fmt == "jpeg" and any(abs(stored["jfif"][i] - size.dpi[i]) > 1e-6 for i in (0, 1)):
        warnings.append("JPEG's JFIF header only stores whole DPI; the exact value is in EXIF.")
    result = {
        "status": outcome.status,
        "message": outcome.message,
        "source": loaded.info_dict(),
        "size": size.to_dict(),
        "fit": plan.to_dict(),
        "encoder": outcome.settings.describe(),
        "paddingBytes": outcome.padded_bytes,
        "ssim": outcome.ssim,
        "attempts": outcome.attempts,
        "range": {"min": target.min_bytes, "max": target.max_bytes, "base": size_base},
        "output": {"format": fmt, "bytes": len(outcome.data), "width": rb["width"], "height": rb["height"],
                   "dpiStored": stored, "readback": rb},
        "warnings": warnings,
        "suggestions": outcome.suggestions,
    }
    return result, outcome.data


def _output_path(out_dir: Path, settings: dict, source: str, result: dict, index: int) -> Path:
    w, h = result["output"]["width"], result["output"]["height"]
    dpi = settings["dpi"]
    stem = render_name(settings["naming"], name=Path(source).stem, w=w, h=h,
                       dpi=int(dpi) if float(dpi).is_integer() else dpi, n=index + 1)
    return unique_path(out_dir, stem, EXTENSIONS[settings["format"]])


def preview(item: dict, raw_settings: dict, preview_dir: str, size_base: int = 1024,
            check: Callable[[], None] = lambda: None) -> dict:
    """Run the real pipeline and keep the encoded file for the before/after view."""
    settings = validate(raw_settings)
    loaded = load_cached(item["path"])
    result, data = process(loaded, item.get("crop"), settings, size_base=size_base, check=check)
    out = Path(preview_dir) / f"preview-{uuid.uuid4().hex}{EXTENSIONS[settings['format']]}"
    write_atomic(out, data)
    result["previewPath"] = str(out)
    return result


def run_batch(job: dict, notify: Callable[[dict], None], cancel: threading.Event | None = None) -> dict:
    """Process job["items"] with one settings object. Writes files, optionally a ZIP."""
    settings = validate(job["settings"])
    out_dir = Path(job["outputDir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    base = int(job.get("sizeBase", 1024))
    check = compress.check_cancel(cancel)
    items = job["items"]
    results: list[dict] = []
    written: list[Path] = []
    for i, item in enumerate(items):
        notify({"index": i, "total": len(items), "fraction": i / max(1, len(items)),
                "message": f"{i + 1}/{len(items)}: {Path(item['path']).name}"})
        try:
            check()
            loaded = load_cached(item["path"])
            result, data = process(loaded, item.get("crop"), settings, size_base=base, check=check)
            if result["status"] in WRITABLE or settings["saveOutOfRange"]:
                path = _output_path(out_dir, settings, item["path"], result, i)
                write_atomic(path, data)
                result["outputPath"] = str(path)
                written.append(path)
            else:
                result["outputPath"] = None
        except Cancelled:
            results.append({"status": "cancelled", "path": item["path"], "message": "Cancelled"})
            for rest in items[i + 1:]:
                results.append({"status": "cancelled", "path": rest["path"], "message": "Not started (cancelled)"})
            break
        except ToolkitError as exc:
            result = {"status": "error", "message": exc.message, "code": exc.code, "outputPath": None}
        except Exception as exc:  # unexpected: report per file, keep the batch going
            result = {"status": "error", "message": f"Unexpected error: {exc}", "code": "internal", "outputPath": None}
        result["path"] = item["path"]
        results.append(result)
    zip_path = None
    if job.get("zip") and written:
        zip_path = unique_path(out_dir, render_name(job.get("zipName") or "resized-images"), ".zip")
        tmp = zip_path.with_suffix(".zip.part")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
            for p in written:
                zf.write(p, arcname=p.name)
        os.replace(tmp, zip_path)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    notify({"index": len(items), "total": len(items), "fraction": 1.0, "message": "Done"})
    return {"results": results, "zipPath": str(zip_path) if zip_path else None, "counts": counts,
            "outputDir": str(out_dir)}
