/**
 * Module 4 (passport photos) in the main process: the editable spec and paper lists, dialogs, the clipboard,
 * the worker calls, and printing.
 *
 * Every passport call goes to the interactive worker: an opened photo lives in that worker's memory (the
 * renderer names it by its id), and a long conversion on the jobs worker never holds up the editor.
 * Preview images are written to <cache>/previews/passport and handed to the renderer as otk:// URLs.
 */

import { randomUUID } from 'node:crypto'
import { mkdir, writeFile } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'
import { BrowserWindow, clipboard, dialog, ipcMain } from 'electron'
import { IPC } from '@shared/api'
import type { PaperSize, PassportSpec } from '@shared/passport'
import { ListFile } from './listfile'
import type { EventLog } from './log'
import { previewDir } from './paths'
import { fileUrl } from './protocol'
import type { Store } from './store'
import { WorkerError, type WorkerPool } from './worker'

const IMAGE_FILTER = { name: 'Images', extensions: ['jpg', 'jpeg', 'jpe', 'jfif', 'png', 'webp', 'bmp', 'tif', 'tiff', 'heic', 'heif', 'hif'] }
const PHOTO_FORMATS: Record<string, { name: string; ext: string }> = {
  jpeg: { name: 'JPEG image', ext: 'jpg' }, png: { name: 'PNG image', ext: 'png' }, pdf: { name: 'PDF', ext: 'pdf' }
}

type Result<T> = { ok: true; value: T } | { ok: false; error: { message: string; code: string } }

interface Deps {
  store: Store
  pool: WorkerPool
  log: EventLog
  resourcesDir: string
  dataDir: string
  getWindow: () => BrowserWindow | null
}

const folder = (): string => join(previewDir(), 'passport')

function handle<A extends unknown[], T>(channel: string, fn: (...args: A) => Promise<T> | T, log: EventLog): void {
  ipcMain.handle(channel, async (_e, ...args: unknown[]): Promise<Result<T>> => {
    try {
      return { ok: true, value: await fn(...(args as A)) }
    } catch (e) {
      const error = e instanceof WorkerError ? { message: e.message, code: e.code } : { message: (e as Error)?.message ?? String(e), code: 'internal' }
      if (error.code !== 'cancelled') log.warn('passport', `${channel}: ${error.message}`, { code: error.code })
      return { ok: false, error }
    }
  })
}

/** Worker results carry file paths; preview files also get an otk:// URL for the renderer. The path stays:
 * a pasted photo lives in the same folder and is still a file the wizard works with. */
function urls<T>(v: T): T {
  if (Array.isArray(v)) return v.map(urls) as T
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = {}
    for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
      o[k] = urls(x)
      if (k === 'path' && typeof x === 'string' && x.startsWith(folder())) o.url = fileUrl(x)
    }
    return o as T
  }
  return v
}

export async function registerPassportIpc({ store, pool, log, resourcesDir, dataDir, getWindow }: Deps): Promise<void> {
  const specs = new ListFile<PassportSpec>('passport-specs', 'specs', resourcesDir, dataDir, store.schema('passport-specs.schema.json'), log)
  const papers = new ListFile<PaperSize>('paper-sizes', 'papers', resourcesDir, dataDir, store.schema('paper-sizes.schema.json'), log)
  await specs.init()
  await papers.init()
  const call = async <T>(method: string, params: Record<string, unknown>, timeout = 0): Promise<T> => {
    await mkdir(folder(), { recursive: true })
    return urls(await pool.interactive.request<T>(method, { ...params, previewDir: folder() }, timeout))
  }

  handle(IPC.passportSpecs, () => specs.state(), log)
  handle(IPC.passportSaveSpec, (s: PassportSpec) => specs.save(s), log)
  handle(IPC.passportRemoveSpec, (id: string) => specs.remove(id), log)
  handle(IPC.passportPapers, () => papers.state(), log)
  handle(IPC.passportSavePaper, (p: PaperSize) => papers.save(p), log)
  handle(IPC.passportRemovePaper, (id: string) => papers.remove(id), log)

  handle(IPC.passportPick, async (multi?: boolean): Promise<string[]> => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: multi ? ['openFile', 'multiSelections'] : ['openFile'], filters: [IMAGE_FILTER] })
    return r.canceled ? [] : r.filePaths
  }, log)

  handle(IPC.passportPaste, async (): Promise<string | null> => {
    for (const item of await clipboard.read()) {
      const type = item.types.find((t) => /^image\/(png|jpeg|webp|bmp|gif)$/i.test(t))
      if (!type) continue
      const blob = (await item.getType(type)) as Blob
      await mkdir(folder(), { recursive: true })
      const ext = type.split('/')[1].toLowerCase().replace('jpeg', 'jpg')
      const path = join(folder(), `pasted-${randomUUID().slice(0, 8)}.${ext}`)
      await writeFile(path, Buffer.from(await blob.arrayBuffer()))
      log.info('passport', 'Photo pasted from the clipboard', { type, bytes: blob.size })
      return path
    }
    return null
  }, log)

  handle(IPC.passportOpen, (path: string) => call('passport.open', { path }), log)
  handle(IPC.passportAnalyze, (req: Record<string, unknown>) => call('passport.analyze', req), log)
  handle(IPC.passportAutofit, (req: Record<string, unknown>) => call('passport.autofit', req), log)
  handle(IPC.passportRender, (req: Record<string, unknown>) => call('passport.render', req), log)
  handle(IPC.passportAuto, (req: Record<string, unknown>) => call('passport.auto', req), log)

  handle(IPC.passportExport, async (req: Record<string, unknown> & { format: string; name?: string }) => {
    const f = PHOTO_FORMATS[req.format]
    if (!f) throw new WorkerError('Unknown format.', 'input')
    const dir = store.getSettings().passport?.export.dir ?? undefined
    const r = await dialog.showSaveDialog(getWindow()!, {
      defaultPath: join(dir ?? '', `${req.name ?? 'passport-photo'}.${f.ext}`), filters: [{ name: f.name, extensions: [f.ext] }]
    })
    if (r.canceled || !r.filePath) return null
    const res = await call<Record<string, unknown>>('passport.export', { ...req, path: r.filePath }, 300_000)
    await store.updateSettings({ passport: { export: { dir: dirname(r.filePath) } } })
    log.info('passport', `Saved ${basename(r.filePath)}`, { format: req.format, bytes: res.bytes })
    return res
  }, log)

  handle(IPC.passportSheet, async (req: Record<string, unknown> & { format: string; name?: string }) => {
    if (req.format === 'preview') return call('passport.sheet', req, 120_000)
    const f = PHOTO_FORMATS[req.format]
    if (!f) throw new WorkerError('Unknown format.', 'input')
    const dir = store.getSettings().passport?.export.dir ?? undefined
    const r = await dialog.showSaveDialog(getWindow()!, {
      defaultPath: join(dir ?? '', `${req.name ?? 'passport-sheet'}.${f.ext}`), filters: [{ name: f.name, extensions: [f.ext] }]
    })
    if (r.canceled || !r.filePath) return null
    const res = await call<Record<string, unknown>>('passport.sheet', { ...req, path: r.filePath }, 300_000)
    await store.updateSettings({ passport: { export: { dir: dirname(r.filePath) } } })
    log.info('passport', `Saved print sheet ${basename(r.filePath)}`, { format: req.format, bytes: res.bytes })
    return res
  }, log)

  handle(IPC.passportPrint, async (req: Record<string, unknown>): Promise<{ printed: boolean; reason?: string }> => {
    const res = await pool.interactive.request<{ html: string; images: string[]; layout: { paper: [number, number] } }>(
      'passport.sheet', { ...req, format: 'html', previewDir: folder() }, 120_000)
    let html = res.html
    res.images.forEach((p, i) => { html = html.split(`{{IMG${i}}}`).join(fileUrl(p)) })
    const page = join(folder(), `print-${randomUUID().slice(0, 8)}.html`)
    await writeFile(page, html, 'utf-8')
    const win = new BrowserWindow({ show: false, webPreferences: { sandbox: true, contextIsolation: true, javascript: false } })
    try {
      await win.loadURL(fileUrl(page))
      const [w, h] = res.layout.paper
      return await new Promise((resolve) => {
        win.webContents.print({
          silent: false, printBackground: true, margins: { marginType: 'none' }, scaleFactor: 100,
          pageSize: { width: Math.round(w * 1000), height: Math.round(h * 1000) }
        }, (printed, reason) => resolve({ printed, reason: printed ? undefined : reason }))
      })
    } finally {
      win.destroy()
    }
  }, log)
}

