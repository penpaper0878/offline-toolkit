"""RPC methods exposed to the Electron main process."""

from __future__ import annotations

import os
import platform
import sys
import uuid
from pathlib import Path

import PIL

from . import __version__, netguard
from .common import imageio, units
from .errors import InputError
from .resizer import compress, pipeline, settings as resizer_settings
from .rpc import Context, Server

_ROTATED = {5, 6, 7, 8}


def ping(params: dict, ctx: Context) -> dict:
    return {
        "pong": True,
        "pid": os.getpid(),
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pillow": PIL.__version__,
        "heif": imageio.HEIF_AVAILABLE,
        "netguard": netguard._installed,
    }


def selftest_canary(params: dict, ctx: Context) -> dict:
    return netguard.canary()


def probe(params: dict, ctx: Context) -> dict:
    """Image info (full size after orientation) plus a downscaled preview for the UI."""
    path = params["path"]
    preview_dir = Path(params["previewDir"])
    max_side = int(params.get("maxSide", 2048))
    loaded = imageio.open_image(path, draft_to=max_side)
    ow, oh = loaded.original_size
    full_w, full_h = (oh, ow) if loaded.orientation in _ROTATED else (ow, oh)
    prev = imageio.save_preview(loaded, preview_dir / f"src-{uuid.uuid4().hex}", max_side)
    info = loaded.info_dict()
    info.update(width=full_w, height=full_h)
    info["preview"] = {"path": prev["path"], "width": prev["width"], "height": prev["height"],
                       "scale": prev["width"] / full_w}
    return info


def validate_settings(params: dict, ctx: Context) -> dict:
    return resizer_settings.validate(params["settings"])


def resolve_units(params: dict, ctx: Context) -> dict:
    size = units.resolve_size(params["width"], params["height"], params["unit"], params["dpi"],
                              fit_dpi=bool(params.get("fitDpi")))
    return size.to_dict()


def resizer_preview(params: dict, ctx: Context) -> dict:
    return pipeline.preview(params["item"], params["settings"], params["previewDir"],
                            size_base=int(params.get("sizeBase", 1024)),
                            check=compress.check_cancel(ctx.cancel_event))


def resizer_run(params: dict, ctx: Context) -> dict:
    if not params.get("items"):
        raise InputError("No images to process.")
    return pipeline.run_batch(params, ctx.progress, ctx.cancel_event)


def register(server: Server) -> None:
    server.register("ping", ping, inline=True)
    server.register("selftest.canary", selftest_canary)
    server.register("image.probe", probe)
    server.register("resizer.validate", validate_settings)
    server.register("units.resolve", resolve_units)
    server.register("resizer.preview", resizer_preview)
    server.register("resizer.run", resizer_run)
