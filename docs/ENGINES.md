# Bundled components and licenses

Status: Phase 5, v1.0.0 (§0–§0d list what is actually bundled; §1–§7 are the Phase 0 plan for the whole app, kept for the reasoning), **Lite bundle, personal use** (decisions D1–D2, confirmed 2026-09-30). Python package versions are the latest on PyPI as of 2026-09-30, pinned in `worker/requirements*.txt`. Every engine download is pinned (URL + SHA-256) in `scripts/engines.lock.json` (§0d). The minimum versions listed here are the ones whose features the toolkit relies on.

**The complete, generated list** of every bundled component with its licence text is in the app (Settings → *About & licences*) and in `THIRD-PARTY-NOTICES.txt` next to the app and with each release (`scripts/collect_licenses.py`, §0d). This document explains the choices.

Sizes are rough figures for Windows x64, unpacked. **Total ≈ 1.5–1.9 GB installed, ≈ 0.6–0.8 GB download.** The Lite bundle leaves out LaMa (≈ 200 MB), IS-Net (≈ 170 MB), the CJK fonts (≈ 130 MB) and switches Tesseract from `tessdata_best` to `tessdata_fast` (≈ 210 MB less).

⚠️ = copyleft that would matter only if the app were **redistributed** (see §3). This build is for personal use (D1), so none of these flags require any action.

## 0. What Phase 2 actually bundles (Module 2)

`scripts/fetch_engines.py` puts these into `engines/win-x64/` at build time; electron-builder copies that folder to `resources/engines/` in the installer and the portable ZIP. The app never downloads anything. The exact versions of each build are written to `engines/win-x64/manifest.json` (printed in the release log, and shown in Settings → *Conversion engines*). Sources and versions as of v1.0.0 (Phase 5 replaced Chocolatey with pinned official downloads, §0d):

| Engine | Version | Source (build time) | Size on Windows (unpacked) |
|---|---|---|---|
| LibreOffice | 26.2.6.3 (the mature 26.2 series) | The official MSI from The Document Foundation's archive, unpacked (`msiexec /a`, an administrative install: nothing registered) and its program folder copied; help and spelling dictionaries removed | ≈ 600 MB |
| Pandoc | 3.8.2.1 (official build) | PyPI wheel `pypandoc_binary==1.16.2` (hash-checked by PyPI). Distribution builds such as Debian's lack the embedded data files and fail under `--sandbox` | ≈ 200 MB |
| Ghostscript | 10.08.0 | The official installer (`ArtifexSoftware/ghostpdl-downloads`), unpacked with 7-Zip; `doc/` and `examples/` removed; Microsoft's C++ runtime DLLs it needs copied next to it from the Java runtime | ≈ 70 MB |
| Tesseract | 5.5.3 | The Windows installer from the `tesseract-ocr/tesseract` 5.5.3 release (the UB Mannheim build), unpacked with 7-Zip | ≈ 50 MB |
| tessdata_fast | commit `874164186573` | eng, osd, hin, mar, san, nep, ben, guj, pan, tam, tel, kan, mal, ori, urd, ara, heb, each file SHA-256 pinned | ≈ 54 MB |
| Java runtime | Temurin 21.0.12.1 | The Temurin JDK zip (Adoptium API), cut with `jlink` to the 12 modules veraPDF needs | ≈ 56 MB (was ≈ 130 MB as a full JRE) |
| veraPDF | 1.28.2 greenfield (CLI + its jars) | Maven Central, each jar checked against Maven's SHA-1 and the lock's SHA-256 | ≈ 20 MB |
| resvg | 0.45.1 | GitHub release `resvg-win64.zip`, SHA-256 pinned | ≈ 4 MB |

Python packages added in Phase 2 (all pinned in `worker/requirements.txt`): PyMuPDF 1.28.2, pikepdf[pdfa] 10.16.0, pypdfium2 5.13.0, pdf2docx 0.5.13, img2pdf 0.6.3, ocrmypdf 17.13.0, python-docx 1.2.0, python-pptx 1.0.2, openpyxl 3.1.5, xlrd 2.0.2 (reads .xls for verification, BSD-3), lxml 6.1.3, rapidfuzz 3.14.6, msoffcrypto-tool 6.0.0, docxcompose 2.2.0, charset-normalizer 3.5.2, opencv-python-headless 5.0.0.93 (Apache-2.0; replaced by the `contrib` build in Phase 3, see §0b), fontTools 4.66.1.

**Differences from the plan below:**

- **OCR is Tesseract only in Phase 2.** RapidOCR (PP-OCR), PP-DocLayout and SLANet+ arrive with Module 3, where layout analysis needs them. Tables in scans are found with OpenCV line detection instead.
- **Chromium prints HTML, TXT, EPUB and SVG to PDF** inside the app (a hidden, sandboxed window that can only read the job folder). No separate browser is bundled.
- **No bundled fonts yet.** Conversions use the fonts LibreOffice ships (Liberation, Carlito, Caladea, DejaVu, Noto Sans/Serif and others) plus the fonts installed in Windows. The Noto families for the UI and Module 3 arrive in Phase 5 / Module 3. The verification report names every font substitution.
- **sRGB ICC v2:** the profile shipped inside pikepdf is used for the PDF/A OutputIntent.
- **Download size of v0.2.0:** 568 MB installer, 790 MB portable ZIP (see [TEST_REPORT.md](TEST_REPORT.md)). The per-engine sizes above are estimates.

## 0b. What Phase 3 adds (Module 3, Image to Editable Design)

Nothing is downloaded by the app. `scripts/fetch_fonts.py` and `scripts/fetch_models.py` fetch these once at build time (CI and release caches keep them); electron-builder copies `fonts/` and `models/` to `resources/fonts` and `resources/models`.

**Fonts: 73 families, 71 MB** (`fonts/fonts.json` is the catalogue; each family's licence file sits next to its fonts). Source: [google/fonts](https://github.com/google/fonts) at commit `9710da1e`; every file's SHA-256 is pinned in `scripts/fonts.lock.json` and checked on fetch. Licences: 70 families SIL OFL-1.1, 2 Apache-2.0 (Roboto Slab, Satisfy), 1 Ubuntu Font Licence 1.0 (Ubuntu). Static families keep the weights 300/400/700/900 (italics for 400 and 700) to stay small; variable fonts are kept whole and cut into static instances on demand (fontTools instancer) for the exports and the editor.

| Role | Families |
|---|---|
| Sans (37) | Archivo, Arimo, Barlow, Carlito, DM Sans, Fira Sans, Hind, Inter, Josefin Sans, Kanit, Lato, Manrope, Montserrat, Mukta, Noto Sans, Noto Sans Arabic, Noto Sans Bengali, Noto Sans Devanagari, Noto Sans Gujarati, Noto Sans Gurmukhi, Noto Sans Hebrew, Noto Sans Kannada, Noto Sans Malayalam, Noto Sans Oriya, Noto Sans Tamil, Noto Sans Telugu, Nunito, Open Sans, PT Sans, Poppins, Quicksand, Raleway, Roboto, Rubik, Source Sans 3, Ubuntu, Work Sans |
| Serif (16) | Bitter, Caladea, Cormorant Garamond, Crimson Text, EB Garamond, Libre Baskerville, Lora, Merriweather, Noto Naskh Arabic, Noto Nastaliq Urdu, Noto Serif, Noto Serif Devanagari, PT Serif, Playfair Display, Roboto Slab, Tinos |
| Display (10) | Abril Fatface, Alfa Slab One, Anton, Archivo Black, Baloo 2, Bebas Neue, Cinzel, Lobster, Oswald, Righteous |
| Script (7) | Allura, Caveat, Dancing Script, Great Vibes, Kaushan Script, Pacifico, Satisfy |
| Mono (3) | Cousine, Roboto Mono, Source Code Pro |

Carlito, Caladea, Arimo, Tinos and Cousine have the metrics of Calibri, Cambria, Arial, Times New Roman and Courier New.

**Models: 5 MB** (`models/manifest.json` records sources and hashes).

| Model | Licence | Used for | How it is bundled |
|---|---|---|---|
| Real-ESRGAN `realesr-general-x4v3` | BSD-3-Clause | Enlarging small text before reading it | The official `.pth` (SHA-256 pinned) is read without PyTorch and written as ONNX (opset 17: Conv, PReLU, DepthToSpace, Resize, Add) at build time; run with ONNX Runtime. 4.9 MB |
| MediaPipe Selfie Segmenter (float16) | Apache-2.0 | Person cut-outs | The `.tflite` (SHA-256 pinned), run with OpenCV DNN; the edge is refined with GrabCut and a guided filter. 0.25 MB |
| PP-OCRv6 detection + recognition (small), PP-OCR angle classifier | Apache-2.0 | Reading Latin and Chinese text with word boxes | Inside the `rapidocr` wheel (no download at run time) |

**Python packages added** (pinned in `worker/requirements.txt` / `requirements-nodeps.txt`): opencv-contrib-python-headless 5.0.0.93 (Apache-2.0, replaces the headless build: xphoto inpainting, ximgproc guided filter, DNN), onnxruntime 1.30.0 (MIT), rapidocr 3.9.2 (Apache-2.0, installed without its `opencv-python` requirement), vtracer 0.6.15 (MIT), brotli 1.2.0 (MIT, WOFF2), and RapidOCR's dependencies pyclipper 1.4.0 (MIT), shapely 2.1.2 (BSD-3), omegaconf 2.3.1 (BSD-3), PyYAML 6.0.3 (MIT), colorlog 6.12.0 (MIT), tqdm 4.70.1 (MPL-2.0/MIT), requests 2.34.2 (Apache-2.0; imported but never used to download, and blocked by the network guard), fire 0.7.1 (Apache-2.0), termcolor 3.3.0 (MIT), six 1.17.0 (MIT). Build time only: onnx 1.23.1 (Apache-2.0).

**Differences from the plan below:**

- **No layout model.** Text comes from OCR line boxes; tables from ruled-line detection; shapes, lines, graphics and photos from colour regions of the text-free picture, tested against ideal shapes. PP-DocLayout / SLANet+ (`rapid-layout`, `rapid-table`) and MediaPipe as a package are not bundled.
- **No HarfBuzz package.** Pillow's raqm layout shapes text for font matching. Pillow's wheels contain HarfBuzz and libraqm but load **FriBiDi** 1.0.17 (LGPL-2.1-or-later) at run time: Linux has it (`libfribidi0`), and for Windows `scripts/fetch-fribidi-win.mjs` takes conda-forge's build (SHA-256 pinned, 0.1 MB) and puts `fribidi-0.dll` next to the bundled `python.exe`, with its licence. Without it, text is measured unshaped and the analysis says so in its notes.
- **Cut-outs** use the MediaPipe selfie segmenter for people and GrabCut for objects (MODNet was not added in Module 4 either; see §0c).
- **Inpainting** adds a smooth-surface fill (quadratic fit plus matched grain) for plain and gradient backgrounds, the commonest case on designed pages, besides Telea and xphoto FSR.

## 0c. What Phase 4 adds (Module 4, Passport Photo Maker)

Two small models, fetched by `scripts/fetch_models.py` at build time like the Module 3 models (SHA-256 pinned, recorded in `models/manifest.json`) and bundled in `resources/models`. **Models now: 8 MB in total.** No new Python or JavaScript packages: the module uses OpenCV (DNN, GrabCut, ximgproc guided filter), Pillow, NumPy, PyMuPDF and the resizer's encoder, all already bundled.

| Model | Licence | Used for | How it is bundled |
|---|---|---|---|
| YuNet `face_detection_yunet_2023mar` | MIT | Finding faces | ONNX from the OpenCV model zoo (`opencv/opencv_zoo`, SHA-256 `8f2383e4…`), run with OpenCV's `FaceDetectorYN`. 0.23 MB |
| MediaPipe Face Landmarker v2: the face landmark model (478 points, irises included, float16) | Apache-2.0 | Eyes, chin, face outline, tilt, eye openness; red-eye and skin areas | `face_landmarks_detector.tflite` taken out of the official `face_landmarker.task` bundle (bundle SHA-256 `64184e22…`, file SHA-256 `c7d54204…`), run with OpenCV DNN (classic engine). 2.5 MB |
| MediaPipe Selfie Segmenter (from Phase 3) | Apache-2.0 | The person matte for background replacement | Reused; refined with a head close-up, band-limited GrabCut, a guided filter and edge decontamination |
| Real-ESRGAN `realesr-general-x4v3` (from Phase 3) | BSD-3-Clause | Optional upscaling of small photos | Reused |

**Differences from the plan below:** MODNet (planned for portrait matting, ≈ 25 MB) is not bundled: its weights could not be fetched from a pinned source when building, and the selfie segmenter with the refinements above passed the background tests on the test portraits. MediaPipe's face *detector* is replaced by YuNet (the landmark model needs a face box; YuNet is smaller and runs through OpenCV, which is already bundled). MediaPipe's multiclass segmenter (hair, skin, clothes) was tried for the hair line and dropped: it needs a layer (TRANSPOSE_CONV) that OpenCV DNN cannot run, and the `mediapipe` package is not bundled.

**Test photos** (not shipped; `worker/tests/fixtures/faces/ATTRIBUTION.md`): the official 2012 portrait of President Obama by Pete Souza (work of the US federal government, public domain) and NASA's portrait of astronaut Eileen Collins (public domain, as distributed with scikit-image).

## 0d. What Phase 5 changes (v1.0.0: one app, installer, licences)

**Pinned engine downloads.** Until v0.4.0 LibreOffice, Ghostscript, Tesseract and Java came from Chocolatey at whatever version was current when the build cache was filled. Now `scripts/engines.lock.json` lists every file the build downloads (URL, SHA-256 and size) for Windows and Linux, and `fetch_engines.py` refuses a file whose SHA-256 differs. `bundle-python-win.mjs` takes the CPython 3.11.9 embeddable package from the same lock. `fetch_engines.py --relock` (or a `[relock]` commit, which runs `.github/workflows/engines-lock.yml`) resolves the current releases: LibreOffice's newest release in the `LIBREOFFICE_SERIES` (26.2) from TDF's permanent archive (the mirrors drop a release when the next one comes out), the highest-numbered Ghostscript and Tesseract installers among the projects' GitHub releases, tessdata_fast at the current commit, and Temurin 21 from the Adoptium API; it checks the publishers' own checksums (GitHub's asset digests, Adoptium's and PyPI's SHA-256, Maven's SHA-1) before writing the lock. The first relock picked LibreOffice 26.8.0.3 (a new feature series' first release) and Tesseract 5.4.0 (UB Mannheim's own repository stopped at it); the series pin and searching the upstream repository too brought back 26.2.6.3 and 5.5.3, the versions the converter's tests were tuned on.

| Lock entry (win-x64) | Version | Download |
|---|---|---|
| python | CPython 3.11.9 embeddable | 11 MB |
| libreoffice | LibreOffice 26.2.6.3 | 374 MB |
| ghostscript | Ghostscript 10.08.0 | 65 MB |
| tesseract | Tesseract 5.5.3.20260724 | 50 MB |
| tessdata | tessdata_fast @ 874164186573 (17 files) | 54 MB |
| jre | Temurin jdk-21.0.12.1+1 (the JDK, for jlink) | 205 MB |
| pandoc | pypandoc_binary 1.16.2 (pandoc 3.8.2.1) | 40 MB |
| verapdf | veraPDF 1.28.2 (19 jars) | 19 MB |
| resvg | resvg 0.45.1 | 1 MB |

**Unpacked, not installed.** The installers are never run: LibreOffice's MSI is unpacked with an administrative install (`msiexec /a`) and the Ghostscript and Tesseract NSIS installers with 7-Zip, and their program folders copied (Ghostscript's `vcredist_x64.exe`, the uninstallers and NSIS's plug-in folder are left out, as are Tesseract's ScrollView jars). Running them silently, tried first, hung a CI job for its whole six hours. Unpacking showed that **Ghostscript needs Microsoft's C++ runtime** (`msvcp140`, `vcruntime140`, `vcruntime140_1`), which its installer installs system-wide and a clean Windows does not have: since v0.2 the copied Ghostscript probably would not have started on such a PC (GitHub's runners have the runtime, so no test noticed). It now carries app-local copies of the three DLLs, taken from the bundled Java runtime (Microsoft allows redistributing them with an application; the licence list names them). The other engines were checked: resvg and Pandoc need only Windows' own runtime, Tesseract carries its MinGW libraries, and LibreOffice, Java and Python ship their own.

**A trimmed Java runtime.** `jlink` builds the runtime from the JDK with `java.base, java.compiler, java.datatransfer, java.desktop, java.logging, java.management, java.naming, java.scripting, java.sql, java.xml, jdk.charsets, jdk.unsupported` (what `jdeps` finds in veraPDF's jars, plus the modules its parsers load by reflection), `--strip-debug --no-man-pages --no-header-files --compress=zip-6`. Checked here with OpenJDK 21: the same veraPDF verdicts and failed-rule counts as the full JDK on a compliant and a non-compliant PDF, and every PDF/A test passes; the packaged smoke test checks the runtime's module list and the full self-test validates a PDF/A with it. 56 MB instead of about 130 MB.

**The licence list.** `scripts/collect_licenses.py` (run by `npm run licenses`, and by the release on the bundled Python) lists what the build actually contains: the Electron runtime (Chromium's own notices ship as `LICENSES.chromium.html`), the JavaScript Vite bundled (a build plugin records it), CPython and every Python distribution in the bundled `site-packages`, the copyleft native libraries found inside wheels and engines by file name (GEOS in shapely, libheif and libde265 in pi-heif, FFmpeg in OpenCV, the GCC runtime), the engines with the licence files they ship, veraPDF's 19 jars (licences checked against their POMs on Maven Central), tessdata, the 73 font families and the models. Each gets an SPDX expression, a copyleft level (AGPL, GPL, weak, none; for a dual licence the most permissive open option, commercial options don't count) and its licence text (the component's own files, or the SPDX text from `scripts/licenses/spdx/`). The build fails if any licence is unknown. On this Linux build: 192 components, 1 AGPL (PyMuPDF), 1 GPL (Pandoc), 25 weak copyleft; the Windows build adds Ghostscript (AGPL), LibreOffice, Tesseract and the Java runtime.

**Found while doing it:** google/fonts has no licence file for **Tinos** at the pinned commit, so v0.3.0–v0.4.0 shipped Tinos without its OFL text. `fetch_fonts.py` now writes the standard OFL text with the font's own copyright notice when upstream has none, and a test checks every font family has its licence.

**Sample files** (`samples/`, `resources/samples/`) are drawn by the test generators or are the two public-domain test portraits: nothing third-party is added.

## 1. Runtimes and CLI engines

| Component | Min. version | License | Used for | How it's used | Size | Flag |
|---|---|---|---|---|---|---|
| Electron (Chromium, Node) | 44.x (current) | MIT; Chromium BSD-3 + third-party; bundled FFmpeg LGPL-2.1 | App shell, HTML/TXT/SVG/EPUB→PDF | App runtime | ≈ 280 MB | |
| CPython (python-build-standalone) | 3.11 | PSF-2.0 (+ OpenSSL Apache-2.0, zlib, libffi MIT, SQLite PD) | Worker runtime | Separate process | ≈ 60 MB | |
| LibreOffice | ≥ 7.4 (PDF/A-3b, JSON filter options) | MPL-2.0 (third-party parts listed in its `license.html`) | Office ⇄ PDF/PDF/A, legacy DOC/XLS/PPT, PDF import, SVG→shapes | Separate process, UNO over named pipe | ≈ 350 MB (trimmed: no help, no Java, no extensions) | |
| Pandoc | ≥ 3.1 (`--sandbox`) | **GPL-2.0-or-later** | HTML/DOCX/EPUB ⇄ each other, TXT/PPTX writers | Separate executable | ≈ 180 MB | ⚠️ GPL |
| Ghostscript | ≥ 10.02 | **AGPL-3.0** or Artifex commercial | PDF → PDF/A-1b/2b/3b, OCRmyPDF back end | Separate executable | ≈ 60 MB | ⚠️ AGPL |
| Tesseract (+ Leptonica) | ≥ 5.3 | Apache-2.0 (Leptonica BSD-2) | OCR for Indic, Arabic, Hebrew and other scripts; OCRmyPDF | Separate executable | ≈ 60 MB | |
| veraPDF (greenfield CLI) | ≥ 1.26 | **GPL-3.0+ or MPL-2.0 (dual)**: we use it under MPL-2.0 | PDF/A validation | Separate JVM process | ≈ 60 MB | |
| Eclipse Temurin JRE (jlink-trimmed) | 21 LTS | GPL-2.0 **with Classpath Exception** | Runs veraPDF | Separate runtime | ≈ 45 MB | CE = no obligation on our code |
| resvg | ≥ 0.45 | Apache-2.0 OR MIT (0.48.1 checked on crates.io) | SVG → PNG | Separate executable | ≈ 4 MB | |

## 2. Libraries

### JavaScript (all MIT unless noted; versions from npm, 2026-09-30)

| Package | Version | License | Purpose |
|---|---|---|---|
| react, react-dom | 19.3 | MIT | UI |
| konva, react-konva | 10.7 / 19.3 | MIT | Canvas editors, cropper, overlays |
| zustand, immer | 5.0 / latest | MIT | State, undo/redo patches |
| ajv | 8.20 | MIT | JSON Schema validation of settings/presets |
| electron-vite, vite, typescript | 5.0 / 8.3 / 7.0 | MIT / MIT / Apache-2.0 | Build (dev only) |
| electron-builder | 26.15 | MIT | Packaging (dev only) |
| vitest, @playwright/test | 5.0 / 1.63 | MIT / Apache-2.0 | Tests (dev only) |

### Python (versions from PyPI, 2026-09-30; all have Python 3.11 wheels for win_amd64)

| Package | Version | License | Purpose | Flag |
|---|---|---|---|---|
| numpy | 2.4.x (2.5 needs 3.12) | BSD-3 | Arrays | |
| Pillow | 12.3 | MIT-CMU (bundles libjpeg-turbo, libwebp, LittleCMS MIT, zlib) | Image I/O, JPEG/WEBP/PNG encoders, ICC | |
| pi-heif | 1.4 | BSD-3; wheel bundles **libheif, libde265 (LGPL-3.0)** | HEIC decode only (no x265 encoder, so no GPL-2.0 code) | LGPL: shipped as separate replaceable DLLs ✔ |
| opencv-contrib-python-headless | 5.0 | Apache-2.0; wheel bundles FFmpeg (LGPL-2.1) | Deskew, denoise, shapes, inpainting (Telea, xphoto FSR), GrabCut cut-outs, guided filter | LGPL DLL ✔ |
| onnxruntime | 1.30 (DirectML variant 1.24, optional GPU) | MIT | Runs all ONNX models | |
| mediapipe | 1.0.1 | Apache-2.0 | Face Landmarker, selfie segmenter | |
| rapidocr | 3.9 | Apache-2.0 | PP-OCR via ONNX Runtime | |
| rapid-layout, rapid-table | 1.2 / 3.0 | Apache-2.0 | Layout regions, table structure | |
| vtracer | 0.6 | MIT | Raster → SVG vectorising | |
| **PyMuPDF** | 1.28 | **AGPL-3.0** or Artifex commercial | PDF extraction, rendering, SVG export, pdf2docx back end | ⚠️ AGPL, *imported into the worker* |
| pdf2docx | 0.5.13 | MIT (but requires PyMuPDF) | PDF → editable DOCX | inherits PyMuPDF's AGPL obligations |
| pypdfium2 | 5.13 | Apache-2.0 / BSD-3 (PDFium BSD-3) | Independent PDF extractor for verification | |
| pikepdf | 10.16 | MPL-2.0 (qpdf Apache-2.0) | PDF structure, XMP, merge, lossless image copy, decryption | |
| img2pdf | 0.6.3 | LGPL-3.0 | Lossless image → PDF | pure-Python module, replaceable ✔ |
| ocrmypdf (+ pdfminer.six, pluggy) | 17.13 | MPL-2.0 (MIT, MIT) | Searchable text layer, OCR+PDF/A for scans | |
| python-docx, python-pptx, openpyxl | 1.2 / 1.0.2 / 3.1.5 | MIT | Office writers/readers | |
| docxcompose | 2.2 | MIT | DOCX merge | |
| msoffcrypto-tool | 6.0 | MIT | Decrypt password-protected Office files | |
| lxml | 6.1 | BSD-3 (libxml2/libxslt MIT) | HTML/XML/EPUB/SVG parsing (entities and network off) | |
| fontTools, brotli | 4.66 / 1.2 | MIT | Font subsetting, WOFF2, metrics | |
| uharfbuzz | 0.56 | Apache-2.0 (HarfBuzz Old-MIT) | Shaping for font matching (Indic/RTL) | |
| rapidfuzz | 3.14 | MIT | Text similarity in verification | |
| charset-normalizer | 3.5 | MIT | TXT encoding detection | |
| psutil, jsonschema | 7.2 / 4.26 | BSD-3 / MIT | Process/socket audit, schema validation | |

## 3. Copyleft — only matters if you ever redistribute

**Personal use only (D1): nothing in this table requires action.** GPL, AGPL and LGPL obligations apply when you give the app to someone else. Running it yourself, on as many of your own machines as you like, triggers none of them. The table is kept so the picture is clear if that ever changes.

| Component | License | Linked how | What you must do when distributing | Risk |
|---|---|---|---|---|
| **PyMuPDF** (and pdf2docx through it) | AGPL-3.0 | Imported into the Python worker, so the worker is a combined work | Distribute the worker (realistically the whole app) under **AGPL-3.0-compatible** terms, with source. Or buy an Artifex commercial licence. | **High** for closed-source distribution. None for personal use or an AGPL-licensed toolkit. |
| **Ghostscript** | AGPL-3.0 | Separate executable (aggregation) | Ship its license and corresponding source (or a written offer). Commercial closed-source distribution normally uses an Artifex licence. | Medium |
| **Pandoc** | GPL-2.0+ | Separate executable (aggregation) | Ship its license and corresponding source (or a written offer) | Low |
| veraPDF | GPL-3.0+ / MPL-2.0 | Separate process | Choose MPL-2.0: ship the license, plus source for any files we modify (none) | Low |
| Temurin JRE | GPL-2.0 + Classpath Exception | Separate runtime | Ship the license | Low |
| libheif / libde265 (pi-heif), FFmpeg (OpenCV, Electron), GEOS (shapely), FriBiDi (Pillow, Windows build), the GLib/Pango/cairo family if an engine build carries them | LGPL | Dynamic libraries | Ship licenses, keep them replaceable (they are separate DLLs), offer source | Low |
| img2pdf, fpdf2 (OCRmyPDF's text layer) | LGPL-3.0 | Python modules (replaceable files) | Ship the license | Low |
| LibreOffice, pikepdf, OCRmyPDF, certifi, tqdm (MPL-2.0 AND MIT), Rhino (in veraPDF) | MPL-2.0 | Separate process / library | Ship licenses, plus source of any MPL files we modify (none) | Low |
| JAXB and JavaBeans Activation (in veraPDF) | CDDL-1.1 or GPL-2.0 with the Classpath exception | Jars run by the separate Java process | Ship the licences | Low |

If you ever do share it, the simplest path is to license the toolkit's own code AGPL-3.0-or-later and publish the source. The alternatives are Artifex commercial licences, or replacing PyMuPDF/pdf2docx with pypdfium2 + pikepdf, which makes PDF → editable DOCX clearly worse.

## 4. Considered and **not** bundled

| Component | License | Why not |
|---|---|---|
| Calibre (`ebook-convert`) | GPL-3.0 | ~400 MB. Pandoc + Chromium cover EPUB in both directions. |
| Inkscape | GPL-2.0+ | ~300 MB. resvg, Chromium and LibreOffice cover the SVG routes. |
| potrace | GPL-2.0 | Black-and-white only. vtracer (MIT) traces colour. |
| Poppler | GPL-2.0/3.0 | Duplicates PyMuPDF/pypdfium2. |
| PaddlePaddle runtime | Apache-2.0 | ~1 GB with Windows install problems. The same PP-OCR models run on ONNX Runtime via RapidOCR. |
| ultralytics YOLO, DocLayout-YOLO | **AGPL-3.0** | PP-DocLayout (Apache-2.0) does the same job |
| BRIA RMBG 1.4 / 2.0 | **CC BY-NC 4.0** (non-commercial) | MODNet (Apache-2.0) + OpenCV GrabCut instead |
| InsightFace models | Non-commercial | MediaPipe (Apache-2.0) instead |
| ebooklib | AGPL-3.0 | EPUB is read with zipfile + lxml, and written by Pandoc |
| LaMa inpainting | Apache-2.0 | **Lite bundle (D2).** OpenCV Telea + `xphoto` FSR instead (weaker on text over photos) |
| IS-Net (DIS) cut-outs | Apache-2.0 | **Lite bundle (D2).** MODNet for people + OpenCV GrabCut for objects |
| Noto Sans CJK (SC/TC/JP/KR) | OFL-1.1 | **Lite bundle (D2).** CJK text uses the fonts Windows already ships |
| Tesseract `tessdata_best`; chi_sim/chi_tra/jpn/kor models; PP-OCR Japanese/Korean packs | Apache-2.0 | **Lite bundle (D2).** `tessdata_fast` for the kept languages; the default PP-OCR model still reads Chinese |

## 5. AI models (all run offline through ONNX Runtime or MediaPipe; SHA-256 pinned)

| Model | License | Module | Size |
|---|---|---|---|
| PP-OCR (v4/v5) detection + recognition (English + Chinese) + angle | Apache-2.0 | 2, 3, 4 | ≈ 20 MB |
| Tesseract `tessdata_fast` (eng, hin, mar, san, ben, guj, pan, tam, tel, kan, mal, ori, urd, ara, heb; configurable) | Apache-2.0 | 2, 3 | ≈ 35 MB |
| PP-DocLayout (via RapidLayout) | Apache-2.0 | 2, 3 | ≈ 10–40 MB |
| SLANet+ table structure (via RapidTable) | Apache-2.0 | 2, 3 | ≈ 10 MB |
| Real-ESRGAN `realesr-general-x4v3` | BSD-3-Clause | 3, 4 | ≈ 5 MB |
| MODNet photographic portrait matting (planned; **not bundled**, see §0c) | Apache-2.0 | 4 | ≈ 25 MB |
| MediaPipe Face Landmarker (landmark model only), Selfie Segmenter | Apache-2.0 | 3, 4 | 2.8 MB |
| YuNet face detector (added in Phase 4) | MIT | 4 | 0.23 MB |

## 6. Fonts and colour

| Asset | License | Purpose |
|---|---|---|
| Noto Sans/Serif + Devanagari, Bengali, Gujarati, Gurmukhi, Kannada, Malayalam, Oriya, Tamil, Telugu, Sinhala, Naskh Arabic, Hebrew, Thai (no CJK, see D2) | OFL-1.1 | UI, fallback for every conversion, Unicode coverage (≈ 60 MB) |
| Liberation Sans/Serif/Mono (Arial / Times New Roman / Courier New metrics) | OFL-1.1 | LibreOffice metric-compatible substitution |
| Carlito (Calibri metrics), Caladea (Cambria metrics), Gelasio (Georgia metrics) | OFL-1.1 / Apache-2.0 / OFL-1.1 | Same |
| ~40 design families for Module 3 font matching (e.g. Roboto, Open Sans, Lato, Montserrat, Poppins, Inter, Oswald, Playfair Display, Merriweather, EB Garamond, Cinzel, Great Vibes, Dancing Script, Bebas Neue, Mukta, Hind, Baloo 2) | OFL-1.1 / Apache-2.0 | Closest-font mapping; the list lives in `fonts.json` and is editable |
| sRGB ICC **v2** profile (Compact-ICC-Profiles) | CC0-1.0 | PDF/A OutputIntent (v2 works for PDF/A-1, 2 and 3) and the optional JPEG embed |

## 7. Build-time only (not shipped)

electron-builder (MIT), NSIS (zlib), the Temurin JDK (GPL-2.0 with the Classpath exception: only its `jlink` and module files are used, to cut the runtime), Windows Installer (`msiexec /a`, an administrative install, which only unpacks) for LibreOffice and 7-Zip (LGPL-2.1, preinstalled on GitHub's runners) for the Ghostscript and Tesseract installers, as the plan said (with `msiexec /a` instead of lessmsi). Running the installers silently was tried first and hung a CI job for six hours.
