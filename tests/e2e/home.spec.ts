/**
 * End-to-end: the shared home screen. Status of the offline engines, the module cards and shortcuts,
 * "Open a file…" (pictures ask which module, documents go to the converter), the recent list across
 * modules (reopen, remove, clear, turned off), and starting where you left off.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launch, makePhoto, ROOT, stubDialogs, tempDir } from './helpers'

const PORTRAIT = join(ROOT, 'worker', 'tests', 'fixtures', 'faces', 'portrait-souza.jpg')

test('home screen: modules, open a file, the picture chooser and recent work', async () => {
  const data = tempDir('data-home')
  const inputs = tempDir('home-in')
  const a = join(inputs, 'holiday.jpg')
  const b = join(inputs, 'garden.jpg')
  makePhoto(a, 900, 600)
  makePhoto(b, 800, 800)
  const notes = join(inputs, 'notes.txt')
  writeFileSync(notes, 'Meeting notes\nनमस्ते — مرحبا\n', 'utf-8')

  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    // The app opens on the home screen, with the state of what is bundled.
    await expect(page.getByTestId('home-page')).toBeVisible()
    await expect(page.getByTestId('status-offline')).toHaveClass(/good/, { timeout: 30_000 })
    await expect(page.getByTestId('status-fonts')).toContainText('73 families')
    await expect(page.getByTestId('status-models')).toContainText('4 of 4')
    await expect(page.getByTestId('status-engines')).toContainText(/Conversion engines: \d of \d/)
    await expect(page.getByTestId('home-recent')).toContainText('appear here')
    await page.screenshot({ path: 'test-results/screens/50-home.png' })

    // Cards and shortcuts.
    await page.getByTestId('home-go-design').click()
    await expect(page.getByTestId('design-home')).toBeVisible()
    await page.keyboard.press('Control+Shift+H')
    await expect(page.getByTestId('home-page')).toBeVisible()
    await page.keyboard.press('Control+2')
    await expect(page.getByTestId('nav-converter')).toHaveAttribute('aria-current', 'page')
    await page.getByTestId('brand').click()
    await expect(page.getByTestId('home-page')).toBeVisible()

    // Open one picture: the chooser asks; make a passport photo.
    await stubDialogs(app, [PORTRAIT], inputs)
    await page.getByTestId('home-open').click()
    await expect(page.getByTestId('home-chooser')).toBeVisible()
    await expect(page.getByTestId('home-chooser')).toContainText('portrait-souza.jpg')
    await page.screenshot({ path: 'test-results/screens/51-home-chooser.png' })
    await page.getByTestId('choose-passport').click()
    await expect(page.getByTestId('passport-crop-stage')).toBeVisible({ timeout: 60_000 })

    // Two pictures through Ctrl+O on the home screen: resize them both.
    await page.keyboard.press('Control+Shift+H')
    await stubDialogs(app, [a, b], inputs)
    await page.keyboard.press('Control+o')
    await expect(page.getByTestId('home-chooser')).toContainText('these 2 pictures')
    await page.getByTestId('choose-resizer').click()
    await expect(page.getByTestId('thumbs').locator('.thumb')).toHaveCount(2, { timeout: 30_000 })

    // A document goes straight to the converter.
    await page.getByTestId('brand').click()
    await stubDialogs(app, [notes], inputs)
    await page.getByTestId('home-open').click()
    await expect(page.getByTestId('nav-converter')).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('[data-testid="conv-row"]')).toHaveCount(1, { timeout: 60_000 })

    // Recent work, newest first, across the modules; reopen the passport photo from it.
    await page.getByTestId('brand').click()
    const items = page.getByTestId('recent-item')
    await expect(items).toHaveCount(3)
    await expect(items.nth(0)).toHaveAttribute('data-module', 'converter')
    await expect(items.nth(0)).toContainText('notes.txt')
    await expect(items.nth(1)).toHaveAttribute('data-module', 'resizer')
    await expect(items.nth(1)).toContainText('2 images')
    await expect(items.nth(2)).toHaveAttribute('data-module', 'passport')
    await page.screenshot({ path: 'test-results/screens/52-home-recent.png' })
    const stored = JSON.parse(readFileSync(join(data, 'recent.json'), 'utf-8')) as { items: { module: string; paths: string[] }[] }
    expect(stored.items.map((r) => r.module)).toEqual(['converter', 'resizer', 'passport'])
    expect(stored.items[1].paths.sort()).toEqual([a, b].sort())
    await items.nth(2).locator('.recent-open').click()
    await expect(page.getByTestId('passport-photo-info').or(page.getByTestId('passport-crop-stage'))).toBeVisible({ timeout: 60_000 })

    // Reopening moved the photo back to the top. Remove one entry, then clear the list.
    await page.getByTestId('brand').click()
    await expect(items.nth(0)).toHaveAttribute('data-module', 'passport')
    await page.getByRole('button', { name: /Remove notes\.txt/ }).click()
    await expect(items).toHaveCount(2)
    await page.getByTestId('home-recent-clear').click()
    await expect(items).toHaveCount(0)
    expect(JSON.parse(readFileSync(join(data, 'recent.json'), 'utf-8')).items).toEqual([])

    // Turned off: nothing is kept.
    await page.getByTestId('nav-settings').click()
    await page.getByTestId('remember-recent').click({ force: true })
    await expect(page.getByTestId('remember-recent')).not.toBeChecked()
    await page.getByTestId('nav-resizer').click()
    await stubDialogs(app, [a], inputs)
    await page.getByTestId('brand').click()
    await page.getByTestId('home-open').click()
    await page.getByTestId('choose-resizer').click()
    await page.getByTestId('brand').click()
    await expect(page.getByTestId('home-recent')).toContainText('not kept')
    expect(JSON.parse(readFileSync(join(data, 'recent.json'), 'utf-8')).items).toEqual([])

    // Start where I left off.
    await page.getByTestId('nav-settings').click()
    await page.getByTestId('start-page').locator('[data-value="last"]').click()
    await page.getByTestId('nav-converter').click()
    await expect.poll(() => (JSON.parse(readFileSync(join(data, 'settings.json'), 'utf-8')) as { home: { lastPage: string } }).home.lastPage,
      { timeout: 10_000 }).toBe('converter')
    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
  const again = await launch(data)
  try {
    await expect(again.page.getByTestId('nav-converter')).toHaveAttribute('aria-current', 'page')
  } finally {
    await again.app.close()
  }
  expect(existsSync(join(data, 'recent.json'))).toBe(true)
})

test('Try a sample: each module opens its bundled sample, copied into the data folder', async () => {
  const data = tempDir('data-samples')
  const { app, page } = await launch(data)
  try {
    await expect(page.getByTestId('home-page')).toBeVisible()

    // The resizer's photo is stored sideways with an EXIF rotation: its thumbnail is upright (portrait).
    await page.getByTestId('home-sample-resizer').click()
    const thumb = page.getByTestId('thumbs').locator('.thumb.ready')
    await expect(thumb).toHaveCount(1, { timeout: 60_000 })
    const [w, h] = await thumb.locator('img').first().evaluate((img: HTMLImageElement) => [img.naturalWidth, img.naturalHeight])
    expect(h).toBeGreaterThan(w)

    await page.getByTestId('brand').click()
    await page.getByTestId('home-sample-converter').click()
    await expect(page.locator('[data-testid="conv-row"][data-status="ready"]')).toHaveCount(1, { timeout: 120_000 })

    await page.getByTestId('brand').click()
    await page.getByTestId('home-sample-passport').click()
    await expect(page.getByTestId('passport-crop-stage')).toBeVisible({ timeout: 120_000 })

    await page.getByTestId('brand').click()
    await page.getByTestId('home-sample-design').click()
    await expect(page.getByTestId('design-editor')).toBeVisible({ timeout: 300_000 })

    for (const f of ['resizer/camera-photo-rotated.jpg', 'converter/report.docx', 'passport/portrait.jpg', 'design/poster.png']) {
      expect(existsSync(join(data, 'samples', f)), f).toBe(true)
    }
    await page.getByTestId('brand').click()
    await expect(page.getByTestId('recent-item')).toHaveCount(4)
  } finally {
    await app.close()
  }
})
