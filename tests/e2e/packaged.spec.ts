/**
 * Smoke test for the packaged Windows app (run by .github/workflows/release.yml).
 * Launches the built .exe exactly as a user would, with no development Python:
 * it must find and use its own bundled Python, stay offline, and resize a photo.
 *
 *   OTK_PACKAGED_EXE  path to "Offline Toolkit.exe" (test is skipped without it)
 *   OTK_TEST_PYTHON   the bundled python.exe, used by the test's own helpers
 *   OTK_PACKAGED_ARGS optional extra arguments (dry runs against a dev build, e.g. ". --no-sandbox")
 */

import { copyFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { _electron as electron, expect, test } from '@playwright/test'
import { makePhoto, readback, ROOT, stubDialogs, tempDir } from './helpers'

const exe = process.env.OTK_PACKAGED_EXE

test.skip(!exe, 'Set OTK_PACKAGED_EXE to the packaged app to run this test')

test('packaged app: bundled Python, offline self-test, HEIC, resize to 240×240 @200 DPI', async () => {
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
  } finally {
    await app.close()
  }
})
