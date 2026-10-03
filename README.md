# Offline Toolkit

A fully offline desktop app for **personal use (not for redistribution)**. Electron + React + TypeScript run the interface, and a local Python worker does the image and document work. Your files never leave the computer.

| Module | What it does | Status |
|---|---|---|
| 1. Image Resizer | Exact pixels or physical size at any DPI, crop/pad/stretch, target file size (e.g. 20–50 KB), DPI written into the file, presets, batch + ZIP | **Done (Phase 1)** |
| 2. Document Converter | PDF, PDF/A-1b/2b/3b, DOCX/DOC, XLSX/XLS, PPTX/PPT, HTML, TXT, EPUB, PNG, JPEG, SVG in every direction, OCR for scans, veraPDF-validated PDF/A, each job verified with a report | **Done (Phase 2)** |
| 3. Image to Editable Design | Any picture (poster, screenshot, scan, certificate, infographic, ID card) becomes separate editable layers: live text in the closest bundled font, native shapes, traced vector graphics, photos, real tables, on a cleaned background. Built-in editor; export to PowerPoint, Word, layered SVG, editable HTML and a project file | **Done (Phase 3)** |
| 4. Passport Photo Maker | 4-step wizard: crop, face-guided sizing, background, print sheets | Phase 4 |
| Installer, portable ZIP, merged home screen | | Phase 5 |

Design documents: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/ENGINES.md](docs/ENGINES.md) · [docs/CONVERSION_MATRIX.md](docs/CONVERSION_MATRIX.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md)

## Download (Windows 10/11, 64-bit)

Get the latest build from the **[Releases page](https://github.com/penpaper0878/offline-toolkit/releases)**:

- **`Offline-Toolkit-Setup-<version>.exe`**: installer. It installs for your user only (`%LOCALAPPDATA%\Programs\Offline Toolkit`), needs no admin rights, and adds Start-menu and desktop shortcuts.
- **`Offline-Toolkit-<version>-portable-win-x64.zip`**: portable. Unzip anywhere (e.g. a USB stick) and run `Offline Toolkit.exe`. Settings, presets and logs stay in a `data` folder next to it.

The download is large because LibreOffice, Pandoc, Ghostscript, Tesseract and a Java runtime for veraPDF (Module 2), and 73 open-source font families plus two small AI models (Module 3) are bundled, so everything works without installing anything. The builds are made and smoke-tested on a Windows machine by `.github/workflows/release.yml`. Python and every library are bundled, so nothing else needs installing. The app is not code-signed, so on first start Windows SmartScreen may say *"Windows protected your PC"*: choose **More info → Run anyway**.

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
- Linux: install `libreoffice`, `ghostscript`, `tesseract-ocr` (+ the language packs you want) and a Java runtime with your package manager, then `python3 scripts/fetch_engines.py --platform linux-x64` for Pandoc, veraPDF and resvg.

Settings → *Conversion engines* shows what was found and where.

**Fonts and models (Module 3) in development.** Run once (needs the internet; the files are checked against pinned hashes):

```bash
node scripts/run-python.mjs scripts/fetch_fonts.py    # 73 families from google/fonts at a pinned commit -> fonts/ (71 MB)
node scripts/run-python.mjs scripts/fetch_models.py   # Real-ESRGAN (converted to ONNX) and MediaPipe selfie segmenter -> models/ (5 MB)
```

`npm run dev` starts the app with hot reload instead. It uses a local Vite dev server, which is the only address the offline guard allows, and only in development.

Linux as root (containers only): Chromium refuses to start sandboxed as root, so pass `--no-sandbox`, e.g. `npx electron . --no-sandbox`. A normal user never needs this.

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
| Ctrl+1 / Ctrl+2 / Ctrl+3 | Image Resizer / Document Converter / Image to Design |
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

### Your data

| | Windows | Portable ZIP |
|---|---|---|
| Settings, presets, logs | `%APPDATA%\Offline Toolkit\` | `data\` next to the exe |
| Converter work folders (deleted when every file in the batch succeeded; kept for *Resume* otherwise) | `%APPDATA%\Offline Toolkit\cache\jobs\` | `data\cache\jobs\` |
| Designs (one folder each: layers, pictures, analysis cache; delete them from the module's start page) | `%APPDATA%\Offline Toolkit\designs\` | `data\designs\` |

Settings → *Your data* shows the exact paths. The JSON files are validated when the app starts. An invalid file is reported and the built-in default is used, and your file is never overwritten.

## Tests

```bash
npm run typecheck      # TypeScript (main, preload, renderer)
npm test               # vitest: units maths (shared vectors with Python), crop maths, undo/redo, schemas
npm run test:py        # pytest: resizer, RPC, network guard, converter, design (ground-truth samples, exports drawn back and compared)
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
src/renderer/    React UI (modules/resizer, modules/converter, modules/design, pages, components)
src/shared/      TypeScript shared by all three (units, crop geometry, the design scene and its geometry, types)
worker/          Python worker: JSON-RPC over stdio, resizer engine, converter (planner, steps, PDF/A, OCR, verification),
                 design (analysis pipeline, exporters, verification), tests
scripts/         Python setup, Windows Python bundling, engine, font and model fetching, the standalone PDF printer
resources/       JSON schemas and shipped defaults (settings, presets, conversion routes)
tests/           shared test vectors and Playwright end-to-end tests
fonts/, models/  Module 3 assets (fetched, not in git)
docs/            architecture, engines and licences, conversion matrix, test report
```
