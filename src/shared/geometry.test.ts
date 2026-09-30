import { describe, expect, it } from 'vitest'
import { defaultCrop, normaliseCrop } from './geometry'

// Same cases as worker/tests/test_geometry_render.py.
describe('crop window', () => {
  it('default crop is centred with the exact aspect', () => {
    expect(defaultCrop(1200, 900, 240, 240)).toEqual({ x: 150, y: 0, w: 900, h: 900 })
    const r = defaultCrop(900, 1200, 140, 60)
    expect(r.w / r.h).toBeCloseTo(140 / 60, 12)
    expect(r.w).toBe(900)
  })

  it('normalise clamps and forces the aspect', () => {
    const r = normaliseCrop({ x: -50, y: 10, w: 500, h: 300 }, 1000, 800, 200, 200)
    expect(r.w / r.h).toBeCloseTo(1, 12)
    expect(r.x).toBeGreaterThanOrEqual(0)
    expect(r.x + r.w).toBeLessThanOrEqual(1000)
    expect(r.y + r.h).toBeLessThanOrEqual(800)
    const big = normaliseCrop({ x: 0, y: 0, w: 5000, h: 5000 }, 1000, 800, 400, 300)
    expect(big.w).toBeLessThanOrEqual(1000)
    expect(big.h).toBeLessThanOrEqual(800)
    expect(big.w / big.h).toBeCloseTo(400 / 300, 12)
  })

  it('an empty window falls back to the default', () => {
    expect(normaliseCrop({ x: 0, y: 0, w: 0, h: 10 }, 100, 100, 10, 10)).toEqual(defaultCrop(100, 100, 10, 10))
  })
})
