/**
 * Module 4 (passport photos): types shared by the main process and the editor, and the crop/placement maps.
 *
 * The maps are the same as worker/otk_worker/passport/geometry.py (see its docstring); both are checked
 * against tests/vectors/passport.json. Coordinates are continuous (a pixel's centre is at i + 0.5).
 */

export type LengthUnit = 'mm' | 'cm' | 'in'

export interface Range { min?: number; max?: number }

export interface PassportSpec {
  id: string
  name: string
  description?: string
  width: number
  height: number
  unit: LengthUnit
  dpi: number
  head: { min: number; max: number; crown: 'hair' | 'skull' }
  eyeLine?: Range
  topMargin?: Range
  bottomMargin?: Range
  headWidth?: Range
  backgrounds: { name: string; color: string }[]
  digital?: { width: number; height: number }
  notes?: string
  source: { status: 'official' | 'official-excerpt' | 'unverified' | 'user'; authority?: string; url?: string; checked?: string; quote?: string }
}

export interface PaperSize { id: string; name: string; width: number; height: number; unit: LengthUnit }

export interface Crop { cx: number; cy: number; w: number; h: number; angle: number; flipH: boolean; flipV: boolean }
export interface Place { x: number; y: number; scale: number; angle: number }
export interface Background { mode: 'keep' | 'replace'; color: string; feather: number }
export interface Stroke { mode: 'restore' | 'erase'; radius: number; hardness: number; points: [number, number][] }
export interface Overrides { crown?: [number, number]; chin?: [number, number] }

export interface Adjust {
  exposure: number; brightness: number; contrast: number; highlights: number; shadows: number; warmth: number; tint: number
  saturation: number; vibrance: number; denoise: number; sharpness: number; redEye: boolean; skinSmoothing: number
}

export const NO_ADJUST: Adjust = {
  exposure: 0, brightness: 0, contrast: 0, highlights: 0, shadows: 0, warmth: 0, tint: 0, saturation: 0, vibrance: 0,
  denoise: 0, sharpness: 0, redEye: false, skinSmoothing: 0
}

export interface Hint { id: string; level: 'ok' | 'warn' | 'bad'; label: string; detail: string }

export interface PhotoInfo {
  id: string
  path: string
  width: number
  height: number
  meta: { format?: string; dpi?: number[] | null; orientation?: number; fileSize?: number }
  warnings: string[]
  preview: { url: string; width: number; height: number; scale: number }
}

export interface FaceInfo {
  eyes: [number, number][]
  chin: [number, number]
  crown: [number, number]
  crownFrom: string
  hair: [number, number] | null
  hairCut: boolean
  skull: [number, number]
  centre: [number, number]
  tilt: number
  width: number
  openness: number[]
  outline: [number, number][]
}

export interface AnalyzeResult {
  faces: number
  face: FaceInfo | null
  cropSize: [number, number]
  analysisScale: number
  image: { url: string; width: number; height: number }
  person: boolean
  matte?: { url: string; width: number; height: number }
}

export interface RenderResult {
  image: { url: string; width: number; height: number }
  before?: { url: string; width: number; height: number }
  hints: Hint[]
  measures: Record<string, unknown> & { place: Place; size: { px: [number, number]; errorMm: [number, number]; dpi: number } }
}

/** The editable state of one photo (what undo/redo steps through). */
export interface PassportDoc {
  crop: Crop | null
  ratio: string                       // 'free' | '1:1' | 'spec' | 'w:h'
  specId: string
  customSpec: PassportSpec | null
  place: Place | null
  background: Background
  strokes: Stroke[]
  adjust: Adjust
  overrides: Overrides
  upscale: boolean
}

export interface SheetPhoto {
  kind: 'current' | 'file'
  path?: string
  name: string
  widthMm?: number
  heightMm?: number
  copies: number | null
}

// ---------------------------------------------------------------- maps
export type Affine = [number, number, number, number, number, number]   // [a b c; d e f]: x' = a x + b y + c

const rad = (d: number): number => (d * Math.PI) / 180

export function rot(deg: number): [number, number, number, number] {
  const c = Math.cos(rad(deg)), s = Math.sin(rad(deg))
  return [c, -s, s, c]
}

export function apply(m: Affine, x: number, y: number): [number, number] {
  return [m[0] * x + m[1] * y + m[2], m[3] * x + m[4] * y + m[5]]
}

export function compose(a: Affine, b: Affine): Affine {
  return [
    a[0] * b[0] + a[1] * b[3], a[0] * b[1] + a[1] * b[4], a[0] * b[2] + a[1] * b[5] + a[2],
    a[3] * b[0] + a[4] * b[3], a[3] * b[1] + a[4] * b[4], a[3] * b[2] + a[4] * b[5] + a[5]
  ]
}

export function invert(m: Affine): Affine {
  const det = m[0] * m[4] - m[1] * m[3]
  const a = m[4] / det, b = -m[1] / det, d = -m[3] / det, e = m[0] / det
  return [a, b, -(a * m[2] + b * m[5]), d, e, -(d * m[2] + e * m[5])]
}

/** Cropped picture -> source. */
export function cropMap(c: Crop): Affine {
  const [r0, r1, r2, r3] = rot(-c.angle)
  const fx = c.flipH ? -1 : 1, fy = c.flipV ? -1 : 1
  const l: [number, number, number, number] = [r0 * fx, r1 * fy, r2 * fx, r3 * fy]
  return [l[0], l[1], c.cx - (l[0] * c.w / 2 + l[1] * c.h / 2), l[2], l[3], c.cy - (l[2] * c.w / 2 + l[3] * c.h / 2)]
}

/** Output (W x H px) -> cropped picture. */
export function placeMap(p: Place, cropW: number, cropH: number, W: number, H: number): Affine {
  const k = p.scale * H
  const [r0, r1, r2, r3] = rot(-p.angle)
  const l = [r0 / k, r1 / k, r2 / k, r3 / k]
  const ox = p.x * W, oy = p.y * H
  return [l[0], l[1], cropW / 2 - (l[0] * ox + l[1] * oy), l[2], l[3], cropH / 2 - (l[2] * ox + l[3] * oy)]
}

export function cornersInside(c: Crop, width: number, height: number, tol = 1e-6): boolean {
  const m = cropMap(c)
  return ([[0, 0], [c.w, 0], [c.w, c.h], [0, c.h]] as const).every(([x, y]) => {
    const [sx, sy] = apply(m, x, y)
    return sx >= -tol && sx <= width + tol && sy >= -tol && sy <= height + tol
  })
}

/** The largest crop with the same ratio and angle, its centre moved in as little as needed, whose corners
 * are all inside the picture (automatic zoom when straightening). */
export function fitInside(c: Crop, width: number, height: number): Crop {
  const [r0, r1, r2, r3] = rot(-c.angle)
  let ex = Math.abs(r0) * c.w / 2 + Math.abs(r1) * c.h / 2
  let ey = Math.abs(r2) * c.w / 2 + Math.abs(r3) * c.h / 2
  const k = Math.min(1, ex ? width / 2 / ex : 1, ey ? height / 2 / ey : 1)
  ex *= k
  ey *= k
  return { ...c, w: c.w * k, h: c.h * k, cx: Math.min(Math.max(c.cx, ex), width - ex), cy: Math.min(Math.max(c.cy, ey), height - ey) }
}

export const PER_INCH: Record<LengthUnit, number> = { mm: 25.4, cm: 2.54, in: 1 }

export function roundPx(v: number): number {
  return Math.floor(v + 0.5 + 1e-9)
}

/** Output pixels of a spec, and the size actually printed at its DPI (mm). */
export function specPx(s: Pick<PassportSpec, 'width' | 'height' | 'unit' | 'dpi'>): { w: number; h: number; mm: [number, number]; errorMm: [number, number] } {
  const ppu = s.dpi / PER_INCH[s.unit]
  const w = Math.max(1, roundPx(s.width * ppu)), h = Math.max(1, roundPx(s.height * ppu))
  const mmPer = 25.4 / s.dpi
  const wm = (s.width * 25.4) / PER_INCH[s.unit], hm = (s.height * 25.4) / PER_INCH[s.unit]
  return { w, h, mm: [wm, hm], errorMm: [w * mmPer - wm, h * mmPer - hm] }
}

export function toMm(v: number, unit: LengthUnit): number {
  return (v * 25.4) / PER_INCH[unit]
}

export function fullCrop(width: number, height: number): Crop {
  return { cx: width / 2, cy: height / 2, w: width, h: height, angle: 0, flipH: false, flipV: false }
}

/** A crop of the given ratio (w/h) centred where `c` is, as large as fits at its angle. */
export function cropWithRatio(c: Crop, ratio: number, width: number, height: number): Crop {
  const area = c.w * c.h
  let w = Math.sqrt(area * ratio), h = w / ratio
  const big = Math.max(width, height) * 2
  if (w > big) { w = big; h = w / ratio }
  return fitInside({ ...c, w, h }, width, height)
}
