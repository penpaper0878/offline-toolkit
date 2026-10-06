/**
 * End-to-end: large files keep the app responsive. A 50-megapixel photo goes through the resizer, a PDF of more
 * than 100 MB through the converter and a 50-megapixel portrait through the passport wizard while the window's frames and main-process IPC round trips are timed. The work
 * runs in the Python worker, so the interface must keep drawing and answering throughout. The measurements are
 * written to test-results/large-files.json (docs/TEST_REPORT.md quotes them).
 */

import { mkdirSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, type Page, test } from '@playwright/test'
import { launch, py, ROOT, stubDialogs, tempDir } from './helpers'

interface Watch { frames: number; maxGap: number; p99Gap: number; over250: number; ipcCalls: number; ipcMax: number; ipcP95: number; seconds: number }

/** Time every animation frame and a main-process IPC call (the recent list) every 50 ms. */
async function startWatch(page: Page): Promise<void> {
  await page.evaluate(() => {
    const w = window as unknown as { __watch: { gaps: number[]; ipc: number[]; stop: boolean; t0: number }; otk: { recent: { list(): Promise<unknown> } } }
    const p = { gaps: [] as number[], ipc: [] as number[], stop: false, t0: performance.now() }
    w.__watch = p
    let last = performance.now()
    const tick = (t: number): void => {
      p.gaps.push(t - last)
      last = t
      if (!p.stop) requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
    void (async () => {
      while (!p.stop) {
        const t0 = performance.now()
        await w.otk.recent.list()
        p.ipc.push(performance.now() - t0)
        await new Promise((r) => setTimeout(r, 50))
      }
    })()
  })
}

async function stopWatch(page: Page): Promise<Watch> {
  return page.evaluate(() => {
    const p = (window as unknown as { __watch: { gaps: number[]; ipc: number[]; stop: boolean; t0: number } }).__watch
    p.stop = true
    const q = (a: number[], f: number): number => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(f * s.length))] ?? 0 }
    const r = (n: number): number => Math.round(n)
    return {
      frames: p.gaps.length, maxGap: r(Math.max(...p.gaps)), p99Gap: r(q(p.gaps, 0.99)), over250: p.gaps.filter((g) => g > 250).length,
      ipcCalls: p.ipc.length, ipcMax: r(Math.max(...p.ipc)), ipcP95: r(q(p.ipc, 0.95)), seconds: r((performance.now() - p.t0) / 1000)
    }
  })
}

function expectResponsive(w: Watch, what: string): void {
  expect(w.frames, `${what}: frames drawn`).toBeGreaterThan(w.seconds * 10)
  expect(w.maxGap, `${what}: longest pause between frames (ms)`).toBeLessThan(1000)
  expect(w.over250, `${what}: frames later than 250 ms`).toBeLessThanOrEqual(3)
  expect(w.ipcMax, `${what}: slowest main-process answer (ms)`).toBeLessThan(500)
  expect(w.ipcP95, `${what}: 95th percentile main-process answer (ms)`).toBeLessThan(100)
}

test.setTimeout(900_000)

test('large files: 50 MP photos and a 100+ MB PDF are processed while the window keeps drawing and answering', async () => {
  const inputs = tempDir('large-in')
  const out = tempDir('large-out')
  const photo = join(inputs, 'camera-50mp.jpg')
  const pdf = join(inputs, 'scans-105mb.pdf')
  const made = py<{ mp: number; pdfPages: number; pdfBytes: number; photoBytes: number }>(`import sys, io, os, json
import numpy as np, pymupdf
from PIL import Image
photo, pdf = sys.argv[1], sys.argv[2]
rng = np.random.default_rng(5)
w, h = 8660, 5780
img = np.empty((h, w, 3), np.uint8)
x = np.linspace(0, 1, w, dtype=np.float32)[None, :]
for y0 in range(0, h, 500):
    n = min(500, h - y0)
    y = np.linspace(y0 / h, (y0 + n) / h, n, dtype=np.float32)[:, None]
    blk = np.stack([x * 200 + 30 * np.sin(y * 20) + 0 * y, y * 180 + 40 * np.cos(x * 15), (x + y) * 100], axis=2)
    blk += rng.normal(0, 8, blk.shape).astype(np.float32)
    img[y0:y0 + n] = blk.clip(0, 255).astype(np.uint8)
Image.fromarray(img).save(photo, quality=92)
doc = pymupdf.open()
size = 0
while size < 105e6:
    arr = rng.integers(0, 256, (2200, 1700, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, 'JPEG', quality=90)
    page = doc.new_page(width=612, height=792)
    page.insert_image(page.rect, stream=buf.getvalue())
    page.insert_text((72, 72), f'Scanned page {doc.page_count}', fontsize=24)
    size += buf.tell()
doc.save(pdf)
print(json.dumps({'mp': w * h / 1e6, 'pdfPages': doc.page_count, 'pdfBytes': os.path.getsize(pdf), 'photoBytes': os.path.getsize(photo)}))`, photo, pdf)
  expect(made.mp).toBeGreaterThanOrEqual(50)
  expect(statSync(pdf).size).toBeGreaterThan(100e6)

  const { app, page } = await launch(tempDir('data-large'))
  const results: Record<string, unknown> = { files: made }
  try {
    // Resizer: open the 50 MP photo, let the live preview find the size, then process it.
    await page.getByTestId('nav-resizer').click()
    await stubDialogs(app, [photo], out)
    await startWatch(page)
    await page.getByTestId('add-images').click()
    await expect(page.getByTestId('thumbs').locator('.thumb.ready')).toHaveCount(1, { timeout: 180_000 })
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'ok', { timeout: 180_000 })
    // The window answers a click at once while the worker is busy.
    const t0 = Date.now()
    await page.getByTestId('nav-settings').click()
    await expect(page.getByTestId('diagnostics')).toBeVisible()
    results.navigateMs = Date.now() - t0
    await page.getByTestId('nav-resizer').click()
    await page.getByTestId('process').click()
    await expect(page.getByTestId('batch-counts')).toContainText('ok', { timeout: 300_000 })
    const resizer = await stopWatch(page)
    results.resizer = resizer
    await page.getByTestId('batch-close').click()

    // Converter: the 100+ MB PDF to page images; cancel after the first pages, which also has to answer at once.
    await page.getByTestId('nav-converter').click()
    await stubDialogs(app, [pdf], out)
    await page.getByTestId('target-png').click()
    await startWatch(page)
    await page.getByTestId('add-docs').click()
    await expect(page.locator('[data-testid="conv-row"][data-status="ready"]')).toHaveCount(1, { timeout: 300_000 })
    await page.getByTestId('convert').click()
    await page.waitForTimeout(20_000)
    const cancelAt = Date.now()
    await page.getByTestId('convert-cancel').click()
    await expect(page.getByTestId('convert')).toBeVisible({ timeout: 60_000 })
    results.cancelMs = Date.now() - cancelAt
    const converter = await stopWatch(page)
    results.converter = converter

    // Passport wizard: a 50 MP portrait (the public-domain portrait enlarged), cropped and sized to UK rules.
    const portrait = join(inputs, 'portrait-50mp.jpg')
    py(`import sys, json
from PIL import Image
Image.open(sys.argv[1]).convert('RGB').resize((6330, 7910), Image.Resampling.BICUBIC).save(sys.argv[2], quality=92)
print(json.dumps(True))`, join(ROOT, 'worker', 'tests', 'fixtures', 'faces', 'portrait-souza.jpg'), portrait)
    await page.getByTestId('nav-passport').click()
    await stubDialogs(app, [portrait], out)
    await startWatch(page)
    await page.getByTestId('passport-open').click()
    await expect(page.getByTestId('passport-next')).toBeEnabled({ timeout: 180_000 })
    await page.getByTestId('passport-next').click()
    await expect(page.getByTestId('passport-size-stage')).toHaveAttribute('data-fresh', '1', { timeout: 180_000 })
    await expect(page.getByTestId('hint-face')).toHaveAttribute('data-level', 'ok')
    const passport = await stopWatch(page)
    results.passport = passport

    mkdirSync('test-results', { recursive: true })
    writeFileSync(join('test-results', 'large-files.json'), JSON.stringify(results, null, 1))
    console.log('large files:', JSON.stringify(results))
    expectResponsive(resizer, 'resizer, 50 MP')
    expectResponsive(converter, 'converter, 100+ MB PDF')
    expectResponsive(passport, 'passport, 50 MP portrait')
    expect(results.navigateMs as number).toBeLessThan(2000)
    expect(results.cancelMs as number).toBeLessThan(30_000)
  } finally {
    await app.close()
  }
})
