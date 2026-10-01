/**
 * End-to-end: Module 2 in the real Electron app with the real Python worker and engines.
 * Converts Word, HTML, TXT and a password-protected PDF to PDF (HTML and TXT are printed by
 * the app's own Chromium window, through the worker -> app request channel), then to PDF/A-2b,
 * and reads the verification reports.
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launch, py, ROOT, stubDialogs, tempDir } from './helpers'

function makeSamples(dir: string): Record<string, string> {
  return py(`import sys, json
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'worker', 'tests'))})
import corpus
from pathlib import Path
s = corpus.build(Path(sys.argv[1]), legacy=False, pdfa=False)
print(json.dumps({k: str(v) for k, v in s.items()}))`, dir)
}

interface Report { verdict: string; checks: { id: string; status: string; summary: string }[] }

test('convert Word, HTML and TXT to PDF, then Word and a locked PDF to PDF/A-2b, with verification reports', async () => {
  const data = tempDir('data')
  const inputs = tempDir('docs')
  const out = tempDir('out')
  const s = makeSamples(inputs)

  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    await stubDialogs(app, [s.docx, s.html, s.txt], out)
    await page.getByTestId('nav-converter').click()
    await page.getByTestId('target-pdf').click()
    await page.getByTestId('add-docs').click()
    await expect(page.getByTestId('conv-row')).toHaveCount(3)
    await expect(page.locator('[data-testid="conv-row"][data-status="ready"]')).toHaveCount(3, { timeout: 60_000 })

    // The output folder chooser.
    await page.getByRole('button', { name: 'Change…' }).click()
    await expect(page.getByTestId('conv-outdir')).toHaveText(out)
    await page.screenshot({ path: 'test-results/screens/10-converter-ready.png' })

    await page.getByTestId('convert').click()
    await expect(page.getByTestId('verdict')).toHaveCount(3, { timeout: 170_000 })
    await page.screenshot({ path: 'test-results/screens/11-converter-done.png' })

    const pdfs = readdirSync(out).filter((n) => n.endsWith('.pdf')).sort()
    expect(pdfs).toEqual(['notes.pdf', 'page.pdf', 'report.pdf'])
    for (const name of pdfs) {
      expect(existsSync(join(out, `${name}.report.html`)), `${name} report`).toBe(true)
      const r = JSON.parse(readFileSync(join(out, `${name}.report.json`), 'utf-8')) as Report
      const text = r.checks.find((c) => c.id === 'text')!
      expect(['pass', 'expected'], `${name}: ${text.summary}`).toContain(text.status)
    }
    // The HTML page referenced a remote image: not loaded, and the report says so.
    const html = JSON.parse(readFileSync(join(out, 'page.pdf.report.json'), 'utf-8')) as Report & { notes: string[] }
    expect(html.notes.join(' ')).toContain('remote resource')

    // PDF/A-2b of the Word file and of a password-protected PDF, proven by veraPDF.
    await page.getByRole('button', { name: 'Clear' }).click()
    await stubDialogs(app, [s.docx, s.pdf_encrypted], out)
    await page.getByTestId('target-pdfa2b').click()
    await page.getByTestId('add-docs').click()
    const dialog = page.getByTestId('password-dialog')
    await expect(dialog).toBeVisible({ timeout: 60_000 })
    await page.getByTestId('password-input').fill('secret-123')
    await page.getByTestId('password-ok').click()
    await expect(dialog).toBeHidden()
    await expect(page.locator('[data-testid="conv-row"][data-status="ready"]')).toHaveCount(2, { timeout: 60_000 })
    await page.getByTestId('convert').click()
    await expect(page.getByTestId('verdict')).toHaveCount(2, { timeout: 170_000 })
    const second = readdirSync(out).find((n) => n.startsWith('report (1)') && n.endsWith('.pdf'))!
    expect(second, 'a second report.pdf gets a new name instead of overwriting').toBeTruthy()
    for (const name of [second, 'locked.pdf']) {
      const r = JSON.parse(readFileSync(join(out, `${name}.report.json`), 'utf-8')) as Report
      expect(r.checks.find((c) => c.id === 'pdfa')?.status, name).toBe('pass')
    }
    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
})
