/** Types shared by the main process, preload and renderer. Mirrors the worker's JSON. */

import type { Axis, Unit } from './units'

export type FitMode = 'crop' | 'pad' | 'stretch'
export type OutputFormat = 'jpeg' | 'png' | 'webp'
export type SizeMode = 'exactPixels' | 'exactPhysical'

export interface SizeRange {
  min?: number | null
  max?: number | null
  unit: 'KB' | 'MB'
}

/** resources/schemas/resizer-settings.schema.json */
export interface ResizerSettings {
  width: number
  height: number
  unit: Unit
  dpi: number
  sizeMode?: SizeMode
  fitDpi?: boolean
  lockAspect?: boolean
  fit: FitMode
  padColor?: string
  format: OutputFormat
  quality?: number
  sizeRange?: SizeRange | null
  subsampling?: 'auto' | '4:4:4' | '4:2:0'
  stripMetadata?: boolean
  allowPadding?: boolean
  allowQuantize?: boolean
  webpLossless?: 'auto' | 'never'
  saveOutOfRange?: boolean
  naming?: string
}

export interface Preset {
  id: string
  name: string
  description?: string
  settings: ResizerSettings
}

export interface PresetState {
  presets: Preset[]
  defaultIds: string[]
  error: string | null
}

export type Theme = 'system' | 'light' | 'dark'

/** resources/schemas/settings.schema.json */
export interface AppSettings {
  version: 1
  theme: Theme
  sizeUnitBase: 1000 | 1024
  workers: 'auto' | number
  resizer: {
    settings: ResizerSettings
    outputDir: string | null
    zip: boolean
    lastPresetId: string | null
  }
  logging: { hashPaths: boolean }
}

export interface SettingsState {
  settings: AppSettings
  error: string | null
  paths: { data: string; logs: string; settingsFile: string; presetsFile: string }
}

export interface Crop {
  x: number
  y: number
  w: number
  h: number
}

export interface ProbeResult {
  path: string
  format: string
  fileSize: number
  width: number
  height: number
  orientation: number
  dpi: [number, number] | null
  mode: string
  hasAlpha: boolean
  iccName: string | null
  colourConverted: boolean
  hasExif: boolean
  frames: number
  warnings: string[]
  preview: { path: string; url: string; width: number; height: number; scale: number }
}

export type ResultStatus = 'ok' | 'ok_padded' | 'below_min' | 'above_max' | 'no_target' | 'error' | 'cancelled'

export interface Suggestion {
  kind: 'smallest' | 'dimensions' | 'format'
  text: string
  bytes: number
  width?: number
  height?: number
  format?: OutputFormat
}

export interface ItemResult {
  status: ResultStatus
  message: string
  path?: string
  code?: string
  source?: ProbeResult
  size?: { width: Axis; height: Axis }
  fit?: {
    mode: FitMode
    target: [number, number]
    crop: Crop | null
    inner: [number, number]
    offset: [number, number]
    scale: [number, number]
    upscale: number
    distortion: number
  }
  encoder?: Record<string, unknown>
  paddingBytes?: number
  ssim?: number | null
  attempts?: number
  range?: { min: number | null; max: number | null; base: number }
  output?: {
    format: OutputFormat
    bytes: number
    width: number
    height: number
    dpiStored: { jfif?: number[]; exif?: number[]; pngPpm?: number[]; pngDpi?: number[] }
    readback: Record<string, unknown>
  }
  warnings?: string[]
  suggestions?: Suggestion[]
  outputPath?: string | null
}

export interface PreviewResult extends ItemResult {
  previewPath: string
  previewUrl: string
}

export interface BatchItem {
  path: string
  crop?: Crop | null
}

export interface BatchRequest {
  jobId: string
  items: BatchItem[]
  settings: ResizerSettings
  outputDir: string
  zip: boolean
}

export interface BatchResult {
  results: ItemResult[]
  zipPath: string | null
  counts: Partial<Record<ResultStatus, number>>
  outputDir: string
}

export interface JobProgress {
  jobId: string
  index: number
  total: number
  fraction: number
  message: string
}

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogEntry {
  ts: string
  level: LogLevel
  source: string
  message: string
  data?: unknown
}

export interface SelfTestCheck {
  name: string
  passed: boolean
  detail: string
}

export interface SelfTestReport {
  passed: boolean
  checks: SelfTestCheck[]
  violationsBefore: number
  violationsAfter: number
}

export interface AppInfo {
  version: string
  electron: string
  chrome: string
  node: string
  platform: string
  worker: Record<string, unknown> | null
  workerError: string | null
  pythonPath: string
  dataDir: string
  portable: boolean
}
