import type { ResizerSettings, SizeRange } from './types'

/** Defaults from resources/schemas/resizer-settings.schema.json (a test keeps them in sync). */
export type FullResizerSettings = Required<Omit<ResizerSettings, 'sizeRange'>> & { sizeRange: SizeRange | null }

export const RESIZER_DEFAULTS: FullResizerSettings = {
  width: 240,
  height: 240,
  unit: 'px',
  dpi: 200,
  sizeMode: 'exactPixels',
  fitDpi: false,
  lockAspect: true,
  fit: 'crop',
  padColor: '#FFFFFF',
  format: 'jpeg',
  quality: 90,
  sizeRange: null,
  subsampling: 'auto',
  stripMetadata: true,
  allowPadding: false,
  allowQuantize: false,
  webpLossless: 'auto',
  saveOutOfRange: false,
  naming: '{name}_{w}x{h}'
}

export function withDefaults(s: ResizerSettings): FullResizerSettings {
  return { ...RESIZER_DEFAULTS, ...s, sizeRange: s.sizeRange ?? null } as FullResizerSettings
}

/** Problems the UI can spot before asking the worker (the worker validates again). */
export function clientIssues(s: FullResizerSettings): string[] {
  const out: string[] = []
  const pos = (v: number) => Number.isFinite(v) && v > 0
  if (!pos(s.width)) out.push('Width must be a positive number.')
  if (!pos(s.height)) out.push('Height must be a positive number.')
  if (s.unit === 'px' && (!Number.isInteger(s.width) || !Number.isInteger(s.height))) out.push('Pixel sizes must be whole numbers.')
  if (!(s.dpi >= 72 && s.dpi <= 1200)) out.push('DPI must be between 72 and 1200.')
  if (s.width > 100000 || s.height > 100000) out.push('Width and height must be at most 100000.')
  const r = s.sizeRange
  if (r) {
    if (r.min != null && !(r.min >= 0)) out.push('Minimum size must be 0 or more.')
    if (r.max != null && !(r.max > 0)) out.push('Maximum size must be more than 0.')
    if (r.min != null && r.max != null && r.min > r.max) out.push('The minimum file size is larger than the maximum.')
  }
  if (!/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(s.padColor)) out.push('Padding colour must look like #RRGGBB.')
  if (!s.naming.trim()) out.push('The file name pattern is empty.')
  return out
}

/** Keep only the keys the schema knows (presets and settings are validated strictly). */
export function toStoredSettings(s: FullResizerSettings): ResizerSettings {
  const keys = Object.keys(RESIZER_DEFAULTS) as (keyof FullResizerSettings)[]
  const out: Record<string, unknown> = {}
  for (const k of keys) out[k] = s[k]
  return out as unknown as ResizerSettings
}
