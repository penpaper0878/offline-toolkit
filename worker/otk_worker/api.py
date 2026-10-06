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


def _bundled_assets() -> tuple[int | None, dict[str, bool]]:
    """Font families and AI models found (the model list is models/manifest.json; every file listed must exist)."""
    import json

    from .design import assets

    try:
        fonts: int | None = len(assets.catalogue())
    except Exception:  # noqa: BLE001 - reported as missing
        fonts = None
    models: dict[str, bool] = {}
    try:
        manifest = json.loads((assets.models_dir() / "manifest.json").read_text(encoding="utf-8"))
        models = {key: assets.model_path(entry["file"]) is not None for key, entry in manifest.items()}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return fonts, models


def ping(params: dict, ctx: Context) -> dict:
    fonts, models = _bundled_assets()
    return {
        "pong": True,
        "pid": os.getpid(),
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pillow": PIL.__version__,
        "heif": imageio.HEIF_AVAILABLE,
        "netguard": netguard._installed,
        "fonts": fonts,
        "models": models,
    }


def selftest_canary(params: dict, ctx: Context) -> dict:
    return netguard.canary()


def selftest_modules(params: dict, ctx: Context) -> dict:
    from . import selftest

    return selftest.run(params, ctx.progress, ctx.cancel_event, host=_host(ctx))


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


# ------------------------------------------------------------------ design (Module 3)
def _project(params: dict) -> Path:
    project = Path(params["project"])
    if not project.is_absolute():
        raise InputError("The design folder must be an absolute path.")
    return project


def design_analyze(params: dict, ctx: Context) -> dict:
    from .design import pipeline

    check = compress.check_cancel(ctx.cancel_event)
    scene = pipeline.analyze(params["source"], _project(params), langs=params.get("langs") or ["eng"],
                             upscale=params.get("upscale", "auto"), deskew=bool(params.get("deskew", True)),
                             denoise=bool(params.get("denoise", True)), check=check,
                             progress=lambda f, m: ctx.progress({"fraction": f, "message": m}))
    return {"scene": scene}


def design_accuracy(params: dict, ctx: Context) -> dict:
    from .design import project, verify

    proj = _project(params)
    scene = params.get("scene") or project.load(proj)
    return verify.accuracy(scene, proj, host=_host(ctx), check=compress.check_cancel(ctx.cancel_event))


def design_load(params: dict, ctx: Context) -> dict:
    from .design import project

    return {"scene": project.load(_project(params))}


def design_save(params: dict, ctx: Context) -> dict:
    from .design import project

    return project.save(_project(params), params["scene"])


def design_export(params: dict, ctx: Context) -> dict:
    from .design import project

    return project.export(_project(params), params["scene"], params["format"], Path(params["out"]),
                          fonts_folder=bool(params.get("fontsFolder")))


def design_open(params: dict, ctx: Context) -> dict:
    from .design import project

    return {"scene": project.unpack(Path(params["path"]), _project(params))}


def design_import_image(params: dict, ctx: Context) -> dict:
    from .design import project

    return project.import_image(_project(params), params["path"])


def design_cutout(params: dict, ctx: Context) -> dict:
    from .design import project

    return project.cutout(_project(params), params["asset"], params.get("mode", "auto"))


def design_fonts(params: dict, ctx: Context) -> dict:
    """The bundled fonts for the editor's font list: families, styles, scripts, licences and metrics."""
    from .design import assets, layout

    out = []
    for f in assets.catalogue():
        styles = [{"weight": w, "italic": it} for it in (False, True) for w in assets.weights(f["family"], it)]
        m = layout.metrics(f["family"], 400, False)
        out.append({"family": f["family"], "category": f.get("category"), "role": f.get("role"), "scripts": f["scripts"],
                    "licence": f.get("licence"), "styles": styles,
                    "metrics": {k: round(v, 4) for k, v in m.items()}})
    return {"families": out}


def design_font_file(params: dict, ctx: Context) -> dict:
    """A static font file for one face (the editor loads exactly what the exports use)."""
    from .design import fonts_out, layout

    fam, w, it = params["family"], int(params.get("weight", 400)), bool(params.get("italic", False))
    path = fonts_out.static_font(fam, w, it)
    if path is None:
        raise InputError(f"The font {fam} is not bundled.")
    return {"path": str(path), "weight": fonts_out.snap_weight(w), "italic": it,
            "metrics": layout.metrics(fam, fonts_out.snap_weight(w), it)}


def design_install_fonts(params: dict, ctx: Context) -> dict:
    from .design import project

    return project.install_fonts(params["scene"])


def register(server: Server) -> None:
    server.register("ping", ping, inline=True)
    server.register("selftest.canary", selftest_canary)
    server.register("selftest.modules", selftest_modules)
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
    server.register("design.analyze", design_analyze)
    server.register("design.accuracy", design_accuracy)
    server.register("design.load", design_load)
    server.register("design.save", design_save)
    server.register("design.export", design_export)
    server.register("design.open", design_open)
    server.register("design.importImage", design_import_image)
    server.register("design.cutout", design_cutout)
    server.register("design.fonts", design_fonts)
    server.register("design.fontFile", design_font_file)
    server.register("design.installFonts", design_install_fonts)
    from .passport import api as passport

    for name in ("open_photo", "analyze", "autofit", "render", "auto", "export_photo", "sheet"):
        rpc = {"open_photo": "open", "export_photo": "export"}.get(name, name)
        server.register(f"passport.{rpc}", getattr(passport, name))
