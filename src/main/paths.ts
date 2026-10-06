import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { app } from 'electron'

/** Where things live in development and in a packaged build. */

export const isPackaged = app.isPackaged

function projectRoot(): string {
  // electron-vite runs main from out/main; app.getAppPath() is the folder holding package.json.
  return app.getAppPath()
}

export function resourcesDir(): string {
  return process.env.OTK_RESOURCES ?? (isPackaged ? join(process.resourcesPath, 'resources') : join(projectRoot(), 'resources'))
}

export function workerDir(): string {
  return process.env.OTK_WORKER_DIR ?? (isPackaged ? join(process.resourcesPath, 'worker') : join(projectRoot(), 'worker'))
}

export function rendererDir(): string {
  return join(projectRoot(), 'out', 'renderer')
}

export function pythonExecutable(): string {
  if (process.env.OTK_PYTHON) return process.env.OTK_PYTHON
  const win = process.platform === 'win32'
  const candidates = isPackaged
    ? [join(process.resourcesPath, 'engines', 'python', win ? 'python.exe' : join('bin', 'python3'))]
    : [join(workerDir(), '.venv', win ? join('Scripts', 'python.exe') : join('bin', 'python'))]
  for (const c of candidates) if (existsSync(c)) return c
  return win ? 'python' : 'python3'
}

/** Portable mode: a `portable.txt` next to the executable keeps all data in ./data. */
export function isPortable(): boolean {
  return isPackaged && existsSync(join(dirname(process.execPath), 'portable.txt'))
}

export function dataDir(): string {
  if (process.env.OTK_DATA_DIR) return process.env.OTK_DATA_DIR
  if (isPortable()) return join(dirname(process.execPath), 'data')
  return app.getPath('userData')
}

/** Bundled conversion engines (LibreOffice, Pandoc, Ghostscript, Tesseract, Java + veraPDF, resvg). */
export function enginesDir(): string {
  if (process.env.OTK_ENGINES) return process.env.OTK_ENGINES
  if (isPackaged) return join(process.resourcesPath, 'engines')
  const arch = process.arch === 'arm64' ? 'arm64' : 'x64'
  const os = process.platform === 'win32' ? 'win' : process.platform === 'darwin' ? 'mac' : 'linux'
  return join(projectRoot(), 'engines', `${os}-${arch}`)
}

/** Bundled fonts and models for the design module (scripts/fetch_fonts.py, scripts/fetch_models.py). */
export function fontsDir(): string {
  return process.env.OTK_FONTS ?? (isPackaged ? join(process.resourcesPath, 'fonts') : join(projectRoot(), 'fonts'))
}

export function modelsDir(): string {
  return process.env.OTK_MODELS ?? (isPackaged ? join(process.resourcesPath, 'models') : join(projectRoot(), 'models'))
}

export const logsDir = (): string => join(dataDir(), 'logs')
export const cacheDir = (): string => join(dataDir(), 'cache')
export const previewDir = (): string => join(cacheDir(), 'previews')
export const designsDir = (): string => join(dataDir(), 'designs')
export const jobsDir = (): string => join(cacheDir(), 'jobs')
