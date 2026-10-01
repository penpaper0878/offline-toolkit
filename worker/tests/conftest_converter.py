"""Shared fixtures for the converter tests: one sample corpus per test session, engine availability marks."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from otk_worker.converter import engines

HAVE_LO = engines.find("soffice") is not None
HAVE_PANDOC = engines.find("pandoc") is not None
HAVE_GS = engines.find("gs") is not None
HAVE_TESS = engines.find("tesseract") is not None
HAVE_VERAPDF = bool(engines.verapdf_classpath() and engines.find("java"))
HAVE_RESVG = engines.find("resvg") is not None


def _electron() -> bool:
    from otk_worker.converter import chromium
    return chromium.electron_binary() is not None


HAVE_CHROMIUM = _electron()
HAVE_ALL = all((HAVE_LO, HAVE_PANDOC, HAVE_GS, HAVE_TESS, HAVE_VERAPDF, HAVE_RESVG, HAVE_CHROMIUM))

needs_lo = pytest.mark.skipif(not HAVE_LO, reason="LibreOffice not installed")
needs_gs = pytest.mark.skipif(not HAVE_GS, reason="Ghostscript not installed")
needs_tess = pytest.mark.skipif(not HAVE_TESS, reason="Tesseract not installed")
needs_verapdf = pytest.mark.skipif(not HAVE_VERAPDF, reason="veraPDF/Java not installed")
needs_chromium = pytest.mark.skipif(not HAVE_CHROMIUM, reason="Electron (Chromium) not installed: run npm ci, then node -e \"require('electron')\"")
needs_all = pytest.mark.skipif(not HAVE_ALL, reason="not every conversion engine is installed")


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    import corpus

    out = tmp_path_factory.mktemp("corpus")
    return corpus.build(out, legacy=HAVE_LO, pdfa=HAVE_LO)


def copy_sample(samples: dict[str, Path], key: str, dest: Path) -> Path:
    """A private copy (with the picture next to it for HTML) so tests never share outputs."""
    src = samples[key]
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / src.name
    shutil.copyfile(src, out)
    if key == "html":
        shutil.copyfile(src.parent / "office.png", dest / "office.png")
    return out
