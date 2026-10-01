# Test report

Updated at the end of each phase. Every result below is from an actual run. Anything not run is listed as such.

## Phase 2: Module 2 (Document Converter), 2026-10-01

### Environment

- **Machine:** the same Linux container (Ubuntu 24.04, x86-64, 4 cores, 15 GB RAM), run as root, Xvfb for the app tests.
- **Engines here:** LibreOffice 24.2.7, Ghostscript 10.02.1, Tesseract 5.3.4 (eng, hin, ara, heb, tam and more from Ubuntu), OpenJDK 21 + veraPDF 1.28.2, Pandoc 3.8.2.1 (official build), resvg 0.45.1, Electron 44.5.1 (Chromium printing).
- **Windows engines** (CI and the release): fetched by `scripts/fetch_engines.py` (see [ENGINES.md](ENGINES.md) §0); the exact versions of each build are in `engines/win-x64/manifest.json`, printed in the release log.

### Results

| Suite | Command | Result |
|---|---|---|
| TypeScript typecheck | `npm run typecheck` | **pass** |
| JavaScript unit tests (vitest) | `npm test` | **32 / 32 pass** |
| Python tests (pytest): resizer, RPC, planner, converter basics, jobs, 43 representative routes | `npm run test:py` | **185 / 185 pass** |
| **Full conversion matrix**: every source × target × mode the planner offers, on the sample corpus, each verified | `OTK_FULL_MATRIX=1 … test_converter_matrix.py` | **268 / 268 routes converted; 89 Perfect, 179 Expected changes, 0 Needs review** |
| End-to-end, real app + worker (Playwright): resizer ×2, converter (Word/HTML/TXT → PDF; Word + a password-protected PDF → PDF/A-2b, reports opened) | `npm run test:e2e` | **3 / 3 pass** |
| Ubuntu CI (`ubuntu-latest`): all of the above except the full matrix, plus the no-network run | `.github/workflows/ci.yml` | CI_LINUX |
| Windows CI (`windows-latest`) with the bundled Windows engines | `.github/workflows/ci.yml` | CI_WINDOWS |
| Packaged Windows app (installer + portable, engines bundled, smoke test converts to PDF/A-2b) | `.github/workflows/release.yml` | RELEASE |

### The matrix in numbers

- **15 source kinds** (PDF, scanned PDF, PDF/A-2b, DOCX, DOC, XLSX, XLS, PPTX, PPT, HTML, TXT, EPUB, PNG, JPEG, SVG) **× 13 targets × the modes that differ** = 268 routes. All converted, and none ended *Needs review*. `KNOWN_REVIEW` (routes allowed to end in review, with a reason) is empty.
- **PDF/A:** 44 PDF/A-1b/2b/3b outputs, **44 / 44 compliant according to veraPDF**. A separate test (`test_failed_validation_is_never_called_pdfa`) makes veraPDF reject a file and checks that it is saved as `NOT-PDFA` with verdict *Needs review*.
- **Why 179 are "Expected changes", not "Perfect":** the route cannot hold something the source has, and the report says what. The count of each check that ended *expected* (a route can have several):
  - text 95: for example pictures' alt text in TXT, OCR text from scans, page headers that Pandoc or LibreOffice add;
  - images 42: pictures in TXT, XLSX, or a page rasterised to PNG/JPEG;
  - fonts 25: metric-compatible substitutes such as Calibri → Carlito;
  - tables 22;
  - notes 18;
  - links 5;
  - bookmarks 2;
  - appearance 1 (SVG to editable DOCX shapes).
- **Appearance** was compared on all 44 exact-layout routes with a fixed-layout source: 43 pass, and 1 is an expected change (above).

### Found and fixed in this phase by larger inputs (not visible on the small samples)

| Input | Before | Cause | After |
|---|---|---|---|
| 100-page PDF (LibreOffice, Caladea/Carlito) → exact DOCX | *Needs review*: every page 1.65 pt off, SSIM 0.906 | Text boxes were placed from PyMuPDF's line boxes, whose ascent (1.05 em for Caladea) is not the one LibreOffice uses (0.90 em: the font sets USE_TYPO_METRICS) | Boxes placed from the baseline with the ascent measured for Writer (ascender + line gap, read from the embedded font). Lowest SSIM **0.997** |
| Same → exact PPTX | *Needs review*: SSIM 0.88–0.95 | Impress puts the first baseline 1.00 em below the box top for every font (measured on 8 fonts × 3 sizes), and lays glyphs on a coarser grid (lines about 0.35% shorter) | Baseline rule for slides, plus per-tile ±2 px alignment in the check. Lowest SSIM **0.984**, no changed areas |
| Appearance check itself | A page with one word missing scored SSIM **0.999** (passes) | SSIM is a page average | New changed-area test (ink on one side only). Missing word, a line moved 6 px and a missing table rule are all caught (tests), and the report embeds before/after crops |
| Windows | Missing test samples (DOC/XLS/PPT); a Hindi font Windows lacks; HTML fonts | The test corpus looked for LibreOffice on PATH; the sample named Noto Sans Devanagari; a web page's CSS fallback was treated as a missing document font | Corpus fixed; Windows samples use Nirmala UI; web-page fallbacks are *expected changes* |
| Windows-made PDF with an Arabic line → exact DOCX/PPTX | *Needs review* on Windows only: the Arabic line 13 pt too wide | LibreOffice on Windows draws each space of that line twice (in Tahoma and again in Lucida Sans Unicode), sometimes as separate lines, sometimes inside the line itself; the extractor kept both, so spaces doubled and the line gained a leading space. The text check compares words, so it did not notice | A space drawn on top of an existing space is ignored, keeping the copy in the words' font (two tests, one with the exact line PyMuPDF read on Windows). This also removes the double spaces from editable DOCX, HTML and TXT made from such PDFs |
| Font names | "Calibri Light" became Calibri, "Segoe UI Semibold" became Segoe UI bold | Weight words were stripped | Office's weighted families are kept |

### Measured performance (Linux container, worker plus engines, verification included)

| Case | Time | Peak memory (worker + engine processes) | Verdict |
|---|---|---|---|
| 100-page DOCX (text, 100 tables, 20 pictures) → PDF/A-2b | 6.7 s | 0.47 GB | Expected (Calibri → Carlito, Cambria → Caladea) |
| Same DOCX → PDF | 3.2 s | 0.28 GB | Expected (same fonts) |
| 100-page PDF → DOCX (editable, pdf2docx) | 18 s | 0.36 GB | Perfect |
| 100-page PDF → DOCX (exact layout) | 124–144 s | 1.05 GB | Expected (headings in text boxes are not Word headings) |
| 100-page PDF → PPTX (exact layout) | 102–160 s | 1.1 GB (2.2 GB while LibreOffice renders 100 slides for the check) | Expected |
| 100-page PDF → PNG, 300 DPI, zipped | 86 s | 1.0 GB | Expected (a picture of each page) |
| 100-page PDF → HTML (editable) | 9.3 s | 0.15 GB | Perfect |
| 10-page scan (300 DPI) → PDF/A-2b with OCR text layer | 34 s | 0.33 GB | Expected (text from OCR); veraPDF pass; page images byte-identical |
| Same scan → DOCX (editable) / TXT | 45 s | 0.40 GB | Expected |

**OCR accuracy** on that scan (clean 300 DPI, Caladea 11 pt, `tessdata_fast` eng): **0 errors in 3,100 words** of prose and numbers. In the 200 synthetic table codes such as `R0C0`, about half were misread as `ROCO`/`RICO` (0/O and 1/I look the same in this font). The report flagged 71 words below 80% confidence, almost all of them these codes. Some misreads still had high confidence, so the flag is a hint, not a guarantee.

Everything stays far below the 8 GB target. The largest peak (2.2 GB) is LibreOffice rendering a 100-slide deck for the appearance check.

### Known limits (Module 2)

- **Exact-layout DOCX/PPTX in Word and PowerPoint.** Text-box positions are computed for LibreOffice's layout rules, which were measured. Word and PowerPoint use the same metrics for most fonts (Calibri, Cambria, Arial, Times New Roman, Segoe UI). For fonts that set USE_TYPO_METRICS (e.g. Caladea, some Google fonts) they may place lines up to about 0.15 em lower. This could not be measured here (no Word).
- **Fonts.** The Lite bundle has no fonts of its own. A document that names a font this computer lacks is reported (*Fonts* check) and rendered with a substitute. Metric-compatible substitutes keep the line breaks; others can change them, and the verdict says so.
- **OCR** is Tesseract `tessdata_fast` only. It reads clean scans well, but expect errors on low-resolution photos, handwriting and stylised fonts; low-confidence words are listed in the report. No Chinese, Japanese or Korean in the Lite bundle.
- **Appearance check** at 100 DPI: changes smaller than about 40 px there (a full stop, a single thin character) are left to the text check, which compares every word.
- **Resume** works within a session (after a cancel or a failure). After the app is closed, convert again.
- **Not run here:** Microsoft Word/PowerPoint rendering of the outputs, macOS.

## Phase 1: Module 1 (Image Resizer), 2026-09-30

### Environment

- **Machine:** Linux container (Ubuntu 24.04, x86-64), run as root (hence `--no-sandbox` for Electron in tests only), virtual display via Xvfb.
- **Runtimes:** Node 22.22.2, Electron 44.5.1 (Chromium 152, Node 24.21), Python 3.11.15.
- **Python packages:** Pillow 12.3.0, numpy 2.4.6, pi-heif 1.4.0, jsonschema 4.26.0, pytest 9.1.1.

### Results

| Suite | Command | Result |
|---|---|---|
| TypeScript typecheck (main, preload, renderer) | `npm run typecheck` | **pass** |
| JavaScript unit tests (vitest) | `npm test` | **31 / 31 pass** |
| Python tests (pytest), including 33 Phase 0 planner tests | `npm run test:py` | **115 / 115 pass** |
| Conversion matrix up to date | `python scripts/gen_matrix.py --check` | **pass** |
| End-to-end, real Electron app + real Python worker (Playwright) | `npm run test:e2e` | **2 / 2 pass** |
| Offline run: pytest + end-to-end inside a network namespace with **no network interfaces** (only loopback, which Playwright needs for its debugging connection) | `npm run test:offline` | **115 / 115 + 2 / 2 pass** |
| Windows 11 / Server (GitHub Actions `windows-latest`, CI run 36747879326) | typecheck, vitest, pytest, Playwright E2E | **all pass** (31 vitest, 115 pytest, 2 E2E) |
| Ubuntu (GitHub Actions `ubuntu-latest`, same run) | the same suites + the no-network run | **all pass** |
| Packaged Windows app (installer build + smoke test of the built `.exe` with its bundled Python) | `.github/workflows/release.yml`, run 36749011530 | **pass**: installer, smoke test and portable ZIP all succeeded; published as pre-release v0.1.0 |
| macOS | — | **not run** |

### Windows packaging

`release.yml` runs on a Windows runner and does four things:

1. Bundles the official CPython 3.11.9 embeddable package with the worker's win_amd64 wheels.
2. Builds the NSIS installer.
3. Launches the packaged `Offline Toolkit.exe` with `tests/e2e/packaged.spec.ts`. The test checks that the app uses its **bundled** Python, that the network guard is on, that HEIC works and that the offline self-test passes. It then resizes a photo and a HEIC file and checks 240×240 px @200 DPI on disk.
4. Makes the portable ZIP and publishes both files as a GitHub release.

The same test steps were dry-run here against the development build (pass).

**On Windows (run 36749011530): every step passed.** Release v0.1.0:

- `Offline-Toolkit-Setup-0.1.0.exe`: 129 MB installer
- `Offline-Toolkit-0.1.0-portable-win-x64.zip`: 188 MB portable ZIP

The builds are not code-signed.

### What the tests prove (spec → test)

| Requirement | Evidence |
|---|---|
| px = cm / 2.54 × DPI, with the rounding error shown; "3 cm @200 DPI = 236.2 px", "240 px @200 DPI = 3.048 cm" | `tests/vectors/units.json`, checked by both `worker/tests/test_units.py` and `src/shared/units.test.ts` (same numbers in Python and TypeScript). The UI string is checked in `units.test.ts`. The E2E test checks the live conversion text. |
| Exact pixels vs exact physical size | `units.test.ts` → *field logic* (DPI change keeps px or keeps cm) |
| Fit modes give exact dimensions | `test_geometry_render.py`: every mode × 4 target sizes, incl. 1×1 and 3000×2000 |
| Crop window selects the right region (visual regression) | `test_pipeline.py::test_crop_visual_regression` (exact colour and size of a cropped quadrant). The E2E test nudges the window and checks the coordinates. |
| 20–50 KB target at fixed dimensions | `test_encode_compress.py`, `test_pipeline.py::test_photo_preset_end_to_end`. E2E: 240×240 JPEG between 20 480 and 51 200 bytes, read back from disk. |
| Impossible target: said so, closest result and suggestions, dimensions unchanged | `test_above_max_suggestions_are_real` (the suggested size is re-encoded and really fits). E2E step with a 0.3 KB maximum. |
| Below the minimum: reported; optional padding keeps pixels identical | `test_below_min_without_and_with_padding`, `test_padding_keeps_pixels_and_reaches_size` (JPEG/PNG/WEBP, pixel-exact). E2E signature preset (10–20 KB). |
| DPI written correctly: JFIF + EXIF (JPEG), pHYs (PNG), EXIF (WEBP) | `test_jpeg_dpi_in_jfif_and_exif`, `test_png_dpi_in_phys`, `test_webp_dpi_in_exif`. E2E reads JFIF and EXIF from saved files. |
| EXIF orientation applied; orientation reset in output | `test_exif_orientation_applied` (orientations 1/3/6/8, pixel check), `test_orientation_is_applied_and_reset` |
| Inputs: JPG, PNG, WEBP, BMP, TIFF, HEIC | `test_imageio.py` (HEIC from a committed fixture; CMYK, 16-bit, palette and multi-page TIFF included) |
| Strip / keep metadata | `test_strip_keeps_only_resolution_and_keep_resets_orientation`, `test_xmp_orientation_reset` |
| Batch, no overwrites, Unicode names, ZIP, errors don't stop the batch, cancel | `test_batch_names_collisions_zip_and_errors` (Devanagari file name), `test_cancel_mid_batch`, `test_rpc.py` (cancel through the RPC), E2E batch + ZIP |
| Presets: editable JSON, validated | `resizer-defaults.test.ts` (shipped files validate; bad values are rejected). E2E saves a preset, and the JSON file is written. |
| Undo/redo | `history.test.ts`; E2E Ctrl+Z / Ctrl+Y on a size change |
| Offline: no outbound calls | In-app self-test: 4 / 4 canaries blocked and recorded (Node, Chromium, page, Python), and "no other network attempts since start-up" (E2E). `test_rpc.py::test_ping_and_guard`. The whole suite passes with no network interface. |
| Settings remembered | E2E: dark theme survives a restart |

### Measured performance (Linux container, one CPU core in use)

| Case | Time | Notes |
|---|---|---|
| Decode + orient a 50 MP JPEG | 0.5 s | |
| 50 MP → 240×240 JPEG, 20–50 KB | 0.1 s | 8 encodes |
| 50 MP → 4000×3000 JPEG, max 1 MB | 6.8 s | 19 encodes |
| 50 MP → 15×10 cm @300 DPI WEBP, max 800 KB | 4.9 s | |
| 50 MP → 4000×3000 PNG (noise content, worst case) | 13.6 s | PNG maximum compression is slow on noisy images |
| Peak memory, worker process, 50 MP source | ~740 MB | Fine on an 8 GB laptop. The UI and main process are separate. |

### Known limits (Module 1)

- **Stored DPI precision.**
  - JPEG's JFIF header stores whole DPI only. The exact value, e.g. 199.81 with "fit DPI", is in EXIF.
  - PNG stores whole pixels per metre, so 72 DPI reads back as 72.009.
  - WEBP has no DPI field. It is written in EXIF, which many viewers ignore.
- **Metadata when kept:** IPTC (APP13) and camera maker notes are not carried over. The app says so in the result.
- **Colour:** 16-bit sources become 8-bit, and non-sRGB colour profiles are converted to sRGB. Both are shown as warnings.
- **Before/after view:** the "before" half is drawn from the ≤2048 px preview copy, so at high zoom it is softer than the real source. The "after" half is always the real output file.
- **Very large images:** for targets above 4 MP, the size search skips baseline-JPEG variants to save time. It can therefore miss an option a few percent smaller.
- **Not in Phase 1 yet** (planned in the architecture): the RAM-aware scheduler and job journal (resume after a crash) arrive with the heavier Module 2 jobs, and bundled Noto UI fonts arrive in Phase 5 (the UI uses system fonts until then).
