"""Checking a reconstruction against the picture it came from, and an export against the reconstruction.

The scene is drawn by Chromium from its SVG export (the same engine as the editor) and compared with the
prepared picture: SSIM after alignment, plus the regions where one side has ink and the other has none
(the document converter's appearance check). An exported PPTX or DOCX is drawn by LibreOffice and
compared the same way with the scene's own drawing, which isolates what the format changed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from . import out_svg

CSS_PT = 0.75   # one CSS pixel in points


def _pdf_page_image(pdf: Path, width: int, height: int) -> Image.Image:
    import fitz

    with fitz.open(str(pdf)) as doc:
        page = doc[0]
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, height / page.rect.height), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return img if img.size == (width, height) else img.resize((width, height), Image.LANCZOS)


def render_scene(scene: dict, project: Path, *, host=None, check=lambda: None) -> Image.Image:
    """The scene drawn by Chromium at its pixel size."""
    from ..converter import chromium

    work = project / "cache" / "render"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    W, H = scene["page"]["width"], scene["page"]["height"]
    out_svg.write(scene, project, work / "design.svg")
    html = work / "page.html"
    html.write_text(f"<!doctype html><meta charset=utf-8><style>@page{{size:{W}px {H}px;margin:0}}"
                    f"html,body{{margin:0;padding:0}}img{{display:block;width:{W}px;height:{H}px}}</style>"
                    f'<img src="design.svg">', encoding="utf-8")
    pdf = work / "page.pdf"
    chromium.print_html(html, pdf, page_size_pt=(W * CSS_PT, H * CSS_PT), allow_dir=work, host=host, check=check)
    return _pdf_page_image(pdf, W, H)


def render_office(path: Path, width: int, height: int, *, scene: dict | None = None, check=lambda: None) -> Image.Image:
    """A PPTX or DOCX drawn by LibreOffice (first page or slide), at the given pixel size. With `scene`,
    the scene's fonts are made visible to LibreOffice first (on Linux, through fontconfig)."""
    import sys

    from ..converter import engines
    from . import fonts_out

    found = engines.find("soffice")
    if found is None:
        raise engines.EngineMissing("LibreOffice is needed to draw the exported file, and it was not found.")
    outdir = path.parent / f"{path.stem}-render"
    outdir.mkdir(exist_ok=True)
    profile = outdir / "profile"
    extra = {}
    if scene is not None and sys.platform.startswith("linux"):
        fdir = outdir / "fonts"
        fonts_out.export_files(scene, fdir)
        extra = fonts_out.fontconfig_env(fdir)
    engines.run([found.path, f"-env:UserInstallation={profile.resolve().as_uri()}", "--headless", "--convert-to", "pdf",
                 "--outdir", str(outdir), str(path)], check=check, timeout=300, what="LibreOffice",
                env=engines.clean_env(extra))
    pdf = outdir / f"{path.stem}.pdf"
    if not pdf.exists():
        raise engines.EngineFailed("LibreOffice did not draw the exported file.")
    return _pdf_page_image(pdf, width, height)


def compare(reference: Image.Image, candidate: Image.Image) -> dict:
    """SSIM (after alignment) and changed regions of `candidate` against `reference`."""
    from ..common.ssim import ssim
    from ..converter.verify.compare import _compare_page, _snapshot

    a, b = reference.convert("RGB"), candidate.convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    score, shift, regions = _compare_page(a, b, ssim)
    return {"ssim": round(float(score), 4), "alignment": shift if isinstance(shift, str) else list(shift),
            "regions": [{"x": r[0], "y": r[1], "w": r[2], "h": r[3], "pixels": r[4]} for r in regions[:20]],
            "snapshots": [_snapshot(a, b, r) for r in regions[:3]]}


def accuracy(scene: dict, project: Path, *, host=None, check=lambda: None) -> dict:
    """How closely the reconstruction reproduces the prepared picture."""
    prepared = Image.open(project / scene["assets"]["prepared"]).convert("RGB")
    drawn = render_scene(scene, project, host=host, check=check)
    drawn.save(project / "cache" / "render" / "drawn.png")
    out = compare(prepared, drawn)
    diff = np.abs(np.asarray(prepared, np.int16) - np.asarray(drawn, np.int16)).max(axis=2)
    out["meanDifference"] = round(float(diff.mean()), 3)
    return out
