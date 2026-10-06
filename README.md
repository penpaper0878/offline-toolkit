# Offline Toolkit

A fully offline desktop app for **personal use (not for redistribution)**. Electron + React + TypeScript run the interface, and a local Python worker does the image and document work. Your files never leave the computer: there is no cloud, no telemetry and no update check, and Settings → *Run offline self-test* proves that every part of the app is blocked from the network.

| Module | What it does |
|---|---|
| **Home screen** | The four modules on one screen: open any file and it goes to the right module (pictures ask which), drop files on a module, *Try a sample*, recent work across the modules, and the state of the bundled engines, fonts and models |
| 1. Image Resizer & Compressor | Exact pixels or physical size at any DPI, crop/pad/stretch, target file size (e.g. 20–50 KB), DPI written into the file, presets, batch + ZIP |
| 2. Document Converter | PDF, PDF/A-1b/2b/3b, DOCX/DOC, XLSX/XLS, PPTX/PPT, HTML, TXT, EPUB, PNG, JPEG, SVG in every direction, OCR for scans in 16 languages, veraPDF-validated PDF/A, every job verified with a report |
| 3. Image to Editable Design | Any picture (poster, screenshot, scan, certificate, infographic, ID card) becomes separate editable layers: live text in the closest bundled font, native shapes, traced vector graphics, photos, real tables, on a cleaned background. Built-in editor; export to PowerPoint, Word, layered SVG, editable HTML and a project file |
| 4. Passport Photo Maker | 4-step wizard: browse, crop, passport sizing with offline face detection and compliance hints, background replacement, adjustments, then a photo at exact size and DPI or a print sheet (PDF at exact scale, JPG/PNG at 300/600 DPI, cut marks, several people) |

Version 1.0.0 (Phase 5) merges the modules into one app with a shared home screen and ships a Windows installer and a portable ZIP. Design documents: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/ENGINES.md](docs/ENGINES.md) (every bundled component and its licence) · [docs/CONVERSION_MATRIX.md](docs/CONVERSION_MATRIX.md) · [docs/TEST_REPORT.md](docs/TEST_REPORT.md) (what was tested, the results, and what is not covered)

## Download (Windows 10/11, 64-bit)

Get the latest build from the **[Releases page](https://github.com/penpaper0878/offline-toolkit/releases)**:

- **`Offline-Toolkit-Setup-<version>.exe`**: installer. It installs for your user only (`%LOCALAPPDATA%\Programs\Offline Toolkit`), needs no admin rights, and adds Start-menu and desktop shortcuts. Uninstall it from Settings → Apps; your data folder is kept.
- **`Offline-Toolkit-<version>-portable-win-x64.zip`**: portable. Unzip anywhere (e.g. a USB stick) and run `Offline Toolkit.exe`. Settings, presets and logs stay in a `data` folder next to it. Delete `portable.txt` to use `%APPDATA%` instead.
- **`THIRD-PARTY-NOTICES.txt`**: the licence of every bundled component (also next to the app and in Settings → *About & licences*).

The download is large because everything the modules need is inside: Python and its libraries, LibreOffice, Pandoc, Ghostscript, Tesseract with 16 OCR languages, a trimmed Java runtime for veraPDF, resvg, 73 open-source font families, and small AI models for super-resolution, reading text, cut-outs and faces. Nothing else needs installing, and nothing is ever downloaded later. The builds are made and smoke-tested on a Windows machine by `.github/workflows/release.yml` (the packaged app runs its full self-test before a release is published).

The app is not code-signed, so on first start Windows SmartScreen may say *"Windows protected your PC"*: choose **More info → Run anyway**. 8 GB of RAM is enough; a 50-megapixel photo or a 100 MB PDF is handled in the background without freezing the window.

## The home screen

The app opens on the home screen (Settings → *Home screen* can make it open where you left off instead).

- **Open a file…** (Ctrl+O) takes any supported file. Documents (PDF, Office, HTML, text, EPUB, SVG) go to the converter and design projects (`.otkd`) to the design module. For pictures the app asks what you want to do: resize or compress them, turn one into an editable design, or make a passport photo.
- **Drop files** on a module's card to open them there, or anywhere else in the window: on the home screen pictures ask; inside a module, files that module handles stay there (documents always go to the converter, design projects to the design module).
- **Try a sample** on each card opens a small bundled sample in that module (a copy in your data folder, so results can be saved next to it).
- **Recent work** lists the last 20 files and designs across the modules, newest first; click one to reopen it where you used it. Entries whose files were moved or deleted are greyed out. Remove one with ×, or clear the list; turn it off in Settings → *Home screen*.
- **Status**: whether the offline guard is on and how many conversion engines, font families and models are bundled. *Check every module* (Settings) runs the full self-test: every module does a small real job with the network blocked (10–30 seconds).
- Ctrl+1…4 open the modules, Ctrl+Shift+H or a click on *Offline Toolkit* returns home.

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

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+Shift+H (or click *Offline Toolkit* at the top left) | Home screen |
| Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 | Image Resizer / Document Converter / Image to Design / Passport Photo |
| Ctrl+O | Home screen: open any file. In a module: add files |
| Ctrl+Shift+O | Add a folder (resizer, converter) |
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

## Your data

| | Windows | Portable ZIP |
|---|---|---|
| Settings, presets, logs | `%APPDATA%\Offline Toolkit\` | `data\` next to the exe |
| Converter work folders (deleted when every file in the batch succeeded; kept for *Resume* otherwise) | `%APPDATA%\Offline Toolkit\cache\jobs\` | `data\cache\jobs\` |
| Designs (one folder each: layers, pictures, analysis cache; delete them from the module's start page) | `%APPDATA%\Offline Toolkit\designs\` | `data\designs\` |
| Passport presets: `presets\passport-specs.json`, `presets\paper-sizes.json` (with the other presets) | `%APPDATA%\Offline Toolkit\presets\` | `data\presets\` |
| Passport previews and pasted photos (temporary) | `%APPDATA%\Offline Toolkit\cache\previews\passport\` | `data\cache\previews\passport\` |
| Recent work on the home screen (`recent.json`; nothing is kept when *Keep a list of recent files* is off) | `%APPDATA%\Offline Toolkit\` | `data\` |
| Copies of the samples opened with *Try a sample* | `%APPDATA%\Offline Toolkit\samples\` | `data\samples\` |

Settings → *Your data* shows the exact paths. The JSON files are validated when the app starts. An invalid file is reported and the built-in default is used, and your file is never overwritten.

## Sample files

[`samples/`](samples/README.md) has ready files for every module, with a README saying what each one shows: a sideways camera photo with an EXIF rotation, a 12 MP landscape, a transparent logo and a HEIC photo (resizer); Word, Excel, PowerPoint, HTML, text with Hindi and Arabic, SVG, EPUB, a PDF, scans for OCR and two password-protected files (converter); a poster, a certificate, a crooked scan and a small screenshot (design); and two public-domain portraits (passport). `npm run samples` draws them again with the tests' own generators, and also makes the smaller set the app bundles for *Try a sample*.

## Set up for development

Prerequisites: **Node.js 22+**, **Python 3.11+** (from python.org on Windows; 3.11 is what the app bundles) and Git. Setup needs the internet once; the app itself never uses it.

```bash
git clone https://github.com/penpaper0878/offline-toolkit.git
cd offline-toolkit
npm run setup          # everything, one command (skips what is already there; --force fetches again)
npm run dev            # start the app with hot reload (or: npm start for the built app)
```

`npm run setup` (`scripts/setup.mjs`) does, in order:

1. `npm ci` if `node_modules` is missing, and fetches the Electron binary.
2. `npm run setup:py`: creates `worker/.venv` and installs the worker's pinned packages (`worker/requirements*.txt`).
3. On Windows, puts FriBiDi next to the venv's `python.exe` (Pillow needs it to shape Hindi, Arabic and kerning; SHA-256 pinned).
4. `scripts/fetch_fonts.py`: 73 font families from google/fonts at a pinned commit, every file checked against `scripts/fonts.lock.json` → `fonts/` (73 MB).
5. `scripts/fetch_models.py`: Real-ESRGAN (converted to ONNX), MediaPipe selfie segmenter and face landmarks, YuNet → `models/` (8 MB), SHA-256 pinned.
6. `scripts/fetch_engines.py --platform <win-x64|linux-x64>`: the conversion engines → `engines/<platform>/`. Every download is pinned (URL + SHA-256) in `scripts/engines.lock.json`. On Windows: LibreOffice 26.2 (MSI), Ghostscript and Tesseract (official installers, run silently: allow the admin prompt), tessdata_fast, Temurin 21 cut down with jlink, veraPDF, Pandoc and resvg, about 0.8 GB of downloads. On Linux: Pandoc, veraPDF and resvg; install LibreOffice, Ghostscript, Tesseract (+ language packs) and a Java runtime with your package manager (the script prints the `apt` line). `--no-engines` skips this step.
7. `npm run build` and `npm run licenses` (the list Settings → *About & licences* shows).
8. A quick check: Pillow's text shaping and every engine found.

The app looks for engines in `engines/<platform>/` (or `OTK_ENGINES`), then on `PATH`; Settings → *Conversion engines* shows what was found and where. `npm run dev` uses a local Vite dev server, the only address the offline guard allows, and only in development. Linux as root (containers only): Chromium refuses to start sandboxed as root, so pass `--no-sandbox`, e.g. `npx electron . --no-sandbox`.

**Updating the engines.** `python scripts/fetch_engines.py --platform win-x64 --relock` looks up the current releases (LibreOffice stays on the series in `LIBREOFFICE_SERIES`), checks the publishers' checksums and rewrites the lock; or push a commit whose message contains `[relock]` (or `[relock:tesseract,jre]` for some of them) and the *Engine lock* workflow does it on GitHub and commits the new lock. Pandoc, veraPDF, resvg and Python stay at the versions in the script, because the tests depend on their exact behaviour.

## Build and package (Windows)

On Windows, after `npm run setup`:

```bash
npm run dist:win
```

This bundles CPython 3.11 (the official embeddable package, pinned in the engine lock) with the worker's packages and FriBiDi into `build\python-win`, builds the app, writes the licence list from that bundled Python (`npm run licenses:win`), and runs electron-builder. Results in `dist\`:

- `Offline-Toolkit-Setup-<version>.exe`: the NSIS installer (per-user, no admin rights, choice of folder).
- `win-unpacked\`: the app itself. For the portable build, add a `portable.txt` next to `Offline Toolkit.exe` and zip the folder (the release workflow does exactly this).

What goes in (`electron-builder.yml`): the app (`out/`, in `app.asar`), `resources/` (schemas, defaults, samples), the worker's code, the bundled Python (`resources\engines\python`), the engines (`resources\engines`), fonts, models, the licence list (`resources\licenses`) and `THIRD-PARTY-NOTICES.txt` next to the exe.

**Smoke test** of a build: `set OTK_PACKAGED_EXE=dist\win-unpacked\Offline Toolkit.exe` and `set OTK_TEST_PYTHON=dist\win-unpacked\resources\engines\python\python.exe`, then `npx playwright test tests/e2e/packaged.spec.ts`. It checks the bundled Python and engines, the offline self-test and the full self-test of every module, the licence list and the trimmed Java runtime, then resizes (HEIC too), converts Word and HTML to validated PDF/A-2b, rebuilds a poster as an editable design and makes a passport photo and print sheet.

**Releases** are built on GitHub: push a commit whose message contains `[release]` (the release is tagged `v<package.json version>`) or a `v*` tag. `.github/workflows/release.yml` builds on `windows-latest`, runs the smoke test, makes the portable ZIP and publishes both with `THIRD-PARTY-NOTICES.txt`.

## Tests

```bash
npm run typecheck      # TypeScript (main, preload, renderer)
npm test               # vitest: units maths (shared vectors with Python), crop and passport geometry, design scene,
                       #         routing of opened files, the recent list, settings merging, undo/redo, schemas
npm run test:py        # pytest: resizer (DPI/cm/px maths, file-size targeting), RPC, network guard, converter (round
                       #         trips, PDF/A with veraPDF), design (ground-truth samples, exports drawn back and compared),
                       #         passport (face measurements, every preset fitted, reference pictures), the module
                       #         self-test, the licence list
OTK_FULL_MATRIX=1 npm run test:py -- worker/tests/test_converter_matrix.py   # every conversion route (~270, about an hour)
npm run test:e2e       # Playwright drives the real Electron app with the real Python worker: every module, the home
                       #         screen, the self-tests, About & licences, and large files (50 MP photos, a 107 MB PDF)
npm run test:offline   # Linux: pytest + end-to-end inside a network namespace with no network interfaces
npm run test:all       # typecheck + vitest + pytest + end-to-end
```

The end-to-end tests need `npm run build` (done by `test:e2e`) and `npm run licenses` for the licence test. Visual tests compare rendered pictures with stored references (`worker/tests/golden/`, SSIM thresholds); `OTK_UPDATE_GOLDEN=1` rewrites them after a deliberate change. CI runs everything on Ubuntu (also inside a network namespace with no network) and Windows (`.github/workflows/ci.yml`). Results, including what could not be run, are in [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## Troubleshooting

**Installing and starting**

- **Windows SmartScreen** on first run: the build is not code-signed. Choose *More info → Run anyway*.
- **"The Python worker could not start"** (development): run `npm run setup:py`. Settings → *Diagnostics* shows which Python the app uses; set `OTK_PYTHON` to choose one. In the installed app, reinstall: the worker's Python is inside the app folder.
- **A preset or settings file error at start-up**: the message names the file and the field. Fix the JSON or delete the file to get the defaults back; the app never overwrites a file it could not read.
- **Something is wrong but no message says why**: the *Event log* (Ctrl+L) lists every job and error (paths can be hashed in Settings → *Privacy*). Settings → *Check every module* runs a small real job in each module and says which part fails.

**Setting up for development**

- **`npm run setup` stops**: it names the step that failed. Run it again after fixing that; finished steps are skipped. Behind a proxy, set `HTTPS_PROXY` for npm and pip.
- **"Python 3.11 or newer was not found"**: install it from python.org (tick *Add to PATH*), or set `OTK_PYTHON_BOOTSTRAP` to its `python.exe`.
- **"SHA-256 mismatch" while fetching engines, fonts or models**: the file at the pinned URL changed. Nothing unverified is used. Delete `build/cache/engines` and try again; if it persists, update the lock (*Updating the engines* above) and run the tests.
- **The engine installers ask for admin rights** (Windows): LibreOffice, Ghostscript and Tesseract are installed into `build\engine-install` and copied from there. Allow the prompt; the installed app itself never needs admin rights.
- **Pillow cannot shape text** (Hindi or Arabic measured wrongly in the design module, setup's quick check says *NO*): on Windows run `node scripts/fetch-fribidi-win.mjs worker\.venv\Scripts`; on Linux install `libfribidi0`.

**Using the modules**

- **HEIC files don't open**: check Settings → *Diagnostics* shows "HEIC yes".
- **"Engine missing: LibreOffice"** (or another engine) in a development run: see *Set up for development*. Settings → *Conversion engines* lists what was found.
- **A conversion says "Needs review"**: open the report (the row's details button). It names the check that failed, with the missing or extra text, the page that looks different or the PDF/A clause.
- **Fonts substituted**: the report's *Fonts* check names each one. Metric-compatible substitutes (Calibri → Carlito, Cambria → Caladea, Arial → Liberation Sans) keep the line breaks; others may not. Installed Windows fonts are used when present.
- **The app was closed during a conversion**: convert the files again. *Resume* lasts for the session; the work folders left behind can be deleted (see *Your data*).
- **A line of text was not read** (Image to Design, *Check → Not read*): it is in a language that was not ticked. Tick it under *Reading options* and analyse again, or type the text into a new text box over it.
- **PowerPoint shows a different font**: install the design's fonts (*Export → Install the fonts*) and restart PowerPoint. Word files carry their fonts inside.
- **Passport photo: "N faces found" or the crown/chin markers are off**: crop closer to the one person in step 2, or drag the crown and chin markers and press *Auto fit*. "Enlarged 2.5× (too few pixels)" means the photo is too small for that size at that DPI: use a larger original.
- **Printed passport photos are the wrong size**: print at 100% / *Actual size*, never *Fit to page*, and measure one photo before cutting.
- **Large files are slow**: they are processed in the background and can be cancelled (Esc); the window stays usable. Very large batches need free disk space for the work folders.
- **"Suspension not allowed here" in a terminal**: a harmless libjpeg message. The encoder retries with a bigger buffer.

## Licences

The toolkit is for personal use and is not redistributed. It bundles about 200 open-source components; **Settings → About & licences** lists every one with its version, licence and the licence's text, and `THIRD-PARTY-NOTICES.txt` (next to the app and with each release) has the same in one file. `scripts/collect_licenses.py` makes the list at build time from what is actually bundled, and fails the build if a licence cannot be determined.

Copyleft licences place obligations only on someone who gives the app to others. The parts that would matter then are flagged first:

- **PyMuPDF** (AGPL-3.0, or an Artifex commercial licence) is imported into the Python worker, so the worker is a combined work with it: redistributing the app would mean offering its complete source under AGPL terms, or buying a licence.
- **Ghostscript** (AGPL-3.0) and **Pandoc** (GPL-2.0+) are separate programs: their licences and source offers would have to go with them.
- Weak copyleft (LGPL, MPL, CDDL, GPL with the Classpath exception): veraPDF (used under MPL-2.0), LibreOffice (MPL-2.0), the Java runtime, pikepdf, ocrmypdf, img2pdf, fpdf2, tqdm, certifi, and libraries shipped as separate replaceable files (FFmpeg in Electron and OpenCV, GEOS in shapely, libheif/libde265, FriBiDi). Keep their licences and keep them replaceable.

The fonts are under the SIL Open Font License (70 families), Apache-2.0 (2) and the Ubuntu Font Licence (1); the models under Apache-2.0, MIT and BSD-3-Clause. Details and the reasoning per component: [docs/ENGINES.md](docs/ENGINES.md).

## Project layout

```
src/main/        Electron main: offline guard, otk:// protocol, worker pool, settings/presets store, IPC, self-tests,
                 recent files, samples, About & licences
src/preload/     the typed window.otk bridge (sandboxed)
src/renderer/    React UI: pages (home, settings, log, About & licences), modules/resizer, converter, design, passport
src/shared/      TypeScript shared by all three (units, geometry, file routing, the recent list, the design scene, types)
worker/          Python worker: JSON-RPC over stdio, resizer engine, converter (planner, steps, PDF/A, OCR, verification),
                 design (analysis pipeline, exporters, verification), passport (face, matte, sizing, sheets),
                 the module self-test, and the tests (worker/tests)
scripts/         setup, Windows Python bundling, engines (+ engines.lock.json), fonts (+ fonts.lock.json), models,
                 FriBiDi, samples, the licence collector (+ SPDX texts), the standalone PDF printer
resources/       JSON schemas, shipped defaults (settings, presets, conversion routes), the bundled samples
samples/         sample files for every module (see samples/README.md)
tests/           shared test vectors and Playwright end-to-end tests
fonts/, models/, engines/, build/   fetched and built files (not in git)
docs/            architecture, engines and licences, conversion matrix, test report
.github/         CI (Ubuntu, offline namespace, Windows), the Windows release build, the engine relock job
```
