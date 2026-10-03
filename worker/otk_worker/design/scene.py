"""The scene graph: what the analysis produces, the editor changes and the exporters write.

All geometry is in page pixels (the prepared picture's pixel grid). A layer's `box` is [x, y, w, h] of
its unrotated frame; `rotation` turns it clockwise (degrees) about the box centre, as PowerPoint, CSS,
SVG (y down) and Konva do. Layers are listed bottom to top.

Text layers keep their typography explicit: the first baseline sits `baseline` px below the box top
(the font's ascent at the size), every next line `lineHeight * size` lower, and each line is aligned
inside the box width. Exporters reproduce exactly those baselines.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

FORMAT = "otk-design"
VERSION = 1


def new_scene(width: int, height: int, *, source: dict) -> dict:
    return {"format": FORMAT, "version": VERSION, "source": source,
            "page": {"width": width, "height": height, "background": "#ffffff"},
            "layers": [], "notes": [], "limits": [], "lowConfidence": []}


def layer(type_: str, lid: str, name: str, box, **extra) -> dict:
    x, y, w, h = (round(float(v), 2) for v in box)
    out = {"id": lid, "type": type_, "name": name, "box": [x, y, w, h], "rotation": 0.0, "visible": True,
           "locked": False, "opacity": 1.0}
    out.update(extra)
    return out


def text_lines(lyr: dict, measure=None) -> list[dict]:
    """The lines of a text layer with their pen x and baseline y (layer coordinates).

    `measure(text, style) -> advance px`; without it the stored line widths are used (as analysed)."""
    st = lyr["style"]
    lines = lyr["text"].split("\n")
    stored = {i: ln.get("width") for i, ln in enumerate(lyr.get("lines", []))}
    out = []
    w = lyr["box"][2]
    for i, t in enumerate(lines):
        adv = measure(t, st) if measure else (stored.get(i) or 0.0)
        if st["align"] == "center":
            x = (w - adv) / 2
        elif st["align"] == "right":
            x = w - adv
        else:
            x = 0.0
        out.append({"text": t, "x": round(x, 2), "y": round(lyr["baseline"] + i * st["lineHeight"] * st["size"], 2),
                    "width": round(adv, 2)})
    return out


def save(scene: dict, path: Path) -> Path:
    path.write_text(json.dumps(scene, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def load(path: Path) -> dict:
    scene = json.loads(path.read_text(encoding="utf-8"))
    if scene.get("format") != FORMAT:
        raise ValueError("Not an Offline Toolkit design.")
    return scene


def clone(scene: dict) -> dict:
    return copy.deepcopy(scene)


def find(scene: dict, lid: str) -> dict | None:
    return next((lyr for lyr in scene["layers"] if lyr["id"] == lid), None)
