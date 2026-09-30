import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { _electron as electron, type ElectronApplication, type Page } from '@playwright/test'

export const ROOT = resolve(__dirname, '..', '..')

export function python(): string {
  const win = process.platform === 'win32'
  const venv = join(ROOT, 'worker', '.venv', win ? 'Scripts/python.exe' : 'bin/python')
  return process.env.OTK_PYTHON ?? (existsSync(venv) ? venv : win ? 'python' : 'python3')
}

/** Run Python with the worker on the path and return parsed JSON printed by the snippet. */
export function py<T = unknown>(code: string, ...args: string[]): T {
  const out = execFileSync(python(), ['-c', code, ...args], {
    env: { ...process.env, PYTHONPATH: join(ROOT, 'worker'), PYTHONUTF8: '1' },
    encoding: 'utf-8'
  })
  return JSON.parse(out.trim().split('\n').pop()!) as T
}

/** A deterministic photo-like test image. */
export function makePhoto(path: string, w = 1200, h = 900): void {
  py(`import sys, json
sys.path.insert(0, ${JSON.stringify(join(ROOT, 'worker', 'tests'))})
from conftest import photo_array
from PIL import Image
Image.fromarray(photo_array(int(sys.argv[2]), int(sys.argv[3]))).save(sys.argv[1], quality=95)
print(json.dumps(True))`, path, String(w), String(h))
}

export function readback(path: string): { width: number; height: number; jfifDensity: number[] | null; exifDpi: number[] | null; bytes: number; format: string } {
  return py(`import sys, json
from otk_worker.common.metadata import readback
print(json.dumps(readback(open(sys.argv[1], 'rb').read())))`, path)
}

export function tempDir(prefix: string): string {
  return mkdtempSync(join(tmpdir(), `otk-${prefix}-`))
}

export async function launch(dataDir: string): Promise<{ app: ElectronApplication; page: Page }> {
  const args = [ROOT]
  if (process.platform === 'linux' && process.getuid?.() === 0) args.push('--no-sandbox')
  const app = await electron.launch({
    args,
    env: { ...process.env, OTK_DATA_DIR: dataDir, OTK_PYTHON: python() } as Record<string, string>
  })
  const page = await app.firstWindow()
  await page.waitForSelector('[data-testid="nav-resizer"]')
  return { app, page }
}

/** Replace native dialogs in the main process (Playwright cannot click OS dialogs). */
export async function stubDialogs(app: ElectronApplication, files: string[], dir: string): Promise<void> {
  await app.evaluate(({ dialog }, { files, dir }) => {
    dialog.showOpenDialog = (async (_w: unknown, opts?: { properties?: string[] }) => {
      const props = (opts ?? (_w as { properties?: string[] }))?.properties ?? []
      return props.includes('openDirectory') ? { canceled: false, filePaths: [dir] } : { canceled: false, filePaths: files }
    }) as typeof dialog.showOpenDialog
  }, { files, dir })
}
