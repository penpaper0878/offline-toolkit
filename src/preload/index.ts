/**
 * Sandboxed preload: exposes a small, typed API as window.otk. No Node APIs
 * reach the page; every call is a named IPC channel handled in src/main/ipc.ts.
 */

import { contextBridge, ipcRenderer, webUtils } from 'electron'
import { IPC, type OtkApi } from '@shared/api'
import type { ConverterProgress, JobProgress, LogEntry } from '@shared/types'

class OtkIpcError extends Error {
  constructor(message: string, public code: string) {
    super(message)
    this.name = 'OtkIpcError'
  }
}

async function call<T>(channel: string, ...args: unknown[]): Promise<T> {
  const r = (await ipcRenderer.invoke(channel, ...args)) as { ok: boolean; value?: T; error?: { message: string; code: string } }
  if (r.ok) return r.value as T
  // Errors lose their class across contextBridge; the code travels in the message prefix.
  throw new OtkIpcError(`${r.error!.code}::${r.error!.message}`, r.error!.code)
}

function subscribe<T>(channel: string, cb: (payload: T) => void): () => void {
  const listener = (_e: unknown, payload: T) => cb(payload)
  ipcRenderer.on(channel, listener)
  return () => ipcRenderer.removeListener(channel, listener)
}

const api: OtkApi = {
  app: { info: () => call(IPC.appInfo) },
  dialogs: {
    openImages: () => call(IPC.openImages),
    openDocuments: () => call(IPC.openDocuments),
    openFolder: () => call(IPC.openFolder),
    chooseDir: (current) => call(IPC.chooseDir, current ?? null)
  },
  files: {
    listImages: (folder, recursive) => call(IPC.listImages, folder, recursive ?? false),
    listDocuments: (folder, recursive) => call(IPC.listDocuments, folder, recursive ?? false),
    pathForFile: (file) => webUtils.getPathForFile(file)
  },
  settings: {
    get: () => call(IPC.settingsGet),
    update: (patch) => call(IPC.settingsUpdate, patch)
  },
  presets: {
    list: () => call(IPC.presetsList),
    save: (p) => call(IPC.presetsSave, p),
    remove: (id) => call(IPC.presetsRemove, id),
    importFile: () => call(IPC.presetsImport),
    exportFile: (ids) => call(IPC.presetsExport, ids)
  },
  image: { probe: (path) => call(IPC.probe, path) },
  resizer: {
    preview: (req) => call(IPC.resizerPreview, req),
    run: (req) => call(IPC.resizerRun, req)
  },
  converter: {
    catalog: () => call(IPC.converterCatalog),
    inspect: (req) => call(IPC.converterInspect, req),
    run: (req) => call(IPC.converterRun, req),
    onProgress: (cb) => subscribe<ConverterProgress>(IPC.converterProgress, cb)
  },
  jobs: {
    cancel: (jobId) => call(IPC.jobsCancel, jobId),
    onProgress: (cb) => subscribe<JobProgress>(IPC.jobsProgress, cb)
  },
  shell: {
    showItem: (p) => call(IPC.showItem, p),
    openPath: (p) => call(IPC.openPath, p)
  },
  log: {
    recent: () => call(IPC.logRecent),
    add: (level, message, data) => call(IPC.logAdd, level, message, data),
    onEntry: (cb) => subscribe<LogEntry>(IPC.logEntry, cb)
  },
  selftest: { offline: () => call(IPC.selftestOffline) }
}

contextBridge.exposeInMainWorld('otk', api)

// The page's Content-Security-Policy stops fetches before they reach the network
// layer; report those too so the offline audit counts every blocked attempt.
document.addEventListener('securitypolicyviolation', (e) => {
  ipcRenderer.send(IPC.cspViolation, { directive: e.effectiveDirective, uri: e.blockedURI })
})
