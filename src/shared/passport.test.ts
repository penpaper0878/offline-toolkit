import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { apply, compose, cornersInside, cropMap, cropWithRatio, fitInside, invert, placeMap, specPx, type Crop, type Place } from './passport'

const V = JSON.parse(readFileSync(resolve(__dirname, '../../tests/vectors/passport.json'), 'utf-8'))

describe('passport maps match the worker (tests/vectors/passport.json)', () => {
  it('cropMap', () => {
    for (const c of V.cropMap) {
      const m = cropMap(c.crop as Crop)
      c.points.forEach(([x, y]: [number, number], i: number) => {
        const [ex, ey] = c.expect[i]
        const [gx, gy] = apply(m, x, y)
        expect(gx).toBeCloseTo(ex, 6)
        expect(gy).toBeCloseTo(ey, 6)
      })
    }
  })

  it('fitInside', () => {
    for (const f of V.fitInside) {
      const got = fitInside(f.crop as Crop, f.size[0], f.size[1])
      for (const k of ['cx', 'cy', 'w', 'h'] as const) expect(got[k], k).toBeCloseTo(f.expect[k], 6)
      expect(cornersInside(got, f.size[0], f.size[1])).toBe(true)
    }
  })

  it('placeMap', () => {
    for (const p of V.placeMap) {
      const m = placeMap(p.place as Place, p.crop[0], p.crop[1], p.out[0], p.out[1])
      p.points.forEach(([x, y]: [number, number], i: number) => {
        const [gx, gy] = apply(m, x, y)
        expect(gx).toBeCloseTo(p.expect[i][0], 6)
        expect(gy).toBeCloseTo(p.expect[i][1], 6)
      })
    }
  })

  it('specPx with the rounding error', () => {
    for (const s of V.specPx) {
      const got = specPx(s.spec)
      expect([got.w, got.h]).toEqual(s.expect)
      expect(got.errorMm[0]).toBeCloseTo(s.errorMm[0], 3)
      expect(got.errorMm[1]).toBeCloseTo(s.errorMm[1], 3)
    }
  })
})

describe('passport crop helpers', () => {
  it('invert and compose', () => {
    const m = cropMap({ cx: 10, cy: 20, w: 30, h: 40, angle: 12, flipH: true, flipV: false })
    const id = compose(invert(m), m)
    expect(id[0]).toBeCloseTo(1, 9)
    expect(id[2]).toBeCloseTo(0, 9)
    expect(id[4]).toBeCloseTo(1, 9)
  })

  it('a ratio crop keeps its ratio and stays inside the photo at any angle', () => {
    for (const angle of [-45, -10, 0, 7, 45]) {
      const c = cropWithRatio({ cx: 400, cy: 300, w: 800, h: 600, angle, flipH: false, flipV: false }, 35 / 45, 800, 600)
      expect(c.w / c.h).toBeCloseTo(35 / 45, 9)
      expect(cornersInside(c, 800, 600)).toBe(true)
    }
  })
})
