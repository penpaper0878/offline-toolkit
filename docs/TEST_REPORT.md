# Test report

Updated at the end of each phase. Every result below is from an actual run. Anything not run is listed as such.

## Phase 4: Module 4 (Passport Photo Maker), 2026-10-06

### Environment

- **Machine:** the same Linux container (Ubuntu 24.04, x86-64, 4 cores, 15 GB RAM), run as root, Xvfb for the app tests.
- **Models here:** as in Phase 3, plus YuNet and the MediaPipe face landmark model fetched by `scripts/fetch_models.py` (8 MB of models in all).
- **Test photos:** two public-domain portraits (`worker/tests/fixtures/faces/`): an 820 × 1024 studio portrait in front of a red curtain, a window and flags (a hard background), and a 512 × 512 NASA portrait (too few pixels for most specs on purpose). Synthetic faces are not used: the face and landmark models need real faces.

### Results

| Suite | Command | Result |
|---|---|---|
| TypeScript typecheck | `npm run typecheck` | **pass** |
| JavaScript unit tests (vitest), including the passport geometry and units shared with Python (`tests/vectors/passport.json`), the preset schemas and how settings changes merge | `npm test` | **49 / 49 pass** |
| Python tests (pytest): Phases 1–3 plus 57 passport tests: geometry and DPI/mm/px maths, face measurements on both photos (metamorphic: shifted, scaled, turned and mirrored copies give the same measurements), auto fit for every preset, hints, crown and chin corrections, background and brush, adjustments, white balance, red-eye, single exports (pixels, DPI, PDF mm, size limit), sheet layout and exports, and **visual regression** against reviewed reference pictures (crop, UK and US photos, a 4 × 6 in sheet: auto fit compared by its measurements with stated tolerances, the pictures at the reference placement by SSIM), and the shared models used from 8 threads at once | `npm run test:py` | **269 / 269 pass**, none skipped |
| End-to-end, real app + worker (Playwright): resizer ×2, converter, design ×2, **passport ×2** (open → crop with flip, straighten, undo/redo → size to UK and US rules with hints → background → adjust → save JPG / size-limited JPG / PDF → 4 × 6 in sheet as PDF and PNG → 5 × 5 overflow refused; paste a photo → own preset saved to the JSON file → erase brush with undo/redo → crown marker dragged and refitted → two people on one sheet → print path at 100%) | `npm run test:e2e` | **7 / 7 pass** (the packaged-app test runs on Windows only) |
| The two passport app tests, repeated three times; and five times with four other processes keeping every CPU busy | `playwright test tests/e2e/passport.spec.ts --repeat-each=3` (`=5` under load) | **6 / 6 pass; 10 / 10 pass** |
| **No network at all**: pytest and the app tests inside a Linux network namespace with no interfaces (network guard off, so only the OS blocks) | `npm run test:offline` | **268 / 268 pytest, 7 / 7 app tests pass** here (before the last test was added; the app tests re-run after the paste fix below); Ubuntu CI repeats it on every push: 269 / 269 and 7 / 7 |
| Packaged-app smoke test, dry run against the development build here (all four modules, the passport photo and sheet at exact size) | `OTK_PACKAGED_EXE=… playwright test tests/e2e/packaged.spec.ts` | **pass** (1.7 min) |
| Ubuntu CI (`ubuntu-latest`): all of the above, plus the no-network run | `.github/workflows/ci.yml`, run 37492882513 | **all pass** (49 vitest, 269 pytest, 7 E2E; no network: 269 pytest, 7 E2E) |
| Windows CI (`windows-latest`, bundled engines, FriBiDi on PATH) | same run | **all pass** (49 vitest, 269 pytest including the reference pictures, 7 E2E with both passport flows) |
| Packaged Windows app | `.github/workflows/release.yml` | see *Windows packaging (Phase 4)* below |

### Exact sizes (checked by the tests on the saved files)

| Output | Expected | Measured |
|---|---|---|
| UK passport JPG | 413 × 531 px, 300 DPI in the file | 413 × 531 px, JFIF 300 × 300 |
| Same, *within 20–60 KB* | 413 × 531 px, 20–60 KB | 413 × 531 px, 59.0 KB |
| UK passport PDF | one page, 35 × 45 mm | 35.000 × 45.000 mm |
| US passport PNG | 600 × 600 px at 300 DPI (2 × 2 in) | 600 × 600 px, pHYs 300 DPI |
| 4 × 6 in sheet PDF | 101.6 × 152.4 mm, 6 places, the photo stored once | 101.600 × 152.400 mm, 6 placements of 1 image object, each 35.00 × 45.00 mm |
| 4 × 6 in sheet PNG | 1200 × 1800 px at 300 DPI | 1200 × 1800 px, 300 DPI, nothing printed in the outer 8 px |
| A5 sheet PNG at 300 / JPG at 600 DPI | 1748 × 2480 / 3496 × 4961 px | as expected |
| Print | page 101.6 × 152.4 mm, 100% scale, no margins | `webContents.print` called with 101 600 × 152 400 µm, scaleFactor 100, margins none; the page's CSS size 101.600mm 152.400mm, photos 30.000 × 40.000 mm (own preset) |

### Every preset fitted automatically (first crop and Auto fit, background replaced, no hand corrections)

| Preset | Head allowed | Head after Auto fit | Other checks set by the rules | Hints not green |
|---|---|---|---|---|
| UK passport 35 × 45 mm | 29–34 mm (to the top of the head) | 31.5 mm | | resolution (amber) |
| Schengen visa 35 × 45 mm | 31.5–36 mm | 33.75 mm | | resolution (amber) |
| India passport 4.5 × 3.5 cm | 36–38.25 mm (to the top of the hair) | 37.1 mm | | resolution (amber) |
| Australia passport 35 × 45 mm | 32–36 mm | 34.0 mm | | resolution (amber) |
| US passport 2 × 2 in | 1–1.375 in (hair) | 1.19 in | eye line 1.125–1.375 in: 1.25 in | resolution (amber) |
| China visa 33 × 48 mm | 28–33 mm (hair) | 30.5 mm | space above 3–5 mm: 4.0; below the chin ≥ 7 mm: 13.5 | resolution (amber) |
| Canada passport 50 × 70 mm | 31–36 mm | 33.5 mm | | resolution (amber) |
| ID 25 × 35 mm (unverified) | 24.5–28 mm | 26.25 mm | | none |
| ID 3 × 4 cm (unverified) | 28–32 mm | 30.0 mm | | resolution (amber) |

That is for the 820 × 1024 portrait; the head always lands in the middle of the range, centred and level. The only amber hint is correct: at 300 DPI the photo is enlarged 1.1–1.4× (0.96× for 25 × 35 mm, which is green). On the 512 × 512 portrait the same sizes and positions are reached and the resolution hint is red for every preset (enlarged 1.9–2.7×), as it should be.

The face measurements follow transformed copies of both photos (`test_passport.py`): the measured tilt follows turns of −8° and +6° within 0.8°; a copy at 60% gives 60% of the eye distance within 3% and the chin within 8% of the eye distance; a mirrored copy mirrors the eyes within 5% of the eye distance. The portrait turned 7° and padded, after Auto fit, puts the top of the head and the chin on the same output pixels within 1.5 px and the eye line within 0.15 mm of the original's.

### Measured performance (Linux container, one photo at a time)

| Step | 820 × 1024 | 4000 × 4995 (20 MP) | 6000 × 7493 (45 MP) |
|---|---|---|---|
| Open the photo | 0.04 s | 0.83 s | 1.46 s |
| Find the face, landmarks and person (first crop) | 1.40 s | 1.93 s | 2.01 s |
| Analyse the chosen crop | 0.58 s | 1.61 s | 1.57 s |
| Draw the photo (the preview is the output itself) | 0.11 s | 0.12 s | 0.12 s |
| … with exposure, contrast, sharpening, noise reduction, red-eye | 0.46 s | 0.47 s | 0.50 s |
| Save a JPG within 20–240 KB / a PDF | 0.51 / 0.21 s | 0.49 / 0.20 s | 0.52 / 0.25 s |
| Sheet preview / A4 sheet PDF | 0.02 / 0.17 s | 0.01 / 0.17 s | 0.02 / 0.26 s |
| A4 sheet PNG at 600 DPI (4961 × 7016 px) | 5.5 s | 5.5 s | 5.0 s |
| AI upscaling (Real-ESRGAN), when the photo is too small | 3.1 s | not needed | not needed |
| **Peak memory (worker)** | **0.38 GB** | **0.53 GB** | **0.63 GB** |

Far below the 8 GB target. Every step after the analysis works on the region the output needs, so a large photo costs little more than a small one.

### Windows packaging (Phase 4)

*Filled in from the CI and release runs of this version.*

### Found and fixed in this phase

- **MediaPipe's landmark model lost two of its three outputs** in OpenCV 5's new DNN engine: the classic engine is used.
- **A bright window beside the head was kept as "person"** by the selfie segmenter: the head is segmented again from a close-up, and GrabCut works only in a band around the outline, keeping what touches confident person pixels.
- **A red fringe around the hair** from the old red curtain: edge colours are decontaminated; a too-wide glow at the edge came from a loose guided filter, now tight.
- **Auto white balance "neutralised" the red curtain** (and turned skin green): only near-neutral pixels are used, and the whole range only when the background is near-neutral; its solve is now exact and does not clip.
- Found by running the wizard in the real app (the reason for the app tests):
  - **Pasting a photo crashed the page.** The main process turned every file path under the previews folder into an `otk://` URL and dropped the path; a pasted photo is saved there, so the wizard got a photo without a path. Paths are kept now; the second app test pastes a real image through the system clipboard.
  - **What the crop left out was shown anyway.** Pixels beyond the crop came from the full photo but had no cut-out, so a square US photo made from a 35 × 45 crop showed the shoulders cut off at the crop's sides with white beyond. The crop now limits what is shown (soft-edged), and the crop takes the new shape when the spec changes; the first crop is sized from the spec, so small-head specs (Canada 50 × 70 mm) get room.
  - **The frame hint was amber for every tight portrait** with hair near the top edge, though the replaced background filled the gap seamlessly. It now measures whether the photo's or the crop's edge cuts through the person (green when only background is missing; amber or red, with a clear label, when the head or shoulders are cut).
  - **Other people's photos on a sheet were stretched** to the cell's shape: they are now trimmed around the middle, and their EXIF orientation is applied.
  - **The crop step briefly showed the whole photo** before the face was framed (a click then could be lost): the wizard now frames first.
  - **A switch's hidden checkbox escaped its scrolling panel** and made the whole window scroll (shared control, so it also affected other long panels).
  - **While colours were redrawn the canvas fell back to the unprocessed photo** (a flash of the old background): the last drawn photo stays until the new one arrives.
- Found by CI:
  - **A setting changed just before a click could be ignored** (all modules): a size limit typed into *To* and *Save* clicked at once saved with the old limit (139 KB instead of at most 60 KB on Ubuntu CI). Settings now change in the window at once, merged exactly as the main process merges them, and the main process's answer replaces them only when it answers the newest change; the photo export reads the settings at the moment of the click.
  - **Overlapping requests could break the face and person models** (found while chasing a Windows app-test run where the photo was not redrawn after *Auto white balance*, once in four runs): the worker answers requests on several threads, and the OpenCV face detector, landmark network and person segmenter were shared without a lock, so two calls at once could swap inputs or fail (`cv2.error … buf.shape() == m.shape()`; reproduced here with 8 threads). Each model is now used under its own lock (results identical from 8 threads, a new test), the image pyramid is built under a lock, and the window retries a failed redraw once before reporting it, so a restarted worker no longer leaves the photo out of date.
  - **The UK reference picture differed on Windows** (SSIM 0.934): the face landmark model's floating-point results differ slightly between machines, so auto fit levelled the eyes by 0.53° instead of 0.27° and moved the photo by 0.6 px; drawing at that placement here gives exactly the same SSIM, so the Windows cut-out itself matched. The visual tests now check auto fit by its measurements, with tolerances (angle 0.5°, position 0.6%, scale 0.5%, crown and chin 2 px, eye line and margins 0.5% of the height), and compare the pictures at the reference placement, where a 1 px shift already fails (SSIM 0.88) but edge softness changes do not (0.999).

### Known limits (Module 4)

- **The hints are hints.** Measured: face found, head size, centring, level eyes, eye line and margins where the rules set them, head width (China), eyes open, resolution, frame, background, exposure. Not judged: expression, glasses and reflections, shadows on the face or background, head coverings, mouth closed, lighting evenness on the face. An office decides.
- **Top of the head without the hair** (UK, Schengen, Australia, Canada) is an anthropometric estimate from the landmarks; *top of the hair* comes from the cut-out. Both can be corrected by dragging the markers; very full or very flat hair shifts the estimate.
- **Rules from search excerpts.** The official pages could not be opened from this environment, so the seven national presets come from search excerpts of those pages (shown in the app with the source, quote and date); check the current rules before applying. The two generic ID sizes have no authority and are marked unverified.
- **No MODNet.** The cut-out is the selfie segmenter with refinements; fine stray hairs against a busy background can be lost or keep a trace of the old background. The *Restore* and *Erase* brushes fix it by hand.
- One person per photo is measured (the largest face; the hint says when there are more).
- **Printing** sends the page at 100% with no margins, but the system print dialog and the printer driver can still scale it: measure one printed photo. The print path was tested here with the print call replaced (no printer in the container): the page size, scale and HTML were checked, not paper.
- Drag-and-drop of a photo into the window was not automated (Playwright cannot drop real files); it uses the same routine as *Open*.

## Phase 3: Module 3 (Image to Editable Design), 2026-10-03

### Environment

- **Machine:** the same Linux container (Ubuntu 24.04, x86-64, 4 cores, 15 GB RAM), run as root, Xvfb for the app tests.
- **Engines and assets here:** as in Phase 2, plus the bundled fonts (73 families, 71 MB) and models (5 MB) fetched by `scripts/fetch_fonts.py` and `scripts/fetch_models.py`. Tesseract languages installed here: eng, hin, ara, heb, tam.
- **Ground truth:** `worker/tests/design_samples.py` draws four pictures and records every element: a poster (1200 × 1600: Latin and Hindi text in seven fonts, photo, star, badge, button, outline box, ellipse, rule, 4 × 3 table), a certificate (1100 × 780: script, serif and capitals fonts, double frame, seal, signature lines), a scanned page (A4 at 150 DPI, tilted 1.6°, noise σ 9, 3 × 3 table) and a 420 × 300 screenshot (13–18 px UI text).

### Results

| Suite | Command | Result |
|---|---|---|
| TypeScript typecheck | `npm run typecheck` | **pass** |
| JavaScript unit tests (vitest), including the shared design geometry (text baselines, rotation, table cells) | `npm test` | **40 / 40 pass** |
| Python tests (pytest): Phases 1–2 plus 25 design tests (13 unit, 12 on the ground-truth samples: every layer checked against the truth, exports drawn back and compared, project file round trip) | `npm run test:py` | **212 / 212 pass**, none skipped |
| End-to-end, real app + worker (Playwright): resizer ×2, converter, design ×2 (analyse a poster, edit, check, export every format; edit on the canvas: drag, type in place, recolour, table cells, cut-out, layer controls) | `npm run test:e2e` | **5 / 5 pass** (the packaged-app test runs on Windows only) |
| Same converter and design app tests, repeated three times each | `playwright test … --repeat-each=3` | **9 / 9 pass** (after fixing the two faults this found, listed below) |
| Ubuntu CI (`ubuntu-latest`): all of the above, plus a check that Pillow shapes text, and the no-network run | `.github/workflows/ci.yml`, run 37151110103 | **all pass** (40 vitest, 212 pytest, 5 E2E, no-network run) |
| Windows CI (`windows-latest`, bundled engines incl. LibreOffice 26, FriBiDi on PATH) | same run | **all pass** (40 vitest, 212 pytest including the design samples and their exports drawn by LibreOffice 26, 5 E2E with the canvas test at 1008 × 655) |
| Packaged Windows app | `.github/workflows/release.yml` | see *Windows packaging (Phase 3)* below |

### Analysis accuracy on the ground-truth samples

| | poster | certificate | scan | small (13 px) | all |
|---|---|---|---|---|---|
| Text lines read exactly | 7 / 7 | 6 / 6 | 2 / 2 | 5 / 5 | **20 / 20** |
| Font family | 7 / 7 | 6 / 6 | 2 / 2 | 4 / 5 | **19 / 20** |
| Weight and italic | 7 / 7 | 6 / 6 | 2 / 2 | 4 / 5 | **19 / 20** |
| Size within 5% | 7 / 7 | 6 / 6 | 2 / 2 | 4 / 5 | **19 / 20** |
| Colour (sum of RGB differences ≤ 12) | 7 / 7 | 6 / 6 | 1 / 2 | 5 / 5 | **19 / 20** |
| Alignment | 7 / 7 | 6 / 6 | 2 / 2 | 5 / 5 | **20 / 20** |

- The one miss on the small screenshot is the 14 px bold "Notifications": Roboto 500 at 15 px instead of Inter 600 at 14 px (the label is short and the two faces are close at that size). The scan's body text measures #0a0a0a instead of #111111 after denoising the grain.
- Every shape, rule, frame, graphic, photo and table cell in the truth files is found with the right kind, colours and stroke widths (`test_design_pipeline.py`); the scan is straightened by −1.6°; the screenshot is read on a 2× Real-ESRGAN copy.
- **Rebuilt design vs picture** (the scene drawn by Chromium from its SVG, compared like the converter's appearance check): poster SSIM 0.988, certificate 0.982, scan 0.984, small 0.988; no missing or extra marks except 3 small areas on the scan, where the title is 2% wider than the original (size 57 vs 56 px on the noisy page).
- **Exports drawn back vs the rebuilt design:** PPTX (LibreOffice) 0.980–0.993, DOCX (LibreOffice) 0.977–0.995, HTML (Chromium) 0.979–0.989, no missing marks. DOCX also renders correctly with no fonts installed (the embedded fonts are used: SSIM 0.992 poster, 0.995 certificate).
- **A language not selected:** the poster analysed with English only leaves the Hindi line in the picture untouched and lists it under *Check → Not read* (before the fix it became "#" and was erased).
- **JPEG and large pictures:** the poster saved as JPEG at quality 70, and the poster enlarged to 3000 × 4000 (analysed at 2250 × 3000), give the same layers as the original: all 7 text lines (Hindi included), button, outline box, both ellipses, rule, star, tick, photo and table, with stroke widths within 0.6 px (JPEG) and 1.2 px (enlarged) of the truth (`test_jpeg_compressed_poster`, `test_large_picture_is_analysed_at_working_size`).

### Measured performance (Linux container, idle, one analysis at a time)

| Case | Analysis time | Peak memory (worker) | Layers |
|---|---|---|---|
| Poster 1200 × 1600, English + Hindi | 26.7 s (OCR 9.1 s, fonts and styles 10.6 s) | 0.48 GB | 17 |
| Certificate 1100 × 780 | 9.3 s | 0.40 GB | 13 |
| Scanned A4 page (150 DPI, tilted, grainy) | 17.9 s | 0.52 GB | 4 |
| Screenshot 420 × 300 (13–18 px text, 2× super-resolution) | 9.6 s | 0.43 GB | 9 |
| Poster enlarged to 3000 × 4000 (12 MP) | 43.2 s | 0.91 GB | 17 |

- **Check against the original** (the *Check* tab: the design drawn by Chromium and compared): 6.1 s for the poster, 11.1 s for the 12 MP one.
- **Exports** of the poster: PowerPoint 0.1 s (0.47 MB), Word 0.2 s (1.5 MB, fonts embedded), SVG 2.4 s (0.65 MB) and HTML 4.0 s (0.76 MB) with WOFF2 font subsets, project file 0.0 s (1.5 MB). The 12 MP version: 0.2–3.8 s, 2.8–7.7 MB.
- Analysing the same picture again (for example after changing an option that does not affect reading) reuses the cached preparation, OCR and super-resolution: the poster then takes 18.3 s instead of 26.7 s.
- Everything stays far below the 8 GB target: the largest peak is 0.91 GB, for a 12 MP picture.


### Windows packaging (Phase 3)

**Release v0.3.1 (`release.yml`, run 37152148881): every step passed.**

- The smoke test ran against the packaged `Offline Toolkit.exe` (not skipped, 52 s). Besides the Phase 2 checks (bundled Python and engines, offline self-test, HEIC, resize, Word and HTML to PDF/A-2b with veraPDF), it checked that:
  - the bundled Pillow shapes text (FriBiDi next to the bundled Python);
  - Module 3 works with the bundled Python, fonts and models: a poster is analysed, its photo cut out, the design checked against the picture, and the design exported to Word.
- Files (published as pre-release [v0.3.1](https://github.com/penpaper0878/offline-toolkit/releases/tag/v0.3.1)):
  - `Offline-Toolkit-Setup-0.3.1.exe`: **649 MB** installer
  - `Offline-Toolkit-0.3.1-portable-win-x64.zip`: **890 MB** portable ZIP

  The growth from v0.2.0 (568 / 790 MB) is the fonts (71 MB), the models (5 MB), OpenCV with its extra modules, and ONNX Runtime.
- **v0.3.0** (run 37144728654, installer 649 MB, ZIP 890 MB) was published from an earlier commit of this phase, before Windows CI could run the design tests. It lacks FriBiDi, so text is measured unshaped on Windows, and it lacks the Word-export and small-screen fixes below. Use v0.3.1.
- The builds are not code-signed.

### Found and fixed in this phase

- **Converter deskew (Phase 2 bug):** tilted scans were rotated the wrong way, doubling the tilt. Fixed and tested.
- **Font weights one step heavy** (Open Sans 400 read as 500, 13 px Inter 600 as 700): shape overlap favours heavier faces; the weight is now chosen by ink coverage.
- **Small caption sizes 10% low** (Lora 22 px read as 19.7): hinting snaps small heights; the size now also uses the line's width.
- **Element masks shifted by one pixel:** OpenCV anchors a 2 × 2 kernel off-centre, so an opening moved every mask; replaced by an anchored opening.
- **A filled button found as a table, a frame inside a frame merged into one element, a 1 px input-box outline erased, a header bar at the page edge treated as background, an icon on a button found twice**: each fixed in the element and table stages, with a test.
- **Small-text colours too dark** when read from the super-resolved copy: colours and weights are measured on the original pixels.
- **Canvas fonts failed to load** in the app ("A network error occurred"): fonts load in CORS mode; the `otk://` scheme is now CORS-enabled for font files.
- **A stale accuracy score** after edits: the score is marked out of date until checked again.
- **Red and blue swapped for the OCR detector:** RapidOCR takes NumPy images as BGR and was given RGB. Fixed; detection now sees the true colours.
- **Hindi lines missed by PP-OCR's detector** (trained on Latin and Chinese; whether it finds a Devanagari line depends on colours and size): when another script is chosen, Tesseract's line finder runs too and its lines in that script are merged in.
- **Large pictures** (3000 × 4000): 154 s, 1.3 GB, a slow texture fill (98 s) and halo slivers turned into stray layers. Now analysed at up to 3000 px with photos cut from full resolution (45 s, 0.9 GB), large regions skip the slow fill, and edges are judged on a smoothed copy.
- **JPEG ringing** turned an outline box and a rule into noisy graphics, a tick into a "photo", and left slivers along shape edges. Fixed with edge-preserving smoothing for the shape tests, sliver suppression, and a wider clean-up around removed elements.
- **Shapes read as letters** (a ring as "O", a tick as "V"): low-confidence one- or two-character readings in squarish areas go to shape detection.
- **Text in an unselected script that the OCR did not even detect** became a row of traced graphics without any note; such rows are now reported as lines not read.
- **The analysis cache** could return results from an older pipeline version (or another working size); its keys now carry a version and the working size.
- **Edits could be reported "Not saved"** (found by repeating the app tests): two autosaves running at once shared one temporary file, so the second failed. Saves now run one at a time and in order in the app, and the worker writes each through its own temporary file.
- **The design start page sent requests in an endless loop** (the list of designs and the OCR languages, over 100 queued at once), which slowed the worker and once made a test time out. It now loads them once.
- **Found by the Windows CI and release runs:**
  - The font and model downloads ran under the worker's own offline guard and were blocked (as designed). `run-python.mjs --online` now switches the guard off for build-time downloads only. On Windows the download step was PowerShell, which reports only the last command, so a failed font download went unnoticed; these steps now run in bash.
  - `antlr4-python3-runtime` 4.9.3 (needed by omegaconf, which RapidOCR needs) is published as source only, and the Windows bundle installs wheels only. The bundler now builds that wheel first.
  - **No text shaping on Windows.** Pillow loads FriBiDi at run time, and Windows has none, so text was measured unshaped: Indic conjuncts and vowel signs, Arabic joining and kerning were lost. The test pictures, also drawn by Pillow, were wrong too (OCR read "सवागत" for "स्वागत"; rebuilt-design SSIM 0.966–0.978). FriBiDi 1.0.17 is now bundled next to the app's Python, CI and the packaged test check that Pillow shapes text, and an analysis without shaping says so in its notes. **v0.3.0 was published before this was found and lacks it; v0.3.1 has it.**
  - **Word text boxes in LibreOffice 26** (the bundled engine): centred text in non-wrapping Word text boxes was moved right by the box's own offset (poster DOCX SSIM 0.879, the button label off the page). Text boxes now wrap, with spare width away from the alignment edge (LibreOffice 24 renders the same as before).
  - **The editor on a small screen** (the Windows CI desktop is 1024 × 768): the module bar, layer list and inspector left the canvas 300 px wide, and the page was fitted only once, so after the window shrank part of the page was out of sight. Below 1200 px the module bar now shows icons only (canvas 470 px at 1008 px), and the page refits on resize until the user zooms or pans. The canvas test now runs at 1008 × 655 on every system.
  - The canvas test itself could read the saved scene before an edit reached it (it waited for the "Saved" label, which can still show the previous save); it now waits for each edit to appear in the saved file.
  - **No kerning in the Word export:** Word kerns only when a run asks for it, and LibreOffice follows that, while the design, PowerPoint and Impress kern. Runs now kern (certificate DOCX vs design 0.987 → 0.995, its 2 differing areas gone; poster 0.990 → 0.992).

### Known limits (Module 3)

- Handwriting, heavily decorative or distorted lettering and text on curves are not rebuilt as live text (a line the OCR cannot read stays in the picture and is listed).
- Gradients and shading inside graphics become flat colour bands when traced; the original pixels are kept with each graphic (*Use original pixels instead*).
- Text over a photo is removed by estimation and can leave smudges; textured backgrounds use xphoto FSR, which is weaker than a learned inpainter (Lite bundle: no LaMa).
- Short labels in small UI text can get a near-identical family (Roboto for Inter); the inspector lists the closest matches.
- Tables are found from ruled lines only; borderless tables become text layers.
- CJK fonts are not bundled (Lite bundle): Chinese text uses the fonts installed in Windows.
- PowerPoint uses installed fonts (*Install the fonts* adds them for the user); text placement in Word and PowerPoint follows the rules measured in LibreOffice, and could differ by a fraction of a line in Microsoft Office, which is not available in this environment.
- LibreOffice 26 draws the exact-height table rows of the Word export taller by the border width (2 px per row on the poster); LibreOffice 24, and Word as measured by others, keep the height the file asks for, which is what the export writes. The Windows test accepts exactly this difference and compares the rest of the page as strictly as before.
- LibreOffice Writer shows the text of rotated text boxes from the Word export level (the export says so); the PowerPoint export keeps the rotation in LibreOffice too. Word rotates such boxes with their text, but Microsoft Word is not available here to check.
- Cut-outs of objects with fine or hairy edges (non-person) can need touching up; there is no brush yet, only *Restore original*.

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
| Python tests (pytest): resizer, RPC, planner, converter basics, jobs, 43 representative routes | `npm run test:py` | **186 / 186 pass** |
| **Full conversion matrix**: every source × target × mode the planner offers, on the sample corpus, each verified | `OTK_FULL_MATRIX=1 … test_converter_matrix.py` | **268 / 268 routes converted; 89 Perfect, 179 Expected changes, 0 Needs review** |
| End-to-end, real app + worker (Playwright): resizer ×2, converter (Word/HTML/TXT → PDF; Word + a password-protected PDF → PDF/A-2b, reports opened) | `npm run test:e2e` | **3 / 3 pass** |
| Ubuntu CI (`ubuntu-latest`): all of the above except the full matrix, plus the no-network run | `.github/workflows/ci.yml`, run 36864613139 | **all pass** (32 vitest, 186 pytest, 3 E2E, no-network run) |
| Windows CI (`windows-latest`) with the bundled Windows engines | same run | **all pass** (32 vitest, 186 pytest including the 43 routes with the Windows engines, 3 E2E including the converter) |
| Packaged Windows app (installer + portable, engines bundled, smoke test converts to PDF/A-2b) | `.github/workflows/release.yml`, run 36866447954 | **pass**: published as pre-release v0.2.0 (details below) |

### Windows packaging (Phase 2)

**Release v0.2.0 (`release.yml`, run 36866447954): every step passed.**

- The smoke test ran against the packaged `Offline Toolkit.exe` (not skipped, 15.5 s), and checked that:
  - the app uses its bundled Python;
  - all 7 engines are found and are the bundled copies;
  - the offline self-test passes;
  - the resizer works, including HEIC;
  - a Word file and an HTML page convert to PDF/A-2b, with veraPDF passing both.
- Bundled engines in this build (`manifest.json`):
  - LibreOffice 26.2.6.3
  - Ghostscript 10.08.0
  - Tesseract 5.5.3 + `tessdata_fast` (17 languages)
  - OpenJDK 21.0.9 + veraPDF 1.28.2
  - Pandoc 3.8.2.1
  - resvg 0.45.1
- Files (published as pre-release [v0.2.0](https://github.com/penpaper0878/offline-toolkit/releases/tag/v0.2.0)):
  - `Offline-Toolkit-Setup-0.2.0.exe`: **568 MB** installer
  - `Offline-Toolkit-0.2.0-portable-win-x64.zip`: **790 MB** portable ZIP

  Most of the growth from v0.1.0 (129 / 188 MB) is LibreOffice, Pandoc and the Java runtime.
- The builds are not code-signed.

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
