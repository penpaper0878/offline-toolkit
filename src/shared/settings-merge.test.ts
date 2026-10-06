import { describe, expect, it } from 'vitest'
import { applySettingsPatch, deepMerge } from './settings-merge'
import type { AppSettings } from './types'

describe('settings patches', () => {
  it('merge objects key by key and replace everything else', () => {
    const base = { a: { b: 1, c: [1, 2], d: { e: 'x' } }, f: 2 }
    expect(deepMerge(base, { a: { b: 5, c: [3] } })).toEqual({ a: { b: 5, c: [3], d: { e: 'x' } }, f: 2 })
    expect(deepMerge(base, { a: { d: null } } as never)).toEqual({ a: { b: 1, c: [1, 2], d: null }, f: 2 })
    expect(base.a.b).toBe(1)                                         // the base is not changed
  })

  it("replace the resizer's own settings whole, like the main process", () => {
    const s = { resizer: { settings: { mode: 'px', width: 1, extra: true }, other: 1 },
      passport: { export: { format: 'jpeg', limit: false, sizeLimit: { min: 20, max: 240, unit: 'KB' } } } } as unknown as AppSettings
    const next = applySettingsPatch(s, { resizer: { settings: { mode: 'mm' } } } as never)
    expect(next.resizer).toEqual({ settings: { mode: 'mm' }, other: 1 })
    const p = applySettingsPatch(s, { passport: { export: { limit: true, sizeLimit: { max: 60 } } } } as never)
    expect(p.passport.export).toEqual({ format: 'jpeg', limit: true, sizeLimit: { min: 20, max: 60, unit: 'KB' } })
  })
})
