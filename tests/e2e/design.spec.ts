/**
 * End-to-end: Module 3 in the real Electron app with the real Python worker.
 * Analyses a synthetic poster (known ground truth), edits text and style in the editor, uses undo/redo,
 * adds a text layer, compares against the original, runs the accuracy check (Chromium draws the scene),
 * exports every format and reopens the saved design and the .otkd project file.
 */

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test, type ElectronApplication } from '@playwright/test'
import { launch, py, ROOT, stubDialogs, tempDir } from './helpers'

function makePoster(dir: string): string {
  return py<string>(`import sys, json
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'worker', 'tests'))})
import design_samples
from pathlib import Path
p, _ = design_samples.build(Path(sys.argv[1]), ['poster'])['poster']
print(json.dumps(str(p)))`, dir)
}

async function stubSave(app: ElectronApplication, path: string): Promise<void> {
  await app.evaluate(({ dialog }, path) => {
    dialog.showSaveDialog = (async () => ({ canceled: false, filePath: path })) as typeof dialog.showSaveDialog
  }, path)
}

interface Scene { layers: { id: string; type: string; text?: string; style?: { size: number; family: string } }[] }

function savedScene(data: string): Scene {
  const root = join(data, 'designs')
  const id = readdirSync(root)[0]
  return JSON.parse(readFileSync(join(root, id, 'scene.json'), 'utf-8')) as Scene
}

test('analyse a poster, edit it, check it against the original and export every format', async () => {
  const data = tempDir('data')
  const inputs = tempDir('design-in')
  const out = tempDir('design-out')
  const poster = makePoster(inputs)

  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    await stubDialogs(app, [poster], out)
    await page.getByTestId('nav-design').click()
    await expect(page.getByTestId('design-home')).toBeVisible()
    await page.getByTestId('design-open-image').click()
    await expect(page.getByTestId('design-analyzing')).toBeVisible()
    await expect(page.getByTestId('design-editor')).toBeVisible({ timeout: 170_000 })
    await page.screenshot({ path: 'test-results/screens/20-design-editor.png' })

    // Layers: background, photo, shapes, table, line, graphics and seven text layers.
    const rows = page.locator('[data-testid^="layer-row-"]')
    expect(await rows.count()).toBeGreaterThanOrEqual(14)
    let scene = savedScene(data)
    const title = scene.layers.find((l) => l.type === 'text' && l.text === 'Summer Music Festival')!
    expect(title.style!.family).toBe('Montserrat')

    // Edit the title's text and size in the inspector; it is saved automatically.
    await page.getByTestId(`layer-row-${title.id}`).click()
    await expect(page.getByTestId('design-inspector')).toBeVisible()
    await page.getByTestId('design-text-content').fill('Summer Music Festival 2026')
    await page.getByTestId('design-size').fill('60')
    await expect(page.getByTestId('design-save-state')).toHaveText('Saved', { timeout: 15_000 })
    scene = savedScene(data)
    let t = scene.layers.find((l) => l.id === title.id)!
    expect(t.text).toBe('Summer Music Festival 2026')
    expect(t.style!.size).toBe(60)

    // Undo both edits (the canvas has focus, so the shortcut applies to the design).
    await page.getByTestId('design-canvas').click({ position: { x: 5, y: 5 } })
    await page.keyboard.press('Control+z')
    await page.keyboard.press('Control+z')
    await expect(page.getByTestId('design-save-state')).toHaveText('Saved', { timeout: 15_000 })
    t = savedScene(data).layers.find((l) => l.id === title.id)!
    expect(t.text).toBe('Summer Music Festival')
    await page.keyboard.press('Control+Shift+z')
    await expect(page.getByTestId('design-save-state')).toHaveText('Saved', { timeout: 15_000 })
    expect(savedScene(data).layers.find((l) => l.id === title.id)!.text).toBe('Summer Music Festival 2026')

    // Add a text layer and type into it in place.
    const before = savedScene(data).layers.length
    await page.getByTestId('design-add-text').click()
    const editor = page.getByTestId('design-text-editor')
    await expect(editor).toBeVisible()
    await editor.fill('Hello from the editor')
    await editor.press('Control+Enter')
    await expect(page.getByTestId('design-save-state')).toHaveText('Saved', { timeout: 15_000 })
    scene = savedScene(data)
    expect(scene.layers.length).toBe(before + 1)
    expect(scene.layers[scene.layers.length - 1].text).toBe('Hello from the editor')

    // Compare with the original: slider and difference views.
    await page.getByTestId('design-compare').locator('[data-value="split"]').click()
    await page.screenshot({ path: 'test-results/screens/21-design-compare.png' })
    await page.getByTestId('design-compare').locator('[data-value="diff"]').click()
    await page.screenshot({ path: 'test-results/screens/22-design-difference.png' })
    await page.getByTestId('design-compare').locator('[data-value="off"]').click()

    // The accuracy check (Chromium draws the layers, compared with the picture).
    await page.getByTestId('design-tab-check').click()
    // Only English was chosen: the Hindi line is listed as not read and left in the picture untouched.
    await expect(page.getByTestId('design-unreadable')).toHaveCount(1)
    expect(savedScene(data).layers.some((l) => l.type === 'text' && /#/.test(l.text ?? ''))).toBe(false)
    await expect(page.getByTestId('design-score')).toBeVisible({ timeout: 120_000 })
    // The check that ran after the analysis is out of date after the edits; run it again.
    await expect(page.getByTestId('design-score-stale')).toBeVisible()
    await page.getByRole('button', { name: 'Check again' }).click()
    await expect(page.getByTestId('design-score')).toHaveAttribute('data-stale', '0', { timeout: 120_000 })
    await expect(page.getByTestId('design-score')).toContainText('differ')
    const score = await page.getByTestId('design-score').textContent()
    expect(Number(/([\d.]+)%/.exec(score ?? '')?.[1])).toBeGreaterThan(90)
    await page.screenshot({ path: 'test-results/screens/23-design-check.png' })

    // Export every format.
    for (const fmt of ['pptx', 'docx', 'svg', 'html', 'otkd']) {
      const target = join(out, `poster.${fmt}`)
      await stubSave(app, target)
      await page.getByTestId('design-export').click()
      await page.getByTestId('design-export-format').locator(`[data-value="${fmt}"]`).click()
      await page.getByTestId('design-export-go').click()
      await expect(page.getByTestId('design-export-dialog')).toBeHidden({ timeout: 120_000 })
      await expect.poll(() => existsSync(target), { timeout: 60_000 }).toBe(true)
      expect(statSync(target).size, fmt).toBeGreaterThan(10_000)
    }
    const svg = readFileSync(join(out, 'poster.svg'), 'utf-8')
    expect(svg).toContain('Summer Music Festival 2026')
    expect(svg).toContain('Hello from the editor')
    expect(svg).toContain("@font-face{font-family:'Montserrat'")

    // Back to the list; reopen the design; open the .otkd as a second design.
    await page.getByRole('button', { name: 'Close design' }).click()
    await expect(page.getByTestId('design-card')).toHaveCount(1)
    await page.getByTestId('design-card').locator('.design-thumb').click()
    await expect(page.getByTestId('design-editor')).toBeVisible()
    await page.getByRole('button', { name: 'Close design' }).click()
    await stubDialogs(app, [join(out, 'poster.otkd')], out)
    await page.getByRole('button', { name: /Open a design file/ }).click()
    await expect(page.getByTestId('design-editor')).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: 'Close design' }).click()
    await expect(page.getByTestId('design-card')).toHaveCount(2)
    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
})
