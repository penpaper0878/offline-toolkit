import { describe, expect, it } from 'vitest'
import {
  bounds, cellText, type DesignScene, faceKey, facesUsed, newId, reorder, shapeOutline, snapBox, type ShapeLayer, type TableLayer,
  tableGrid, type TextLayer, textGeometry, textHeight
} from './design'

const metrics = { ascent: 0.9, descent: 0.25, lineGap: 0.05 }

function text(over: Partial<TextLayer> = {}): TextLayer {
  return {
    id: 'text1', type: 'text', name: 'T', box: [100, 50, 300, 80], rotation: 0, visible: true, locked: false, opacity: 1,
    text: 'One\nTwo', style: { family: 'Lato', weight: 400, italic: false, size: 20, color: '#000000', align: 'left', lineHeight: 1.5, underline: false },
    ...over
  }
}

function scene(layers: DesignScene['layers']): DesignScene {
  return { format: 'otk-design', version: 1, source: { name: 'x.png', width: 800, height: 600, dpi: 96 }, page: { width: 800, height: 600, background: '#fff' },
    layers, notes: [], limits: [], lowConfidence: [] }
}

describe('design scene geometry (mirrors worker/otk_worker/design/layout.py)', () => {
  it('places baselines one ascent below the top, then a line pitch apart', () => {
    const g = textGeometry(text(), metrics)
    expect(g.baselines).toEqual([50 + 0.9 * 20, 50 + 0.9 * 20 + 30])
    expect(g.anchor).toBe(100)
    expect(textGeometry(text({ style: { ...text().style, align: 'center' } }), metrics).anchor).toBe(250)
    expect(textGeometry(text({ style: { ...text().style, align: 'right' } }), metrics).anchor).toBe(400)
    expect(textHeight(text(), metrics)).toBeCloseTo(0.9 * 20 + 30 + 0.25 * 20)
  })

  it('marks Arabic and Hebrew text right-to-left', () => {
    expect(textGeometry(text({ script: 'arabic' }), metrics).rtl).toBe(true)
    expect(textGeometry(text({ script: 'devanagari' }), metrics).rtl).toBe(false)
  })

  it('scales table columns and rows to the box and centres cell text', () => {
    const t: TableLayer = {
      id: 'table1', type: 'table', name: 'T', box: [0, 0, 200, 100], rotation: 0, visible: true, locked: false, opacity: 1,
      colWidths: [50, 50], rowHeights: [25, 25], border: { color: '#000', width: 2 }, padding: [6, 2, 6, 2],
      style: { family: 'Lato', size: 10, color: '#000' },
      cells: [{ row: 0, col: 0, rowSpan: 1, colSpan: 1, text: 'A', fill: null, weight: 400, italic: false, align: 'right', valign: 'middle' }]
    }
    expect(tableGrid(t)).toEqual({ xs: [0, 100, 200], ys: [0, 50, 100] })
    const g = cellText(t, t.cells[0], [0, 0, 100, 50], metrics)
    expect(g.anchor).toBe(100 - 1 - 6)
    expect(g.baselines[0]).toBeCloseTo(25 - (0.9 + 0.25) * 10 / 2 + 0.9 * 10)
  })

  it('insets outlines by half the stroke', () => {
    const s: ShapeLayer = { id: 's', type: 'shape', name: 'S', box: [10, 10, 100, 50], rotation: 0, visible: true, locked: false, opacity: 1,
      shape: 'rounded', fill: null, stroke: '#000', strokeWidth: 4, radius: 10 }
    expect(shapeOutline(s)).toEqual([12, 12, 96, 46, 8])
  })

  it('keeps the background at the bottom when reordering', () => {
    const bg = { id: 'background', type: 'image' as const, name: 'B', box: [0, 0, 800, 600] as [number, number, number, number], rotation: 0, visible: true, locked: true, opacity: 1, asset: 'a.png', role: 'background' as const }
    const sc = scene([bg, text({ id: 'a' }), text({ id: 'b' })])
    expect(reorder(sc, ['b'], 'bottom').layers.map((l) => l.id)).toEqual(['background', 'b', 'a'])
    expect(reorder(sc, ['a'], 1).layers.map((l) => l.id)).toEqual(['background', 'b', 'a'])
    expect(reorder(sc, ['a'], -1).layers.map((l) => l.id)).toEqual(['background', 'a', 'b'])
    expect(reorder(sc, ['background'], 'top').layers[0].id).toBe('background')
  })

  it('lists each face once and makes fresh ids', () => {
    const sc = scene([text({ id: 'text1' }), text({ id: 'text2', style: { ...text().style, weight: 700 } }), text({ id: 'text3' })])
    expect(facesUsed(sc).map((f) => faceKey(f.family, f.weight, f.italic))).toEqual(['Lato|400|n', 'Lato|700|n'])
    expect(newId(sc, 'text')).toBe('text4')
  })

  it('snaps to page centre and other edges within tolerance', () => {
    const r = snapBox([395, 10, 10, 10], [[0, 300, 100, 50]], [800, 600], 6)
    expect(r.box[0]).toBe(395)   // its centre is 400 already
    const r2 = snapBox([96, 352, 20, 20], [[0, 300, 100, 50]], [800, 600], 6)
    expect(r2.box).toEqual([100, 350, 20, 20])
  })

  it('bounds of a rotated box', () => {
    const b = bounds([0, 0, 100, 0], 90)
    expect(b[2]).toBeCloseTo(0)
    expect(b[3]).toBeCloseTo(100)
  })
})
