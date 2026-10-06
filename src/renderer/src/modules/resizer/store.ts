import { create } from 'zustand'
import { normaliseCrop } from '@shared/geometry'
import { clientIssues, type FullResizerSettings, RESIZER_DEFAULTS, toStoredSettings, withDefaults } from '@shared/resizer-defaults'
import type { AppSettings, BatchResult, Crop, ItemResult, JobProgress, Preset, PresetState, PreviewResult, ProbeResult } from '@shared/types'
import { resolveSize } from '@shared/units'
import { basename, dirname, isCancelled, newJobId, otk, toUiError } from '../../lib/api'
import { canRedo, canUndo, createHistory, type History, record, redo, undo } from '../../lib/history'
import { rememberFiles } from '../../lib/recent'
import { updateAppSettings, useUi } from '../../lib/ui-store'

export interface FileEntry {
  id: string
  path: string
  name: string
  status: 'loading' | 'ready' | 'error'
  probe?: ProbeResult
  error?: string
  lastResult?: ItemResult
}

export interface Snapshot {
  settings: FullResizerSettings
  crops: Record<string, Crop | null>
}

export interface PreviewState {
  status: 'idle' | 'invalid' | 'running' | 'done' | 'error'
  key?: string
  jobId?: string
  result?: PreviewResult
  error?: string
  issues?: string[]
}

export interface BatchState {
  running: boolean
  jobId?: string
  progress?: JobProgress
  result?: BatchResult
  error?: string
  open: boolean
}

interface ResizerStore {
  files: FileEntry[]
  selectedId: string | null
  history: History<Snapshot>
  presetId: string | null
  presets: PresetState | null
  outputDir: string | null
  zip: boolean
  preview: PreviewState
  batch: BatchState
  view: 'crop' | 'compare'
  zoom: number | 'fit'
  split: number
  initialised: boolean

  init(app: AppSettings): void
  addPaths(paths: string[]): Promise<void>
  select(id: string | null): void
  remove(id: string): void
  clear(): void
  update(patch: Partial<FullResizerSettings>, coalesceKey?: string | null): void
  setCrop(fileId: string, crop: Crop | null, coalesceKey?: string | null): void
  undo(): void
  redo(): void
  canUndo(): boolean
  canRedo(): boolean
  applyPreset(p: Preset): void
  loadPresets(): Promise<void>
  setPresets(state: PresetState): void
  setOutputDir(dir: string | null): void
  setZip(zip: boolean): void
  setView(view: 'crop' | 'compare'): void
  setZoom(zoom: number | 'fit'): void
  setSplit(split: number): void
  runPreview(): Promise<void>
  runBatch(): Promise<void>
  cancelBatch(): Promise<void>
  closeBatch(): void
}

let fileSeq = 1
const settingsOf = (s: ResizerStore) => s.history.present.settings

/** Target pixel size for the current settings, or null if they don't resolve. */
export function targetPx(s: FullResizerSettings): [number, number] | null {
  try {
    const r = resolveSize(s.width, s.height, s.unit, s.dpi, s.fitDpi)
    return [r.width.px, r.height.px]
  } catch {
    return null
  }
}

/** Crop windows follow the target aspect ratio whenever the size changes. */
function refitCrops(snap: Snapshot, files: FileEntry[]): Snapshot {
  const t = targetPx(snap.settings)
  if (!t) return snap
  const crops: Record<string, Crop | null> = {}
  for (const [id, c] of Object.entries(snap.crops)) {
    const f = files.find((x) => x.id === id)
    crops[id] = c && f?.probe ? normaliseCrop(c, f.probe.width, f.probe.height, t[0], t[1]) : c
  }
  return { ...snap, crops }
}

async function probeAll(entries: FileEntry[], concurrency = 3): Promise<void> {
  const queue = [...entries]
  const worker = async () => {
    for (let e = queue.shift(); e; e = queue.shift()) {
      try {
        const probe = await otk().image.probe(e.path)
        useResizer.setState((s) => ({ files: s.files.map((f) => (f.id === e!.id ? { ...f, status: 'ready', probe } : f)) }))
        if (probe.warnings.length) void otk().log.add('info', `${e.name}: ${probe.warnings.join(' ')}`)
      } catch (err) {
        const msg = toUiError(err).message
        useResizer.setState((s) => ({ files: s.files.map((f) => (f.id === e!.id ? { ...f, status: 'error', error: msg } : f)) }))
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, worker))
}

export const useResizer = create<ResizerStore>((set, get) => ({
  files: [],
  selectedId: null,
  history: createHistory<Snapshot>({ settings: RESIZER_DEFAULTS, crops: {} }),
  presetId: null,
  presets: null,
  outputDir: null,
  zip: false,
  preview: { status: 'idle' },
  batch: { running: false, open: false },
  view: 'crop',
  zoom: 'fit',
  split: 50,
  initialised: false,

  init(app) {
    if (get().initialised) return
    const r = app.resizer
    set({
      history: createHistory<Snapshot>({ settings: withDefaults(r.settings), crops: {} }),
      presetId: r.lastPresetId,
      outputDir: r.outputDir,
      zip: r.zip,
      view: r.settings.fit === 'crop' ? 'crop' : 'compare',
      initialised: true
    })
    otk().jobs.onProgress((p) => {
      if (p.jobId === get().batch.jobId) set((s) => ({ batch: { ...s.batch, progress: p } }))
    })
  },

  async addPaths(paths) {
    const have = new Set(get().files.map((f) => f.path))
    const fresh = [...new Set(paths)].filter((p) => !have.has(p))
    if (!fresh.length) return
    rememberFiles('resizer', fresh, 'images')
    const entries: FileEntry[] = fresh.map((p) => ({ id: `f${fileSeq++}`, path: p, name: basename(p), status: 'loading' }))
    set((s) => ({ files: [...s.files, ...entries], selectedId: s.selectedId ?? entries[0].id }))
    await probeAll(entries)
  },

  select(id) {
    set({ selectedId: id })
  },

  remove(id) {
    set((s) => {
      const idx = s.files.findIndex((f) => f.id === id)
      const files = s.files.filter((f) => f.id !== id)
      const selectedId = s.selectedId === id ? (files[Math.min(idx, files.length - 1)]?.id ?? null) : s.selectedId
      return { files, selectedId }
    })
  },

  clear() {
    set({ files: [], selectedId: null, preview: { status: 'idle' } })
  },

  update(patch, coalesceKey = null) {
    set((s) => {
      const settings = { ...settingsOf(s), ...patch }
      const next = refitCrops({ ...s.history.present, settings }, s.files)
      return { history: record(s.history, next, coalesceKey) }
    })
  },

  setCrop(fileId, crop, coalesceKey = null) {
    set((s) => ({ history: record(s.history, { ...s.history.present, crops: { ...s.history.present.crops, [fileId]: crop } }, coalesceKey) }))
  },

  undo: () => set((s) => ({ history: undo(s.history) })),
  redo: () => set((s) => ({ history: redo(s.history) })),
  canUndo: () => canUndo(get().history),
  canRedo: () => canRedo(get().history),

  applyPreset(p) {
    set((s) => {
      const next = refitCrops({ ...s.history.present, settings: withDefaults(p.settings) }, s.files)
      return { history: record(s.history, next), presetId: p.id, view: p.settings.fit === 'crop' ? 'crop' : 'compare' }
    })
  },

  async loadPresets() {
    const presets = await otk().presets.list()
    set({ presets })
    if (presets.error) useUi.getState().toast('error', 'Presets file problem', presets.error, 0)
  },

  setPresets: (presets) => set({ presets }),
  setOutputDir: (outputDir) => set({ outputDir }),
  setZip: (zip) => set({ zip }),
  setView: (view) => set({ view }),
  setZoom: (zoom) => set({ zoom }),
  setSplit: (split) => set({ split }),

  async runPreview() {
    const s = get()
    const file = s.files.find((f) => f.id === s.selectedId)
    if (!file || file.status !== 'ready') {
      set({ preview: { status: 'idle' } })
      return
    }
    const settings = settingsOf(s)
    const issues = clientIssues(settings)
    if (issues.length) {
      set({ preview: { status: 'invalid', issues } })
      return
    }
    const crop = settings.fit === 'crop' ? (s.history.present.crops[file.id] ?? null) : null
    const key = JSON.stringify([file.path, settings, crop])
    if (s.preview.key === key && (s.preview.status === 'done' || s.preview.status === 'running')) return
    if (s.preview.status === 'running' && s.preview.jobId) void otk().jobs.cancel(s.preview.jobId)
    const jobId = newJobId('preview')
    set((st) => ({ preview: { ...st.preview, status: 'running', key, jobId, error: undefined, issues: undefined } }))
    try {
      const result = await otk().resizer.preview({ jobId, item: { path: file.path, crop }, settings: toStoredSettings(settings) })
      if (get().preview.key !== key) return
      set((st) => ({
        preview: { status: 'done', key, jobId, result },
        files: st.files.map((f) => (f.id === file.id ? { ...f, lastResult: result } : f))
      }))
    } catch (e) {
      if (get().preview.key !== key || isCancelled(e)) return
      set({ preview: { status: 'error', key, jobId, error: toUiError(e).message } })
    }
  },

  async runBatch() {
    const s = get()
    const ready = s.files.filter((f) => f.status === 'ready')
    const ui = useUi.getState()
    if (!ready.length) {
      ui.toast('warn', 'No images to process', 'Add images first (Ctrl+O or drag them in).')
      return
    }
    const settings = settingsOf(s)
    const issues = clientIssues(settings)
    if (issues.length) {
      ui.toast('error', 'Fix the settings first', issues.join(' '))
      return
    }
    let outputDir = s.outputDir
    if (!outputDir) {
      outputDir = await otk().dialogs.chooseDir(dirname(ready[0].path))
      if (!outputDir) return
      set({ outputDir })
    }
    const jobId = newJobId('resize')
    const items = ready.map((f) => ({ path: f.path, crop: settings.fit === 'crop' ? (s.history.present.crops[f.id] ?? null) : null }))
    set({ batch: { running: true, jobId, open: true, progress: { jobId, index: 0, total: items.length, fraction: 0, message: 'Starting…' } } })
    try {
      const result = await otk().resizer.run({ jobId, items, settings: toStoredSettings(settings), outputDir, zip: s.zip })
      set((st) => ({
        batch: { ...st.batch, running: false, result },
        files: st.files.map((f) => {
          const r = result.results.find((x) => x.path === f.path)
          return r ? { ...f, lastResult: r } : f
        })
      }))
      const ok = (result.counts.ok ?? 0) + (result.counts.ok_padded ?? 0) + (result.counts.no_target ?? 0)
      const problems = result.results.length - ok
      ui.toast(problems ? 'warn' : 'success', `Saved ${ok} of ${result.results.length} image(s)`,
        problems ? `${problems} need attention — see the results table.` : result.zipPath ? `ZIP: ${basename(result.zipPath)}` : undefined)
    } catch (e) {
      const err = toUiError(e)
      set((st) => ({ batch: { ...st.batch, running: false, error: err.message } }))
      if (err.code !== 'cancelled') ui.reportError('Batch failed', e)
    }
  },

  async cancelBatch() {
    const id = get().batch.jobId
    if (id) await otk().jobs.cancel(id)
  },

  closeBatch: () => set((s) => ({ batch: { ...s.batch, open: false } }))
}))

/** Persist the resizer settings (debounced by the caller). */
export async function persistResizer(): Promise<void> {
  const s = useResizer.getState()
  await updateAppSettings({
    resizer: { settings: toStoredSettings(s.history.present.settings), outputDir: s.outputDir, zip: s.zip, lastPresetId: s.presetId }
  })
}
