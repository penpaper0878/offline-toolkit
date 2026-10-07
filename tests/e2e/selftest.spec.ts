/**
 * End-to-end: the quick offline self-test, then the full one in the same session. The network checks, then a small real job in
 * every module (including a PDF printed by the app's own Chromium), then proof that no network attempt was
 * made meanwhile. Run inside a network namespace by `npm run test:offline` too.
 */

import { expect, test } from '@playwright/test'
import { launch, tempDir } from './helpers'

test('check every module offline', async () => {
  const { app, page } = await launch(tempDir('data-selftest'))
  try {
    await page.getByTestId('home-check').click()
    // The quick offline self-test first, as a user might: its deliberate attempts are not the app's own, and the
    // full self-test must not count them as "other network attempts" (it did, in the first 1.0.0 build).
    await page.getByTestId('run-selftest').click()
    await expect(page.getByTestId('selftest-result')).toContainText('Passed', { timeout: 60_000 })
    await page.getByTestId('run-full-selftest').click()
    await expect(page.getByTestId('full-selftest-progress')).toBeVisible()
    await expect(page.getByTestId('full-selftest-result')).toBeVisible({ timeout: 170_000 })
    const checks = page.getByTestId('module-check')
    await expect(checks).toHaveCount(10)
    const failed = await page.locator('[data-testid="module-check"][data-passed="0"]').allTextContents()
    expect(failed).toEqual([])
    expect(await page.getByTestId('full-selftest-checks').locator('li.bad').allTextContents()).toEqual([])
    await expect(page.getByTestId('full-selftest-result')).toContainText('All passed')
    await expect(page.getByTestId('full-selftest-checks')).toContainText('No network attempts while the modules worked: None.')
    await page.getByTestId('full-selftest-checks').scrollIntoViewIfNeeded()
    await page.screenshot({ path: 'test-results/screens/53-full-selftest.png', fullPage: true })
  } finally {
    await app.close()
  }
})
