import { create } from 'zustand'
import {
  type Box, cssFont, type DesignScene, type FontFamilyInfo, facesUsed, type ImageLayer, type Layer, newId, reorder,
  type ShapeLayer, type TextLayer, textHeight, updateLayer
} from '@shared/design'
import type { AppSettings, DesignAccuracy, DesignExportFormat, DesignSettings, DesignSummary, JobProgress } from '@shared/types'
import { basename, isCancelled, newJobId, otk, toUiError } from '../../lib/api'
import { createHistory, type History, record, redo, replace, undo } from '../../lib/history'
import { updateAppSettings, useUi } from '../../lib/ui-store'
import { ensureFace, measure, metricsFor } from './fonts'

export const DESIGN_DEFAULTS: DesignSettings = {
  languages: ['eng'], upscale: 'auto', deskew: true, denoise: true, exportFormat: 'pptx', exportDir: null, fontsFolder: false,
  highlightLowConfidence: true, snap: true
}

export type Overlay = 'off' | 'split' | 'diff'

interface AnalysisJob {
  jobId: string
  source: string
  fraction: number
  message: string
}

interface DesignStore {
  settings: DesignSettings
  designs: DesignSummary[]
  job: AnalysisJob | null
  id: string | null
  history: History<DesignScene> | null
  selection: string[]
  overlay: Overlay
  split: number
  assetUrls: Record<string, string>
  fonts: FontFamilyInfo[] | null
  accuracy: DesignAccuracy | null
  /** The scene the accuracy result belongs to (a later edit makes it out of date). */
  accuracyFor: DesignScene | null
  accuracyState: 'idle' | 'running' | 'error'
  saveState: 'saved' | 'dirty' | 'saving' | 'error'
  editingText: string | null
  busy: string | null
  initialised: boolean

  init(app: AppSettings): void
  setSettings(patch: Partial<DesignSettings>): void
  refreshList(): Promise<void>
  loadFonts(): Promise<void>
  analyze(path?: string | null): Promise<void>
  cancelAnalysis(): Promise<void>
  openDesign(id: string): Promise<void>
  openFile(path?: string | null): Promise<void>
  deleteDesign(id: string): Promise<void>
  close(): Promise<void>

  scene(): DesignScene | null
  commit(next: DesignScene, coalesceKey?: string | null): void
  /** Change the current state without a new undo step (a box resized to fit text just edited). */
  amend(next: DesignScene): void
  patchLayer<T extends Layer>(id: string, patch: Partial<T> | ((l: T) => T), coalesceKey?: string | null): void
  select(ids: string[]): void
  undo(): void
  redo(): void
  save(): Promise<void>
  addText(): void
  addShape(shape: ShapeLayer['shape']): void
  addImage(): Promise<void>
  replaceImage(id: string): Promise<void>
  cutout(id: string, mode: 'auto' | 'person' | 'subject'): Promise<void>
  restoreImage(id: string): void
  vectorToPixels(id: string): Promise<void>
  removeSelected(): void
  duplicateSelected(): void
  reorderSelected(to: 1 | -1 | 'top' | 'bottom'): void
  nudge(dx: number, dy: number): void
  fitTextBox(id: string): void
  setOverlay(o: Overlay): void
  setSplit(v: number): void
  setEditingText(id: string | null): void
  checkAccuracy(): Promise<void>
  exportAs(format: DesignExportFormat, fontsFolder: boolean): Promise<void>
  installFonts(): Promise<void>
  assetUrl(rel: string): Promise<string>
  openLoaded(id: string, scene: DesignScene): Promise<void>
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
let saving: Promise<void> | null = null
let saveAgain = false
let progressUnsub: (() => void) | null = null

function log(message: string): void {
  void otk().log.add('info', message)
}

export const useDesign = create<DesignStore>((set, get) => ({
  settings: DESIGN_DEFAULTS,
  designs: [],
  job: null,
  id: null,
  history: null,
  selection: [],
  overlay: 'off',
  split: 0.5,
  assetUrls: {},
  fonts: null,
  accuracy: null,
  accuracyFor: null,
  accuracyState: 'idle',
  saveState: 'saved',
  editingText: null,
  busy: null,
  initialised: false,

  init(app) {
    if (get().initialised) return
    set({ settings: { ...DESIGN_DEFAULTS, ...(app.design ?? {}) }, initialised: true })
    progressUnsub?.()
    progressUnsub = otk().jobs.onProgress((p: JobProgress & { fraction?: number; message?: string }) => {
      const job = get().job
      if (job && p.jobId === job.jobId) set({ job: { ...job, fraction: p.fraction ?? job.fraction, message: p.message ?? job.message } })
    })
  },

  setSettings(patch) {
    const next = { ...get().settings, ...patch }
    set({ settings: next })
    void updateAppSettings({ design: patch }).catch((e) => useUi.getState().reportError('Could not save the settings', e))
  },

  async refreshList() {
    try {
      set({ designs: await otk().design.list() })
    } catch (e) {
      useUi.getState().reportError('Could not list your designs', e)
    }
  },

  async loadFonts() {
    if (get().fonts) return
    try {
      set({ fonts: await otk().design.fonts() })
    } catch (e) {
      useUi.getState().reportError('The bundled fonts could not be loaded', e)
    }
  },

  async analyze(path) {
    const source = path ?? (await otk().design.pickImage())
    if (!source) return
    const jobId = newJobId('design')
    const s = get().settings
    set({ job: { jobId, source, fraction: 0, message: 'Starting' } })
    try {
      const res = await otk().design.analyze({
        jobId, source, options: { languages: s.languages, upscale: s.upscale, deskew: s.deskew, denoise: s.denoise }
      })
      set({ job: null })
      await get().openLoaded(res.id, res.scene)
      const missed = res.scene.unreadable?.length ?? 0
      if (missed) {
        useUi.getState().toast('warn', 'Some lines were not read', `${missed} line(s) are not in the chosen languages and were left in the picture as they are. See Check.`, 10000)
      } else {
        useUi.getState().toast('success', 'Design ready', `${res.scene.layers.length} layers from ${basename(source)}. Check the highlighted words and the overlay.`)
      }
      void get().checkAccuracy()
    } catch (e) {
      set({ job: null })
      if (!isCancelled(e)) useUi.getState().reportError('The picture could not be analysed', e)
    }
  },

  async cancelAnalysis() {
    const job = get().job
    if (job) await otk().jobs.cancel(job.jobId)
  },

  async openDesign(id) {
    try {
      const { scene } = await otk().design.load(id)
      await get().openLoaded(id, scene)
    } catch (e) {
      useUi.getState().reportError('The design could not be opened', e)
    }
  },

  async openFile(path) {
    try {
      const res = await otk().design.openFile(path)
      if (res) await get().openLoaded(res.id, res.scene)
    } catch (e) {
      useUi.getState().reportError('The design file could not be opened', e)
    }
  },

  async deleteDesign(id) {
    await otk().design.remove(id)
    await get().refreshList()
  },

  async close() {
    if (get().saveState === 'dirty') await get().save()
    set({ id: null, history: null, selection: [], accuracy: null, accuracyFor: null, accuracyState: 'idle', editingText: null, assetUrls: {}, overlay: 'off' })
    await get().refreshList()
  },

  scene: () => get().history?.present ?? null,

  commit(next, coalesceKey = null) {
    const h = get().history
    if (!h || next === h.present) return
    set({ history: record(h, next, coalesceKey), saveState: 'dirty' })
    scheduleSave()
  },

  amend(next) {
    const h = get().history
    if (!h || next === h.present) return
    set({ history: { ...h, present: next }, saveState: 'dirty' })
    scheduleSave()
  },

  patchLayer(id, patch, coalesceKey = null) {
    const scene = get().scene()
    if (!scene) return
    get().commit(updateLayer(scene, id, patch), coalesceKey)
  },

  select(ids) {
    const scene = get().scene()
    const valid = new Set(scene?.layers.map((l) => l.id) ?? [])
    set({ selection: ids.filter((i) => valid.has(i)) })
  },

  undo() {
    const h = get().history
    if (!h) return
    set({ history: undo(h), saveState: 'dirty', editingText: null })
    get().select(get().selection)
    scheduleSave()
  },

  redo() {
    const h = get().history
    if (!h) return
    set({ history: redo(h), saveState: 'dirty', editingText: null })
    get().select(get().selection)
    scheduleSave()
  },

  async save() {
    // One save at a time, in order: a change made while saving is saved right after.
    if (saving) {
      saveAgain = true
      return saving
    }
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = null
    saving = (async () => {
      do {
        saveAgain = false
        const { id } = get()
        const scene = get().scene()
        if (!id || !scene) return
        set({ saveState: 'saving' })
        try {
          await otk().design.save(id, scene)
          set({ saveState: get().scene() === scene ? 'saved' : 'dirty' })
          if (get().scene() !== scene) saveAgain = true
        } catch (e) {
          set({ saveState: 'error' })
          useUi.getState().reportError('The design could not be saved', e)
          return
        }
      } while (saveAgain)
    })().finally(() => {
      saving = null
    })
    return saving
  },

  addText() {
    const scene = get().scene()
    if (!scene) return
    const family = mostUsedFamily(scene)
    const size = Math.max(12, Math.round(Math.min(scene.page.width, scene.page.height) / 24))
    const style = { family, weight: 400, italic: false, size, color: '#222222', align: 'left' as const, lineHeight: 1.2, underline: false }
    const m = metricsFor(family, 400, false)
    const text = 'New text'
    const w = measure(text, cssFont(family, 400, false, size)) + 4
    const layer: TextLayer = {
      id: newId(scene, 'text'), type: 'text', name: 'New text', box: [scene.page.width / 2 - w / 2, scene.page.height / 2 - size / 2, w, 0],
      rotation: 0, visible: true, locked: false, opacity: 1, text, style, words: [], lowConfidence: [], script: 'latin'
    }
    layer.box[3] = textHeight(layer, m)
    void ensureFace(family, 400, false)
    get().commit({ ...scene, layers: [...scene.layers, layer] })
    set({ selection: [layer.id], editingText: layer.id })
    log(`Design: added a text layer`)
  },

  addShape(shape) {
    const scene = get().scene()
    if (!scene) return
    const s = Math.round(Math.min(scene.page.width, scene.page.height) / 5)
    const box: Box = [scene.page.width / 2 - s / 2, scene.page.height / 2 - s / 3, s, shape === 'line' ? 4 : Math.round(s * 0.66)]
    const layer: ShapeLayer = shape === 'line'
      ? { id: newId(scene, 'line'), type: 'shape', name: 'Line', box, rotation: 0, visible: true, locked: false, opacity: 1, shape,
          fill: null, stroke: '#222222', strokeWidth: 4, points: [0, 2, s, 2] }
      : { id: newId(scene, 'shape'), type: 'shape', name: { rect: 'Rectangle', rounded: 'Rounded rectangle', ellipse: 'Ellipse' }[shape],
          box, rotation: 0, visible: true, locked: false, opacity: 1, shape, fill: '#4a7fd6', stroke: null, strokeWidth: 0,
          radius: shape === 'rounded' ? Math.round(s / 8) : 0 }
    get().commit({ ...scene, layers: [...scene.layers, layer] })
    set({ selection: [layer.id] })
  },

  async addImage() {
    const { id } = get()
    const scene = get().scene()
    if (!id || !scene) return
    try {
      const r = await otk().design.importImage(id)
      if (!r) return
      const cur = get().scene()!
      const k = Math.min(1, (cur.page.width * 0.5) / r.width, (cur.page.height * 0.5) / r.height)
      const w = r.width * k
      const h = r.height * k
      const layer: ImageLayer = {
        id: newId(cur, 'image'), type: 'image', name: 'Picture', box: [cur.page.width / 2 - w / 2, cur.page.height / 2 - h / 2, w, h],
        rotation: 0, visible: true, locked: false, opacity: 1, asset: r.asset, kind: 'photo'
      }
      get().commit({ ...cur, layers: [...cur.layers, layer] })
      set({ selection: [layer.id] })
    } catch (e) {
      useUi.getState().reportError('The picture could not be added', e)
    }
  },

  async replaceImage(layerId) {
    const { id } = get()
    if (!id) return
    try {
      const r = await otk().design.importImage(id)
      if (!r) return
      get().patchLayer<ImageLayer>(layerId, (l) => {
        // Keep the frame's width and centre; take the new picture's proportions.
        const [x, y, w, h] = l.box
        const nh = (w * r.height) / r.width
        return { ...l, asset: r.asset, originalAsset: undefined, box: [x, y + h / 2 - nh / 2, w, nh] }
      })
    } catch (e) {
      useUi.getState().reportError('The picture could not be replaced', e)
    }
  },

  async cutout(layerId, mode) {
    const { id } = get()
    const layer = get().scene()?.layers.find((l) => l.id === layerId) as ImageLayer | undefined
    if (!id || !layer) return
    set({ busy: 'Cutting out the background…' })
    try {
      const r = await otk().design.cutout({ jobId: newJobId('cutout'), id, asset: layer.asset, mode })
      get().patchLayer<ImageLayer>(layerId, (l) => ({ ...l, asset: r.asset, originalAsset: l.originalAsset ?? l.asset }))
      useUi.getState().toast('success', 'Background removed', `${r.method === 'person' ? 'Person' : 'Subject'} kept (${Math.round(r.coverage * 100)}% of the picture).`)
    } catch (e) {
      useUi.getState().reportError('The background could not be removed', e)
    } finally {
      set({ busy: null })
    }
  },

  restoreImage(layerId) {
    get().patchLayer<ImageLayer>(layerId, (l) => (l.originalAsset ? { ...l, asset: l.originalAsset, originalAsset: undefined } : l))
  },

  async vectorToPixels(layerId) {
    const scene = get().scene()
    const layer = scene?.layers.find((l) => l.id === layerId)
    if (!scene || !layer || layer.type !== 'vector' || !layer.source?.pixels) return
    const img: ImageLayer = {
      id: layer.id, type: 'image', name: layer.name, box: layer.box, rotation: layer.rotation, visible: layer.visible,
      locked: layer.locked, opacity: layer.opacity, asset: layer.source.pixels
    }
    get().commit({ ...scene, layers: scene.layers.map((l) => (l.id === layerId ? img : l)) })
  },

  removeSelected() {
    const scene = get().scene()
    const sel = new Set(get().selection)
    if (!scene || !sel.size) return
    const layers = scene.layers.filter((l) => !sel.has(l.id))
    get().commit({ ...scene, layers })
    set({ selection: [], editingText: null })
  },

  duplicateSelected() {
    const scene = get().scene()
    if (!scene) return
    let cur = scene
    const added: string[] = []
    for (const id of get().selection) {
      const l = cur.layers.find((x) => x.id === id)
      if (!l || (l.type === 'image' && l.role === 'background')) continue
      const copy = structuredClone(l) as Layer
      copy.id = newId(cur, l.type === 'shape' && l.shape === 'line' ? 'line' : l.type)
      copy.name = `${l.name} copy`
      copy.box = [l.box[0] + 12, l.box[1] + 12, l.box[2], l.box[3]]
      const at = cur.layers.findIndex((x) => x.id === l.id)
      cur = { ...cur, layers: [...cur.layers.slice(0, at + 1), copy, ...cur.layers.slice(at + 1)] }
      added.push(copy.id)
    }
    if (added.length) {
      get().commit(cur)
      set({ selection: added })
    }
  },

  reorderSelected(to) {
    const scene = get().scene()
    if (scene && get().selection.length) get().commit(reorder(scene, get().selection, to))
  },

  nudge(dx, dy) {
    const scene = get().scene()
    if (!scene) return
    const sel = new Set(get().selection)
    get().commit({
      ...scene,
      layers: scene.layers.map((l) => (sel.has(l.id) && !l.locked ? { ...l, box: [l.box[0] + dx, l.box[1] + dy, l.box[2], l.box[3]] as Box } : l))
    }, 'nudge')
  },

  fitTextBox(layerId) {
    const scene = get().scene()
    const l = scene?.layers.find((x) => x.id === layerId)
    if (!scene || !l || l.type !== 'text') return
    const st = l.style
    const font = cssFont(st.family, st.weight, st.italic, st.size)
    const widest = Math.max(4, ...l.text.split('\n').map((t) => measure(t, font))) + 2
    const m = metricsFor(st.family, st.weight, st.italic)
    const h = textHeight(l, m)
    let [x, y, w] = l.box
    if (widest > w) {
      // Grow around the alignment anchor so the text stays where it was.
      if (st.align === 'center') x -= (widest - w) / 2
      else if (st.align === 'right') x -= widest - w
      w = widest
    }
    if (Math.abs(h - l.box[3]) > 0.01 || w !== l.box[2]) {
      get().amend(updateLayer<TextLayer>(scene, layerId, { box: [x, y, w, h] }))
    }
  },

  setOverlay: (overlay) => set({ overlay }),
  setSplit: (split) => set({ split: Math.max(0, Math.min(1, split)) }),
  setEditingText: (editingText) => set({ editingText }),

  async checkAccuracy() {
    const { id } = get()
    const scene = get().scene()
    if (!id || !scene) return
    set({ accuracyState: 'running' })
    try {
      const accuracy = await otk().design.accuracy({ jobId: newJobId('accuracy'), id, scene })
      set({ accuracy, accuracyFor: scene, accuracyState: 'idle' })
      log(`Design check: rebuilt vs original SSIM ${accuracy.ssim.toFixed(3)}, ${accuracy.regions.length} area(s) differ`)
    } catch (e) {
      set({ accuracyState: 'error' })
      if (!isCancelled(e)) useUi.getState().toast('warn', 'The accuracy check did not run', toUiError(e).message)
    }
  },

  async exportAs(format, fontsFolder) {
    const { id } = get()
    const scene = get().scene()
    if (!id || !scene) return
    await get().save()
    set({ busy: 'Exporting…' })
    try {
      const res = await otk().design.exportAs({ id, scene, format, fontsFolder })
      if (!res) return
      get().setSettings({ exportFormat: format, fontsFolder })
      useUi.getState().toast('success', 'Exported', [basename(res.path), ...res.notes].join(' — '), 8000)
    } catch (e) {
      useUi.getState().reportError('The export failed', e)
    } finally {
      set({ busy: null })
    }
  },

  async installFonts() {
    const scene = get().scene()
    if (!scene) return
    try {
      const r = await otk().design.installFonts(scene)
      useUi.getState().toast('success', 'Fonts installed', `${r.installed.length} font(s) for your user account. Restart Office programs to see them.`, 8000)
    } catch (e) {
      useUi.getState().reportError('The fonts could not be installed', e)
    }
  },

  async assetUrl(rel) {
    const have = get().assetUrls[rel]
    if (have) return have
    const { id } = get()
    if (!id) throw new Error('No design open')
    const url = await otk().design.assetUrl(id, rel)
    set((s) => ({ assetUrls: { ...s.assetUrls, [rel]: url } }))
    return url
  },

  async openLoaded(id: string, scene: DesignScene) {
    set({
      id, history: replace(createHistory(scene), scene), selection: [], accuracy: null, accuracyFor: null, accuracyState: 'idle', saveState: 'saved',
      editingText: null, assetUrls: {}, overlay: 'off'
    })
    void get().loadFonts()
    for (const f of facesUsed(scene)) void ensureFace(f.family, f.weight, f.italic).catch(() => undefined)
  }
}))

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => void useDesign.getState().save(), 1200)
}

function mostUsedFamily(scene: DesignScene): string {
  const n = new Map<string, number>()
  for (const l of scene.layers) if (l.type === 'text') n.set(l.style.family, (n.get(l.style.family) ?? 0) + l.text.length)
  let best = 'Noto Sans'
  let most = -1
  for (const [f, c] of n) if (c > most) [best, most] = [f, c]
  return best
}
