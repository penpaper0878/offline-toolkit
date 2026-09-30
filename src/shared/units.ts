/**
 * Physical size <-> pixel conversion. Mirrors worker/otk_worker/common/units.py;
 * both are tested against tests/vectors/units.json.
 *
 * px = inches x DPI, 1 in = 2.54 cm = 25.4 mm, half-up rounding once at the end.
 */

export type Unit = 'px' | 'cm' | 'mm' | 'in'
export type PhysicalUnit = Exclude<Unit, 'px'>
export const UNITS: Unit[] = ['px', 'cm', 'mm', 'in']
export const PER_INCH: Record<PhysicalUnit, number> = { in: 1, cm: 2.54, mm: 25.4 }
export const DPI_MIN = 72
export const DPI_MAX = 1200
const EPS = 1e-9

export class UnitError extends Error {}

function checkUnit(unit: string): asserts unit is Unit {
  if (!UNITS.includes(unit as Unit)) throw new UnitError(`Unknown unit "${unit}"`)
}

function checkDpi(dpi: number): void {
  if (!Number.isFinite(dpi) || dpi <= 0) throw new UnitError(`DPI must be a positive number`)
}

/** Half-up rounding (Math.round is half-up for positives too, but this matches Python exactly). */
export function roundPx(value: number): number {
  return Math.floor(value + 0.5 + EPS)
}

export function lengthToPx(value: number, unit: Unit, dpi: number): number {
  checkUnit(unit)
  if (unit === 'px') return value
  checkDpi(dpi)
  return (value / PER_INCH[unit]) * dpi
}

export function pxToLength(px: number, unit: Unit, dpi: number): number {
  checkUnit(unit)
  if (unit === 'px') return px
  checkDpi(dpi)
  return (px / dpi) * PER_INCH[unit]
}

export interface Axis {
  requested: number
  unit: Unit
  exactPx: number
  px: number
  dpi: number
  errorPx: number
  actual: number
  error: number
  actualMm: number
  errorMm: number
}

export interface SizeResult {
  width: Axis
  height: Axis
}

function axis(value: number, unit: Unit, dpi: number, fitDpi: boolean): Axis {
  if (!Number.isFinite(value) || value <= 0) throw new UnitError('Size must be a positive number')
  checkDpi(dpi)
  const exact = lengthToPx(value, unit, dpi)
  const px = roundPx(unit === 'px' ? value : exact)
  if (unit === 'px' && Math.abs(px - value) > EPS) throw new UnitError('Pixel sizes must be whole numbers')
  if (px < 1) throw new UnitError(`${value} ${unit} at ${dpi} DPI is less than one pixel`)
  let axisDpi = dpi
  if (fitDpi && unit !== 'px') axisDpi = px / (value / PER_INCH[unit])
  const actual = unit === 'px' ? px : pxToLength(px, unit, axisDpi)
  const actualMm = (px / axisDpi) * 25.4
  const requestedMm = unit === 'px' ? actualMm : (value / PER_INCH[unit]) * 25.4
  return {
    requested: value, unit, exactPx: exact, px, dpi: axisDpi, errorPx: px - exact,
    actual, error: actual - value, actualMm, errorMm: actualMm - requestedMm
  }
}

export function resolveSize(width: number, height: number, unit: Unit, dpi: number, fitDpi = false): SizeResult {
  checkUnit(unit)
  return { width: axis(width, unit, dpi, fitDpi), height: axis(height, unit, dpi, fitDpi) }
}

export function jfifDensity(dpi: number): number {
  return roundPx(dpi)
}

export function pngPhys(dpi: number): number {
  return Math.floor(dpi / 0.0254 + 0.5)
}

export function pngPhysDpi(ppm: number): number {
  return ppm * 0.0254
}

export type SizeUnit = 'B' | 'KB' | 'MB'

export function bytesFrom(value: number, unit: SizeUnit, base: 1000 | 1024 = 1024): number {
  const f = unit === 'B' ? 1 : unit === 'KB' ? base : base * base
  if (!Number.isFinite(value) || value < 0) throw new UnitError('File size must be a non-negative number')
  return Math.floor(value * f + EPS)
}

// ------------------------------------------------------------------ UI field logic
/** Size fields as the user edits them. */
export interface SizeFields {
  width: number
  height: number
  unit: Unit
  dpi: number
  sizeMode: 'exactPixels' | 'exactPhysical'
  lockAspect: boolean
}

/** Round a derived physical value for display in an input (4 decimals is below 0.01 px at 1200 DPI). */
export function tidy(value: number, unit: Unit): number {
  if (unit === 'px') return roundPx(value)
  return Math.round(value * 10000) / 10000
}

/** Width changed: with the aspect locked, height follows. `aspect` = width / height. */
export function setWidth(f: SizeFields, width: number, aspect: number | null): SizeFields {
  const next = { ...f, width }
  if (f.lockAspect && aspect && Number.isFinite(width) && width > 0) next.height = Math.max(unitMin(f.unit), tidy(width / aspect, f.unit))
  return next
}

export function setHeight(f: SizeFields, height: number, aspect: number | null): SizeFields {
  const next = { ...f, height }
  if (f.lockAspect && aspect && Number.isFinite(height) && height > 0) next.width = Math.max(unitMin(f.unit), tidy(height * aspect, f.unit))
  return next
}

function unitMin(unit: Unit): number {
  return unit === 'px' ? 1 : 0.0001
}

/** Unit changed: convert the numbers so the pixel size stays the same. */
export function setUnit(f: SizeFields, unit: Unit): SizeFields {
  if (unit === f.unit) return f
  // Go through the exact (unrounded) pixel count so 3 cm -> 30 mm stays exact.
  const wPx = lengthToPx(f.width, f.unit, f.dpi)
  const hPx = lengthToPx(f.height, f.unit, f.dpi)
  if (unit === 'px') return { ...f, unit, width: Math.max(1, roundPx(wPx)), height: Math.max(1, roundPx(hPx)) }
  return { ...f, unit, width: tidy(pxToLength(wPx, unit, f.dpi), unit), height: tidy(pxToLength(hPx, unit, f.dpi), unit) }
}

/**
 * DPI changed. exactPixels: the pixel size stays, so physical fields are recomputed.
 * exactPhysical: the physical fields stay, so the pixel size changes.
 */
export function setDpi(f: SizeFields, dpi: number): SizeFields {
  if (!Number.isFinite(dpi) || dpi <= 0 || f.unit === 'px' || f.sizeMode === 'exactPhysical') return { ...f, dpi }
  const wPx = roundPx(lengthToPx(f.width, f.unit, f.dpi))
  const hPx = roundPx(lengthToPx(f.height, f.unit, f.dpi))
  return { ...f, dpi, width: tidy(pxToLength(wPx, f.unit, dpi), f.unit), height: tidy(pxToLength(hPx, f.unit, dpi), f.unit) }
}

// ------------------------------------------------------------------ formatting
const nf = (digits: number) => new Intl.NumberFormat('en-US', { maximumFractionDigits: digits })

export function fmtNum(v: number, digits = 3): string {
  return nf(digits).format(v)
}

export function fmtSigned(v: number, digits = 3): string {
  const s = fmtNum(Math.abs(v), digits)
  if (Math.abs(v) < Math.pow(10, -digits) / 2) return '±0'
  return (v < 0 ? '−' : '+') + s
}

export function fmtBytes(n: number, base: 1000 | 1024 = 1024): string {
  if (n < base) return `${n} B`
  if (n < base * base) return `${fmtNum(n / base, 1)} KB`
  return `${fmtNum(n / (base * base), 2)} MB`
}

/** "3 cm @ 200 DPI = 236.22 px → 236 px (−0.22 px, −0.028 mm)" */
export function describeAxis(a: Axis): string {
  if (a.unit === 'px') {
    return `${a.px} px = ${fmtNum(a.actualMm / 10, 3)} cm = ${fmtNum(a.actualMm / 25.4, 3)} in at ${fmtNum(a.dpi, 3)} DPI`
  }
  const rounded = Math.abs(a.errorPx) > EPS
  const base = `${fmtNum(a.requested, 4)} ${a.unit} @ ${fmtNum(a.dpi, 3)} DPI = ${fmtNum(a.exactPx, 2)} px`
  if (!rounded) return `${base} exactly`
  return `${base} → ${a.px} px (${fmtSigned(a.errorPx, 2)} px, ${fmtSigned(a.errorMm, 3)} mm)`
}
