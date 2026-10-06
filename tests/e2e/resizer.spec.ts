/**
 * End-to-end: the real Electron app with the real Python worker.
 * Covers the spec's acceptance points for Module 1: exact pixel size, DPI in
 * the file, 20–50 KB targeting, crop window, undo/redo, presets, batch + ZIP,
 * and the offline self-test.
 */

import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launch, makePhoto, readback, stubDialogs, tempDir } from './helpers'

test('resize a photo to 240×240 px @200 DPI within 20–50 KB, then batch to disk', async () => {
  const data = tempDir('data')
  const inputs = tempDir('in')
  const out = tempDir('out')
  const a = join(inputs, 'फोटो passport.jpg')
  const b = join(inputs, 'second.jpg')
  makePhoto(a, 1200, 900)
  makePhoto(b, 800, 1000)

  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    await stubDialogs(app, [a, b], out)
    await expect(page.getByTestId('home-page')).toBeVisible()          // the app opens on the home screen
    await page.getByTestId('nav-resizer').click()
    await page.getByTestId('add-images').click()
    await expect(page.getByTestId('thumbs').locator('.thumb')).toHaveCount(2)

    // Default settings are the "Photo 240×240 px @200 DPI" preset.
    await expect(page.getByTestId('target-px')).toHaveText('240 × 240 px')
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'ok', { timeout: 60_000 })
    await expect(page.getByTestId('out-px')).toHaveText('240 × 240 px')
    await expect(page.getByTestId('out-dpi')).toContainText('200 (JFIF)')
    const bytes = Number(await page.getByTestId('out-bytes').getAttribute('data-bytes'))
    expect(bytes).toBeGreaterThanOrEqual(20 * 1024)
    expect(bytes).toBeLessThanOrEqual(50 * 1024)
    await page.screenshot({ path: 'test-results/screens/01-crop-window.png' })

    // Live unit conversion: 240 px at 200 DPI = 3.048 cm.
    await page.getByTestId('unit').locator('[data-value="cm"]').click()
    await expect(page.getByTestId('width')).toHaveValue('3.048')
    await expect(page.getByTestId('conversion')).toContainText('3.048 cm @ 200 DPI = 240 px exactly')
    await page.getByTestId('unit').locator('[data-value="px"]').click()
    await expect(page.getByTestId('width')).toHaveValue('240')

    // Undo/redo of a size change.
    await page.getByTestId('width').fill('300')
    await expect(page.getByTestId('target-px')).toHaveText('300 × 300 px')
    await page.getByTestId('tab-compare').click()
    await page.keyboard.press('Control+z')
    await expect(page.getByTestId('target-px')).toHaveText('240 × 240 px')
    await page.keyboard.press('Control+y')
    await expect(page.getByTestId('target-px')).toHaveText('300 × 300 px')
    await page.keyboard.press('Control+z')
    await expect(page.getByTestId('target-px')).toHaveText('240 × 240 px')

    // Crop window: keyboard nudge moves it by exactly 10 source px.
    await page.getByTestId('tab-crop').click()
    const before = await page.getByTestId('crop-info').innerText()
    await page.getByTestId('crop-stage').focus()
    await page.keyboard.press('Shift+ArrowLeft')
    await expect(page.getByTestId('crop-info')).not.toHaveText(before)
    expect(await page.getByTestId('crop-info').innerText()).toContain('(140, 0)')

    // Before/after view.
    await page.getByTestId('tab-compare').click()
    await expect(page.getByTestId('compare-canvas')).toBeVisible()
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'ok', { timeout: 60_000 })
    await page.screenshot({ path: 'test-results/screens/02-before-after.png' })

    // Impossible target: said so, with suggestions, dimensions untouched.
    await page.getByTestId('size-min').fill('')
    await page.getByTestId('size-max').fill('0.3')
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'above_max', { timeout: 60_000 })
    await expect(page.getByTestId('suggestions')).toBeVisible()
    await expect(page.getByTestId('target-px')).toHaveText('240 × 240 px')
    await page.screenshot({ path: 'test-results/screens/03-impossible-target.png' })
    await page.getByTestId('size-min').fill('20')
    await page.getByTestId('size-max').fill('50')
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', 'ok', { timeout: 60_000 })

    // Batch with ZIP.
    await page.getByText('Also create a ZIP of all results').click()
    await expect(page.getByTestId('zip')).toBeChecked()
    await page.getByTestId('process').click()
    await expect(page.getByTestId('batch-counts')).toContainText('2 ok', { timeout: 120_000 })
    await page.screenshot({ path: 'test-results/screens/04-batch-results.png' })
    await page.getByTestId('batch-close').click()

    const files = readdirSync(out).sort()
    expect(files).toContain('फोटो passport_240x240.jpg')
    expect(files).toContain('second_240x240.jpg')
    expect(files.some((f) => f.endsWith('.zip'))).toBe(true)
    for (const f of files.filter((x) => x.endsWith('.jpg'))) {
      const rb = readback(join(out, f))
      expect([rb.width, rb.height]).toEqual([240, 240])
      expect(rb.jfifDensity).toEqual([200, 200])
      expect(rb.exifDpi).toEqual([200, 200])
      expect(rb.bytes).toBeGreaterThanOrEqual(20 * 1024)
      expect(rb.bytes).toBeLessThanOrEqual(50 * 1024)
    }

    // Signature preset: 140×60 px, fit with padding, 10–20 KB (padding allowed).
    await page.getByTestId('preset-select').selectOption('signature-140x60')
    await expect(page.getByTestId('target-px')).toHaveText('140 × 60 px')
    await expect(page.getByTestId('status-chip')).toHaveAttribute('data-status', /^(ok|ok_padded)$/, { timeout: 60_000 })
    await expect(page.getByTestId('out-px')).toHaveText('140 × 60 px')
    const sigBytes = Number(await page.getByTestId('out-bytes').getAttribute('data-bytes'))
    expect(sigBytes).toBeGreaterThanOrEqual(10 * 1024)
    expect(sigBytes).toBeLessThanOrEqual(20 * 1024)
    await page.screenshot({ path: 'test-results/screens/05-signature-padded.png' })

    // Presets: save the current settings as a new preset; it lands in the JSON file.
    await page.getByTestId('preset-save-as').click()
    await page.getByTestId('preset-name').fill('My exam photo')
    await page.getByTestId('preset-name-ok').click()
    await expect(page.getByTestId('preset-select')).toContainText('My exam photo')
    expect(existsSync(join(data, 'presets', 'resizer.json'))).toBe(true)

    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
})

test('offline self-test passes and settings persist', async () => {
  const data = tempDir('data2')
  const { app, page } = await launch(data)
  try {
    await page.getByTestId('nav-settings').click()
    await page.getByTestId('theme').locator('[data-value="dark"]').click()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
    await page.getByTestId('run-selftest').click()
    await expect(page.getByTestId('selftest-result')).toContainText('Passed', { timeout: 60_000 })
    await page.screenshot({ path: 'test-results/screens/06-settings-selftest-dark.png' })
  } finally {
    await app.close()
  }
  // Theme was saved to settings.json and survives a restart.
  const again = await launch(data)
  try {
    await expect(again.page.locator('html')).toHaveAttribute('data-theme', 'dark')
  } finally {
    await again.app.close()
  }
})
