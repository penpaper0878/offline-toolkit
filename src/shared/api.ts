/** The API the preload script exposes as `window.otk`. */

import type { DesignScene, FontFamilyInfo, FontMetrics } from './design'
import type { AnalyzeResult, PaperSize, PassportSpec, PhotoInfo, Place, RenderResult } from './passport'
import type {
  AppInfo, AppSettings, BatchRequest, BatchResult, BatchItem, ConvertRequest, ConvertResult, ConverterCatalog,
  ConverterOptions, ConverterProgress, DesignAccuracy, DesignAnalyzeRequest, DesignExportRequest, DesignExportResult,
  DesignSummary, JobProgress, LogEntry, LogLevel, Preset, PresetState, PreflightResult, PreviewResult, ProbeResult,
  ResizerSettings, SelfTestReport, SettingsState
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
  design: {
    list(): Promise<DesignSummary[]>
    remove(id: string): Promise<void>
    pickImage(): Promise<string | null>
    analyze(req: DesignAnalyzeRequest): Promise<{ id: string; scene: DesignScene }>
    load(id: string): Promise<{ scene: DesignScene }>
    save(id: string, scene: DesignScene): Promise<{ saved: boolean }>
    accuracy(req: { jobId: string; id: string; scene: DesignScene }): Promise<DesignAccuracy>
    assetUrl(id: string, rel: string): Promise<string>
    importImage(id: string, path?: string | null): Promise<{ asset: string; width: number; height: number } | null>
    cutout(req: { jobId: string; id: string; asset: string; mode: 'auto' | 'person' | 'subject' }): Promise<{ asset: string; method: string; coverage: number }>
    fonts(): Promise<FontFamilyInfo[]>
    fontFace(req: { family: string; weight: number; italic: boolean }): Promise<{ url: string; weight: number; italic: boolean; metrics: FontMetrics }>
    exportAs(req: DesignExportRequest): Promise<DesignExportResult | null>
    openFile(path?: string | null): Promise<{ id: string; scene: DesignScene } | null>
    installFonts(scene: DesignScene): Promise<{ installed: string[]; where: string }>
  }
  passport: {
    specs(): Promise<ListState<PassportSpec>>
    saveSpec(spec: PassportSpec): Promise<ListState<PassportSpec>>
    removeSpec(id: string): Promise<ListState<PassportSpec>>
    papers(): Promise<ListState<PaperSize>>
    savePaper(paper: PaperSize): Promise<ListState<PaperSize>>
    removePaper(id: string): Promise<ListState<PaperSize>>
    pick(multi?: boolean): Promise<string[]>
    paste(): Promise<string | null>
    open(path: string): Promise<PhotoInfo>
    analyze(req: Record<string, unknown>): Promise<AnalyzeResult>
    autofit(req: Record<string, unknown>): Promise<{ place: Place }>
    render(req: Record<string, unknown>): Promise<RenderResult>
    auto(req: Record<string, unknown>): Promise<{ adjust: Record<string, number> }>
    exportPhoto(req: Record<string, unknown>): Promise<PassportSaved | null>
    sheet(req: Record<string, unknown>): Promise<PassportSheetResult | null>
    print(req: Record<string, unknown>): Promise<{ printed: boolean; reason?: string }>
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

export interface ListState<T> {
  items: T[]
  defaultIds: string[]
  error: string | null
  file: string
}

export interface PassportSaved {
  path: string
  bytes: number
  px: [number, number]
  dpi: number
  mm: [number, number]
  notes: string[]
  compression?: { status: string; quality: number; message: string }
}

export interface PassportSheetResult {
  layout: { paper: [number, number]; cell: [number, number]; rows: number; cols: number; count: number; fits: boolean
    maxRows: number; maxCols: number; problems: string[]; cells: [number, number][] }
  counts: number[]
  notes: string[]
  image?: { url: string; width: number; height: number }
  path?: string
  bytes?: number
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
  designList: 'design:list',
  designDelete: 'design:delete',
  designPickImage: 'design:pickImage',
  designAnalyze: 'design:analyze',
  designLoad: 'design:load',
  designSave: 'design:save',
  designAccuracy: 'design:accuracy',
  designAssetUrl: 'design:assetUrl',
  designImportImage: 'design:importImage',
  designCutout: 'design:cutout',
  designFonts: 'design:fonts',
  designFontFace: 'design:fontFace',
  designExport: 'design:export',
  designOpenFile: 'design:openFile',
  designInstallFonts: 'design:installFonts',
  passportSpecs: 'passport:specs',
  passportSaveSpec: 'passport:saveSpec',
  passportRemoveSpec: 'passport:removeSpec',
  passportPapers: 'passport:papers',
  passportSavePaper: 'passport:savePaper',
  passportRemovePaper: 'passport:removePaper',
  passportPick: 'passport:pick',
  passportPaste: 'passport:paste',
  passportOpen: 'passport:open',
  passportAnalyze: 'passport:analyze',
  passportAutofit: 'passport:autofit',
  passportRender: 'passport:render',
  passportAuto: 'passport:auto',
  passportExport: 'passport:export',
  passportSheet: 'passport:sheet',
  passportPrint: 'passport:print',
  cspViolation: 'guard:cspViolation'
} as const
