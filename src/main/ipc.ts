import { readdir, rm } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { app, type BrowserWindow, dialog, ipcMain, nativeTheme, shell } from 'electron'
import { IPC } from '@shared/api'
import type { DeepPartial } from '@shared/api'
import type {
  AppInfo, AppSettings, BatchRequest, BatchResult, BatchItem, ConvertRequest, ConvertResult, ConverterCatalog, LogLevel,
  Preset, PreflightResult, PreviewResult, ProbeResult, ResizerSettings
} from '@shared/types'
import { handle } from './ipc-util'
import type { EventLog } from './log'
import { recordViolation } from './offline-guard'
import { dataDir, isPortable, jobsDir, previewDir, pythonExecutable } from './paths'
import { fileUrl, forgetFile } from './protocol'
import { runFullSelfTest, runOfflineSelfTest } from './selftest'
import type { Store } from './store'
import type { WorkerPool } from './worker'

const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.webp', '.bmp', '.dib', '.tif', '.tiff', '.heic', '.heif', '.hif'])
const IMAGE_FILTER = { name: 'Images', extensions: [...IMAGE_EXTS].map((e) => e.slice(1)) }

interface Deps {
  store: Store
  pool: WorkerPool
  log: EventLog
  getWindow: () => BrowserWindow | null
}

const DOC_EXTS = new Set(['.pdf', '.docx', '.docm', '.dotx', '.doc', '.dot', '.xlsx', '.xlsm', '.xltx', '.xls', '.xlt',
  '.pptx', '.pptm', '.potx', '.ppsx', '.ppt', '.pps', '.pot', '.html', '.htm', '.xhtml', '.txt', '.text', '.epub', '.png',
  '.jpg', '.jpeg', '.jpe', '.jfif', '.svg', '.svgz'])
const DOC_FILTER = { name: 'Documents and images', extensions: [...DOC_EXTS].map((e) => e.slice(1)) }

async function listFiles(folder: string, exts: Set<string>, recursive: boolean, depth = 0): Promise<string[]> {
  const out: string[] = []
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    const p = join(folder, entry.name)
    if (entry.isFile() && exts.has(extname(entry.name).toLowerCase())) out.push(p)
    else if (recursive && entry.isDirectory() && depth < 8 && !entry.name.startsWith('.')) out.push(...await listFiles(p, exts, recursive, depth + 1))
  }
  return out.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
}

const listImages = (folder: string, recursive: boolean): Promise<string[]> => listFiles(folder, IMAGE_EXTS, recursive)

export function registerIpc({ store, pool, log, getWindow }: Deps): void {
  const previews = new Map<string, string>() // source path -> last preview file

  const converterJobs = new Set<string>()
  pool.jobs.on('notification', (method: string, params: unknown) => {
    if (method !== 'job.progress') return
    const jobId = (params as { jobId?: string })?.jobId
    getWindow()?.webContents.send(jobId && converterJobs.has(jobId) ? IPC.converterProgress : IPC.jobsProgress, params)
  })

  handle(IPC.appInfo, async (): Promise<AppInfo> => {
    let worker: Record<string, unknown> | null = null
    let workerError: string | null = null
    try {
      worker = await pool.interactive.request<Record<string, unknown>>('ping', {}, 30_000)
    } catch (e) {
      workerError = (e as Error).message
    }
    return {
      version: app.getVersion(), electron: process.versions.electron, chrome: process.versions.chrome,
      node: process.versions.node, platform: `${process.platform} ${process.arch}`, worker, workerError, pythonPath: pythonExecutable(),
      dataDir: dataDir(), portable: isPortable()
    }
  }, log)

  handle(IPC.openImages, async () => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile', 'multiSelections'], filters: [IMAGE_FILTER] })
    return r.canceled ? [] : r.filePaths
  }, log)
  handle(IPC.openAny, async () => {
    const r = await dialog.showOpenDialog(getWindow()!, {
      properties: ['openFile', 'multiSelections'],
      filters: [{ name: 'Pictures, documents and designs', extensions: [...new Set([...IMAGE_FILTER.extensions, ...DOC_FILTER.extensions, 'otkd'])] },
        IMAGE_FILTER, DOC_FILTER, { name: 'Design projects', extensions: ['otkd'] }]
    })
    return r.canceled ? [] : r.filePaths
  }, log)
  handle(IPC.openFolder, async () => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openDirectory'] })
    return r.canceled ? null : r.filePaths[0]
  }, log)
  handle(IPC.chooseDir, async (current?: string | null) => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openDirectory', 'createDirectory'], defaultPath: current ?? undefined })
    return r.canceled ? null : r.filePaths[0]
  }, log)
  handle(IPC.listImages, (folder: string, recursive?: boolean) => listImages(folder, recursive ?? false), log)
  handle(IPC.openDocuments, async () => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile', 'multiSelections'], filters: [DOC_FILTER, { name: 'All files', extensions: ['*'] }] })
    return r.canceled ? [] : r.filePaths
  }, log)
  handle(IPC.listDocuments, (folder: string, recursive?: boolean) => listFiles(folder, DOC_EXTS, recursive ?? false), log)

  handle(IPC.converterCatalog, () => pool.interactive.request<ConverterCatalog>('converter.catalog', {}, 120_000), log)
  handle(IPC.converterInspect, (req: { paths: string[]; target: string; mode: string; options: unknown; passwords?: Record<string, string> }) =>
    pool.interactive.request<{ files: PreflightResult[] }>('converter.inspect', req as unknown as Record<string, unknown>), log)
  handle(IPC.converterRun, async (req: ConvertRequest): Promise<ConvertResult> => {
    if (!req || typeof req.target !== 'string' || !Array.isArray(req.files) || typeof req.outputDir !== 'string') {
      throw new Error('Invalid conversion request.')
    }
    log.info('converter', `Conversion started: ${req.files.length} file(s) → ${req.target.toUpperCase()} (${req.options.mode})`,
      { jobId: req.jobId, outputDir: req.outputDir })
    const started = Date.now()
    converterJobs.add(req.jobId)
    try {
      // Passwords go to the worker only; they are never logged or saved.
      const res = await pool.runJob<ConvertResult>(req.jobId, 'converter.run', {
        files: req.files, target: req.target, options: req.options, outputDir: req.outputDir, merge: req.merge,
        mergeName: req.mergeName, jobsDir: jobsDir()
      })
      const counts = Object.entries(res.counts).map(([k, v]) => `${v} ${k}`).join(', ')
      log.info('converter', `Conversion finished in ${((Date.now() - started) / 1000).toFixed(1)} s: ${counts}`, { jobId: req.jobId })
      for (const r of res.results) {
        if (r.status === 'failed') log.warn('converter', `${r.source}: ${r.message}`, { code: r.code })
        else if (r.status === 'done') log.info('converter', `${r.source} → ${r.output} (${r.verdict ?? 'not verified'})`)
      }
      return res
    } finally {
      converterJobs.delete(req.jobId)
    }
  }, log)

  handle(IPC.settingsGet, () => store.settingsState(), log)
  handle(IPC.settingsUpdate, async (patch: DeepPartial<AppSettings>) => {
    const state = await store.updateSettings(patch)
    log.hashPaths = state.settings.logging.hashPaths
    nativeTheme.themeSource = state.settings.theme
    return state
  }, log)

  handle(IPC.presetsList, () => store.presetState(), log)
  handle(IPC.presetsSave, (p: Preset) => store.savePreset(p), log)
  handle(IPC.presetsRemove, (id: string) => store.removePreset(id), log)
  handle(IPC.presetsImport, async () => {
    const r = await dialog.showOpenDialog(getWindow()!, { properties: ['openFile'], filters: [{ name: 'Presets', extensions: ['json'] }] })
    if (r.canceled) return null
    const out = await store.importPresets(r.filePaths[0])
    log.info('presets', `Imported ${out.imported} preset(s)`, { file: r.filePaths[0] })
    return out
  }, log)
  handle(IPC.presetsExport, async (ids: string[]) => {
    const r = await dialog.showSaveDialog(getWindow()!, { defaultPath: 'resizer-presets.json', filters: [{ name: 'Presets', extensions: ['json'] }] })
    if (r.canceled || !r.filePath) return null
    await store.exportPresets(r.filePath, ids)
    log.info('presets', `Exported ${ids.length || 'all'} preset(s)`, { file: r.filePath })
    return r.filePath
  }, log)

  handle(IPC.probe, async (path: string): Promise<ProbeResult> => {
    const info = await pool.interactive.request<ProbeResult>('image.probe', { path, previewDir: previewDir(), maxSide: 2048 })
    info.preview.url = fileUrl(info.preview.path)
    return info
  }, log)

  handle(IPC.resizerPreview, async (req: { jobId: string; item: BatchItem; settings: ResizerSettings }): Promise<PreviewResult> => {
    const res = await pool.interactive.request<PreviewResult>('resizer.preview', {
      jobId: req.jobId, item: req.item, settings: req.settings, previewDir: previewDir(),
      sizeBase: store.getSettings().sizeUnitBase
    })
    const old = previews.get(req.item.path)
    if (old) {
      forgetFile(old)
      rm(old, { force: true }).catch(() => undefined)
    }
    previews.set(req.item.path, res.previewPath)
    res.previewUrl = fileUrl(res.previewPath)
    return res
  }, log)

  handle(IPC.resizerRun, async (req: BatchRequest): Promise<BatchResult> => {
    log.info('resizer', `Batch started: ${req.items.length} image(s) → ${req.outputDir}`, { jobId: req.jobId })
    const started = Date.now()
    const res = await pool.runJob<BatchResult>(req.jobId, 'resizer.run', {
      items: req.items, settings: req.settings, outputDir: req.outputDir, zip: req.zip,
      sizeBase: store.getSettings().sizeUnitBase
    })
    const counts = Object.entries(res.counts).map(([k, v]) => `${v} ${k}`).join(', ')
    log.info('resizer', `Batch finished in ${((Date.now() - started) / 1000).toFixed(1)} s: ${counts}`, { jobId: req.jobId, zip: res.zipPath })
    for (const r of res.results) {
      if (r.status === 'error') log.warn('resizer', `${r.path}: ${r.message}`)
    }
    return res
  }, log)

  handle(IPC.jobsCancel, async (jobId: string) => {
    await pool.cancel(jobId)
    log.info('jobs', `Cancel requested for ${jobId}`)
  }, log)

  handle(IPC.showItem, async (path: string) => shell.showItemInFolder(path), log)
  handle(IPC.openPath, async (path: string) => {
    const err = await shell.openPath(path)
    if (err) throw new Error(err)
  }, log)

  handle(IPC.logRecent, () => log.recent(), log)
  handle(IPC.logAdd, (level: LogLevel, message: string, data?: unknown) => {
    log.add(level, 'ui', message, data)
  }, log)
  log.onEntry((e) => getWindow()?.webContents.send(IPC.logEntry, e))

  ipcMain.on(IPC.cspViolation, (_e, v: { directive?: string; uri?: string }) => {
    recordViolation('chromium', `CSP ${String(v?.directive ?? '?')} blocked ${String(v?.uri ?? '?')}`)
  })

  handle(IPC.selftestFull, async (jobId: string) => {
    if (typeof jobId !== 'string' || !/^[\w-]{1,80}$/.test(jobId)) throw new Error('Invalid job id.')
    log.info('selftest', 'Full self-test started')
    const report = await runFullSelfTest(pool, getWindow(), jobId)
    const failed = [...report.network.checks, ...report.modules, report.quiet].filter((c) => !c.passed).map((c) => c.name)
    log.add(report.passed ? 'info' : 'error', 'selftest',
      report.passed ? `Full self-test passed in ${report.seconds} s` : `Full self-test FAILED: ${failed.join('; ')}`, report)
    return report
  }, log)

  handle(IPC.selftestOffline, async () => {
    const report = await runOfflineSelfTest(pool, getWindow())
    log.add(report.passed ? 'info' : 'error', 'selftest', `Offline self-test ${report.passed ? 'passed' : 'FAILED'}`, report)
    return report
  }, log)
}
