/**
 * End-to-end: Module 4 in the real Electron app with the real Python worker.
 * Opens a portrait, checks the crop step (flip, straighten, undo), sizes it to a passport spec (face found,
 * auto fit, hints, background, adjustments), saves a single photo (JPG and PDF: exact pixels, DPI and page
 * size) and print sheets (PDF at exact scale, PNG at 300 DPI), and checks the grid overflow warning.
 */

import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type ElectronApplication } from '@playwright/test'
import { launch, py, readback, ROOT, stubDialogs, tempDir } from './helpers'

const PORTRAIT = join(ROOT, 'worker', 'tests', 'fixtures', 'faces', 'portrait-souza.jpg')

async function stubSave(app: ElectronApplication, path: string): Promise<void> {
  await app.evaluate(({ dialog }, path) => {
    dialog.showSaveDialog = (async () => ({ canceled: false, filePath: path })) as typeof dialog.showSaveDialog
  }, path)
}

async function onDisk(path: string, timeout = 60_000): Promise<void> {
  await expect.poll(() => existsSync(path), { timeout }).toBe(true)
}

interface PdfInfo { pages: { mm: [number, number]; images: number; placements: number }[] }

function pdfInfo(path: string): PdfInfo {
  return py<PdfInfo>(`import sys, json, pymupdf
d = pymupdf.open(sys.argv[1])
pages = []
for p in d:
    xrefs = sorted({i[0] for i in p.get_images(full=True)})
    pages.append({'mm': [round(p.rect.width / 72 * 25.4, 3), round(p.rect.height / 72 * 25.4, 3)], 'images': len(xrefs),
                  'placements': sum(len(p.get_image_rects(x)) for x in xrefs)})
print(json.dumps({'pages': pages}))`, path)
}

test('make a passport photo: crop, size, background, adjust, save a photo and print sheets', async () => {
  const data = tempDir('data')
  const out = tempDir('passport-out')
  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    await stubDialogs(app, [PORTRAIT], out)
    await page.getByTestId('nav-passport').click()
    await expect(page.getByTestId('passport-drop')).toBeVisible()
    await expect(page.getByTestId('passport-next')).toBeDisabled()

    // Step 1: open. The wizard frames the face and moves on to the crop.
    await page.getByTestId('passport-open').click()
    await expect(page.getByTestId('passport-crop-stage')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('passport-step-2')).toHaveAttribute('aria-current', 'step')
    await expect(page.getByTestId('passport-next')).toBeEnabled()
    const crop = async () => JSON.parse((await page.getByTestId('passport-crop-stage').getAttribute('data-crop'))!) as
      { cx: number; cy: number; w: number; h: number; angle: number; flipH: boolean }
    const framed = await crop()
    // The UK spec's shape (35 × 45) around the head, inside the 820 × 1024 photo.
    expect(framed.w / framed.h).toBeCloseTo(35 / 45, 2)
    expect(framed.w).toBeLessThanOrEqual(820)
    expect(framed.cx).toBeGreaterThan(300)
    expect(framed.cx).toBeLessThan(520)
    await expect(page.getByTestId('passport-crop-dims')).toContainText(`${Math.round(framed.w)} × ${Math.round(framed.h)} px`)
    await page.screenshot({ path: 'test-results/screens/30-passport-crop.png' })

    // Back to Browse: the whole photo with its facts.
    await page.getByTestId('passport-back').click()
    await expect(page.getByTestId('passport-photo-info')).toContainText('820 × 1024 px')
    await expect(page.getByTestId('passport-viewer')).toBeVisible()
    await page.screenshot({ path: 'test-results/screens/31-passport-browse.png' })
    await page.getByTestId('passport-next').click()

    // Crop: mirror, straighten, undo both, redo the turn.
    await page.getByTestId('passport-flip-h').click()
    await expect(page.getByTestId('passport-crop-dims')).toContainText('mirrored')
    await page.getByTestId('passport-angle').fill('3')
    await expect.poll(async () => (await crop()).angle).toBe(3)
    // Turning shrinks the crop so that no empty corner appears.
    expect((await crop()).w).toBeLessThanOrEqual(framed.w + 1e-6)
    await page.getByTestId('passport-undo').click()
    await page.getByTestId('passport-undo').click()
    await expect.poll(async () => crop()).toEqual(framed)
    await page.getByTestId('passport-redo').click()
    await expect(page.getByTestId('passport-crop-dims')).toContainText('mirrored')
    await page.getByTestId('passport-undo').click()
    await expect(page.getByTestId('passport-crop-dims')).not.toContainText('mirrored')

    // Step 3: size and enhance. The face is found and fitted to the UK rules.
    await page.getByTestId('passport-next').click()
    await expect(page.getByTestId('passport-size-stage')).toBeVisible()
    await expect(page.getByTestId('hint-face')).toHaveAttribute('data-level', 'ok', { timeout: 90_000 })
    for (const id of ['head', 'centre', 'level', 'frame']) await expect(page.getByTestId(`hint-${id}`)).toHaveAttribute('data-level', 'ok')
    // The 820 × 1024 portrait is enlarged about 1.4 times for 300 DPI: an honest warning, not a failure.
    await expect(page.getByTestId('hint-resolution')).toHaveAttribute('data-level', 'warn')
    await expect(page.getByTestId('passport-spec-facts')).toContainText('413 × 531 px')
    await expect(page.getByTestId('passport-spec-source')).toContainText('GOV.UK')
    const drawn = () => expect(page.getByTestId('passport-size-stage')).toHaveAttribute('data-fresh', '1', { timeout: 60_000 })
    await drawn()
    await page.screenshot({ path: 'test-results/screens/32-passport-size.png' })

    // Another spec: US 2 × 2 in, fitted again; then back to the UK.
    await page.getByTestId('passport-spec').selectOption('us-passport')
    await expect(page.getByTestId('passport-spec-facts')).toContainText('600 × 600 px')
    await expect(page.getByTestId('hint-eyeLine')).toHaveAttribute('data-level', 'ok', { timeout: 60_000 })
    await expect(page.getByTestId('hint-head')).toHaveAttribute('data-level', 'ok')
    // The crop took the square shape of the US photo, so the shoulders are not cut at the crop's sides.
    await expect(page.getByTestId('hint-frame')).toHaveAttribute('data-level', 'ok')
    await drawn()
    await page.screenshot({ path: 'test-results/screens/33-passport-us.png' })
    await page.getByTestId('passport-spec').selectOption('uk-passport')
    await expect(page.getByTestId('passport-spec-facts')).toContainText('413 × 531 px')
    await expect(page.getByTestId('hint-head')).toHaveAttribute('data-level', 'ok', { timeout: 60_000 })

    // Background: light grey, then white again.
    await page.getByTestId('passport-tab-background').click()
    await page.getByTestId('passport-bg-e3e3e3').click()
    await expect(page.getByTestId('passport-bg-e3e3e3')).toHaveAttribute('aria-checked', 'true')
    await expect(page.getByTestId('hint-background')).toContainText('#E3E3E3', { timeout: 30_000 })
    await drawn()
    await page.screenshot({ path: 'test-results/screens/34-passport-background.png' })
    await page.getByTestId('passport-bg-ffffff').click()

    // Adjust: auto enhance and auto white balance change the settings; reset puts them back.
    await page.getByTestId('passport-tab-adjust').click()
    await page.getByTestId('passport-auto-enhance').click()
    await expect(page.getByTestId('passport-adjust-changed')).toBeVisible({ timeout: 30_000 })
    await page.getByTestId('passport-auto-wb').click()
    await drawn()
    await page.screenshot({ path: 'test-results/screens/35-passport-adjust.png' })
    await page.getByTestId('passport-adjust-reset').click()
    await expect(page.getByTestId('passport-adjust-changed')).toHaveCount(0)

    // Step 4: a single photo, JPG at exactly 413 × 531 px and 300 DPI.
    await page.getByTestId('passport-next').click()
    await expect(page.getByTestId('passport-single')).toBeVisible()
    const jpg = join(out, 'photo.jpg')
    await stubSave(app, jpg)
    await page.getByTestId('passport-save-photo').click()
    await onDisk(jpg)
    await expect(page.getByTestId('passport-save-photo')).toBeEnabled({ timeout: 60_000 })
    const rb = readback(jpg)
    expect([rb.width, rb.height]).toEqual([413, 531])
    expect(rb.jfifDensity).toEqual([300, 300])
    expect(rb.format).toBe('JPEG')
    // The background was replaced with white: the top corners of the photo are white.
    const corners = py<number[][]>(`import sys, json
from PIL import Image
im = Image.open(sys.argv[1]).convert('RGB')
print(json.dumps([list(im.getpixel((3, 3))), list(im.getpixel((im.width - 4, 3)))]))`, jpg)
    for (const c of corners) for (const v of c) expect(v).toBeGreaterThanOrEqual(250)

    // JPG within 20–60 KB (the Module 1 compression engine searches the quality).
    // Settings toggles are controlled by the saved settings, so they change state once the setting is saved.
    await page.getByTestId('passport-limit').click({ force: true })
    await expect(page.getByTestId('passport-limit')).toBeChecked()
    await page.getByTestId('passport-limit-max').fill('60')
    const small = join(out, 'photo-small.jpg')
    await stubSave(app, small)
    await page.getByTestId('passport-save-photo').click()
    await onDisk(small)
    await expect(page.getByTestId('passport-save-photo')).toBeEnabled({ timeout: 60_000 })
    const rs = readback(small)
    expect([rs.width, rs.height]).toEqual([413, 531])
    expect(rs.bytes).toBeLessThanOrEqual(60 * 1024)
    expect(rs.bytes).toBeGreaterThanOrEqual(20 * 1024)

    // PDF: one page of exactly 35 × 45 mm.
    await page.getByTestId('passport-format').locator('[data-value="pdf"]').click()
    const pdf = join(out, 'photo.pdf')
    await stubSave(app, pdf)
    await page.getByTestId('passport-save-photo').click()
    await onDisk(pdf)
    await expect(page.getByTestId('passport-save-photo')).toBeEnabled({ timeout: 60_000 })
    const pi = pdfInfo(pdf)
    expect(pi.pages).toHaveLength(1)
    expect(pi.pages[0].mm[0]).toBeCloseTo(35, 2)
    expect(pi.pages[0].mm[1]).toBeCloseTo(45, 2)
    await page.screenshot({ path: 'test-results/screens/36-passport-single.png' })

    // Print sheet on 4 × 6 in: as many as fit (2 × 3 = 6 with 4 mm margins and 2 mm gaps... checked by the worker tests).
    await page.getByTestId('passport-tab-sheet').click()
    await expect(page.getByTestId('passport-sheet-preview')).toBeVisible({ timeout: 60_000 })
    await expect(page.getByTestId('passport-sheet-status')).toContainText('photos on')
    const status = (await page.getByTestId('passport-sheet-status').textContent()) ?? ''
    const count = Number(/=\s*(\d+)/.exec(status)?.[1])
    expect(count).toBeGreaterThan(0)
    await page.screenshot({ path: 'test-results/screens/37-passport-sheet.png' })

    const sheetPdf = join(out, 'sheet.pdf')
    await stubSave(app, sheetPdf)
    await page.getByTestId('passport-save-sheet').click()
    await onDisk(sheetPdf)
    await expect(page.getByTestId('passport-save-sheet')).toBeEnabled({ timeout: 60_000 })
    const si = pdfInfo(sheetPdf)
    expect(si.pages).toHaveLength(1)
    // 4 × 6 in portrait = 101.6 × 152.4 mm; the photo is stored once and placed once per place on the sheet.
    expect(si.pages[0].mm[0]).toBeCloseTo(101.6, 2)
    expect(si.pages[0].mm[1]).toBeCloseTo(152.4, 2)
    expect(si.pages[0].images).toBe(1)
    expect(si.pages[0].placements).toBe(count)

    // PNG at 300 DPI: 1200 × 1800 px.
    await page.getByTestId('passport-sheet-format').locator('[data-value="png"]').click()
    const sheetPng = join(out, 'sheet.png')
    await stubSave(app, sheetPng)
    await page.getByTestId('passport-save-sheet').click()
    await onDisk(sheetPng)
    await expect(page.getByTestId('passport-save-sheet')).toBeEnabled({ timeout: 60_000 })
    const sp = readback(sheetPng)
    expect([sp.width, sp.height]).toEqual([1200, 1800])
    expect(sp.format).toBe('PNG')

    // A 5 × 5 grid of 35 × 45 mm photos does not fit on 4 × 6 in: a warning, and nothing can be saved or printed.
    await page.getByTestId('passport-autofill').click({ force: true })
    await expect(page.getByTestId('passport-autofill')).not.toBeChecked()
    await page.getByTestId('passport-rows').fill('5')
    await page.getByTestId('passport-cols').fill('5')
    await expect(page.getByTestId('passport-sheet-status')).toHaveClass(/bad/, { timeout: 30_000 })
    await expect(page.getByTestId('passport-save-sheet')).toBeDisabled()
    await expect(page.getByTestId('passport-print')).toBeDisabled()
    await page.screenshot({ path: 'test-results/screens/38-passport-overflow.png' })
    // 2 × 2 fits.
    await page.getByTestId('passport-rows').fill('2')
    await page.getByTestId('passport-cols').fill('2')
    await expect(page.getByTestId('passport-sheet-status')).toContainText('2 × 2 = 4', { timeout: 30_000 })
    await expect(page.getByTestId('passport-save-sheet')).toBeEnabled()

    // Settings are remembered: the spec, the background and the sheet layout.
    const saved = py<{ specId: string; sheet: { auto: boolean; rows: number; cols: number } }>(`import sys, json
print(json.dumps(json.load(open(sys.argv[1], encoding='utf-8'))['passport']))`, join(data, 'settings.json'))
    expect(saved.specId).toBe('uk-passport')
    expect(saved.sheet).toMatchObject({ auto: false, rows: 2, cols: 2 })
    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
})
