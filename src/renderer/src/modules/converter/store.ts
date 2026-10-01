import { create } from 'zustand'
import type {
  AppSettings, ConvertFileResult, ConvertResult, ConverterCatalog, ConverterOptions, ConverterProgress, ConverterSettings,
  PreflightResult
} from '@shared/types'
import { basename, dirname, isCancelled, newJobId, otk, toUiError } from '../../lib/api'
import { canRedo, canUndo, createHistory, type History, record, redo, undo } from '../../lib/history'
import { updateAppSettings, useUi } from '../../lib/ui-store'

export type DocStatus = 'checking' | 'ready' | 'needs_password' | 'blocked' | 'error' | 'running' | 'done' | 'failed' | 'cancelled'

export interface DocFile {
  id: string
  path: string
  name: string
  status: DocStatus
  preflight: PreflightResult | null
  /** Kept in memory for this session only; never saved or logged. */
  password?: string
  progress: number
  message: string
  result?: ConvertFileResult
}

export const CONVERTER_DEFAULTS: ConverterSettings = {
  target: 'pdf', mode: 'exact', outputDir: null, ocr: true, ocrLanguages: ['eng'], dpi: 300, jpegQuality: 92, paper: 'a4',
  notesPages: false, pdfaEmbedSource: false, keepPdfaId: true, merge: false, verifyAppearance: true, txtSplitTabs: false,
  txtLinesPerSlide: 20
}

/** Settings that change what the conversion does (undo/redo applies to these). */
export type Snapshot = Omit<ConverterSettings, 'outputDir'>

interface RunState {
  running: boolean
  jobId?: string
  progress?: ConverterProgress
  result?: ConvertResult
  /** The last job that can be resumed (cancelled or with failures, job folder kept). */
  resumable?: { jobId: string; target: string }
}

interface ConverterStore {
  catalog: ConverterCatalog | null
  catalogError: string | null
  files: DocFile[]
  history: History<Snapshot>
  outputDir: string | null
  run: RunState
  passwordFor: string | null
  initialised: boolean

  init(app: AppSettings): void
  loadCatalog(): Promise<void>
  addPaths(paths: string[]): Promise<void>
  remove(id: string): void
  clear(): void
  update(patch: Partial<Snapshot>, coalesceKey?: string): void
  undo(): void
  redo(): void
  canUndo(): boolean
  canRedo(): boolean
  setOutputDir(dir: string | null): void
  inspect(): Promise<void>
  askPassword(id: string | null): void
  setPassword(id: string, password: string, applyToAll: boolean): Promise<void>
  start(resume?: boolean): Promise<void>
  cancel(): Promise<void>
}

let ids = 1
let inspectSeq = 0

function options(s: Snapshot): ConverterOptions {
  const { target: _t, merge: _m, ...rest } = s
  return rest
}

export const useConverter = create<ConverterStore>((set, get) => ({
  catalog: null,
  catalogError: null,
  files: [],
  history: createHistory<Snapshot>(stripDir(CONVERTER_DEFAULTS)),
  outputDir: null,
  run: { running: false },
  passwordFor: null,
  initialised: false,

  init(app) {
    if (get().initialised) return
    const saved = { ...CONVERTER_DEFAULTS, ...(app.converter ?? {}) }
    set({ history: createHistory(stripDir(saved)), outputDir: saved.outputDir, initialised: true })
  },

  async loadCatalog() {
    try {
      const catalog = await otk().converter.catalog()
      set({ catalog, catalogError: null })
      // Keep only OCR languages that are installed (a language may have been removed since last time).
      const s = get().history.present
      const have = new Set(catalog.ocrLanguages)
      const langs = s.ocrLanguages.filter((l) => have.has(l))
      if (langs.length !== s.ocrLanguages.length && have.size) {
        set((st) => ({ history: { ...st.history, present: { ...s, ocrLanguages: langs.length ? langs : [have.has('eng') ? 'eng' : catalog.ocrLanguages[0]] } } }))
      }
    } catch (e) {
      set({ catalogError: toUiError(e).message })
    }
  },

  async addPaths(paths) {
    const have = new Set(get().files.map((f) => f.path))
    const fresh = paths.filter((p) => !have.has(p)).map<DocFile>((p) => ({
      id: `doc-${ids++}`, path: p, name: basename(p), status: 'checking', preflight: null, progress: 0, message: ''
    }))
    if (!fresh.length) return
    set((s) => ({ files: [...s.files, ...fresh] }))
    if (!get().outputDir) get().setOutputDir(dirname(fresh[0].path))
    await get().inspect()
  },

  remove(id) {
    set((s) => ({ files: s.files.filter((f) => f.id !== id) }))
  },

  clear() {
    if (get().run.running) return
    set({ files: [], run: { running: false } })
  },

  update(patch, coalesceKey) {
    const cur = get().history.present
    const next = { ...cur, ...patch }
    set({ history: record(get().history, next, coalesceKey ?? null) })
    void persist()
    if (patch.target !== undefined || patch.mode !== undefined || patch.ocr !== undefined || patch.ocrLanguages !== undefined) {
      void get().inspect()
    }
  },

  undo() {
    set({ history: undo(get().history) })
    void persist()
    void get().inspect()
  },

  redo() {
    set({ history: redo(get().history) })
    void persist()
    void get().inspect()
  },

  canUndo: () => canUndo(get().history),
  canRedo: () => canRedo(get().history),

  setOutputDir(dir) {
    set({ outputDir: dir })
    void persist()
  },

  async inspect() {
    const files = get().files.filter((f) => f.status !== 'running')
    if (!files.length) return
    const seq = ++inspectSeq
    const s = get().history.present
    // A result for another target or mode is stale: the file is ready to convert again.
    const stale = (f: DocFile) => f.result && (f.result.route?.target !== s.target || f.result.route?.mode !== s.mode || f.result.status !== 'done')
    set((st) => ({
      files: st.files.map((f) => (files.includes(f) && (!f.result || stale(f)) ? { ...f, status: 'checking' as DocStatus, result: undefined, progress: 0 } : f))
    }))
    const passwords: Record<string, string> = {}
    for (const f of files) if (f.password) passwords[f.path] = f.password
    try {
      const res = await otk().converter.inspect({ paths: files.map((f) => f.path), target: s.target, mode: s.mode, options: options(s), passwords })
      if (seq !== inspectSeq) return // a newer check is on its way
      const byPath = new Map(res.files.map((r) => [r.path, r]))
      set((st) => ({
        files: st.files.map((f) => {
          const pf = byPath.get(f.path)
          if (!pf || f.status === 'running') return f
          const status: DocStatus = pf.ok ? 'ready' : pf.code === 'password_needed' ? 'needs_password'
            : pf.code === 'no_route' || pf.code === 'not_found' || pf.code === 'unsupported_format' ? 'error' : 'blocked'
          return { ...f, preflight: pf, status: f.result ? f.status : status, message: f.result ? f.message : pf.error ?? '' }
        })
      }))
      const firstLocked = get().files.find((f) => f.status === 'needs_password' && !f.password)
      if (firstLocked && !get().passwordFor) set({ passwordFor: firstLocked.id })
    } catch (e) {
      if (seq !== inspectSeq) return
      useUi.getState().reportError('Could not check the files', e)
      set((st) => ({ files: st.files.map((f) => (f.status === 'checking' ? { ...f, status: 'error', message: toUiError(e).message } : f)) }))
    }
  },

  askPassword(id) {
    set({ passwordFor: id })
  },

  async setPassword(id, password, applyToAll) {
    set((s) => ({
      passwordFor: null,
      files: s.files.map((f) => (f.id === id || (applyToAll && f.status === 'needs_password') ? { ...f, password } : f))
    }))
    await get().inspect()
  },

  async start(resume = false) {
    const st = get()
    if (st.run.running) return
    const s = st.history.present
    const outputDir = st.outputDir
    if (!outputDir) {
      useUi.getState().toast('warn', 'Choose an output folder first')
      return
    }
    const todo = st.files.filter((f) => f.status === 'ready' || (resume && ['cancelled', 'failed', 'done'].includes(f.status) && f.preflight?.ok))
    if (!todo.length) {
      useUi.getState().toast('warn', 'Nothing to convert', 'Add files, or fix the problems shown in the list.')
      return
    }
    const jobId = resume && st.run.resumable ? st.run.resumable.jobId : newJobId('convert')
    set((x) => ({
      run: { running: true, jobId },
      files: x.files.map((f) => (todo.includes(f) ? { ...f, status: 'running', progress: 0, message: 'Waiting…', result: undefined } : f))
    }))
    const order = todo.map((f) => f.id)
    const unsub = otk().converter.onProgress((p) => {
      if (p.jobId !== jobId) return
      const id = order[p.index]
      set((x) => ({
        run: { ...x.run, progress: p },
        files: x.files.map((f) => {
          if (f.id !== id) return f
          if (p.result) return { ...f, result: p.result, status: resultStatus(p.result), progress: 1, message: p.result.message }
          return { ...f, progress: p.fileFraction ?? f.progress, message: p.message.replace(/^\d+\/\d+ [^:]*: /, '') }
        })
      }))
    })
    try {
      const result = await otk().converter.run({
        jobId, target: s.target, options: options(s), outputDir, merge: s.merge && todo.length > 1,
        mergeName: `merged-${s.target}`, files: todo.map((f) => ({ path: f.path, password: f.password }))
      })
      const byIndex = new Map(order.map((id, i) => [id, result.results[i]]))
      const resumable = result.jobDir && result.results.some((r) => r.status !== 'done') ? { jobId, target: s.target } : undefined
      set((x) => ({
        run: { running: false, jobId, result, resumable },
        files: x.files.map((f) => {
          const r = byIndex.get(f.id)
          return r ? { ...f, result: r, status: resultStatus(r), progress: 1, message: r.message } : f
        })
      }))
      announce(result)
    } catch (e) {
      const cancelled = isCancelled(e)
      set((x) => ({
        run: { running: false, jobId, resumable: { jobId, target: s.target } },
        files: x.files.map((f) => (f.status === 'running' ? { ...f, status: cancelled ? 'cancelled' : 'failed', message: cancelled ? 'Cancelled' : toUiError(e).message } : f))
      }))
      if (!cancelled) useUi.getState().reportError('The conversion stopped', e)
    } finally {
      unsub()
    }
  },

  async cancel() {
    const jobId = get().run.jobId
    if (jobId && get().run.running) await otk().jobs.cancel(jobId)
  }
}))

function stripDir(s: ConverterSettings): Snapshot {
  const { outputDir: _o, ...rest } = s
  return rest
}

function resultStatus(r: ConvertFileResult): DocStatus {
  if (r.status === 'done') return 'done'
  if (r.status === 'needs_password') return 'needs_password'
  if (r.status === 'cancelled') return 'cancelled'
  return 'failed'
}

function announce(r: ConvertResult): void {
  const done = r.results.filter((x) => x.status === 'done')
  const perfect = done.filter((x) => x.verdict === 'perfect').length
  const review = done.filter((x) => x.verdict === 'review').length
  const failed = r.results.length - done.length
  const ui = useUi.getState()
  if (!done.length) ui.toast('error', 'Nothing was converted', r.results[0]?.message)
  else if (failed || review) ui.toast('warn', `${done.length} converted, ${review} need review, ${failed} failed`, 'Open each report for details.')
  else ui.toast('success', `${done.length} converted`, `${perfect} perfect, ${done.length - perfect} with expected changes.`)
}

let persistTimer: ReturnType<typeof setTimeout> | undefined
function persist(): Promise<void> {
  clearTimeout(persistTimer)
  return new Promise((resolve) => {
    persistTimer = setTimeout(() => {
      const st = useConverter.getState()
      const conv: ConverterSettings = { ...st.history.present, outputDir: st.outputDir }
      updateAppSettings({ converter: conv }).catch((e) => useUi.getState().reportError('Could not save the converter settings', e))
      resolve()
    }, 500)
  })
}
