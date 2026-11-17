"""Neutral drawing model.

Engines describe a drawing once, as primitives in millimetres (x to the right,
y upwards). The web canvas renders them as SVG, the DXF exporter writes them as
CAD entities and the PDF report embeds them, so the three can never disagree.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Layer = Literal["concrete", "rebar", "stirrup", "dimension", "text", "support", "centerline"]


@dataclass
class View:
    """One view (a section or an elevation) with its own origin."""

    id: str
    title: str
    scale_note: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)

    def line(self, x1: float, y1: float, x2: float, y2: float, layer: Layer = "concrete") -> None:
        self.items.append({"t": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "layer": layer})

    def rect(self, x: float, y: float, w: float, h: float, layer: Layer = "concrete") -> None:
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        self.polyline(pts, closed=True, layer=layer)

    def polyline(
        self, points: list[tuple[float, float]], closed: bool = False, layer: Layer = "concrete"
    ) -> None:
        self.items.append(
            {"t": "polyline", "points": [[float(x), float(y)] for x, y in points], "closed": closed, "layer": layer}
        )

    def circle(self, cx: float, cy: float, r: float, layer: Layer = "rebar", filled: bool = True) -> None:
        self.items.append({"t": "circle", "cx": cx, "cy": cy, "r": r, "layer": layer, "filled": filled})

    def text(
        self,
        x: float,
        y: float,
        text: str,
        height: float = 20.0,
        anchor: Literal["start", "middle", "end"] = "start",
        layer: Layer = "text",
    ) -> None:
        self.items.append({"t": "text", "x": x, "y": y, "text": text, "h": height, "anchor": anchor, "layer": layer})

    def dim(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        offset: float,
        text: str | None = None,
        height: float = 20.0,
    ) -> None:
        """Linear dimension between two points.

        The dimension line is horizontal when the points differ mainly in x and
        vertical otherwise; ``offset`` moves it away from the points (positive
        is up for horizontal, right for vertical).
        """
        horizontal = abs(x2 - x1) >= abs(y2 - y1)
        value = abs(x2 - x1) if horizontal else abs(y2 - y1)
        self.items.append(
            {
                "t": "dim",
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "offset": offset,
                "horizontal": horizontal,
                "text": text if text is not None else f"{value:.0f}",
                "h": height,
                "layer": "dimension",
            }
        )

    def leader(self, x: float, y: float, tx: float, ty: float, text: str, height: float = 20.0) -> None:
        """A callout: a line from the pointed item to a text label."""
        self.items.append(
            {"t": "leader", "x": x, "y": y, "tx": tx, "ty": ty, "text": text, "h": height, "layer": "text"}
        )

    def bounds(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) of the geometry, with room for text and dimensions."""
        xs: list[float] = []
        ys: list[float] = []
        for it in self.items:
            t = it["t"]
            if t == "line":
                xs += [it["x1"], it["x2"]]
                ys += [it["y1"], it["y2"]]
            elif t == "polyline":
                xs += [p[0] for p in it["points"]]
                ys += [p[1] for p in it["points"]]
            elif t == "circle":
                xs += [it["cx"] - it["r"], it["cx"] + it["r"]]
                ys += [it["cy"] - it["r"], it["cy"] + it["r"]]
            elif t == "text":
                w = 0.6 * it["h"] * len(it["text"])
                x0 = it["x"] - (w if it["anchor"] == "end" else w / 2 if it["anchor"] == "middle" else 0)
                xs += [x0, x0 + w]
                ys += [it["y"] - 0.3 * it["h"], it["y"] + it["h"]]
            elif t == "dim":
                pad = 1.6 * it["h"]
                if it["horizontal"]:
                    yd = max(it["y1"], it["y2"]) + it["offset"] if it["offset"] >= 0 else min(it["y1"], it["y2"]) + it["offset"]
                    xs += [it["x1"], it["x2"]]
                    ys += [it["y1"], it["y2"], yd - pad, yd + pad]
                else:
                    xd = max(it["x1"], it["x2"]) + it["offset"] if it["offset"] >= 0 else min(it["x1"], it["x2"]) + it["offset"]
                    ys += [it["y1"], it["y2"]]
                    xs += [it["x1"], it["x2"], xd - pad, xd + pad]
            elif t == "leader":
                w = 0.6 * it["h"] * len(it["text"])
                xs += [it["x"], it["tx"], it["tx"] + (w if it["tx"] >= it["x"] else -w)]
                ys += [it["y"], it["ty"] - 0.3 * it["h"], it["ty"] + it["h"]]
        if not xs:
            return (0.0, 0.0, 1.0, 1.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bounds"] = list(self.bounds())
        return d


@dataclass
class DrawingModel:
    title: str
    views: list[View] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def view(self, id: str, title: str, scale_note: str = "") -> View:
        v = View(id, title, scale_note)
        self.views.append(v)
        return v

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "views": [v.to_dict() for v in self.views], "notes": list(self.notes)}
