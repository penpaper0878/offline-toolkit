/**
 * How a settings patch applies to the settings: objects merge key by key, anything else (arrays, numbers,
 * strings, null) replaces. Used by the main process when it saves, and by the window to show a change at
 * once, before the main process has answered.
 */

import type { DeepPartial } from './api'
import type { AppSettings } from './types'

export function deepMerge<T>(base: T, patch: DeepPartial<T>): T {
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) return patch as T
  const out: Record<string, unknown> = { ...(base as Record<string, unknown>) }
  for (const [k, v] of Object.entries(patch as Record<string, unknown>)) {
    const cur = out[k]
    out[k] = v !== null && typeof v === 'object' && !Array.isArray(v) && cur && typeof cur === 'object' && !Array.isArray(cur)
      ? deepMerge(cur, v as DeepPartial<unknown>)
      : v
  }
  return out as T
}

/** The settings after a patch (the resizer's own settings object is replaced whole, not merged). */
export function applySettingsPatch(settings: AppSettings, patch: DeepPartial<AppSettings>): AppSettings {
  const next = deepMerge(settings, patch)
  if (patch.resizer?.settings) next.resizer.settings = patch.resizer.settings as AppSettings['resizer']['settings']
  return next
}
