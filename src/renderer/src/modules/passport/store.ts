/**
 * Passport wizard state. The photo's editable state (PassportDoc) has one undo history across the steps;
 * the steps themselves are navigation. The worker holds the photo; this store sends parameters and shows
 * the images and hints that come back. Renders are debounced and only the newest one is shown.
 */

import { create } from 'zustand'
import type { PassportSheetResult } from '@shared/api'
import {
  type Adjust, type AnalyzeResult, type Background, type Crop, cropWithRatio, fitInside, fullCrop, NO_ADJUST, type PaperSize,
  type PassportDoc, type PassportSpec, type PhotoInfo, type RenderResult, type SheetPhoto, specPx, type Stroke, toMm
} from '@shared/passport'
import { otk, toUiError } from '../../lib/api'
import { canRedo, canUndo, createHistory, type History, record, redo, replace, undo } from '../../lib/history'
import { updateAppSettings, useUi } from '../../lib/ui-store'

export const STEPS = ['Browse', 'Crop', 'Size & enhance', 'Finalise'] as const

export const CUSTOM_ID = 'custom'

export function blankDoc(specId: string, background: Background): PassportDoc {
  return { crop: null, ratio: 'spec', specId, customSpec: null, place: null, background, strokes: [], adjust: { ...NO_ADJUST },
    overrides: {}, upscale: false }
}

export function customSpecFrom(base: PassportSpec | undefined): PassportSpec {
  return {
    id: CUSTOM_ID, name: 'Custom size', width: base?.width ?? 35, height: base?.height ?? 45, unit: base?.unit ?? 'mm', dpi: base?.dpi ?? 300,
    head: base ? { ...base.head } : { min: 31.5, max: 36, crown: 'hair' },
    backgrounds: base?.backgrounds ?? [{ name: 'White', color: '#FFFFFF' }], source: { status: 'user' }
  }
}

let renderSeq = 0
let renderTimer: ReturnType<typeof setTimeout> | null = null
let settingsTimer: ReturnType<typeof setTimeout> | null = null
let analyzeSeq = 0

interface State {
  step: number
  photo: PhotoInfo | null
  busy: string | null
  specs: PassportSpec[]
  specDefaults: string[]
  papers: PaperSize[]
  history: History<PassportDoc>
  analysis: AnalyzeResult | null
  analysisFor: string | null
  render: RenderResult | null
  renderFor: PassportDoc | null
  rendering: boolean
  tool: 'move' | 'restore' | 'erase'
  brush: { size: number; hardness: number }
  compare: number | null                 // before/after split (0..1) or null
  sheetPhotos: SheetPhoto[]              // other people's photos for the sheet
  sheetMine: number | null               // copies of this photo (null: fill the places left)
  sheetPreview: PassportSheetResult | null
  sheetBusy: boolean
  init(): Promise<void>
  open(path: string): Promise<void>
  openDialog(): Promise<void>
  paste(): Promise<void>
  close(): void
  setStep(n: number): Promise<void>
  doc(): PassportDoc
  spec(): PassportSpec | null
  update(patch: Partial<PassportDoc>, key?: string | null): void
  undo(): void
  redo(): void
  canUndo(): boolean
  canRedo(): boolean
  analyze(): Promise<AnalyzeResult | null>
  frameFace(): Promise<void>
  autofit(): Promise<void>
  scheduleRender(delay?: number): void
  autoAdjust(kind: 'enhance' | 'whiteBalance'): Promise<void>
  addStroke(s: Stroke): void
  request(extra?: Record<string, unknown>): Record<string, unknown>
  refreshSheet(): Promise<void>
  saveSpec(spec: PassportSpec): Promise<void>
  removeSpec(id: string): Promise<void>
  remember(): void
}

function cropKey(c: Crop | null): string {
  return JSON.stringify(c)
}

/** Call the worker; if it lost the photo (restarted), open it again once and retry. */
async function withPhoto<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn()
  } catch (e) {
    const photo = usePassport.getState().photo
    if (photo && /no longer open/i.test(toUiError(e).message)) {
      const again = await otk().passport.open(photo.path)
      usePassport.setState({ photo: again })
      return fn()
    }
    throw e
  }
}

export const usePassport = create<State>((set, get) => ({
  step: 0,
  photo: null,
  busy: null,
  specs: [],
  specDefaults: [],
  papers: [],
  history: createHistory(blankDoc('uk-passport', { mode: 'replace', color: '#FFFFFF', feather: 1 })),
  analysis: null,
  analysisFor: null,
  render: null,
  renderFor: null,
  rendering: false,
  tool: 'move',
  brush: { size: 24, hardness: 0.6 },
  compare: null,
  sheetPhotos: [],
  sheetMine: null,
  sheetPreview: null,
  sheetBusy: false,

  async init() {
    const [specs, papers] = await Promise.all([otk().passport.specs(), otk().passport.papers()])
    if (specs.error) useUi.getState().toast('error', 'Passport specs file problem', specs.error, 0)
    if (papers.error) useUi.getState().toast('error', 'Paper sizes file problem', papers.error, 0)
    const s = useUi.getState().settings?.passport
    const specId = s && specs.items.some((x) => x.id === s.specId) ? s.specId : specs.items[0]?.id ?? 'uk-passport'
    set({ specs: specs.items, specDefaults: specs.defaultIds, papers: papers.items })
    if (!get().photo) set({ history: createHistory(blankDoc(specId, s?.background ?? { mode: 'replace', color: '#FFFFFF', feather: 1 })) })
  },

  async open(path) {
    set({ busy: 'Opening the photo…' })
    try {
      const photo = await otk().passport.open(path)
      const prev = get().doc()
      set({
        photo, analysis: null, analysisFor: null, render: null, renderFor: null, compare: null, tool: 'move', sheetPreview: null,
        history: createHistory({ ...blankDoc(prev.specId, prev.background), customSpec: prev.customSpec }), busy: 'Finding the face…'
      })
      for (const w of photo.warnings) useUi.getState().toast('warn', 'About this photo', w)
      void otk().log.add('info', `Passport: opened ${photo.path.split(/[\\/]/).pop()} (${photo.width}×${photo.height})`)
      await get().frameFace()
      set({ step: 1 })
    } catch (e) {
      useUi.getState().reportError('The photo could not be opened', e)
    } finally {
      set({ busy: null })
    }
  },

  async openDialog() {
    const [path] = await otk().passport.pick(false)
    if (path) await get().open(path)
  },

  async paste() {
    const path = await otk().passport.paste()
    if (path) await get().open(path)
    else useUi.getState().toast('info', 'Nothing to paste', 'Copy a photo first (for example from a browser or an image viewer).')
  },

  close() {
    set({ photo: null, step: 0, analysis: null, analysisFor: null, render: null, renderFor: null, sheetPreview: null })
  },

  async setStep(n) {
    const { photo } = get()
    if (n > 0 && !photo) return
    set({ step: n, compare: null })
    if (n >= 2) {
      const an = await get().analyze()
      if (an && !get().doc().place) await get().autofit()
      get().scheduleRender(0)
      if (n === 3) void get().refreshSheet()
    }
  },

  doc: () => get().history.present,

  spec() {
    const d = get().doc()
    if (d.specId === CUSTOM_ID) return d.customSpec
    return get().specs.find((s) => s.id === d.specId) ?? null
  },

  update(patch, key = null) {
    const prev = get().history.present
    const next = { ...prev, ...patch }
    const { photo } = get()
    const newSpec = next.specId === CUSTOM_ID ? next.customSpec : get().specs.find((x) => x.id === next.specId)
    if (!patch.crop && photo && newSpec && next.ratio === 'spec' && (patch.specId !== undefined || patch.customSpec !== undefined)) {
      // The crop has the photo's shape: a spec of another shape reshapes it (same height and centre).
      const c = prev.crop ?? fullCrop(photo.width, photo.height)
      const r = newSpec.width / newSpec.height
      if (Math.abs(c.w / c.h - r) > 1e-3) next.crop = fitInside({ ...c, w: c.h * r }, photo.width, photo.height)
    }
    const cropChanged = cropKey(next.crop) !== cropKey(prev.crop)
    if (cropChanged) {
      next.place = patch.place ?? null           // a new crop is fitted again
      next.overrides = patch.overrides ?? {}
    }
    set({ history: record(get().history, next, key) })
    if (patch.specId || patch.customSpec || patch.background) get().remember()
    if (get().step >= 2) {
      if (cropChanged || (patch.specId && !patch.place) || (patch.customSpec && !patch.place)) {
        void (async () => {
          await get().analyze()
          if (!get().doc().place) await get().autofit()
          get().scheduleRender(0)
        })()
      } else get().scheduleRender()
    }
    if (get().step === 3) void get().refreshSheet()
  },

  undo() {
    set({ history: undo(get().history) })
    if (get().step >= 2) {
      void get().analyze().then(() => get().scheduleRender(0))
      if (get().step === 3) void get().refreshSheet()
    }
  },

  redo() {
    set({ history: redo(get().history) })
    if (get().step >= 2) {
      void get().analyze().then(() => get().scheduleRender(0))
      if (get().step === 3) void get().refreshSheet()
    }
  },

  canUndo: () => canUndo(get().history),
  canRedo: () => canRedo(get().history),

  async analyze() {
    const { photo } = get()
    const d = get().doc()
    if (!photo) return null
    const crop = d.crop ?? fullCrop(photo.width, photo.height)
    const key = cropKey(crop) + '|' + d.specId
    if (get().analysisFor === key && get().analysis) return get().analysis
    const seq = ++analyzeSeq
    set({ busy: 'Finding the face and the background…' })
    try {
      const an = await withPhoto(() => otk().passport.analyze({ id: get().photo!.id, crop, spec: get().spec(), overrides: d.overrides }))
      if (seq === analyzeSeq) set({ analysis: an, analysisFor: key })
      if (an.faces === 0) useUi.getState().toast('warn', 'No face found', 'Place the photo by hand, and drag the crown and chin markers to the head.')
      return an
    } catch (e) {
      useUi.getState().reportError('The photo could not be analysed', e)
      return null
    } finally {
      if (seq === analyzeSeq) set({ busy: null })
    }
  },

  async frameFace() {
    // A first crop: the spec's shape around the head and shoulders (head about 55% of the height).
    const { photo } = get()
    const spec = get().spec()
    if (!photo || !spec) return
    const full = fullCrop(photo.width, photo.height)
    try {
      const an = await withPhoto(() => otk().passport.analyze({ id: photo.id, crop: full, spec }))
      set({ analysis: an, analysisFor: cropKey(full) + '|' + get().doc().specId })
      const ratio = spec.width / spec.height
      let crop: Crop
      if (an.face) {
        const f = an.face
        const head = Math.hypot(f.chin[0] - f.crown[0], f.chin[1] - f.crown[1])
        // Looser than the finished photo (the head there is the spec's mid-range share of the height), so the
        // next step has room to fit it: at most 55% of the crop, or 80% of the spec's share.
        const share = (spec.head.min + spec.head.max) / 2 / spec.height
        const h = head / Math.min(0.55, share * 0.8)
        const cy = f.crown[1] + head * 0.5 + h * 0.06
        crop = fitInside({ cx: f.centre[0], cy, w: h * ratio, h, angle: 0, flipH: false, flipV: false }, photo.width, photo.height)
      } else crop = cropWithRatio(full, ratio, photo.width, photo.height)
      set({ history: replace(get().history, { ...get().doc(), crop, place: null, overrides: {} }) })
    } catch (e) {
      useUi.getState().reportError('The face could not be found', e)
      set({ history: replace(get().history, { ...get().doc(), crop: cropWithRatio(full, spec.width / spec.height, photo.width, photo.height) }) })
    }
  },

  async autofit() {
    const { photo } = get()
    const d = get().doc()
    const spec = get().spec()
    if (!photo || !spec || !get().analysis?.face) return
    try {
      const r = await withPhoto(() => otk().passport.autofit({ id: get().photo!.id, crop: d.crop, spec, overrides: d.overrides }))
      const cur = get().history.present
      set({ history: cur.place ? record(get().history, { ...cur, place: r.place }) : replace(get().history, { ...cur, place: r.place }) })
      get().scheduleRender(0)
    } catch (e) {
      useUi.getState().reportError('Auto fit failed', e)
    }
  },

  request(extra = {}) {
    const d = get().doc()
    return { id: get().photo?.id, crop: d.crop, place: d.place, spec: get().spec(), background: d.background, strokes: d.strokes,
      adjust: d.adjust, overrides: d.overrides, upscale: d.upscale, ...extra }
  },

  scheduleRender(delay = 140) {
    if (renderTimer) clearTimeout(renderTimer)
    renderTimer = setTimeout(async () => {
      const { photo } = get()
      if (!photo || get().step < 2 || !get().spec()) return
      const seq = ++renderSeq
      const doc = get().doc()
      set({ rendering: true })
      try {
        const r = await withPhoto(() => otk().passport.render(get().request({ id: get().photo!.id, before: get().compare !== null })))
        if (seq !== renderSeq) return
        set({ render: r, renderFor: doc })
        if (!doc.place && r.measures.place) set({ history: replace(get().history, { ...get().doc(), place: r.measures.place }) })
      } catch (e) {
        if (seq === renderSeq) useUi.getState().reportError('The photo could not be drawn', e)
      } finally {
        if (seq === renderSeq) set({ rendering: false })
      }
    }, delay)
  },

  async autoAdjust(kind) {
    try {
      const r = await withPhoto(() => otk().passport.auto(get().request({ kind })))
      get().update({ adjust: { ...get().doc().adjust, ...(r.adjust as Partial<Adjust>) } })
    } catch (e) {
      useUi.getState().reportError(kind === 'enhance' ? 'Auto enhance failed' : 'Auto white balance failed', e)
    }
  },

  addStroke(s) {
    get().update({ strokes: [...get().doc().strokes, s] })
  },

  async refreshSheet() {
    const s = useUi.getState().settings?.passport
    const spec = get().spec()
    if (!s || !spec || !get().photo) return
    set({ sheetBusy: true })
    try {
      const r = await withPhoto(() => otk().passport.sheet(sheetRequest('preview')))
      set({ sheetPreview: r })
    } catch (e) {
      useUi.getState().reportError('The sheet preview failed', e)
    } finally {
      set({ sheetBusy: false })
    }
  },

  async saveSpec(spec) {
    const st = await otk().passport.saveSpec(spec)
    set({ specs: st.items, specDefaults: st.defaultIds })
    get().update({ specId: spec.id, customSpec: null })
  },

  async removeSpec(id) {
    const st = await otk().passport.removeSpec(id)
    set({ specs: st.items, specDefaults: st.defaultIds })
    if (get().doc().specId === id) get().update({ specId: st.items[0]?.id ?? CUSTOM_ID, customSpec: st.items.length ? null : customSpecFrom(undefined) })
  },

  remember() {
    if (settingsTimer) clearTimeout(settingsTimer)
    settingsTimer = setTimeout(() => {
      const d = get().doc()
      void updateAppSettings({ passport: { specId: d.specId === CUSTOM_ID ? (useUi.getState().settings?.passport.specId ?? 'uk-passport') : d.specId, background: d.background } })
        .catch((e) => useUi.getState().reportError('Settings could not be saved', e))
    }, 400)
  }
}))

export function paperOf(papers: PaperSize[], s: NonNullable<ReturnType<typeof useUi.getState>['settings']>['passport']['sheet']): PaperSize {
  return s.paperId === 'custom' ? { id: 'custom', name: 'Custom', ...s.custom } : papers.find((p) => p.id === s.paperId) ?? papers[0]
}

/** The worker request for a sheet: this photo (rendered at the sheet's DPI) plus any other people's photos. */
export function sheetRequest(format: 'preview' | 'pdf' | 'png' | 'jpeg', name?: string): Record<string, unknown> {
  const st = usePassport.getState()
  const s = useUi.getState().settings!.passport.sheet
  const spec = st.spec()!
  const paper = paperOf(st.papers, s)
  const size = specPx(spec)
  const others = st.sheetPhotos.map((p) => ({ kind: 'file', path: p.path, widthMm: size.mm[0], heightMm: size.mm[1], copies: p.copies }))
  return {
    photos: [{ kind: 'current', ...st.request(), copies: others.length ? st.sheetMine : null }, ...others],
    layout: { paper: { width: paper.width, height: paper.height, unit: paper.unit }, orientation: s.orientation, auto: s.auto,
      rows: s.rows, cols: s.cols, margins: s.margins, gutter: s.gutter, center: true },
    format, dpi: s.dpi, previewDpi: 50, borders: s.borders, cutMarks: s.cutMarks, name
  }
}

export const mmOf = toMm
