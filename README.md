# Offline Toolkit

A fully offline desktop app for **personal use (not for redistribution)**. Electron + React + TypeScript run the interface, and a local Python worker does the image and document work. Your files never leave the computer.

| Module | What it does | Status |
|---|---|---|
| 1. Image Resizer | Exact pixels or physical size at any DPI, crop/pad/stretch, target file size (e.g. 20–50 KB), DPI written into the file, presets, batch + ZIP | **Done (Phase 1)** |
| 2. Document Converter | PDF, PDF/A-1b/2b/3b, DOCX/DOC, XLSX/XLS, PPTX/PPT, HTML, TXT, EPUB, PNG, JPEG, SVG in every direction, OCR for scans, veraPDF-validated PDF/A, each job verified with a report | **Done (Phase 2)** |
| 3. Image to Editable Design | Any picture (poster, screenshot, scan, certificate, infographic, ID card) becomes separate editable layers: live text in the closest bundled font, native shapes, traced vector graphics, photos, real tables, on a cleaned background. Built-in editor; export to PowerPoint, Word, layered SVG, editable HTML and a project file | **Done (Phase 3)** |
| 4. Passport Photo Maker | 4-step wizard: browse, crop, passport sizing with offline face detection and compliance hints, background replacement, adjustments, then a photo at exact size and DPI or a print sheet (PDF at exact scale, JPG/PNG at 300/600 DPI, cut marks, several people) | **Done (Phase 4)** |
| Installer, portable ZIP, merged home screen | | Phase 5 |

Design documents: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/ENGINES.md](docs/ENGINES.md) · [docs/CONVERSION_MATRIX.md](docs/CONVERSION_MATRIX.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md)

## Download (Windows 10/11, 64-bit)

Get the latest build from the **[Releases page](https://github.com/penpaper0878/offline-toolkit/releases)**:

- **`Offline-Toolkit-Setup-<version>.exe`**: installer. It installs for your user only (`%LOCALAPPDATA%\Programs\Offline Toolkit`), needs no admin rights, and adds Start-menu and desktop shortcuts.
- **`Offline-Toolkit-<version>-portable-win-x64.zip`**: portable. Unzip anywhere (e.g. a USB stick) and run `Offline Toolkit.exe`. Settings, presets and logs stay in a `data` folder next to it.

The download is large because LibreOffice, Pandoc, Ghostscript, Tesseract and a Java runtime for veraPDF (Module 2), 73 open-source font families plus two small AI models (Module 3), and two face models (Module 4) are bundled, so everything works without installing anything. The builds are made and smoke-tested on a Windows machine by `.github/workflows/release.yml`. Python and every library are bundled, so nothing else needs installing. The app is not code-signed, so on first start Windows SmartScreen may say *"Windows protected your PC"*: choose **More info → Run anyway**.

To build it yourself on Windows: `npm ci`, then `npm run dist:win` (needs Python 3.11 and the internet once). The output lands in `dist\`.

## Run it (development)

Prerequisites: **Node.js 22+** and **Python 3.11+** (from python.org on Windows). Setup needs the internet once, to install packages; the app itself never uses it.

```bash
npm ci                 # JavaScript dependencies (Electron itself downloads on first start)
npm run setup:py       # creates worker/.venv and installs the Python worker's packages
npm run build          # builds the app into out/
npm start              # runs the built app
```

**Conversion engines (Module 2) in development.** The converter needs LibreOffice, Pandoc, Ghostscript, Tesseract, Java + veraPDF and resvg. The app looks in `engines/<platform>/` first (or `OTK_ENGINES`), then on `PATH`.

- Windows: `python scripts/fetch_engines.py --platform win-x64` fetches all of them into `engines\win-x64\` (uses Chocolatey for LibreOffice, Ghostscript, Tesseract and Java; about 1 GB of downloads).
- Windows, for the design module: `node scripts/fetch-fribidi-win.mjs build\fribidi-win`, then add that folder to `PATH`. Pillow needs FriBiDi to shape text (Hindi, Arabic, kerning); the packaged app has it next to its Python.
- Linux: install `libreoffice`, `ghostscript`, `tesseract-ocr` (+ the language packs you want) and a Java runtime with your package manager, then `python3 scripts/fetch_engines.py --platform linux-x64` for Pandoc, veraPDF and resvg.

Settings → *Conversion engines* shows what was found and where.

**Fonts and models (Modules 3 and 4) in development.** Run once (needs the internet; the files are checked against pinned hashes):

```bash
node scripts/run-python.mjs --online scripts/fetch_fonts.py    # 73 families from google/fonts at a pinned commit -> fonts/ (71 MB)
node scripts/run-python.mjs --online scripts/fetch_models.py   # Real-ESRGAN (ONNX), MediaPipe selfie segmenter and face landmarks, YuNet face detector -> models/ (8 MB)
```

`npm run dev` starts the app with hot reload instead. It uses a local Vite dev server, which is the only address the offline guard allows, and only in development.

Linux as root (containers only): Chromium refuses to start sandboxed as root, so pass `--no-sandbox`, e.g. `npx electron . --no-sandbox`. A normal user never needs this.

## Using the Passport Photo Maker

Open it from the side bar or with Ctrl+4. The stepper at the top shows the four steps; *Back* / *Next* (or Ctrl+Enter) move between them, and undo/redo (Ctrl+Z / Ctrl+Shift+Z) covers every change in every step.

1. **Browse.** Open (Ctrl+O), drop or paste (Ctrl+V) a photo: JPG, PNG, WEBP or HEIC. Phone photos are turned upright from their EXIF orientation. The whole photo is shown with zoom (wheel) and pan (drag).
2. **Crop (first stage).** The app finds the face and proposes a loose head-and-shoulders crop. Drag the photo, drag the frame's corners or scroll to zoom; the frame shows the rule-of-thirds grid and its size in pixels. *Shape*: the photo's own shape, 1:1, free, or a custom ratio. *Straighten* ±45° (the crop shrinks so no empty corner appears; `[` `]` turn by 0.1°), flip, *Frame the face*, *Whole photo*. What the crop leaves out is never shown later.
3. **Size & enhance (second stage).**
   - **Photo rules**: UK passport 35×45 mm, Schengen visa 35×45 mm, India passport 4.5×3.5 cm (35×45 mm), Australia passport 35×45 mm, US passport 2×2 in (51×51 mm), China visa 33×48 mm, Canada passport 50×70 mm, and two generic ID sizes (25×35 mm, 3×4 cm) for which no authority's rule was found (marked *unverified*: set the rules of the office you apply to), plus *Custom size*. Each preset shows its pixel size at its DPI, the head size it needs (chin to the top of the head or to the top of the hair, as that authority measures it), where its rules come from and when they were checked. *Edit…* changes a preset for this photo only, saves it as your own preset, or deletes it. Presets live in `presets/passport-specs.json`.
   - **Placement**: the face and its landmarks are found offline and the photo is turned level and scaled so the head is in the middle of the allowed range, centred, with the eye line or the space above the head where the rules ask. Guides show the head-top, eye and chin lines, the centre line and the allowed head band. Drag the photo, scroll to zoom, arrow keys move it by one output pixel (Shift = 10), *Turn* sets the angle; if the top of the head or the chin is measured wrongly, drag the orange or green marker and press *Auto fit*.
   - **Checks**: green, amber or red hints for face found, head size (in mm and as a share of the height), centring, level eyes, eye line and margins where the rules set them, eyes open, enough pixels, whether the photo or the crop fills the frame, background and exposure. They are hints from measuring the photo; an office decides whether it accepts it.
   - **Background**: replace it (white, off-white, light grey, light blue, the colours the chosen authority lists, or any colour) or keep it; *Edge softness*; a *Restore* and an *Erase* brush (size and hardness) to touch up the cut-out.
   - **Adjust**: exposure, brightness, contrast, highlights, shadows, saturation, vibrance, warmth, tint, sharpness, noise reduction, *Auto enhance*, *Auto white balance*, red-eye fix, skin smoothing (off by default, with a warning: many authorities refuse retouched photos), AI upscaling for small photos (Real-ESRGAN, offline; also warned about), a before/after slider and *Reset*.
4. **Finalise.**
   - **Single photo**: JPG, PNG or PDF at the exact size: the pixel size comes from the size and DPI, the DPI is written into the file, and the PDF page is exactly the photo's size in millimetres. For JPG, *Keep the file within a size range* (e.g. 20–240 KB) searches the quality with the Image Resizer's compression engine; the pixel size never changes.
   - **Print sheet**: paper 4×6 in, 5×7 in, A4, A5, Letter or custom, portrait or landscape; *As many photos as fit* or your own rows × columns; margins, gap, cut marks (drawn only in the margins), thin borders. The preview updates live; a grid that does not fit is explained (how much room it needs and how many fit) and cannot be saved. Add other people's photos with *Another person…* and set the copies of each (empty = fill the places left); a photo of another shape is trimmed to fit, never stretched. Save as PDF (exact scale), JPG or PNG at 300 or 600 DPI, or *Print…* (the page is sent at 100% with no margins; still check that the print dialog says *Actual size*).

Print at 100% / *Actual size*, never *Fit to page*, and measure one printed photo before cutting them all. The spec, background, export and sheet settings are remembered.

## Using Image to Design

Open it from the side bar or with Ctrl+3.

1. **Choose a picture** (or drop one into the window): a poster, screenshot, scanned page, infographic, certificate or ID card. Under *Reading options* tick the **languages in the picture** (the same OCR languages as the converter), and choose whether small text is first enlarged with offline super-resolution (*When text is small* by default), whether tilted pictures are straightened and whether scan grain is reduced.
2. **The analysis** (seconds to a minute, cancellable) straightens and cleans the picture, reads every line, finds tables, shapes, lines, icons and photos, matches each text to the closest of the 73 bundled font families (weight, size, colour, alignment and line spacing too), removes everything it rebuilt from the background, and traces icons and logos into vector paths.
3. **The editor** shows the layers (left), the page (centre) and the inspector (right).
   - Click anything to select it (Shift adds to the selection); drag to move (it snaps to edges and centres; hold Alt to move freely), drag the handles to resize or rotate, arrow keys nudge (Shift = 10 px).
   - **Text**: double-click to type in place, or edit in the inspector: content, font (the closest matches are listed first; the list is filtered to fonts that have the text's letters), weight, size, colour, italic, underline, alignment and line spacing.
   - **Pictures**: replace them, or remove the background around a person or the main object (*Restore original* undoes it).
   - **Graphics** (traced icons and logos): recolour each colour, or switch back to the original pixels for gradients.
   - **Shapes**: rectangle, rounded rectangle, ellipse or line, with fill, outline, width and corner radius.
   - **Tables**: edit cells, bold, alignment and fills; add or remove rows and columns.
   - **Layers**: reorder (drag, or the arrows), hide, lock, rename (double-click), duplicate, delete. Add text, shapes and pictures from the toolbar.
4. **Check the result.** *Compare* slides between the original picture and the rebuilt design; *Difference* shows black where they match. The *Check* tab gives a similarity score and marks areas where one side has marks and the other has none, lists words the OCR was unsure of (also outlined in orange on the page), and lists lines it **could not read**: those are left in the picture exactly as they are, never replaced by guessed text. *Known limits* lists what the automation cannot rebuild (handwriting, heavily decorative or distorted lettering, text on curves, gradients in graphics) so you can fix it by hand.
5. **Export** (Ctrl+E):
   - **PowerPoint**: best for editing every element. Text boxes, shapes, freeform graphics (one shape per colour), native tables and pictures on one slide, with the background as the slide background.
   - **Word**: one page of floating text boxes, shapes, graphics, pictures and a native table; the fonts are embedded in the file.
   - **SVG**: one layer per element, text kept as text, fonts embedded.
   - **HTML**: one self-contained page; click any text or table cell to edit it in the browser.
   - **Project file (.otkd)**: the whole design, to open again later or on another computer.
   PowerPoint uses installed fonts: *Install the fonts* (in the export panel) adds this design's fonts for your user, no admin rights needed. *Also save the font files* puts them next to the export for another computer.

Designs are saved automatically and listed on the module's start page. Undo/redo covers every edit.

## Using the Document Converter

Open it from the side bar or with Ctrl+2.

1. **Add documents.** Drag files or a folder into the window, or use **Add files** (Ctrl+O) or **Add folder** (Ctrl+Shift+O). Accepted: PDF (including PDF/A and scans), DOCX, DOC, XLSX, XLS, PPTX, PPT, HTML, TXT, EPUB, PNG, JPEG and SVG. The format is detected from the file's contents, not its name.
2. **Choose the target**: PDF, PDF/A-1b, PDF/A-2b, PDF/A-3b, DOCX, XLSX, PPTX, HTML, TXT, EPUB, PNG, JPEG or SVG. Every file row shows the engine chain that will be used (e.g. *DOCX → LibreOffice → PDF → PDF/A-2b*) and, before you start, **what that route cannot keep** (click the count to see the list).
3. **Choose the fidelity** where it matters:
   - *Exact layout*: same pages, positions, fonts and pictures. PDF → DOCX/PPTX places every line, picture and shape where it was.
   - *Editable*: reflowed text with real headings, lists and tables. Easier to edit; the layout may change.
4. **OCR** (on by default) recognises text in scanned PDFs and photos. Tick the **languages on the page**: English, Hindi, Marathi, Sanskrit, Nepali, Bengali, Gujarati, Punjabi, Tamil, Telugu, Kannada, Malayalam, Odia, Urdu, Arabic and Hebrew are bundled. Scans to PDF/PDF/A get an invisible, searchable text layer over the untouched page images. Words below the confidence threshold are listed in the report.
5. **Options** appear only when they apply to the chosen target:
   - page images: resolution (default 300 DPI) and JPEG quality. A multi-page document becomes one image per page, zipped;
   - page size for HTML, text and EPUB to PDF;
   - speaker-notes pages for PowerPoint to PDF;
   - attach the source file inside a PDF/A-3;
   - PDF/A to plain PDF: copy the file unchanged (default) or remove its PDF/A identification;
   - text to spreadsheet: split lines into cells at tabs; text to slides: lines per slide;
   - compare rendered pages (exact mode): adds the visual check.
6. **Output folder**: chosen once and remembered. Existing files are never overwritten (`name (1).pdf`). Tick **merge** to also get one combined file (PDF with one bookmark per input, DOCX with section breaks, XLSX with sheets renamed on clashes and reported, PPTX, HTML, TXT, EPUB; images are zipped).
7. **Convert** (Ctrl+Enter). Each row shows progress, then a verdict:
   - **Perfect**: every check passed and nothing was changed.
   - **Expected changes**: nothing failed; the report lists what this route changes by design (e.g. pictures dropped in TXT).
   - **Needs review**: at least one check failed. Open the report before using the file.

**The verification report** (`<output>.report.html` and `.json`, saved next to the output) compares the source and the output with independent readers: text (every word, in order), pages/sheets/slides, pictures (pixel hashes), tables and merged cells, links, bookmarks, notes, spreadsheet cells, fonts, the page appearance (SSIM ≥ 0.98) and, for PDF/A, the veraPDF result. A file that fails PDF/A validation is never given a PDF/A name: it is saved as `name.NOT-PDFA.pdf` with the failed clauses in the report.

**Passwords.** Protected PDFs and Office files ask for the password when you start (optionally once for the whole list). Passwords stay in memory for the run only: they are never logged or saved. The output is not protected.

**Cancel and resume.** Esc or *Cancel* stops the batch, and the engines are stopped too. *Resume* (in the progress panel, until you close the app) carries on with the same job: files that finished are not redone, and inside an interrupted file the finished steps are reused after their checksums are confirmed.

## Using the Image Resizer

1. **Add images.** Drag files or a folder anywhere into the window, or use **Add images** (Ctrl+O) or **Add folder** (Ctrl+Shift+O). JPG, PNG, WEBP, BMP, TIFF and HEIC are supported, and EXIF orientation is applied automatically.
2. **Pick a preset**, or set the size yourself.
   - **Width, height and unit** (px / cm / mm / inch), plus **DPI** (72–1200, default 200). The panel shows both directions live, with the rounding error. Example: *3 cm @ 200 DPI = 236.22 px → 236 px (−0.22 px, −0.028 mm)*.
   - **When DPI changes, keep**: *exact pixels* (the physical size follows) or *exact physical size* (the pixels follow).
   - The lock keeps the width/height ratio. "Use the image's proportions" copies the source's ratio.
3. **Choose a fit.**
   - *Crop to fill*: drag or resize the crop window. Arrow keys move it by 1 px, Shift+arrow by 10 px.
   - *Fit with padding*: choose the padding colour.
   - *Stretch*: the change in proportions is shown.
4. **Format and file size.** Choose JPG, PNG or WEBP and, optionally, a min–max size in KB or MB. The app searches quality, chroma subsampling and encoder options to land in the range. It **never changes the dimensions**:
   - If the range can't be reached, it says so, with the smallest possible size and suggested dimensions or formats that would fit. Nothing changes unless you click one.
   - *Pad to minimum size* (off by default) adds a harmless comment block when even the best quality is still below the minimum.
5. **Check the result.** *Before / after* compares the source with the real encoded file, with zoom (up to 800%) and a split slider. Below it you see the exact pixels, the physical size, where the DPI is stored (JFIF + EXIF for JPEG, pHYs for PNG, EXIF for WEBP), the size in KB and bytes, the encoder settings and an SSIM similarity score.
6. **Process** (Ctrl+Enter) writes every image to the output folder. Existing files are never overwritten (`name (1).jpg`). A results table shows each file, and a ZIP is made if you ask for one.

**Presets** can be saved, updated, renamed, deleted, imported and exported. They are stored as editable JSON in your data folder (`presets/resizer.json`). The built-in presets include:

- "Photo 240×240 px @200 DPI (about 3×3 cm)"
- "Signature 140×60 px"
- "Photo 3×3 cm @200 DPI"
- "Print 10×15 cm @300 DPI"
- "Web 1920×1080 WEBP"

### Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 | Image Resizer / Document Converter / Image to Design / Passport Photo |
| Ctrl+O / Ctrl+Shift+O | Add files / add a folder |
| Ctrl+Enter | Process all images / convert all documents |
| Esc | Cancel the running conversion |
| Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z) | Undo / redo size, format and crop changes (resizer) or target and option changes (converter) |
| + / − / 0 / 1 | Zoom in / out / fit / 100% |
| ↑ / ↓ | Previous / next image |
| Delete | Remove the selected image from the list |
| Arrow keys in the crop window | Move the crop window (Shift = 10 px) |
| Ctrl+L / Ctrl+, | Event log / settings |

In the design editor:

| Keys | Action |
|---|---|
| Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) | Undo / redo |
| T | Add a text box |
| Enter / double-click | Type into the selected text |
| Ctrl+Enter / Esc (while typing) | Finish / cancel typing |
| Arrow keys (Shift = 10 px) | Move the selection |
| Ctrl+D / Delete | Duplicate / delete the selection |
| Ctrl+] / Ctrl+[ | Bring forward / send backward |
| Ctrl+wheel, Ctrl++ / Ctrl+− / Ctrl+0 | Zoom / fit |
| Wheel, Shift+wheel, Space+drag | Pan |
| Ctrl+S / Ctrl+E | Save now / export |
| Esc | Clear the selection |

In the passport wizard:

| Keys | Action |
|---|---|
| Ctrl+O / Ctrl+V | Open / paste a photo |
| Ctrl+Enter | Next step |
| Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y) | Undo / redo |
| Arrow keys (Shift = 10) | Move the crop (step 2, source pixels) or the photo in the frame (step 3, output pixels) |
| `[` / `]` | Straighten by −0.1° / +0.1° (step 2) |
| Wheel | Zoom |

### Your data

| | Windows | Portable ZIP |
|---|---|---|
| Settings, presets, logs | `%APPDATA%\Offline Toolkit\` | `data\` next to the exe |
| Converter work folders (deleted when every file in the batch succeeded; kept for *Resume* otherwise) | `%APPDATA%\Offline Toolkit\cache\jobs\` | `data\cache\jobs\` |
| Designs (one folder each: layers, pictures, analysis cache; delete them from the module's start page) | `%APPDATA%\Offline Toolkit\designs\` | `data\designs\` |
| Passport presets: `presets\passport-specs.json`, `presets\paper-sizes.json` (with the other presets) | `%APPDATA%\Offline Toolkit\presets\` | `data\presets\` |
| Passport previews and pasted photos (temporary) | `%APPDATA%\Offline Toolkit\cache\previews\passport\` | `data\cache\previews\passport\` |

Settings → *Your data* shows the exact paths. The JSON files are validated when the app starts. An invalid file is reported and the built-in default is used, and your file is never overwritten.

## Tests

```bash
npm run typecheck      # TypeScript (main, preload, renderer)
npm test               # vitest: units maths (shared vectors with Python), crop maths, undo/redo, schemas
npm run test:py        # pytest: resizer, RPC, network guard, converter, design (ground-truth samples, exports drawn back and compared),
                       #         passport (face measurements, every preset fitted, exact px/DPI/mm, reference pictures)
OTK_FULL_MATRIX=1 npm run test:py -- worker/tests/test_converter_matrix.py   # every conversion route (~270, about an hour)
npm run test:e2e       # Playwright drives the real Electron app with the real Python worker
npm run test:offline   # Linux: pytest + end-to-end inside a network namespace with no network interfaces
```

The converter tests print HTML to PDF with the project's Electron. Run `node -e "require('electron')"` once after `npm ci` so its binary is present (tests that need it are skipped otherwise).

Results from the last run, including what could not be run here, are in [docs/TEST_REPORT.md](docs/TEST_REPORT.md). CI runs the same tests on Ubuntu and Windows (`.github/workflows/ci.yml`).

## Troubleshooting

- **"The Python worker could not start"**: run `npm run setup:py`. Settings → Diagnostics shows which Python the app uses. Set `OTK_PYTHON` to point at a specific interpreter.
- **Windows SmartScreen** on first run of an unsigned build: choose *More info → Run anyway*.
- **A preset or settings file error at start-up**: the message names the file and the field. Fix the JSON or delete the file to get the defaults back.
- **HEIC files don't open**: check Diagnostics shows "HEIC yes". The `pi-heif` package provides decoding.
- **"Engine missing: LibreOffice" (or another engine)** in a development run: see *Conversion engines* above. Settings → *Conversion engines* lists what was found.
- **A conversion says "Needs review"**: open the report (the row's details button). It names the check that failed, with the missing or extra text, the page that looks different or the PDF/A clause.
- **Fonts substituted**: the report's *Fonts* check names each one. Metric-compatible substitutes (Calibri → Carlito, Cambria → Caladea, Arial → Liberation Sans) keep the line breaks; others may not. On Windows, installed Microsoft fonts are used when present.
- **The app was closed or crashed during a conversion**: convert the files again. *Resume* only lasts for the session; the work folders left behind can be deleted (see *Your data*).
- **A line of text was not read** (Image to Design, *Check → Not read*): it is in a language that was not ticked. Tick it under *Reading options* and analyse the picture again, or type the text into a new text box over it.
- **PowerPoint shows a different font**: install the design's fonts (*Export → Install the fonts*) and restart PowerPoint. Word files carry their fonts inside.
- **"Suspension not allowed here" in a terminal**: harmless libjpeg message. The encoder retries with a bigger buffer.

## Project layout

```
src/main/        Electron main: offline guard, otk:// protocol, worker pool, settings/presets store, IPC, self-test
src/preload/     the typed window.otk bridge (sandboxed)
src/renderer/    React UI (modules/resizer, modules/converter, modules/design, modules/passport, pages, components)
src/shared/      TypeScript shared by all three (units, crop geometry, the design scene and its geometry, types)
worker/          Python worker: JSON-RPC over stdio, resizer engine, converter (planner, steps, PDF/A, OCR, verification),
                 design (analysis pipeline, exporters, verification), passport (face, matte, sizing, sheets), tests
scripts/         Python setup, Windows Python bundling, engine, font and model fetching, the standalone PDF printer
resources/       JSON schemas and shipped defaults (settings, presets, conversion routes)
tests/           shared test vectors and Playwright end-to-end tests
fonts/, models/  Module 3 assets (fetched, not in git)
docs/            architecture, engines and licences, conversion matrix, test report
```
