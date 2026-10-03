"""Synthetic designs with exact ground truth, for the image-to-design tests (Module 3).

Each builder draws a picture the way a design tool would export it and returns (image path, truth), where
truth lists every element: kind, box (x0, y0, x1, y1 in px), and for text the string, font family, size
(px, the em size), weight, italic, colour and alignment. The fonts are the bundled ones (fonts/), so a
perfect pipeline could recover every attribute exactly.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "fonts"


def _catalogue() -> dict:
    return {f["family"]: f for f in json.loads((FONTS / "fonts.json").read_text(encoding="utf-8"))["families"]}


def font(family: str, size: int, weight: int = 400, italic: bool = False) -> ImageFont.FreeTypeFont:
    fam = _catalogue()[family]
    style = "italic" if italic else "normal"
    files = [f for f in fam["files"] if f["style"] == style] or fam["files"]
    best = min(files, key=lambda f: 0 if f["weight"][0] <= weight <= f["weight"][1] else
               min(abs(weight - f["weight"][0]), abs(weight - f["weight"][1])))
    ft = ImageFont.truetype(str(FONTS / best["file"]), size, layout_engine=ImageFont.Layout.RAQM)
    if "[" in best["file"]:
        axes = ft.get_variation_axes()
        values = []
        for a in axes:
            name = a["name"].decode() if isinstance(a["name"], bytes) else a["name"]
            values.append(max(a["minimum"], min(a["maximum"], weight)) if name in ("Weight", "wght") else a["default"])
        ft.set_variation_by_axes(values)
    return ft


class Canvas:
    def __init__(self, w: int, h: int, background):
        self.img = background if isinstance(background, Image.Image) else Image.new("RGB", (w, h), background)
        self.draw = ImageDraw.Draw(self.img)
        self.truth: list[dict] = []

    def text(self, xy, s: str, family: str, size: int, color: str, *, weight: int = 400, italic: bool = False,
             align: str = "left", width: int | None = None) -> dict:
        """One line of text. xy is the left baseline, or the centre/right baseline for those alignments."""
        ft = font(family, size, weight, italic)
        x, y = xy
        anchor = {"left": "ls", "center": "ms", "right": "rs"}[align]
        self.draw.text((x, y), s, font=ft, fill=color, anchor=anchor)
        box = self.draw.textbbox((x, y), s, font=ft, anchor=anchor)
        el = {"kind": "text", "text": s, "family": family, "size": size, "weight": weight, "italic": italic,
              "color": color, "align": align, "box": list(box), "baseline": y}
        self.truth.append(el)
        return el

    def paragraph(self, x: int, y: int, lines: list[str], family: str, size: int, color: str, *, leading: float = 1.4,
                  weight: int = 400, align: str = "left") -> dict:
        els = [self.text((x, y + i * round(size * leading)), s, family, size, color, weight=weight, align=align)
               for i, s in enumerate(lines)]
        for e in els:
            self.truth.remove(e)
        box = [min(e["box"][0] for e in els), min(e["box"][1] for e in els),
               max(e["box"][2] for e in els), max(e["box"][3] for e in els)]
        el = {"kind": "text", "text": "\n".join(lines), "family": family, "size": size, "weight": weight, "italic": False,
              "color": color, "align": align, "box": box, "lines": [e["box"] for e in els], "leading": leading}
        self.truth.append(el)
        return el

    def rect(self, box, fill=None, outline=None, width: int = 1, radius: int = 0) -> dict:
        if radius:
            self.draw.rounded_rectangle(box, radius, fill=fill, outline=outline, width=width)
        else:
            self.draw.rectangle(box, fill=fill, outline=outline, width=width)
        el = {"kind": "shape", "shape": "rounded" if radius else "rect", "box": list(box), "fill": fill,
              "stroke": outline, "strokeWidth": width if outline else 0, "radius": radius}
        self.truth.append(el)
        return el

    def ellipse(self, box, fill=None, outline=None, width: int = 1) -> dict:
        self.draw.ellipse(box, fill=fill, outline=outline, width=width)
        el = {"kind": "shape", "shape": "ellipse", "box": list(box), "fill": fill, "stroke": outline,
              "strokeWidth": width if outline else 0}
        self.truth.append(el)
        return el

    def line(self, p0, p1, color: str, width: int) -> dict:
        self.draw.line([p0, p1], fill=color, width=width)
        x0, x1 = sorted((p0[0], p1[0]))
        y0, y1 = sorted((p0[1], p1[1]))
        el = {"kind": "shape", "shape": "line", "box": [x0, y0 - width // 2, x1, y1 + width // 2], "stroke": color,
              "strokeWidth": width}
        self.truth.append(el)
        return el

    def photo(self, box, seed: int = 1) -> dict:
        from imagegen import photo_array

        x0, y0, x1, y1 = box
        self.img.paste(Image.fromarray(photo_array(x1 - x0, y1 - y0, seed=seed)), (x0, y0))
        el = {"kind": "image", "box": list(box)}
        self.truth.append(el)
        return el

    def star(self, cx: int, cy: int, r: int, color: str) -> dict:
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        self.draw.polygon(pts, fill=color)
        el = {"kind": "vector", "box": [cx - r, cy - r, cx + r, cy + r], "colors": [color]}
        self.truth.append(el)
        return el

    def badge(self, cx: int, cy: int, r: int, color: str, mark: str) -> dict:
        """A filled circle with a check mark: a two-colour icon."""
        self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        w = max(3, r // 4)
        self.draw.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
                       fill=mark, width=w, joint="curve")
        el = {"kind": "vector", "box": [cx - r, cy - r, cx + r, cy + r], "colors": [color, mark]}
        self.truth.append(el)
        return el

    def table(self, x0: int, y0: int, col_w: list[int], row_h: int, rows: list[list[str]], family: str, size: int,
              color: str = "#222222", border: str = "#444444", header_fill: str | None = "#E8E2D6") -> dict:
        x_edges = [x0]
        for w in col_w:
            x_edges.append(x_edges[-1] + w)
        y_edges = [y0 + i * row_h for i in range(len(rows) + 1)]
        if header_fill:
            self.draw.rectangle((x_edges[0], y_edges[0], x_edges[-1], y_edges[1]), fill=header_fill)
        for x in x_edges:
            self.draw.line([(x, y_edges[0]), (x, y_edges[-1])], fill=border, width=2)
        for y in y_edges:
            self.draw.line([(x_edges[0], y), (x_edges[-1], y)], fill=border, width=2)
        cells = []
        for r, row in enumerate(rows):
            for c, s in enumerate(row):
                ft = font(family, size, 700 if r == 0 else 400)
                bx = x_edges[c] + 12
                by = y_edges[r] + row_h // 2 + size // 3
                self.draw.text((bx, by), s, font=ft, fill=color, anchor="ls")
                cells.append({"row": r, "col": c, "text": s, "bold": r == 0})
        el = {"kind": "table", "box": [x_edges[0], y_edges[0], x_edges[-1], y_edges[-1]], "rows": len(rows),
              "cols": len(col_w), "cells": cells, "family": family, "size": size}
        self.truth.append(el)
        return el

    def save(self, path: Path) -> tuple[Path, dict]:
        self.img.save(path, dpi=(150, 150))
        truth = {"size": list(self.img.size), "elements": self.truth}
        path.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False), encoding="utf-8")
        return path, truth


def gradient(w: int, h: int, top, bottom) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top)[None, None] * (1 - t) + np.array(bottom)[None, None] * t).repeat(w, axis=1)
    return Image.fromarray(arr.astype(np.uint8))


def poster(out: Path) -> tuple[Path, dict]:
    """A festival poster: headline, paragraph, photo, button, icons, shapes, a ruled table, Hindi text."""
    c = Canvas(1200, 1600, gradient(1200, 1600, (252, 246, 236), (250, 226, 210)))
    c.text((600, 130), "Summer Music Festival", "Montserrat", 76, "#8B1E3F", weight=800, align="center")
    c.text((600, 190), "Live in the city park, 12 to 14 July 2026", "Lato", 32, "#333333", align="center")
    c.line((80, 230), (1120, 230), "#8B1E3F", 4)
    c.photo((60, 270, 580, 630), seed=3)
    c.paragraph(620, 300, ["Three days of open-air concerts,", "food stalls and workshops for", "all ages. Bring a blanket,",
                           "meet friends and enjoy the", "longest evenings of the year."],
                "Open Sans", 26, "#222222", leading=1.45)
    c.rect((620, 540, 1000, 620), fill="#1E5AA8", radius=24)
    c.text((810, 592), "Book tickets", "Poppins", 32, "#FFFFFF", weight=700, align="center")
    c.star(1080, 580, 44, "#F2A900")
    c.badge(1080, 720, 44, "#2E8B57", "#FFFFFF")
    c.ellipse((620, 680, 780, 760), fill="#FFD7C2")
    c.rect((820, 680, 1000, 760), outline="#8B1E3F", width=5)
    c.text((600, 860), "संगीत महोत्सव में आपका स्वागत है", "Noto Sans Devanagari", 40, "#5A2A82", align="center")
    c.table(80, 920, [300, 360, 380], 64, [["Day", "Stage", "Headliner"], ["Friday", "Lakeside", "The Night Owls"],
                                           ["Saturday", "Main field", "Aurora Quartet"], ["Sunday", "Garden", "Kids Choir"]],
            "Roboto", 26)
    c.paragraph(600, 1330, ["Free entry for children under twelve.", "Gates open at 4 pm every day."],
                "Lato", 28, "#333333", align="center", leading=1.5)
    c.text((600, 1520), "Tickets at the gate or online", "Playfair Display", 30, "#555555", italic=True, align="center")
    return c.save(out / "poster.png")


def certificate(out: Path) -> tuple[Path, dict]:
    """A certificate: double border, script title, display name, serif body, signature line."""
    c = Canvas(1100, 780, "#FBF8EF")
    c.rect((24, 24, 1076, 756), outline="#7A5C1E", width=6)
    c.rect((44, 44, 1056, 736), outline="#C9A74A", width=2)
    c.text((550, 190), "Certificate of Achievement", "Great Vibes", 72, "#7A5C1E", align="center")
    c.text((550, 270), "This is presented to", "Lora", 26, "#444444", align="center")
    c.text((550, 360), "ANANYA SHARMA", "Cinzel", 52, "#1F2D4A", weight=700, align="center")
    c.paragraph(550, 440, ["for outstanding work in the regional", "science fair, held on 5 March 2026."],
                "Lora", 26, "#444444", align="center", leading=1.5)
    c.line((140, 640), (440, 640), "#444444", 2)
    c.line((660, 640), (960, 640), "#444444", 2)
    c.text((290, 680), "Director", "Lora", 22, "#444444", align="center")
    c.text((810, 680), "Date", "Lora", 22, "#444444", align="center")
    c.badge(550, 640, 46, "#C9A74A", "#FBF8EF")
    return c.save(out / "certificate.png")


def scanned_page(out: Path) -> tuple[Path, dict]:
    """A printed page scanned slightly crooked with sensor noise (deskew and denoise must handle it)."""
    c = Canvas(1240, 1754, "#FFFFFF")
    c.text((110, 180), "Annual Report", "Tinos", 56, "#000000", weight=700)
    c.paragraph(110, 260, ["The committee met four times this year and", "approved the new reading room, the summer",
                           "programme and the budget for repairs to the", "east wing. Membership grew by twelve percent."],
                "Tinos", 30, "#111111", leading=1.5)
    c.table(110, 520, [340, 300, 300], 60, [["Item", "2025", "2026"], ["Members", "1,240", "1,389"],
                                            ["Events", "36", "41"]], "Tinos", 28, header_fill=None)
    img = c.img.rotate(1.6, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="#FFFFFF")
    rng = np.random.default_rng(7)
    arr = np.asarray(img, np.float32) + rng.normal(0, 9, (img.height, img.width, 1))
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    path = out / "scan.png"
    img.save(path, dpi=(150, 150))
    truth = {"size": list(img.size), "elements": c.truth, "rotation": 1.6, "noise": 9}
    path.with_suffix(".truth.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False), encoding="utf-8")
    return path, truth


def small_screenshot(out: Path) -> tuple[Path, dict]:
    """A low-resolution UI screenshot (13 px text): the case for super-resolution."""
    c = Canvas(420, 300, "#F4F6FA")
    c.rect((0, 0, 420, 44), fill="#243B6B")
    c.text((16, 28), "Settings", "Inter", 18, "#FFFFFF", weight=600)
    c.text((16, 80), "Notifications", "Inter", 14, "#1A1A1A", weight=600)
    c.text((16, 102), "Email me when a report is ready", "Inter", 13, "#555555")
    c.rect((16, 130, 404, 170), fill="#FFFFFF", outline="#C8CFDB", width=1, radius=6)
    c.text((28, 155), "name@example.com", "Inter", 13, "#333333")
    c.rect((16, 190, 140, 226), fill="#2F6FEB", radius=6)
    c.text((78, 213), "Save", "Inter", 14, "#FFFFFF", weight=600, align="center")
    return c.save(out / "small.png")


BUILDERS = {"poster": poster, "certificate": certificate, "scan": scanned_page, "small": small_screenshot}


def build(out: Path, which: list[str] | None = None) -> dict[str, tuple[Path, dict]]:
    out.mkdir(parents=True, exist_ok=True)
    return {k: b(out) for k, b in BUILDERS.items() if which is None or k in which}


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    for k, (p, t) in build(Path(sys.argv[1] if len(sys.argv) > 1 else "samples/design")).items():
        print(k, p, len(t["elements"]), "elements")
