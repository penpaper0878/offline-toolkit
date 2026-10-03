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

interface FullLayer { id: string; type: string; name: string; box: number[]; text?: string; visible: boolean; locked: boolean
  asset?: string; paths?: { fill: string }[]; cells?: { row: number; col: number; text: string }[]; shape?: string; fill?: string | null }

test('edit on the canvas: drag, type in place, recolour, table cells, cut-out, layer controls', async () => {
  const data = tempDir('data')
  const inputs = tempDir('design-in')
  const poster = makePoster(inputs)
  const { app, page } = await launch(data)
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  const layers = () => (savedScene(data) as unknown as { layers: FullLayer[] }).layers
  // Wait for an edit to reach the saved scene on disk. (Waiting for the "Saved" label alone can pass before
  // the label has changed for the new edit, and then read the scene from before it.)
  const onDisk = <T,>(read: (ls: FullLayer[]) => T) => expect.poll(() => read(layers()), { timeout: 15_000 })
  try {
    await stubDialogs(app, [poster], inputs)
    await page.getByTestId('nav-design').click()
    await page.getByTestId('design-open-image').click()
    await expect(page.getByTestId('design-editor')).toBeVisible({ timeout: 170_000 })
    const canvas = page.getByTestId('design-canvas')
    // A small laptop screen (the Windows CI desktop is 1024 x 768): the module bar folds to icons, the canvas
    // keeps a usable width and the page is fitted again.
    const zoomBefore = Number(await canvas.getAttribute('data-zoom'))
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1008, 655))
    await expect.poll(async () => (await canvas.boundingBox())!.width).toBeGreaterThan(440)
    await expect.poll(async () => Number(await canvas.getAttribute('data-zoom'))).toBeLessThan(zoomBefore)
    // Page px -> screen px from the canvas's view state.
    const toScreen = async (x: number, y: number) => {
      const box = (await canvas.boundingBox())!
      const z = Number(await canvas.getAttribute('data-zoom'))
      const px = Number(await canvas.getAttribute('data-pan-x'))
      const py2 = Number(await canvas.getAttribute('data-pan-y'))
      return { x: box.x + px + x * z, y: box.y + py2 + y * z, z }
    }

    // Drag the title 60 px right and 40 px down (Alt: no snapping).
    const title = layers().find((l) => l.text === 'Summer Music Festival')!
    const c = await toScreen(title.box[0] + title.box[2] / 2, title.box[1] + title.box[3] / 2)
    // What is under the point, the window and whether animation frames run (Konva draws its hit areas in
    // them): reported if the click does not select the title.
    const where = await page.evaluate(`(async () => {
      const e = document.elementFromPoint(${c.x}, ${c.y})
      const r = document.querySelector('[data-testid="design-canvas"]').getBoundingClientRect()
      const frame = await Promise.race([new Promise((ok) => requestAnimationFrame(() => ok(true))),
        new Promise((ok) => setTimeout(() => ok(false), 1000))])
      return JSON.stringify({ x: ${c.x}, y: ${c.y}, at: e ? e.tagName + '.' + e.className : null,
        window: [innerWidth, innerHeight, devicePixelRatio], canvas: [r.x, r.y, r.width, r.height],
        visibility: document.visibilityState, frame })
    })()`)
    await page.mouse.click(c.x, c.y)
    await expect(page.getByTestId(`layer-row-${title.id}`), `title ${title.box} not selected: ${where}`)
      .toHaveAttribute('aria-selected', 'true', { timeout: 5_000 })
    await page.keyboard.down('Alt')
    await page.mouse.move(c.x, c.y)
    await page.mouse.down()
    await page.mouse.move(c.x + 30 * c.z, c.y + 20 * c.z, { steps: 5 })
    await page.mouse.move(c.x + 60 * c.z, c.y + 40 * c.z, { steps: 5 })
    await page.mouse.up()
    await page.keyboard.up('Alt')
    await onDisk((ls) => ls.find((l) => l.id === title.id)!.box[0] - title.box[0]).toBeCloseTo(60, -1)
    await onDisk((ls) => ls.find((l) => l.id === title.id)!.box[1] - title.box[1]).toBeCloseTo(40, -1)

    // Double-click the button label and retype it in place.
    const label = layers().find((l) => l.text === 'Book tickets')!
    const b = await toScreen(label.box[0] + label.box[2] / 2, label.box[1] + label.box[3] / 2)
    await page.mouse.dblclick(b.x, b.y)
    const editor = page.getByTestId('design-text-editor')
    await expect(editor).toBeVisible()
    await editor.fill('Buy tickets')
    await editor.press('Control+Enter')
    await onDisk((ls) => ls.find((l) => l.id === label.id)!.text).toBe('Buy tickets')

    // Recolour the star graphic.
    const star = layers().find((l) => l.type === 'vector' && l.paths?.some((p) => p.fill === '#f2a900'))!
    await page.getByTestId(`layer-row-${star.id}`).click()
    await page.getByRole('textbox', { name: 'Colour #f2a900 hex' }).fill('#ff0000')
    await onDisk((ls) => ls.find((l) => l.id === star.id)!.paths!.every((p) => p.fill !== '#f2a900')).toBe(true)

    // Edit a table cell.
    const table = layers().find((l) => l.type === 'table')!
    await page.getByTestId(`layer-row-${table.id}`).click()
    await page.getByTestId('design-table-editor').locator('textarea').first().fill('Date')
    await onDisk((ls) => ls.find((l) => l.id === table.id)!.cells!.find((x) => x.row === 0 && x.col === 0)!.text).toBe('Date')

    // Remove the background of the photo (kept: a new picture with transparency; the old one can be restored).
    const photo = layers().find((l) => l.type === 'image' && l.name.startsWith('Photo'))!
    await page.getByTestId(`layer-row-${photo.id}`).click()
    await page.getByTestId('design-cutout').click()
    await expect(page.getByText('Background removed')).toBeVisible({ timeout: 60_000 })
    await onDisk((ls) => ls.find((l) => l.id === photo.id)!.asset).toContain('-cutout-')
    await page.getByRole('button', { name: 'Restore original' }).click()
    await onDisk((ls) => ls.find((l) => l.id === photo.id)!.asset).toBe(photo.asset)

    // Hide and lock a layer; duplicate and delete; add a rectangle.
    await page.getByTestId(`layer-row-${star.id}`).getByRole('button', { name: 'Hide' }).click()
    await page.getByTestId(`layer-row-${star.id}`).getByRole('button', { name: 'Lock' }).click()
    await onDisk((ls) => { const s1 = ls.find((l) => l.id === star.id)!; return [s1.visible, s1.locked] }).toEqual([false, true])
    const n = layers().length
    await page.getByTestId(`layer-row-${title.id}`).click()
    await canvas.click({ position: { x: 3, y: 3 } })
    await page.getByTestId(`layer-row-${title.id}`).click()
    await page.getByRole('button', { name: 'Duplicate' }).click()
    await onDisk((ls) => ls.length).toBe(n + 1)
    await page.getByRole('button', { name: 'Delete' }).click()
    await onDisk((ls) => ls.length).toBe(n)
    await page.getByTestId('design-add-shape').click()
    await page.getByRole('button', { name: 'Rectangle', exact: true }).click()
    await onDisk((ls) => [ls[ls.length - 1].type, ls[ls.length - 1].shape]).toEqual(['shape', 'rect'])
    await page.screenshot({ path: 'test-results/screens/24-design-edited.png' })
    expect(errors).toEqual([])
  } finally {
    await app.close()
  }
})
