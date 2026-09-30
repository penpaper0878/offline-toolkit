import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  bytesFrom, describeAxis, jfifDensity, lengthToPx, pngPhys, pngPhysDpi, pxToLength, resolveSize, roundPx,
  setDpi, setHeight, setUnit, setWidth, type SizeFields, type Unit, UnitError
} from './units'

const vectors = JSON.parse(readFileSync(resolve(__dirname, '../../tests/vectors/units.json'), 'utf-8'))

describe('shared vectors (same file as the Python tests)', () => {
  for (const c of vectors.resolve) {
    it(c.name, () => {
      const a = c.in
      const r = resolveSize(a.width, a.height, a.unit, a.dpi, a.fitDpi ?? false)
      expect([r.width.px, r.height.px]).toEqual(c.px)
      for (const key of ['exactPx', 'dpi', 'errorMm', 'actualMm'] as const) {
        if (!c[key]) continue
        ;[r.width, r.height].forEach((ax, i) => expect(ax[key]).toBeCloseTo(c[key][i], 6))
      }
    })
  }

  it('conversions', () => {
    for (const c of vectors.pxToLength) expect(pxToLength(c.px, c.unit, c.dpi)).toBeCloseTo(c.out, 9)
    for (const c of vectors.lengthToPx) expect(lengthToPx(c.value, c.unit, c.dpi)).toBeCloseTo(c.out, 9)
    for (const c of vectors.pngPhys) {
      expect(pngPhys(c.dpi)).toBe(c.ppm)
      expect(pngPhysDpi(c.ppm)).toBeCloseTo(c.readback, 4)
    }
    for (const c of vectors.jfif) expect(jfifDensity(c.dpi)).toBe(c.out)
    for (const c of vectors.bytes) expect(bytesFrom(c.value, c.unit, c.base)).toBe(c.out)
  })

  it('errors', () => {
    for (const c of vectors.errors) {
      const a = c.in
      expect(() => resolveSize(a.width, a.height, a.unit as Unit, a.dpi)).toThrow(UnitError)
    }
  })
})

describe('spec examples', () => {
  it('3 cm at 200 DPI = 236.2 px; 240 px at 200 DPI = 3.048 cm', () => {
    expect(Math.round(lengthToPx(3, 'cm', 200) * 10) / 10).toBe(236.2)
    expect(pxToLength(240, 'cm', 200)).toBeCloseTo(3.048, 9)
  })

  it('describes rounding for the user', () => {
    const r = resolveSize(3, 3, 'cm', 200)
    expect(describeAxis(r.width)).toBe('3 cm @ 200 DPI = 236.22 px → 236 px (−0.22 px, −0.028 mm)')
    const p = resolveSize(240, 240, 'px', 200)
    expect(describeAxis(p.width)).toBe('240 px = 3.048 cm = 1.2 in at 200 DPI')
  })

  it('half-up rounding matches Python', () => {
    expect(roundPx(2.5)).toBe(3)
    expect(roundPx(2.4999)).toBe(2)
  })
})

describe('field logic', () => {
  const base: SizeFields = { width: 240, height: 240, unit: 'px', dpi: 200, sizeMode: 'exactPixels', lockAspect: true }

  it('unit changes keep the pixel size', () => {
    const cm = setUnit(base, 'cm')
    expect(cm.width).toBe(3.048)
    expect(setUnit(cm, 'px').width).toBe(240)
    const mm = setUnit({ ...base, unit: 'cm', width: 3, height: 3 }, 'mm')
    expect(mm.width).toBe(30)
  })

  it('exact pixels: DPI change keeps pixels, changes cm', () => {
    const f = setDpi({ ...base, unit: 'cm', width: 3.048, height: 3.048 }, 300)
    expect(f.dpi).toBe(300)
    expect(resolveSize(f.width, f.height, f.unit, f.dpi).width.px).toBe(240)
  })

  it('exact physical: DPI change keeps cm, changes pixels', () => {
    const f = setDpi({ ...base, unit: 'cm', width: 3, height: 3, sizeMode: 'exactPhysical' }, 300)
    expect(f.width).toBe(3)
    expect(resolveSize(f.width, f.height, f.unit, f.dpi).width.px).toBe(354)
  })

  it('aspect lock', () => {
    const f = { ...base, width: 140, height: 60 }
    expect(setWidth(f, 280, 140 / 60).height).toBe(120)
    expect(setHeight(f, 30, 140 / 60).width).toBe(70)
    expect(setWidth({ ...f, lockAspect: false }, 280, 140 / 60).height).toBe(60)
  })
})
