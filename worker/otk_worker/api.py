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


class RpcHost:
    """Chromium printing done by the Electron main process, asked over the same stdio channel."""

    def __init__(self, ctx: Context):
        self.ctx = ctx

    def render_pdf(self, html_path, pdf_path, *, paper: str, allow_dir, page_size=None) -> dict:
        return self.ctx.server.request_host("host.renderPdf", {
            "html": str(html_path), "pdf": str(pdf_path), "paper": paper, "allowDir": str(allow_dir),
            "pageSize": list(page_size) if page_size else None}, timeout=600, cancel=self.ctx.cancel_event)


def _host(ctx: Context):
    return RpcHost(ctx) if os.environ.get("OTK_HOST_RPC") == "1" else None


def converter_catalog(params: dict, ctx: Context) -> dict:
    from .converter import engines, ocr, runner

    cat = runner.catalog()
    fmts = []
    for fid, f in cat.formats.items():
        if "internal" in f["roles"]:
            continue
        fmts.append({"id": fid, "label": f["label"], "short": f.get("short", fid), "ext": f.get("ext", []),
                     "roles": f["roles"], "targetModes": f.get("targetModes", []), "note": f.get("note")})
    try:
        langs = ocr.languages_available()
    except Exception:
        langs = []
    return {"formats": fmts, "sources": cat.sources(), "targets": cat.targets(), "ocrLanguages": langs,
            "engines": engines.status(), "features": {k: v["label"] for k, v in cat.features.items()}}


def converter_inspect(params: dict, ctx: Context) -> dict:
    from .converter import runner

    passwords = params.get("passwords") or {}
    out = []
    for path in params.get("paths") or []:
        out.append(runner.preflight(path, params["target"], params.get("mode", "exact"), passwords.get(path),
                                    params.get("options")))
    return {"files": out}


def converter_plan(params: dict, ctx: Context) -> dict:
    from .converter import runner
    from .converter.planner import NoRouteError

    cat = runner.catalog()
    try:
        route = cat.plan(params["source"], params["target"], params.get("mode", "exact"))
    except NoRouteError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "route": runner.route_dict(route),
            "losses": [{"feature": x.feature, "label": x.label, "level": x.level} for x in cat.potential_losses(route)],
            "stepLosses": cat.step_losses(route)}


def converter_run(params: dict, ctx: Context) -> dict:
    from .converter import runner

    return runner.run_batch(params, ctx.progress, ctx.cancel_event, host=_host(ctx))


def engines_status(params: dict, ctx: Context) -> dict:
    from .converter import engines, ocr

    st = engines.status()
    try:
        st["ocrLanguages"] = ocr.languages_available()
    except Exception as exc:
        st["ocrLanguages"] = []
        st["ocrError"] = str(exc)
    return st


def register(server: Server) -> None:
    server.register("ping", ping, inline=True)
    server.register("selftest.canary", selftest_canary)
    server.register("image.probe", probe)
    server.register("resizer.validate", validate_settings)
    server.register("units.resolve", resolve_units)
    server.register("resizer.preview", resizer_preview)
    server.register("resizer.run", resizer_run)
    server.register("converter.catalog", converter_catalog)
    server.register("converter.inspect", converter_inspect)
    server.register("converter.plan", converter_plan)
    server.register("converter.run", converter_run)
    server.register("engines.status", engines_status)
