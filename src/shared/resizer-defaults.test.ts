import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import { describe, expect, it } from 'vitest'
import { clientIssues, RESIZER_DEFAULTS, toStoredSettings, withDefaults } from './resizer-defaults'

const res = (p: string) => JSON.parse(readFileSync(resolve(__dirname, '../../resources', p), 'utf-8'))
const schemas = ['resizer-settings.schema.json', 'converter-settings.schema.json', 'design-settings.schema.json', 'passport-settings.schema.json',
  'settings.schema.json', 'resizer-presets.schema.json', 'passport-specs.schema.json', 'paper-sizes.schema.json'].map((n) => res(`schemas/${n}`))

function ajv() {
  const a = new Ajv2020({ allErrors: true, strict: false })
  for (const s of schemas) a.addSchema(s)
  return a
}

describe('resizer defaults', () => {
  it('match the schema defaults', () => {
    const props = schemas[0].properties as Record<string, { default?: unknown }>
    for (const [k, v] of Object.entries(props)) {
      if ('default' in v) expect(RESIZER_DEFAULTS[k as keyof typeof RESIZER_DEFAULTS], k).toEqual(v.default)
    }
  })

  it('stored settings validate', () => {
    const v = ajv().getSchema('otk://schemas/resizer-settings.schema.json')!
    expect(v(toStoredSettings(RESIZER_DEFAULTS)), JSON.stringify(v.errors)).toBe(true)
  })

  it('shipped settings.json and presets validate', () => {
    const a = ajv()
    const vs = a.getSchema('otk://schemas/settings.schema.json')!
    expect(vs(res('defaults/settings.json')), JSON.stringify(vs.errors)).toBe(true)
    const vp = a.getSchema('otk://schemas/resizer-presets.schema.json')!
    const presets = res('defaults/presets/resizer.json')
    expect(vp(presets), JSON.stringify(vp.errors)).toBe(true)
    const names = presets.presets.map((p: { name: string }) => p.name)
    expect(names).toContain('Photo 240×240 px @200 DPI (about 3×3 cm)')
    expect(names).toContain('Signature 140×60 px')
  })

  it('passport specs, paper sizes and settings validate; every spec names its source or says it is unverified', () => {
    const a = ajv()
    const vs = a.getSchema('otk://schemas/passport-specs.schema.json')!
    const specs = res('defaults/presets/passport-specs.json')
    expect(vs(specs), JSON.stringify(vs.errors)).toBe(true)
    for (const s of specs.specs) {
      expect(s.head.min, s.id).toBeLessThan(s.head.max)
      expect(s.head.max, s.id).toBeLessThan(s.height)
      if (s.source.status === 'official-excerpt') expect(s.source.url && s.source.quote && s.source.checked, s.id).toBeTruthy()
      else expect(s.source.status, s.id).toBe('unverified')
    }
    expect(specs.specs.map((s: { width: number; height: number; unit: string }) => `${s.width}x${s.height}${s.unit}`))
      .toEqual(expect.arrayContaining(['35x45mm', '2x2in', '33x48mm', '50x70mm', '25x35mm', '30x40mm']))
    const vpp = a.getSchema('otk://schemas/paper-sizes.schema.json')!
    expect(vpp(res('defaults/presets/paper-sizes.json')), JSON.stringify(vpp.errors)).toBe(true)
    const vset = a.getSchema('otk://schemas/passport-settings.schema.json')!
    const pass = res('defaults/settings.json').passport
    expect(vset(pass), JSON.stringify(vset.errors)).toBe(true)
    expect(vset({ ...pass, sheet: { ...pass.sheet, dpi: 150 } })).toBe(false)
    expect(vs({ version: 1, specs: [{ ...specs.specs[0], head: { min: 1, max: 2, crown: 'ears' } }] })).toBe(false)
  })

  it('converter settings: shipped defaults validate, bad values are rejected', () => {
    const v = ajv().getSchema('otk://schemas/converter-settings.schema.json')!
    const conv = res('defaults/settings.json').converter
    expect(v(conv), JSON.stringify(v.errors)).toBe(true)
    expect(v({ ...conv, target: 'doc' })).toBe(false)
    expect(v({ ...conv, dpi: 20 })).toBe(false)
    expect(v({ ...conv, ocrLanguages: [] })).toBe(false)
    expect(v({ ...conv, mode: 'fast' })).toBe(false)
  })

  it('schema rejects bad values', () => {
    const v = ajv().getSchema('otk://schemas/resizer-settings.schema.json')!
    expect(v({ ...toStoredSettings(RESIZER_DEFAULTS), dpi: 5000 })).toBe(false)
    expect(v({ ...toStoredSettings(RESIZER_DEFAULTS), format: 'gif' })).toBe(false)
    expect(v({ ...toStoredSettings(RESIZER_DEFAULTS), extra: 1 })).toBe(false)
  })

  it('client-side issues', () => {
    expect(clientIssues(RESIZER_DEFAULTS)).toEqual([])
    expect(clientIssues(withDefaults({ ...RESIZER_DEFAULTS, width: 240.5 }))).toContain('Pixel sizes must be whole numbers.')
    expect(clientIssues(withDefaults({ ...RESIZER_DEFAULTS, sizeRange: { min: 60, max: 50, unit: 'KB' } })))
      .toContain('The minimum file size is larger than the maximum.')
  })
})
