# Sample files

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
| `locked.pdf`, `locked.docx` | Password-protected. The password is `secret-123`; the app asks for it and never saves it. |
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
