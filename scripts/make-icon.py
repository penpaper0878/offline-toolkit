"""Draw the app icon (build/icon.png 1024 px + build/icon.ico 16-256 px).

A blue rounded square with a white shield and a diagonal resize arrow.
Run: worker/.venv/bin/python scripts/make-icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
OUT = Path(__file__).resolve().parents[1] / "build"


def draw(size: int = S) -> Image.Image:
    k = 4  # supersample for smooth edges
    n = size * k
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(n * 0.04)
    top, bottom = (47, 111, 237), (31, 76, 184)
    for y in range(pad, n - pad):  # vertical gradient inside the rounded square
        t = (y - pad) / (n - 2 * pad)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(pad, y), (n - pad, y)], fill=c + (255,))
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, n - pad, n - pad], radius=int(n * 0.22), fill=255)
    img.putalpha(mask)
    w = int(n * 0.055)
    white = (255, 255, 255, 255)
    # Shield outline.
    cx = n / 2
    shield = [(cx, n * 0.17), (n * 0.78, n * 0.28), (n * 0.76, n * 0.55), (cx, n * 0.84), (n * 0.24, n * 0.55), (n * 0.22, n * 0.28)]
    # Start and end mid-edge so the seam sits on a straight line, not a corner.
    seam = ((shield[-1][0] + shield[0][0]) / 2, (shield[-1][1] + shield[0][1]) / 2)
    d.line([seam] + shield + [seam], fill=white, width=w, joint="curve")
    # Diagonal resize arrow inside the shield.
    a, b = (n * 0.41, n * 0.58), (n * 0.60, n * 0.39)
    d.line([a, b], fill=white, width=w)
    h = n * 0.085
    d.line([(b[0] - h, b[1]), b, (b[0], b[1] + h)], fill=white, width=w, joint="curve")
    d.line([(a[0] + h, a[1]), a, (a[0], a[1] - h)], fill=white, width=w, joint="curve")
    return img.resize((size, size), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    big = draw(S)
    big.save(OUT / "icon.png")
    big.save(OUT / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT / "icon.png", OUT / "icon.ico")
