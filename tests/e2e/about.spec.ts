/**
 * End-to-end: Settings → About & licences reads the list scripts/collect_licenses.py made (`npm run licenses`, run by
 * CI after the build): the copyleft summary first, filtering and searching, and a component's licence text.
 */

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launch, ROOT, tempDir } from './helpers'

const LIST = join(ROOT, 'build', 'licenses', 'third-party.json')

test('About & licences: every bundled component, copyleft first, with its licence text', async () => {
  test.skip(!existsSync(LIST), 'run `npm run licenses` first')
  const report = JSON.parse(readFileSync(LIST, 'utf-8')) as { summary: { total: number }; components: { name: string; copyleft: string }[] }
  const { app, page } = await launch(tempDir('data-about'))
  try {
    await page.getByTestId('nav-settings').click()
    const about = page.getByTestId('about-licences')
    await about.scrollIntoViewIfNeeded()
    await expect(page.getByTestId('licence-total')).toHaveText(String(report.summary.total))

    // PyMuPDF (AGPL) is named first, with what it would mean to give the app away.
    const flags = page.getByTestId('licence-flag')
    await expect(flags.filter({ hasText: 'pymupdf' })).toHaveAttribute('data-level', 'network')
    await expect(page.getByTestId('licence-flagged')).toContainText('give the app to someone else')
    await expect(page.getByTestId('licence-summary').locator('[data-level="network"]')).toContainText('1 AGPL')
    await page.screenshot({ path: 'test-results/screens/60-about-licences.png' })

    // Filters and search.
    const rows = page.getByTestId('licence-row')
    await expect(rows).toHaveCount(report.summary.total)
    await page.getByTestId('licence-filter').selectOption('copyleft')
    await expect(rows).toHaveCount(report.components.filter((c) => c.copyleft !== 'none').length)
    await expect(rows.locator('[data-copyleft="none"]')).toHaveCount(0)
    await page.getByTestId('licence-filter').selectOption('font')
    await expect(rows).toHaveCount(73)
    await page.getByTestId('licence-search').fill('noto sans devanagari')
    await expect(rows).toHaveCount(1)

    // The font's own licence text.
    await rows.first().locator('.licence-name').click()
    const text = page.getByTestId('licence-text')
    await expect(text).toContainText('SIL OPEN FONT LICENSE')
    await page.screenshot({ path: 'test-results/screens/61-licence-text.png' })
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('licence-text-modal')).toHaveCount(0)

    // An engine's licence (Pandoc, GPL) from the flagged list.
    await page.getByTestId('licence-flag').filter({ hasText: 'Pandoc' }).locator('button').click()
    await expect(text).toContainText('GNU GENERAL PUBLIC LICENSE')
    await page.keyboard.press('Escape')
    await expect(page.getByTestId('open-notices')).toBeVisible()
  } finally {
    await app.close()
  }
})
