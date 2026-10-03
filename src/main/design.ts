/**
 * Module 3 (image to editable design) in the main process: design folders, dialogs, and the worker calls.
 *
 * Each design lives in <data>/designs/<id>/ (scene.json, assets/, cache/). The renderer only ever names a
 * design by its id; paths are built and checked here.
 */

import { randomUUID } from 'node:crypto'
import { existsSync } from 'node:fs'
import { mkdir, readdir, readFile, rm, stat } from 'node:fs/promises'
import { basename, extname, join, relative, resolve } from 'node:path'
import { app, type BrowserWindow, dialog, ipcMain } from 'electron'
import { IPC } from '@shared/api'
import type { DesignScene, FontFamilyInfo, FontMetrics } from '@shared/design'
import type { DesignAnalyzeRequest, DesignExportRequest, DesignSummary } from '@shared/types'
import type { EventLog } from './log'
import { dataDir } from './paths'
import { fileUrl } from './protocol'
import type { Store } from './store'
import { WorkerError, type WorkerPool } from './worker'

const IMAGE_FILTER = { name: 'Images', extensions: ['jpg', 'jpeg', 'jpe', 'jfif', 'png', 'webp', 'bmp', 'dib', 'tif', 'tiff', 'heic', 'heif', 'hif'] }
const EXPORTS: Record<string, { name: string; ext: string }> = {
  pptx: { name: 'PowerPoint', ext: 'pptx' }, docx: { name: 'Word', ext: 'docx' }, svg: { name: 'SVG (layers)', ext: 'svg' },
  html: { name: 'Editable HTML', ext: 'html' }, otkd: { name: 'Offline Toolkit design', ext: 'otkd' }
}

type Result<T> = { ok: true; value: T } | { ok: false; error: { message: string; code: string } }

interface Deps {
  store: Store
  pool: WorkerPool
  log: EventLog
  getWindow: () => BrowserWindow | null
}

export const designsDir = (): string => join(dataDir(), 'designs')

function designDir(id: string): string {
  if (!/^[a-f0-9-]{8,64}$/i.test(id)) throw new WorkerError('Unknown design.', 'input')
  return join(designsDir(), id)
}

function insideDesign(id: string, rel: string): string {
  const dir = designDir(id)
  const full = resolve(dir, rel)
  const r = relative(dir, full)
  if (r.startsWith('..') || resolve(full) === resolve(dir)) throw new WorkerError('That file is not part of the design.', 'input')
  return full
}

function handle<A extends unknown[], T>(channel: string, fn: (...args: A) => Promise<T> | T, log: EventLog): void {
  ipcMain.handle(channel, async (_e, ...args: unknown[]): Promise<Result<T>> => {
    try {
      return { ok: true, value: await fn(...(args as A)) }
    } catch (e) {
      const error = e instanceof WorkerError ? { message: e.message, code: e.code } : { message: (e as Error)?.message ?? String(e), code: 'internal' }
      if (error.code !== 'cancelled') log.warn('design', `${channel}: ${error.message}`, { code: error.code })
      return { ok: false, error }
    }
  })
}

async function summary(id: string): Promise<DesignSummary | null> {
  const dir = join(designsDir(), id)
  try {
    const st = await stat(join(dir, 'scene.json'))
    const scene = JSON.parse(await readFile(join(dir, 'scene.json'), 'utf-8')) as DesignScene
    const thumb = join(dir, 'assets', 'prepared.png')
    return {
      id, name: scene.source?.name ?? id, modified: st.mtimeMs, width: scene.page.width, height: scene.page.height,
      layers: scene.layers.length, thumbUrl: existsSync(thumb) ? fileUrl(thumb) : null
    }
  } catch {
    return null
  }
}

export function registerDesignIpc({ store, pool, log, getWindow }: Deps): void {
  let fonts: FontFamilyInfo[] | null = null
  const faceUrls = new Map<string, { url: string; weight: number; italic: boolean; metrics: FontMetrics }>()

  handle(IPC.designList, async (): Promise<DesignSummary[]> => {
    if (!existsSync(designsDir())) return []
    const ids = (await readdir(designsDir(), { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name)
    const out = (await Promise.all(ids.map(summary))).filter((s): s is DesignSummary => s !== null)
    return out.sort((a, b) => b.modified - a.modified)
  }, log)

  handle(IPC.designDelete, async (id: string) => {
    await rm(designDir(id), { recursive: true, force: true })
    log.info('design', `Design deleted (${id})`)
  }, log)

  handle(IPC.designPickImage, async (): Promise<string | null> => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile'], filters: [IMAGE_FILTER] })
    return r.canceled ? null : r.filePaths[0]
  }, log)

  handle(IPC.designAnalyze, async (req: DesignAnalyzeRequest): Promise<{ id: string; scene: DesignScene }> => {
    if (!req || typeof req.source !== 'string' || typeof req.jobId !== 'string') throw new WorkerError('Invalid request.', 'input')
    const id = randomUUID()
    const dir = designDir(id)
    await mkdir(dir, { recursive: true })
    log.info('design', `Analysis started: ${basename(req.source)}`, { jobId: req.jobId, languages: req.options.languages })
    const started = Date.now()
    try {
      const res = await pool.runJob<{ scene: DesignScene }>(req.jobId, 'design.analyze', {
        source: req.source, project: dir, langs: req.options.languages, upscale: req.options.upscale,
        deskew: req.options.deskew, denoise: req.options.denoise
      })
      const s = res.scene
      const counts = s.layers.reduce<Record<string, number>>((acc, l) => ({ ...acc, [l.type]: (acc[l.type] ?? 0) + 1 }), {})
      log.info('design', `Analysis finished in ${((Date.now() - started) / 1000).toFixed(1)} s: ` +
        Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(', '), { jobId: req.jobId, lowConfidence: s.lowConfidence.length })
      return { id, scene: s }
    } catch (e) {
      await rm(dir, { recursive: true, force: true }).catch(() => undefined)
      throw e
    }
  }, log)

  handle(IPC.designLoad, async (id: string) => pool.interactive.request<{ scene: DesignScene }>('design.load', { project: designDir(id) }), log)

  handle(IPC.designSave, async (id: string, scene: DesignScene) => pool.interactive.request('design.save', { project: designDir(id), scene }), log)

  handle(IPC.designAccuracy, async (req: { jobId: string; id: string; scene: DesignScene }) =>
    pool.runJob(req.jobId, 'design.accuracy', { project: designDir(req.id), scene: req.scene }), log)

  handle(IPC.designAssetUrl, (id: string, rel: string) => {
    const p = insideDesign(id, rel)
    if (!existsSync(p)) throw new WorkerError(`Missing picture: ${rel}`, 'input')
    return fileUrl(p)
  }, log)

  handle(IPC.designImportImage, async (id: string, path?: string | null) => {
    let src = path ?? null
    if (!src) {
      const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile'], filters: [IMAGE_FILTER] })
      if (r.canceled) return null
      src = r.filePaths[0]
    }
    return pool.interactive.request<{ asset: string; width: number; height: number }>('design.importImage', { project: designDir(id), path: src })
  }, log)

  handle(IPC.designCutout, async (req: { jobId: string; id: string; asset: string; mode: string }) => {
    insideDesign(req.id, req.asset)
    const res = await pool.runJob<{ asset: string; method: string; coverage: number }>(req.jobId, 'design.cutout', {
      project: designDir(req.id), asset: req.asset, mode: req.mode
    })
    log.info('design', `Cut-out (${res.method}): kept ${(res.coverage * 100).toFixed(0)}% of the picture`)
    return res
  }, log)

  handle(IPC.designFonts, async (): Promise<FontFamilyInfo[]> => {
    if (!fonts) fonts = (await pool.interactive.request<{ families: FontFamilyInfo[] }>('design.fonts', {}, 60_000)).families
    return fonts
  }, log)

  handle(IPC.designFontFace, async (req: { family: string; weight: number; italic: boolean }) => {
    const key = `${req.family}|${req.weight}|${req.italic}`
    let hit = faceUrls.get(key)
    if (!hit) {
      const r = await pool.interactive.request<{ path: string; weight: number; italic: boolean; metrics: FontMetrics }>('design.fontFile', req, 60_000)
      hit = { url: fileUrl(r.path), weight: r.weight, italic: r.italic, metrics: r.metrics }
      faceUrls.set(key, hit)
    }
    return hit
  }, log)

  handle(IPC.designExport, async (req: DesignExportRequest) => {
    const fmt = EXPORTS[req.format]
    if (!fmt) throw new WorkerError(`Unknown format ${req.format}`, 'input')
    const settings = store.getSettings().design
    const base = (req.scene.source?.name ?? 'design').replace(/\.[^.]+$/, '') || 'design'
    const r = await dialog.showSaveDialog(getWindow()!, {
      defaultPath: join(settings?.exportDir ?? app.getPath('documents'), `${base}.${fmt.ext}`),
      filters: [{ name: fmt.name, extensions: [fmt.ext] }]
    })
    if (r.canceled || !r.filePath) return null
    const out = extname(r.filePath).toLowerCase() === `.${fmt.ext}` ? r.filePath : `${r.filePath}.${fmt.ext}`
    const res = await pool.runJob<{ path: string; notes: string[]; fonts: string[] }>(`export-${randomUUID()}`, 'design.export', {
      project: designDir(req.id), scene: req.scene, format: req.format, out, fontsFolder: req.fontsFolder
    })
    log.info('design', `Exported ${fmt.name}: ${res.path}`, { notes: res.notes, fonts: res.fonts.length })
    await store.updateSettings({ design: { exportDir: join(out, '..'), exportFormat: req.format } })
    return res
  }, log)

  handle(IPC.designOpenFile, async (path?: string | null): Promise<{ id: string; scene: DesignScene } | null> => {
    let src = path ?? null
    if (!src) {
      const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile'], filters: [{ name: 'Offline Toolkit design', extensions: ['otkd'] }] })
      if (r.canceled) return null
      src = r.filePaths[0]
    }
    const id = randomUUID()
    const dir = designDir(id)
    await mkdir(dir, { recursive: true })
    try {
      const res = await pool.interactive.request<{ scene: DesignScene }>('design.open', { path: src, project: dir })
      log.info('design', `Opened design file ${basename(src)}`)
      return { id, scene: res.scene }
    } catch (e) {
      await rm(dir, { recursive: true, force: true }).catch(() => undefined)
      throw e
    }
  }, log)

  handle(IPC.designInstallFonts, async (scene: DesignScene) => {
    const res = await pool.interactive.request<{ installed: string[]; where: string }>('design.installFonts', { scene }, 120_000)
    log.info('design', `Installed ${res.installed.length} font(s) for this user`, { where: res.where })
    return res
  }, log)
}
