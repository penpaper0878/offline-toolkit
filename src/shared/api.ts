/** The API the preload script exposes as `window.otk`. */

import type {
  AppInfo, AppSettings, BatchRequest, BatchResult, BatchItem, ConvertRequest, ConvertResult, ConverterCatalog,
  ConverterOptions, ConverterProgress, JobProgress, LogEntry, LogLevel, Preset, PresetState, PreflightResult,
  PreviewResult, ProbeResult, ResizerSettings, SelfTestReport, SettingsState
} from './types'

export type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K] }

export interface OtkApi {
  app: {
    info(): Promise<AppInfo>
  }
  dialogs: {
    openImages(): Promise<string[]>
    openDocuments(): Promise<string[]>
    openFolder(): Promise<string | null>
    chooseDir(current?: string | null): Promise<string | null>
  }
  files: {
    listImages(folder: string, recursive?: boolean): Promise<string[]>
    listDocuments(folder: string, recursive?: boolean): Promise<string[]>
    pathForFile(file: File): string
  }
  settings: {
    get(): Promise<SettingsState>
    update(patch: DeepPartial<AppSettings>): Promise<SettingsState>
  }
  presets: {
    list(): Promise<PresetState>
    save(preset: Preset): Promise<PresetState>
    remove(id: string): Promise<PresetState>
    importFile(): Promise<{ state: PresetState; imported: number } | null>
    exportFile(ids: string[]): Promise<string | null>
  }
  image: {
    probe(path: string): Promise<ProbeResult>
  }
  resizer: {
    preview(req: { jobId: string; item: BatchItem; settings: ResizerSettings }): Promise<PreviewResult>
    run(req: BatchRequest): Promise<BatchResult>
  }
  converter: {
    catalog(): Promise<ConverterCatalog>
    inspect(req: { paths: string[]; target: string; mode: string; options: ConverterOptions; passwords?: Record<string, string> }): Promise<{ files: PreflightResult[] }>
    run(req: ConvertRequest): Promise<ConvertResult>
    onProgress(cb: (p: ConverterProgress) => void): () => void
  }
  jobs: {
    cancel(jobId: string): Promise<void>
    onProgress(cb: (p: JobProgress) => void): () => void
  }
  shell: {
    showItem(path: string): Promise<void>
    openPath(path: string): Promise<void>
  }
  log: {
    recent(): Promise<LogEntry[]>
    add(level: LogLevel, message: string, data?: unknown): Promise<void>
    onEntry(cb: (e: LogEntry) => void): () => void
  }
  selftest: {
    offline(): Promise<SelfTestReport>
  }
}

/** Error shape thrown across IPC: `message` is safe to show to the user. */
export interface OtkError {
  message: string
  code: string
}

export const IPC = {
  appInfo: 'app:info',
  openImages: 'dialog:openImages',
  openDocuments: 'dialog:openDocuments',
  listDocuments: 'files:listDocuments',
  converterCatalog: 'converter:catalog',
  converterInspect: 'converter:inspect',
  converterRun: 'converter:run',
  converterProgress: 'converter:progress',
  openFolder: 'dialog:openFolder',
  chooseDir: 'dialog:chooseDir',
  listImages: 'files:listImages',
  settingsGet: 'settings:get',
  settingsUpdate: 'settings:update',
  presetsList: 'presets:list',
  presetsSave: 'presets:save',
  presetsRemove: 'presets:remove',
  presetsImport: 'presets:import',
  presetsExport: 'presets:export',
  probe: 'image:probe',
  resizerPreview: 'resizer:preview',
  resizerRun: 'resizer:run',
  jobsCancel: 'jobs:cancel',
  jobsProgress: 'jobs:progress',
  showItem: 'shell:showItem',
  openPath: 'shell:openPath',
  logRecent: 'log:recent',
  logAdd: 'log:add',
  logEntry: 'log:entry',
  selftestOffline: 'selftest:offline',
  cspViolation: 'guard:cspViolation'
} as const
