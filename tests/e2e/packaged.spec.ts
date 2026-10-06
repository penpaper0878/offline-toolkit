/**
 * Smoke test for the packaged Windows app (run by .github/workflows/release.yml).
 * Launches the built .exe exactly as a user would, with no development Python:
 * it must find and use its own bundled Python, stay offline, and use every module once.
 *
 *   OTK_PACKAGED_EXE  path to "Offline Toolkit.exe" (test is skipped without it)
 *   OTK_TEST_PYTHON   the bundled python.exe, used by the test's own helpers
 *   OTK_PACKAGED_ARGS optional extra arguments (dry runs against a dev build, e.g. ". --no-sandbox")
 */

import { copyFileSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { _electron as electron, expect, test } from '@playwright/test'
import { makePhoto, py, readback, ROOT, stubDialogs, tempDir } from './helpers'

const exe = process.env.OTK_PACKAGED_EXE

test.skip(!exe, 'Set OTK_PACKAGED_EXE to the packaged app to run this test')
test.setTimeout(600_000)

test('packaged app: bundled Python and engines, offline self-test, HEIC, resize, convert to PDF/A-2b, image to design, passport photo', async () => {
  const data = tempDir('pkg-data')
  const inputs = tempDir('pkg-in')
  const out = tempDir('pkg-out')
  const photo = join(inputs, 'फोटो.jpg')
  makePhoto(photo, 1600, 1200)
  const heic = join(inputs, 'quadrants.heic')
  copyFileSync(join(ROOT, 'worker', 'tests', 'fixtures', 'quadrants.heic'), heic)

  const env = { ...process.env, OTK_DATA_DIR: data } as Record<string, string>
  delete env.OTK_PYTHON // the app must use its own bundled Python
  delete env.OTK_RESOURCES
  delete env.OTK_WORKER_DIR
  const extra = (process.env.OTK_PACKAGED_ARGS ?? '').split(' ').filter(Boolean)
  const bundled = extra.length === 0
  const app = await electron.launch({ executablePath: exe!, args: extra, env })
  const page = await app.firstWindow()
  try {
    await page.waitForSelector('[data-testid="nav-resizer"]')

    await page.getByTestId('nav-settings').click()
    await expect(page.getByTestId('diagnostics')).toContainText('Python 3.11', { timeout: 60_000 })
    await expect(page.getByTestId('diagnostics')).toContainText('network guard on')
    await expect(page.getByTestId('diagnostics')).toContainText('HEIC yes')
    if (bundled) await expect(page.getByTestId('python-path')).toContainText(join('resources', 'engines', 'python'))
    // Every conversion engine is present, and in the packaged app it is the bundled copy.
    for (const name of ['soffice', 'pandoc', 'gs', 'tesseract', 'java', 'resvg', 'verapdf']) {
      const row = page.getByTestId('engines').locator(`[data-engine="${name}"]`)
      await expect(row, name).toHaveClass(/good/, { timeout: 60_000 })
      if (bundled) await expect(row, name).toHaveAttribute('data-bundled', 'yes')
    }
    await page.getByTestId('run-selftest').click()
    await expect(page.getByTestId('selftest-result')).toContainText('Passed', { timeout: 60_000 })
    await page.screenshot({ path: 'test-results/screens/packaged-settings.png' })

    await page.getByTestId('nav-resizer').click()
    await stubDialogs(app, [photo, heic], out)
    await page.getByTestId('add-images').click()
    await expect(page.getByTestId('thumbs').locator('.thumb.ready')).toHaveCount(2, { timeout: 60_000 })
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'ok', { timeout: 60_000 })
    await expect(page.getByTestId('out-px')).toHaveText('240 × 240 px')
    await page.screenshot({ path: 'test-results/screens/packaged-resizer.png' })

    // The HEIC fixture is a tiny flat image: allow padding so it can reach 20 KB too.
    await page.locator('summary', { hasText: 'Advanced' }).click()
    await page.getByText('Pad to minimum size').click()
    await expect(page.getByTestId('allow-padding')).toBeChecked()
    await page.getByTestId('process').click()
    await expect(page.getByTestId('batch-counts')).toContainText('ok', { timeout: 120_000 })
    await page.getByTestId('batch-close').click()
    const jpgs = readdirSync(out).filter((f) => f.endsWith('.jpg'))
    expect(jpgs.length).toBe(2)
    for (const f of jpgs) {
      const rb = readback(join(out, f))
      expect([rb.width, rb.height]).toEqual([240, 240])
      expect(rb.jfifDensity).toEqual([200, 200])
    }

    // Module 2 with the bundled engines: Word (LibreOffice) and HTML (the app's Chromium) to PDF/A-2b.
    const docs = tempDir('pkg-docs')
    const s = py<Record<string, string>>(`import sys, json
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'worker', 'tests'))})
import corpus
from pathlib import Path
print(json.dumps({k: str(v) for k, v in corpus.build(Path(sys.argv[1]), legacy=False, pdfa=False).items()}))`, docs)
    const convOut = tempDir('pkg-conv')
    await page.getByTestId('nav-converter').click()
    await stubDialogs(app, [s.docx, s.html], convOut)
    await page.getByTestId('target-pdfa2b').click()
    await page.getByTestId('add-docs').click()
    await expect(page.locator('[data-testid="conv-row"][data-status="ready"]')).toHaveCount(2, { timeout: 120_000 })
    await page.getByRole('button', { name: 'Change…' }).click()
    await page.getByTestId('convert').click()
    await expect(page.getByTestId('verdict')).toHaveCount(2, { timeout: 300_000 })
    await page.screenshot({ path: 'test-results/screens/packaged-converter.png' })
    for (const name of ['report.pdf', 'page.pdf']) {
      const r = JSON.parse(readFileSync(join(convOut, `${name}.report.json`), 'utf-8')) as { checks: { id: string; status: string }[] }
      expect(r.checks.find((c) => c.id === 'pdfa')?.status, name).toBe('pass')
    }

    // Module 3 with the bundled Python, fonts and models: analyse a poster, cut out its photo, check it
    // against the picture (the app's Chromium) and export Word (fonts embedded). The bundled Pillow must
    // shape text (FriBiDi next to python.exe), or Hindi and Arabic are measured unshaped.
    expect(py<boolean>(`import json
from PIL import features
print(json.dumps(features.check('raqm')))`)).toBe(true)
    const poster = py<string>(`import sys, json
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'worker', 'tests'))})
import design_samples
from pathlib import Path
p, _ = design_samples.build(Path(sys.argv[1]), ['poster'])['poster']
print(json.dumps(str(p)))`, tempDir('pkg-design'))
    const designOut = tempDir('pkg-design-out')
    await page.getByTestId('nav-design').click()
    await stubDialogs(app, [poster], designOut)
    await page.getByTestId('design-open-image').click()
    await expect(page.getByTestId('design-editor')).toBeVisible({ timeout: 300_000 })
    await page.locator('[data-testid^="layer-row-photo"]').first().click()
    await page.getByTestId('design-cutout').click()
    await expect(page.getByText('Background removed')).toBeVisible({ timeout: 120_000 })
    await page.getByTestId('design-tab-check').click()
    await expect(page.getByTestId('design-score')).toBeVisible({ timeout: 180_000 })
    await page.screenshot({ path: 'test-results/screens/packaged-design.png' })
    const docx = join(designOut, 'poster.docx')
    await app.evaluate(({ dialog }, path) => {
      dialog.showSaveDialog = (async () => ({ canceled: false, filePath: path })) as typeof dialog.showSaveDialog
    }, docx)
    await page.getByTestId('design-export').click()
    await page.getByTestId('design-export-format').locator('[data-value="docx"]').click()
    await page.getByTestId('design-export-go').click()
    await expect.poll(() => readdirSync(designOut).includes('poster.docx'), { timeout: 120_000 }).toBe(true)

    // Module 4 with the bundled face and segmentation models: a UK passport photo at exactly 413 × 531 px
    // and 300 DPI, and a 4 × 6 in print sheet PDF at exact scale.
    const passOut = tempDir('pkg-passport-out')
    await page.getByTestId('nav-passport').click()
    await stubDialogs(app, [join(ROOT, 'worker', 'tests', 'fixtures', 'faces', 'portrait-souza.jpg')], passOut)
    await page.getByTestId('passport-open').click()
    await expect(page.getByTestId('passport-next')).toBeEnabled({ timeout: 120_000 })
    await page.getByTestId('passport-next').click()
    await expect(page.getByTestId('hint-face')).toHaveAttribute('data-level', 'ok', { timeout: 120_000 })
    await expect(page.getByTestId('hint-head')).toHaveAttribute('data-level', 'ok')
    await expect(page.getByTestId('hint-background')).toContainText('Background replaced')
    await expect(page.getByTestId('passport-size-stage')).toHaveAttribute('data-fresh', '1', { timeout: 120_000 })
    await page.screenshot({ path: 'test-results/screens/packaged-passport.png' })
    await page.getByTestId('passport-next').click()
    const passJpg = join(passOut, 'photo.jpg')
    await app.evaluate(({ dialog }, path) => {
      dialog.showSaveDialog = (async () => ({ canceled: false, filePath: path })) as typeof dialog.showSaveDialog
    }, passJpg)
    await page.getByTestId('passport-save-photo').click()
    await expect.poll(() => readdirSync(passOut).includes('photo.jpg'), { timeout: 120_000 }).toBe(true)
    await expect(page.getByTestId('passport-save-photo')).toBeEnabled({ timeout: 60_000 })
    const prb = readback(passJpg)
    expect([prb.width, prb.height]).toEqual([413, 531])
    expect(prb.jfifDensity).toEqual([300, 300])
    await page.getByTestId('passport-tab-sheet').click()
    await expect(page.getByTestId('passport-sheet-preview')).toBeVisible({ timeout: 120_000 })
    const passPdf = join(passOut, 'sheet.pdf')
    await app.evaluate(({ dialog }, path) => {
      dialog.showSaveDialog = (async () => ({ canceled: false, filePath: path })) as typeof dialog.showSaveDialog
    }, passPdf)
    await page.getByTestId('passport-save-sheet').click()
    await expect.poll(() => readdirSync(passOut).includes('sheet.pdf'), { timeout: 120_000 }).toBe(true)
    await expect(page.getByTestId('passport-save-sheet')).toBeEnabled({ timeout: 60_000 })
    const pageMm = py<number[]>(`import sys, json, pymupdf
p = pymupdf.open(sys.argv[1])[0]
print(json.dumps([round(p.rect.width / 72 * 25.4, 3), round(p.rect.height / 72 * 25.4, 3)]))`, passPdf)
    expect(pageMm).toEqual([101.6, 152.4])
  } finally {
    await app.close()
  }
})
