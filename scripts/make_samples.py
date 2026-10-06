#!/usr/bin/env python3
"""Make the sample files: samples/ (one folder per module, with a README) and the small set the app bundles in
resources/samples/ for "Try a sample" on the home screen.

    node scripts/run-python.mjs scripts/make_samples.py            # or: npm run samples

Everything is drawn by the test generators (worker/tests/corpus.py, design_samples.py, imagegen.py), so the samples
are the same files the tests use, and need nothing from the internet. The two portraits are public-domain photos
(worker/tests/fixtures/faces/ATTRIBUTION.md).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker" / "tests"))
sys.path.insert(0, str(ROOT / "worker"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import corpus  # noqa: E402
import design_samples  # noqa: E402
import imagegen  # noqa: E402

FACES = ROOT / "worker" / "tests" / "fixtures" / "faces"
OUT = ROOT / "samples"
BUNDLED = ROOT / "resources" / "samples"


def resizer(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    s = {}
    # A camera photo stored sideways with an EXIF orientation tag: the resizer must show and write it upright.
    im = Image.open(FACES / "astronaut-collins.jpg").convert("RGB").resize((1536, 1536), Image.Resampling.LANCZOS)
    im = im.crop((192, 0, 1344, 1536))      # 1152 × 1536, upright; stored as 1536 × 1152
    exif = Image.Exif()
    exif[0x0112] = 6                        # rotate 90° clockwise to display
    exif[0x010F] = "Sample camera"
    im.transpose(Image.Transpose.ROTATE_90).save(out / "camera-photo-rotated.jpg", quality=90, exif=exif, dpi=(72, 72))
    s["rotated"] = out / "camera-photo-rotated.jpg"
    # A large landscape for size targets (12 MP).
    Image.fromarray(imagegen.photo_array(4000, 3000, seed=7)).save(out / "landscape-12mp.jpg", quality=85)
    s["large"] = out / "landscape-12mp.jpg"
    # A logo with a transparent background: JPEG output puts it on white, PNG and WEBP keep it.
    logo = Image.new("RGBA", (800, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.rounded_rectangle((20, 20, 780, 380), radius=60, fill=(30, 110, 200, 255))
    d.ellipse((60, 80, 300, 320), fill=(255, 200, 40, 255))
    d.rectangle((340, 150, 740, 250), fill=(255, 255, 255, 230))
    logo.save(out / "logo-transparent.png")
    s["logo"] = out / "logo-transparent.png"
    shutil.copyfile(ROOT / "worker" / "tests" / "fixtures" / "quadrants.heic", out / "phone-photo.heic")
    s["heic"] = out / "phone-photo.heic"
    return s


def passport(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FACES / "portrait-souza.jpg", out / "portrait.jpg")
    shutil.copyfile(FACES / "astronaut-collins.jpg", out / "portrait-small.jpg")
    shutil.copyfile(FACES / "ATTRIBUTION.md", out / "ATTRIBUTION.md")
    return {"portrait": out / "portrait.jpg", "small": out / "portrait-small.jpg"}


def converter(out: Path) -> dict[str, Path]:
    # No LibreOffice needed: the legacy .doc/.xls/.ppt and PDF/A samples come from it, so they are left out.
    return corpus.build(out, legacy=False, pdfa=False)


def design(out: Path) -> dict[str, Path]:
    made = design_samples.build(out)
    for truth in out.glob("*.truth.json"):
        truth.unlink()                      # the tests' answer keys, not samples
    return {k: v[0] for k, v in made.items()}


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    made = {"resizer": resizer(OUT / "resizer"), "converter": converter(OUT / "converter"),
            "design": design(OUT / "design"), "passport": passport(OUT / "passport")}
    (OUT / "README.md").write_text(README.format(password=corpus.PASSWORD), encoding="utf-8")

    # The bundled set for "Try a sample": one small file per module (resources/samples/<module>/).
    shutil.rmtree(BUNDLED, ignore_errors=True)
    pick = {"resizer": made["resizer"]["rotated"], "converter": made["converter"]["docx"],
            "design": made["design"]["poster"], "passport": made["passport"]["portrait"]}
    for module, src in pick.items():
        (BUNDLED / module).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, BUNDLED / module / src.name)
    shutil.copyfile(FACES / "ATTRIBUTION.md", BUNDLED / "passport" / "ATTRIBUTION.md")
    shutil.copyfile(FACES / "ATTRIBUTION.md", BUNDLED / "resizer" / "ATTRIBUTION.md")

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    bundled = sum(f.stat().st_size for f in BUNDLED.rglob("*") if f.is_file())
    print(f"[samples] {sum(len(v) for v in made.values())} files, {total / 1e6:.1f} MB in {OUT}; "
          f"bundled set {bundled / 1e6:.2f} MB in {BUNDLED}")
    for module, files in made.items():
        print(f"[samples]   {module}: {', '.join(sorted(p.name for p in files.values()))}")


README = """# Sample files

Ready-made files for trying every module. They are drawn by the same generators the tests use
(`node scripts/run-python.mjs scripts/make_samples.py` makes them again). Nothing here is needed to build or run
the app; the home screen's **Try a sample** buttons use a smaller copy bundled with the app.

## resizer/ (Image Resizer & Compressor)

| File | Try |
|---|---|
| `camera-photo-rotated.jpg` | Stored sideways with an EXIF "rotate 90°" tag. The preview and the output are upright. Pick the *Photo 3×3 cm @200 DPI* preset, or type any size in cm, inches or pixels. |
| `landscape-12mp.jpg` | 4000 × 3000 px, about 3 MB. Set *Max file size* to 200 KB and see the quality the app chooses. |
| `logo-transparent.png` | Transparent background. Saved as JPEG it goes on white; PNG and WEBP keep the transparency. |
| `phone-photo.heic` | A small HEIC (iPhone format) picture. |

## converter/ (Document Converter)

| File | Try |
|---|---|
| `report.docx` | Word with headings, a table, a picture, Hindi and Arabic. Convert to PDF/A-2b: the report shows veraPDF's verdict. |
| `sales.xlsx`, `slides.pptx` | Excel and PowerPoint to PDF. |
| `page.html`, `notes.txt`, `drawing.svg`, `book.epub` | HTML, text (Unicode, Indic and right-to-left lines), SVG and EPUB. |
| `document.pdf` | A born-digital PDF: to Word (editable), to images, to text. |
| `scan-page.png`, `scan-photo.jpg`, `scanned.pdf` | Scans for OCR (searchable PDF, Word, text). |
| `locked.pdf`, `locked.docx` | Password-protected. The password is `{password}`; the app asks for it and never saves it. |
| `office.png` | The picture used inside the documents. |

## design/ (Image to Editable Design)

| File | Try |
|---|---|
| `poster.png` | A festival poster: headline, paragraph, photo, button, icons, shapes, a table and Hindi text. Every element becomes an editable layer; export to SVG, PDF, Word or PowerPoint. |
| `certificate.png` | Borders, a script title and serif text: font matching. |
| `scan.png` | A page scanned slightly crooked with noise: deskew and clean-up. |
| `small.png` | A low-resolution screenshot (13 px text): the case for super-resolution. |

## passport/ (Passport Photo Maker)

| File | Try |
|---|---|
| `portrait.jpg` | Pick a country (UK, Schengen, India, US...): the face is found, the crop sized to the rules, the background made plain, and a print sheet laid out. |
| `portrait-small.jpg` | 512 × 512 px: too few pixels for a 300 DPI passport photo. The check says so ("Enlarged 2.5× (too few pixels)" for the UK) and offers AI upscaling. |

Both portraits are in the public domain: see `passport/ATTRIBUTION.md`.
"""

if __name__ == "__main__":
    main()
