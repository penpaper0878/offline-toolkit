/**
 * Editable JSON settings and presets (docs/ARCHITECTURE.md §10).
 *
 * Shipped defaults live read-only in resources/defaults and are copied to the
 * data folder on first run. An invalid user file is reported and the shipped
 * default is used instead; the user's file is never modified or overwritten
 * until they save from the app.
 */

import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import Ajv2020, { type ErrorObject, type ValidateFunction } from 'ajv/dist/2020'
import type { DeepPartial } from '@shared/api'
import type { AppSettings, Preset, PresetState, SettingsState } from '@shared/types'
import type { EventLog } from './log'

const SCHEMAS = ['resizer-settings.schema.json', 'converter-settings.schema.json', 'design-settings.schema.json', 'settings.schema.json', 'resizer-presets.schema.json']

interface PresetFile {
  $schema?: string
  version: 1
  deletedDefaults?: string[]
  presets: Preset[]
}

export class ValidationError extends Error {
  constructor(message: string, public details: string[]) {
    super(message)
  }
}

function describeErrors(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map((e) => `${e.instancePath || '(root)'} ${e.message ?? ''}`.trim())
}

async function readJson<T>(path: string): Promise<T> {
  return JSON.parse(await readFile(path, 'utf-8')) as T
}

async function writeJsonAtomic(path: string, data: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  const tmp = `${path}.${process.pid}.tmp`
  await writeFile(tmp, JSON.stringify(data, null, 2) + '\n', 'utf-8')
  await rename(tmp, path)
}

function deepMerge<T>(base: T, patch: DeepPartial<T>): T {
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

export class Store {
  private ajv = new Ajv2020({ allErrors: true, strict: false })
  private validateSettings!: ValidateFunction
  private validatePresets!: ValidateFunction
  validateResizer!: ValidateFunction
  private settings!: AppSettings
  private settingsError: string | null = null
  private defaults!: AppSettings
  private presetFile!: PresetFile
  private presetError: string | null = null
  private shippedPresets!: PresetFile

  constructor(private resourcesDir: string, private dataDir: string, private log: EventLog) {}

  get settingsFile(): string {
    return join(this.dataDir, 'settings.json')
  }

  get presetsFile(): string {
    return join(this.dataDir, 'presets', 'resizer.json')
  }

  async init(): Promise<void> {
    for (const name of SCHEMAS) this.ajv.addSchema(await readJson(join(this.resourcesDir, 'schemas', name)))
    this.validateResizer = this.ajv.getSchema('otk://schemas/resizer-settings.schema.json')!
    this.validateSettings = this.ajv.getSchema('otk://schemas/settings.schema.json')!
    this.validatePresets = this.ajv.getSchema('otk://schemas/resizer-presets.schema.json')!
    this.defaults = await readJson<AppSettings>(join(this.resourcesDir, 'defaults', 'settings.json'))
    this.shippedPresets = await readJson<PresetFile>(join(this.resourcesDir, 'defaults', 'presets', 'resizer.json'))
    await this.loadSettings()
    await this.loadPresets()
  }

  // ---------------------------------------------------------------- settings
  private async loadSettings(): Promise<void> {
    if (!existsSync(this.settingsFile)) {
      await writeJsonAtomic(this.settingsFile, { ...this.defaults, $schema: undefined })
    }
    try {
      const data = await readJson<AppSettings>(this.settingsFile)
      if (!this.validateSettings(data)) {
        const details = describeErrors(this.validateSettings.errors)
        throw new ValidationError(`settings.json is invalid: ${details.join('; ')}`, details)
      }
      // Sections added by an update (e.g. "converter" in 0.2) start from the shipped defaults.
      for (const key of Object.keys(this.defaults) as (keyof AppSettings)[]) {
        if (!(key in data) && key !== ('$schema' as keyof AppSettings)) (data as unknown as Record<string, unknown>)[key] = structuredClone(this.defaults[key])
      }
      this.settings = data
      this.settingsError = null
    } catch (e) {
      this.settings = structuredClone(this.defaults)
      this.settingsError = `${(e as Error).message}. Using the built-in defaults; your file was not changed.`
      this.log.error('settings', this.settingsError, { file: this.settingsFile })
    }
  }

  settingsState(): SettingsState {
    return {
      settings: structuredClone(this.settings),
      error: this.settingsError,
      paths: { data: this.dataDir, logs: join(this.dataDir, 'logs'), settingsFile: this.settingsFile, presetsFile: this.presetsFile }
    }
  }

  getSettings(): AppSettings {
    return this.settings
  }

  async updateSettings(patch: DeepPartial<AppSettings>): Promise<SettingsState> {
    const next = deepMerge(this.settings, patch)
    if (patch.resizer?.settings) next.resizer.settings = patch.resizer.settings as AppSettings['resizer']['settings']
    if (!this.validateSettings(next)) {
      const details = describeErrors(this.validateSettings.errors)
      throw new ValidationError(`These settings are not valid: ${details.join('; ')}`, details)
    }
    this.settings = next
    if (!this.settingsError) await writeJsonAtomic(this.settingsFile, next)
    return this.settingsState()
  }

  // ---------------------------------------------------------------- presets
  private async loadPresets(): Promise<void> {
    if (!existsSync(this.presetsFile)) {
      await writeJsonAtomic(this.presetsFile, { ...this.shippedPresets, $schema: undefined })
    }
    try {
      const data = await readJson<PresetFile>(this.presetsFile)
      if (!this.validatePresets(data)) {
        const details = describeErrors(this.validatePresets.errors)
        throw new ValidationError(`presets/resizer.json is invalid: ${details.join('; ')}`, details)
      }
      // Bring in shipped presets added by an update, unless the user deleted them.
      const have = new Set(data.presets.map((p) => p.id))
      const deleted = new Set(data.deletedDefaults ?? [])
      const added = this.shippedPresets.presets.filter((p) => !have.has(p.id) && !deleted.has(p.id))
      if (added.length) {
        data.presets.push(...added)
        await writeJsonAtomic(this.presetsFile, data)
      }
      this.presetFile = data
      this.presetError = null
    } catch (e) {
      this.presetFile = structuredClone(this.shippedPresets)
      this.presetError = `${(e as Error).message}. Showing the built-in presets; your file was not changed.`
      this.log.error('presets', this.presetError, { file: this.presetsFile })
    }
  }

  presetState(): PresetState {
    return {
      presets: structuredClone(this.presetFile.presets),
      defaultIds: this.shippedPresets.presets.map((p) => p.id),
      error: this.presetError
    }
  }

  private async savePresetFile(next: PresetFile): Promise<PresetState> {
    if (!this.validatePresets(next)) {
      const details = describeErrors(this.validatePresets.errors)
      throw new ValidationError(`This preset is not valid: ${details.join('; ')}`, details)
    }
    if (this.presetError) {
      throw new ValidationError('Your presets file has errors, so the app will not overwrite it. Fix or remove it first.', [])
    }
    this.presetFile = next
    await writeJsonAtomic(this.presetsFile, next)
    return this.presetState()
  }

  async savePreset(preset: Preset): Promise<PresetState> {
    const presets = this.presetFile.presets.filter((p) => p.id !== preset.id)
    const idx = this.presetFile.presets.findIndex((p) => p.id === preset.id)
    presets.splice(idx === -1 ? presets.length : idx, 0, preset)
    return this.savePresetFile({ ...this.presetFile, presets })
  }

  async removePreset(id: string): Promise<PresetState> {
    const isDefault = this.shippedPresets.presets.some((p) => p.id === id)
    const deleted = new Set(this.presetFile.deletedDefaults ?? [])
    if (isDefault) deleted.add(id)
    return this.savePresetFile({
      ...this.presetFile,
      deletedDefaults: [...deleted],
      presets: this.presetFile.presets.filter((p) => p.id !== id)
    })
  }

  /** Add presets from a file; clashing ids get a new id and "(imported)" in the name. */
  async importPresets(path: string): Promise<{ state: PresetState; imported: number }> {
    let data: PresetFile
    try {
      data = await readJson<PresetFile>(path)
    } catch (e) {
      throw new ValidationError(`Could not read ${path}: ${(e as Error).message}`, [])
    }
    if (!this.validatePresets(data)) {
      const details = describeErrors(this.validatePresets.errors)
      throw new ValidationError(`That file is not a valid presets file: ${details.join('; ')}`, details)
    }
    const ids = new Set(this.presetFile.presets.map((p) => p.id))
    const incoming = data.presets.map((p) => {
      if (!ids.has(p.id)) {
        ids.add(p.id)
        return p
      }
      let n = 2
      while (ids.has(`${p.id}-${n}`)) n++
      ids.add(`${p.id}-${n}`)
      return { ...p, id: `${p.id}-${n}`, name: `${p.name} (imported)` }
    })
    const state = await this.savePresetFile({ ...this.presetFile, presets: [...this.presetFile.presets, ...incoming] })
    return { state, imported: incoming.length }
  }

  async exportPresets(path: string, ids: string[]): Promise<void> {
    const chosen = this.presetFile.presets.filter((p) => ids.length === 0 || ids.includes(p.id))
    await writeJsonAtomic(path, { version: 1, presets: chosen })
  }
}
