/**
 * The design scene (Module 3): what the analysis produces, the editor changes and the exporters write.
 *
 * Geometry is in page pixels. `box` is [x, y, w, h] of a layer's unrotated frame; `rotation` turns it
 * clockwise (degrees) about the box centre. Layers are listed bottom to top. A text layer's first baseline
 * lies the font's ascent (at the layer's size) below the box top, each next line `lineHeight * size` lower
 * (the same rule as worker/otk_worker/design/layout.py, which the exporters use).
 */

export type Box = [number, number, number, number]

export interface FontMetrics {
  ascent: number
  descent: number
  lineGap: number
  capHeight?: number
  xHeight?: number
}

export interface LayerBase {
  id: string
  type: 'image' | 'shape' | 'vector' | 'text' | 'table'
  name: string
  box: Box
  rotation: number
  visible: boolean
  locked: boolean
  opacity: number
}

export interface ImageLayer extends LayerBase {
  type: 'image'
  asset: string
  role?: 'background'
  kind?: 'photo'
  /** The picture before a cut-out, to restore it. */
  originalAsset?: string
  source?: { box?: number[] }
}

export interface ShapeLayer extends LayerBase {
  type: 'shape'
  shape: 'rect' | 'rounded' | 'ellipse' | 'line'
  fill: string | null
  stroke: string | null
  strokeWidth: number
  radius?: number
  /** Lines: [x0, y0, x1, y1] relative to the box. */
  points?: [number, number, number, number]
}

export interface VectorPath {
  d: string
  fill: string
}

export interface VectorLayer extends LayerBase {
  type: 'vector'
  paths: VectorPath[]
  natural?: [number, number]
  colors?: string[]
  source?: { pixels?: string }
}

export interface TextStyle {
  family: string
  weight: number
  italic: boolean
  size: number
  color: string
  align: 'left' | 'center' | 'right' | 'justify'
  lineHeight: number
  underline: boolean
}

export interface Word {
  text: string
  box: number[]
  conf: number
}

export interface FontCandidate {
  family: string
  weight: number
  italic: boolean
  score: number
  size: number
}

export interface TextLayer extends LayerBase {
  type: 'text'
  text: string
  style: TextStyle
  baseline?: number
  lines?: { text: string; width: number }[]
  words?: Word[]
  lowConfidence?: number[]
  script?: string
  confidence?: number
  fontCandidates?: FontCandidate[]
  engine?: string
  /** The box when the words were read (their positions are relative to it). */
  analysisBox?: Box
}

export interface TableCell {
  row: number
  col: number
  rowSpan: number
  colSpan: number
  text: string
  fill: string | null
  weight: number
  italic: boolean
  align: 'left' | 'center' | 'right'
  valign: 'top' | 'middle' | 'bottom'
  color?: string
}

export interface TableLayer extends LayerBase {
  type: 'table'
  colWidths: number[]
  rowHeights: number[]
  border: { color: string; width: number }
  padding?: [number, number, number, number]
  style: { family: string; size: number; color: string }
  cells: TableCell[]
  fontCandidates?: FontCandidate[]
}

export type Layer = ImageLayer | ShapeLayer | VectorLayer | TextLayer | TableLayer

export interface Limit {
  id: string
  text: string
}

export interface DesignScene {
  format: 'otk-design'
  version: number
  source: {
    name: string
    sha256?: string
    width: number
    height: number
    dpi: number
    dpiAssumed?: boolean
    rotation?: number
    denoised?: boolean
    upscale?: number
    upscaleMethod?: string | null
    languages?: string[]
    app?: string
  }
  page: { width: number; height: number; background: string }
  assets?: { original: string; prepared: string; background: string }
  layers: Layer[]
  notes: string[]
  limits: Limit[]
  lowConfidence: { layer: string; text: string; conf: number }[]
  /** Lines the OCR could not read; left in the picture untouched. */
  unreadable?: { box: Box; text: string; conf: number }[]
  stats?: Record<string, unknown>
}

export interface FontFamilyInfo {
  family: string
  category: string | null
  role: string | null
  scripts: string[]
  licence: string | null
  styles: { weight: number; italic: boolean }[]
  metrics: FontMetrics
}

export const RTL_SCRIPTS = new Set(['arabic', 'hebrew'])

export const WEIGHT_NAMES: Record<number, string> = {
  100: 'Thin', 200: 'ExtraLight', 300: 'Light', 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold', 900: 'Black'
}

export const snapWeight = (w: number): number => Math.max(100, Math.min(900, Math.round(w / 100) * 100))

export function faceKey(family: string, weight: number, italic: boolean): string {
  return `${family}|${snapWeight(weight)}|${italic ? 'i' : 'n'}`
}

/** Canvas/CSS font shorthand. */
export function cssFont(family: string, weight: number, italic: boolean, size: number): string {
  return `${italic ? 'italic ' : ''}${snapWeight(weight)} ${Math.max(0.5, size)}px "${family.replace(/"/g, '')}"`
}

export interface TextGeometry {
  lines: string[]
  baselines: number[]
  pitch: number
  anchor: number
  align: TextStyle['align']
  rtl: boolean
}

/** Lines of a text layer with their baselines and anchor x (page px). */
export function textGeometry(layer: TextLayer, m: FontMetrics): TextGeometry {
  const [x, y, w] = layer.box
  const { size, lineHeight, align } = layer.style
  const pitch = lineHeight * size
  const first = y + m.ascent * size
  const lines = layer.text.split('\n')
  const anchor = align === 'center' ? x + w / 2 : align === 'right' ? x + w : x
  return { lines, baselines: lines.map((_, i) => first + i * pitch), pitch, anchor, align, rtl: RTL_SCRIPTS.has(layer.script ?? '') }
}

/** Height a text layer needs for its lines. */
export function textHeight(layer: TextLayer, m: FontMetrics): number {
  const n = Math.max(1, layer.text.split('\n').length)
  const { size, lineHeight } = layer.style
  return m.ascent * size + (n - 1) * lineHeight * size + m.descent * size
}

export function tableGrid(layer: TableLayer): { xs: number[]; ys: number[] } {
  const [x, y, w, h] = layer.box
  const sw = layer.colWidths.reduce((a, b) => a + b, 0) || 1
  const sh = layer.rowHeights.reduce((a, b) => a + b, 0) || 1
  const xs = [x]
  const ys = [y]
  for (const v of layer.colWidths) xs.push(xs[xs.length - 1] + (v * w) / sw)
  for (const v of layer.rowHeights) ys.push(ys[ys.length - 1] + (v * h) / sh)
  return { xs, ys }
}

export function tableCells(layer: TableLayer): { cell: TableCell; box: [number, number, number, number] }[] {
  const { xs, ys } = tableGrid(layer)
  return layer.cells.map((cell) => {
    const r1 = Math.min(ys.length - 1, cell.row + (cell.rowSpan || 1))
    const c1 = Math.min(xs.length - 1, cell.col + (cell.colSpan || 1))
    return { cell, box: [xs[cell.col], ys[cell.row], xs[c1], ys[r1]] }
  })
}

/** Lines of one table cell, centred vertically, with the anchor x for its alignment (as the exporters). */
export function cellText(layer: TableLayer, cell: TableCell, box: [number, number, number, number], m: FontMetrics): TextGeometry {
  const pad = layer.padding ?? [6, 2, 6, 2]
  const half = layer.border.width / 2
  const size = layer.style.size
  const pitch = (m.ascent + m.descent + m.lineGap) * size
  const lines = cell.text ? cell.text.split('\n') : []
  const [x0, y0, x1, y1] = box
  const block = lines.length ? (lines.length - 1) * pitch + (m.ascent + m.descent) * size : 0
  const top = cell.valign === 'top' ? y0 + half + pad[1] : cell.valign === 'bottom' ? y1 - half - pad[3] - block : (y0 + y1) / 2 - block / 2
  const first = top + m.ascent * size
  const anchor = cell.align === 'center' ? (x0 + x1) / 2 : cell.align === 'right' ? x1 - half - pad[2] : x0 + half + pad[0]
  return { lines, baselines: lines.map((_, i) => first + i * pitch), pitch, anchor, align: cell.align, rtl: false }
}

/** The rules of a table as segments, every cell outline, shared edges once. */
export function cellEdges(layer: TableLayer): [number, number, number, number][] {
  const seen = new Set<string>()
  const out: [number, number, number, number][] = []
  for (const { box: [x0, y0, x1, y1] } of tableCells(layer)) {
    for (const s of [[x0, y0, x1, y0], [x0, y1, x1, y1], [x0, y0, x0, y1], [x1, y0, x1, y1]] as [number, number, number, number][]) {
      const k = s.map((v) => v.toFixed(1)).join(',')
      if (!seen.has(k)) {
        seen.add(k)
        out.push(s)
      }
    }
  }
  return out
}

/** (x, y, w, h, radius) of the path a stroke is centred on: the box inset by half the stroke. */
export function shapeOutline(layer: ShapeLayer): [number, number, number, number, number] {
  const [x, y, w, h] = layer.box
  const sw = layer.stroke ? layer.strokeWidth || 0 : 0
  const i = sw / 2
  return [x + i, y + i, Math.max(0.5, w - sw), Math.max(0.5, h - sw), Math.max(0, (layer.radius ?? 0) - i)]
}

export function vectorScale(layer: VectorLayer): [number, number] {
  const [nw, nh] = layer.natural ?? [layer.box[2], layer.box[3]]
  return [layer.box[2] / Math.max(1e-6, nw), layer.box[3] / Math.max(1e-6, nh)]
}

export function facesUsed(scene: DesignScene): { family: string; weight: number; italic: boolean }[] {
  const seen = new Map<string, { family: string; weight: number; italic: boolean }>()
  const add = (family: string, weight: number, italic: boolean) => {
    const k = faceKey(family, weight, italic)
    if (!seen.has(k)) seen.set(k, { family, weight: snapWeight(weight), italic })
  }
  for (const l of scene.layers) {
    if (l.type === 'text') add(l.style.family, l.style.weight, l.style.italic)
    else if (l.type === 'table') for (const c of l.cells) add(l.style.family, c.weight, c.italic)
  }
  return [...seen.values()]
}

/** A fresh layer id with the given prefix ("text7"). */
export function newId(scene: DesignScene, prefix: string): string {
  const used = new Set(scene.layers.map((l) => l.id))
  for (let i = 1; ; i++) if (!used.has(`${prefix}${i}`)) return `${prefix}${i}`
}

/** Move layers within the stack: +1 up one, -1 down one, 'top' or 'bottom'. The background stays at the bottom. */
export function reorder(scene: DesignScene, ids: string[], to: 1 | -1 | 'top' | 'bottom'): DesignScene {
  const pick = new Set(ids)
  const layers = [...scene.layers]
  const pinned = layers.length && (layers[0] as ImageLayer).role === 'background' ? 1 : 0
  if (to === 'top' || to === 'bottom') {
    const moving = layers.filter((l) => pick.has(l.id) && !(l as ImageLayer).role)
    const rest = layers.filter((l) => !moving.includes(l))
    const out = to === 'top' ? [...rest, ...moving] : [...rest.slice(0, pinned), ...moving, ...rest.slice(pinned)]
    return { ...scene, layers: out }
  }
  const order = to === 1 ? [...layers.keys()].reverse() : [...layers.keys()]
  for (const i of order) {
    const j = i + to
    if (!pick.has(layers[i].id) || (layers[i] as ImageLayer).role === 'background') continue
    if (j < pinned || j >= layers.length || pick.has(layers[j].id)) continue
    ;[layers[i], layers[j]] = [layers[j], layers[i]]
  }
  return { ...scene, layers }
}

/** Replace one layer (by id) with a changed copy. */
export function updateLayer<T extends Layer>(scene: DesignScene, id: string, patch: Partial<T> | ((l: T) => T)): DesignScene {
  return {
    ...scene,
    layers: scene.layers.map((l) => (l.id !== id ? l : typeof patch === 'function' ? patch(l as T) : ({ ...l, ...patch } as Layer)))
  }
}

/** Rotated box corners (page px). */
export function corners(box: Box, rotation: number): [number, number][] {
  const [x, y, w, h] = box
  const cx = x + w / 2
  const cy = y + h / 2
  const a = (rotation * Math.PI) / 180
  const c = Math.cos(a)
  const s = Math.sin(a)
  return ([[x, y], [x + w, y], [x + w, y + h], [x, y + h]] as [number, number][]).map(([px, py]) => {
    const dx = px - cx
    const dy = py - cy
    return [cx + dx * c - dy * s, cy + dx * s + dy * c]
  })
}

/** Axis-aligned bounds of a rotated box. */
export function bounds(box: Box, rotation: number): Box {
  if (!rotation) return box
  const pts = corners(box, rotation)
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)]
}

/** Snap a moving box to page edges/centre and other boxes' edges/centres within `tol` px. */
export function snapBox(box: Box, others: Box[], page: [number, number], tol: number): { box: Box; guides: { x: number[]; y: number[] } } {
  const [x, y, w, h] = box
  const xsTargets = [0, page[0] / 2, page[0]]
  const ysTargets = [0, page[1] / 2, page[1]]
  for (const [ox, oy, ow, oh] of others) {
    xsTargets.push(ox, ox + ow / 2, ox + ow)
    ysTargets.push(oy, oy + oh / 2, oy + oh)
  }
  const best = (vals: number[], targets: number[]): { d: number; t: number } | null => {
    let out: { d: number; t: number } | null = null
    for (const v of vals) for (const t of targets) {
      const d = t - v
      if (Math.abs(d) <= tol && (!out || Math.abs(d) < Math.abs(out.d))) out = { d, t }
    }
    return out
  }
  const bx = best([x, x + w / 2, x + w], xsTargets)
  const by = best([y, y + h / 2, y + h], ysTargets)
  return {
    box: [x + (bx?.d ?? 0), y + (by?.d ?? 0), w, h],
    guides: { x: bx ? [bx.t] : [], y: by ? [by.t] : [] }
  }
}
