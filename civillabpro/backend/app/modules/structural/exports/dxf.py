"""Drawing model to DXF (AutoCAD R2010), one millimetre per drawing unit.

Views are laid out side by side on layers named after the model's layers, with
true DIMENSION entities so the drawing stays editable in CAD.
"""

from __future__ import annotations

import io
from typing import Any

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

# layer name -> (AutoCAD colour index, lineweight in 1/100 mm)
LAYERS = {
    "concrete": ("CLP-CONCRETE", 7, 35),
    "rebar": ("CLP-REBAR", 1, 50),
    "stirrup": ("CLP-STIRRUP", 5, 25),
    "dimension": ("CLP-DIM", 8, 18),
    "text": ("CLP-TEXT", 7, 18),
    "support": ("CLP-SUPPORT", 8, 25),
    "centerline": ("CLP-CENTER", 8, 18),
}
_ALIGN = {"start": TextEntityAlignment.LEFT, "middle": TextEntityAlignment.CENTER, "end": TextEntityAlignment.RIGHT}


def build_dxf(drawing: dict[str, Any]) -> bytes:
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.MM
    doc.header["$MEASUREMENT"] = 1
    for name, colour, weight in LAYERS.values():
        doc.layers.add(name, color=colour, lineweight=weight)
    msp = doc.modelspace()

    x_cursor = 0.0
    for view in drawing["views"]:
        xmin, ymin, xmax, ymax = view["bounds"]
        ox, oy = x_cursor - xmin, -ymin

        def P(x: float, y: float, ox: float = ox, oy: float = oy) -> tuple[float, float]:  # noqa: N802
            return (x + ox, y + oy)

        title_h = max((ymax - ymin) / 25.0, 20.0)
        for it in view["items"]:
            layer = LAYERS[it.get("layer", "text")][0]
            t = it["t"]
            if t == "line":
                msp.add_line(P(it["x1"], it["y1"]), P(it["x2"], it["y2"]), dxfattribs={"layer": layer})
            elif t == "polyline":
                msp.add_lwpolyline([P(x, y) for x, y in it["points"]], close=it["closed"], dxfattribs={"layer": layer})
            elif t == "circle":
                if it["filled"]:
                    hatch = msp.add_hatch(color=LAYERS["rebar"][1], dxfattribs={"layer": layer})
                    hatch.paths.add_edge_path().add_arc(P(it["cx"], it["cy"]), it["r"], 0, 360)
                msp.add_circle(P(it["cx"], it["cy"]), it["r"], dxfattribs={"layer": layer})
            elif t == "text":
                msp.add_text(it["text"], height=it["h"], dxfattribs={"layer": layer, "rotation": float(it.get("rot", 0))}).set_placement(
                    P(it["x"], it["y"]), align=_ALIGN[it["anchor"]])
            elif t == "leader":
                msp.add_line(P(it["x"], it["y"]), P(it["tx"], it["ty"] + 0.3 * it["h"]), dxfattribs={"layer": LAYERS["dimension"][0]})
                if it["tx"] < it["x"]:  # label to the left of its point: right-aligned so it reads towards it
                    msp.add_text(it["text"], height=it["h"], dxfattribs={"layer": layer}).set_placement(
                        P(it["tx"] - 0.3 * it["h"], it["ty"]), align=TextEntityAlignment.RIGHT)
                else:
                    msp.add_text(it["text"], height=it["h"], dxfattribs={"layer": layer}).set_placement(P(it["tx"] + 0.3 * it["h"], it["ty"]))
            elif t == "dim":
                override = {"dimtxt": it["h"], "dimasz": 0.6 * it["h"], "dimexo": 0.3 * it["h"], "dimexe": 0.4 * it["h"], "dimgap": 0.25 * it["h"],
                            "dimtad": 1, "dimdec": 0, "dimtsz": 0.35 * it["h"]}
                if it["horizontal"]:
                    yd = (max(it["y1"], it["y2"]) if it["offset"] >= 0 else min(it["y1"], it["y2"])) + it["offset"]
                    dim = msp.add_linear_dim(base=P(it["x1"], yd), p1=P(it["x1"], it["y1"]), p2=P(it["x2"], it["y2"]), angle=0, text=it["text"],
                                             override=override, dxfattribs={"layer": layer})
                else:
                    xd = (max(it["x1"], it["x2"]) if it["offset"] >= 0 else min(it["x1"], it["x2"])) + it["offset"]
                    dim = msp.add_linear_dim(base=P(xd, it["y1"]), p1=P(it["x1"], it["y1"]), p2=P(it["x2"], it["y2"]), angle=90, text=it["text"],
                                             override=override, dxfattribs={"layer": layer})
                dim.render()
        msp.add_text(view["title"].upper(), height=title_h, dxfattribs={"layer": LAYERS["text"][0]}).set_placement(
            (x_cursor + (xmax - xmin) / 2.0, -2.5 * title_h), align=TextEntityAlignment.CENTER)
        x_cursor += (xmax - xmin) * 1.15 + 200.0

    y = -6.0 * 40.0
    for note in [drawing["title"], *drawing["notes"]]:
        msp.add_text(note, height=30.0, dxfattribs={"layer": LAYERS["text"][0]}).set_placement((0.0, y))
        y -= 55.0

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
