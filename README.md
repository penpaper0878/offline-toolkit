# Offline Toolkit

A fully offline desktop app for **personal use (not for redistribution)**. Electron + React + TypeScript run the interface, and a local Python worker does the image and document work. Your files never leave the computer.

| Module | What it does | Status |
|---|---|---|
| 1. Image Resizer | Exact pixels or physical size at any DPI, crop/pad/stretch, target file size (e.g. 20–50 KB), DPI written into the file, presets, batch + ZIP | **Done (Phase 1)** |
| 2. Document Converter | PDF, PDF/A-1b/2b/3b, DOCX/DOC, XLSX/XLS, PPTX/PPT, HTML, TXT, EPUB, PNG, JPEG, SVG in every direction, each job verified | Phase 2 (route planner done) |
| 3. Image to Editable Design | OCR, layout analysis and clean-up into a layered, editable document | Phase 3 |
| 4. Passport Photo Maker | 4-step wizard: crop, face-guided sizing, background, print sheets | Phase 4 |
| Installer, portable ZIP, merged home screen | | Phase 5 |

Design documents: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/ENGINES.md](docs/ENGINES.md) · [docs/CONVERSION_MATRIX.md](docs/CONVERSION_MATRIX.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md)

## Download (Windows 10/11, 64-bit)

Get the latest build from the **[Releases page](https://github.com/penpaper0878/offline-toolkit/releases)**:

- **`Offline-Toolkit-Setup-<version>.exe`**: installer. It installs for your user only (`%LOCALAPPDATA%\Programs\Offline Toolkit`), needs no admin rights, and adds Start-menu and desktop shortcuts.
- **`Offline-Toolkit-<version>-portable-win-x64.zip`**: portable. Unzip anywhere (e.g. a USB stick) and run `Offline Toolkit.exe`. Settings, presets and logs stay in a `data` folder next to it.

The builds are made and smoke-tested on a Windows machine by `.github/workflows/release.yml`. Python and every library are bundled, so nothing else needs installing. The app is not code-signed, so on first start Windows SmartScreen may say *"Windows protected your PC"*: choose **More info → Run anyway**.

To build it yourself on Windows: `npm ci`, then `npm run dist:win` (needs Python 3.11 and the internet once). The output lands in `dist\`.

## Run it (development)

Prerequisites: **Node.js 22+** and **Python 3.11+** (from python.org on Windows). Setup needs the internet once, to install packages; the app itself never uses it.

```bash
npm ci                 # JavaScript dependencies (downloads Electron)
npm run setup:py       # creates worker/.venv and installs the Python worker's packages
npm run build          # builds the app into out/
npm start              # runs the built app
```

`npm run dev` starts the app with hot reload instead. It uses a local Vite dev server, which is the only address the offline guard allows, and only in development.

Linux as root (containers only): Chromium refuses to start sandboxed as root, so pass `--no-sandbox`, e.g. `npx electron . --no-sandbox`. A normal user never needs this.

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
| Ctrl+O / Ctrl+Shift+O | Add images / add a folder |
| Ctrl+Enter | Process all images |
| Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z) | Undo / redo size, format and crop changes |
| + / − / 0 / 1 | Zoom in / out / fit / 100% |
| ↑ / ↓ | Previous / next image |
| Delete | Remove the selected image from the list |
| Arrow keys in the crop window | Move the crop window (Shift = 10 px) |
| Ctrl+L / Ctrl+, | Event log / settings |

### Your data

| | Windows | Portable ZIP |
|---|---|---|
| Settings, presets, logs | `%APPDATA%\Offline Toolkit\` | `data\` next to the exe |

Settings → *Your data* shows the exact paths. The JSON files are validated when the app starts. An invalid file is reported and the built-in default is used, and your file is never overwritten.

## Tests

```bash
npm run typecheck      # TypeScript (main, preload, renderer)
npm test               # vitest: units maths (shared vectors with Python), crop maths, undo/redo, schemas
npm run test:py        # pytest: units, loading, fit modes, DPI metadata, size targeting, batch, RPC, network guard
npm run test:e2e       # Playwright drives the real Electron app with the real Python worker
npm run test:offline   # Linux: pytest + end-to-end inside a network namespace with no network interfaces
```

Results from the last run, including what could not be run here, are in [docs/TEST_REPORT.md](docs/TEST_REPORT.md). CI runs the same tests on Ubuntu and Windows (`.github/workflows/ci.yml`).

## Troubleshooting

- **"The Python worker could not start"**: run `npm run setup:py`. Settings → Diagnostics shows which Python the app uses. Set `OTK_PYTHON` to point at a specific interpreter.
- **Windows SmartScreen** on first run of an unsigned build: choose *More info → Run anyway*.
- **A preset or settings file error at start-up**: the message names the file and the field. Fix the JSON or delete the file to get the defaults back.
- **HEIC files don't open**: check Diagnostics shows "HEIC yes". The `pi-heif` package provides decoding.
- **"Suspension not allowed here" in a terminal**: harmless libjpeg message. The encoder retries with a bigger buffer.

## Project layout

```
src/main/        Electron main: offline guard, otk:// protocol, worker pool, settings/presets store, IPC, self-test
src/preload/     the typed window.otk bridge (sandboxed)
src/renderer/    React UI (modules/resizer, pages, components)
src/shared/      TypeScript shared by all three (units, crop geometry, types)
worker/          Python worker: JSON-RPC over stdio, resizer engine, converter planner, tests
resources/       JSON schemas and shipped defaults (settings, presets, conversion routes)
tests/           shared test vectors and Playwright end-to-end tests
docs/            architecture, engines and licences, conversion matrix, test report
```
