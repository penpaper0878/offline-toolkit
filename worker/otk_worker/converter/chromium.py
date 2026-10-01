"""HTML/SVG to PDF with Chromium.

Inside the app the worker asks the Electron main process (ctx.host), which
prints from a hidden, sandboxed window with JavaScript off and every request
outside the job folder blocked. Outside the app (tests, command line) the same
print runs in a headless Electron started from scripts/render-pdf.cjs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import engines
from .context import PAPER_MM, StepContext


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def electron_binary() -> str | None:
    env = os.environ.get("OTK_ELECTRON")
    if env and Path(env).is_file():
        return env
    dist = _repo_root() / "node_modules" / "electron" / "dist"
    for name in ("electron.exe", "electron", "Electron.app/Contents/MacOS/Electron"):
        p = dist / name
        if p.is_file():
            return str(p)
    return None


def render_pdf(ctx: StepContext, html: Path, out: Path, *, paper: str | None = None,
               page_size_pt: tuple[float, float] | None = None) -> dict:
    """Print `html` (a self-contained file in the job folder) to `out`."""
    paper = paper or ctx.options.paper
    request = {"html": str(html), "pdf": str(out), "paper": paper, "allowDir": str(ctx.work),
               "pageSize": list(page_size_pt) if page_size_pt else None}
    if ctx.host is not None:
        result = ctx.host.render_pdf(html, out, paper=paper, allow_dir=ctx.work, page_size=page_size_pt)
    else:
        exe = electron_binary()
        if exe is None:
            raise engines.EngineMissing("Chromium (Electron) is needed to turn HTML into PDF, and it was not found.")
        script = _repo_root() / "scripts" / "render-pdf.cjs"
        req_file = ctx.path("render-request.json")
        req_file.write_text(json.dumps(request), encoding="utf-8")
        cmd = [exe]
        if sys.platform.startswith("linux"):
            cmd += ["--no-sandbox", "--headless"] if os.geteuid() == 0 else ["--headless"]
        cmd += [str(script), str(req_file)]
        env = engines.clean_env({"ELECTRON_ENABLE_LOGGING": "0", "ELECTRON_RUN_AS_NODE": ""})
        env.pop("ELECTRON_RUN_AS_NODE", None)
        res = engines.run(cmd, check=ctx.check, timeout=300, env=env, what="Chromium")
        try:
            result = json.loads(res.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {}
    if not out.exists() or out.stat().st_size == 0:
        raise engines.EngineFailed("Chromium did not produce a PDF.")
    for url in (result or {}).get("blocked", []):
        ctx.note(f"Blocked while rendering (offline): {url}")
    return result or {}


def paper_css(paper: str) -> str:
    w, h = PAPER_MM[paper]
    return f"@page {{ size: {w}mm {h}mm; }}"
