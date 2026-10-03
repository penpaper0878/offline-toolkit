"""Bundled fonts and models: where they are, and opening a font at a weight.

Fonts come from scripts/fetch_fonts.py (fonts/fonts.json is the catalogue), models from
scripts/fetch_models.py. The app passes OTK_FONTS and OTK_MODELS (resources/fonts, resources/models in a
packaged build); in development the repository's fonts/ and models/ are used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..errors import ToolkitError

_REPO = Path(__file__).resolve().parents[3]


def fonts_dir() -> Path:
    return Path(os.environ.get("OTK_FONTS") or _REPO / "fonts")


def models_dir() -> Path:
    return Path(os.environ.get("OTK_MODELS") or _REPO / "models")


def model_path(name: str) -> Path | None:
    p = models_dir() / name
    return p if p.is_file() else None


@lru_cache(maxsize=1)
def catalogue() -> list[dict]:
    path = fonts_dir() / "fonts.json"
    if not path.is_file():
        raise ToolkitError("The bundled fonts are missing (fonts/fonts.json). Reinstall the app, or run "
                           "scripts/fetch_fonts.py in a development copy.")
    return json.loads(path.read_text(encoding="utf-8"))["families"]


def family(name: str) -> dict | None:
    return next((f for f in catalogue() if f["family"].lower() == name.lower()), None)


def families_for_script(script: str) -> list[dict]:
    return [f for f in catalogue() if script in f["scripts"]]


@dataclass(frozen=True)
class FontFace:
    family: str
    path: Path
    weight: int          # the weight this face draws at (a variable font is set to it)
    italic: bool
    variable: bool

    def pil(self, size: float):
        return pil_font(self.path, size, self.weight if self.variable else None)


def face(name: str, weight: int = 400, italic: bool = False) -> FontFace | None:
    """The closest face of a bundled family: same style if it has one, the nearest weight."""
    fam = family(name)
    if fam is None:
        return None
    style = "italic" if italic else "normal"
    files = [f for f in fam["files"] if f["style"] == style] or fam["files"]

    def distance(f) -> int:
        lo, hi = f["weight"]
        return 0 if lo <= weight <= hi else min(abs(weight - lo), abs(weight - hi))

    best = min(files, key=distance)
    lo, hi = best["weight"]
    variable = "[" in best["file"]
    return FontFace(fam["family"], fonts_dir() / best["file"], max(lo, min(hi, weight)) if variable else lo,
                    best["style"] == "italic", variable)


def weights(name: str, italic: bool = False) -> list[int]:
    """Weights worth trying for a family: its static files, or 300..900 inside a variable font's range."""
    fam = family(name)
    if fam is None:
        return []
    style = "italic" if italic else "normal"
    out: set[int] = set()
    for f in fam["files"]:
        if f["style"] != style:
            continue
        lo, hi = f["weight"]
        if "[" in f["file"]:
            out.update(w for w in (300, 400, 500, 600, 700, 800, 900) if lo <= w <= hi)
        else:
            out.add(lo)
    return sorted(out)


_pil_cache: dict = {}


def pil_font(path: Path, size: float, weight: int | None = None):
    """A Pillow font with complex-script shaping (raqm), the weight axis set for variable fonts."""
    from PIL import ImageFont

    key = (str(path), round(size * 4) / 4, weight)
    ft = _pil_cache.get(key)
    if ft is None:
        if len(_pil_cache) > 512:
            _pil_cache.clear()
        ft = ImageFont.truetype(str(path), max(1, int(round(size))), layout_engine=ImageFont.Layout.RAQM)
        if weight is not None:
            try:
                values = []
                for a in ft.get_variation_axes():
                    name = a["name"].decode() if isinstance(a["name"], bytes) else str(a["name"])
                    values.append(max(a["minimum"], min(a["maximum"], weight)) if name in ("Weight", "wght")
                                  else a["default"])
                ft.set_variation_by_axes(values)
            except OSError:
                pass
        _pil_cache[key] = ft
    return ft
