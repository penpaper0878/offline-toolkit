# Test report

Updated at the end of each phase. Every result below is from an actual run. Anything not run is listed as such.

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
