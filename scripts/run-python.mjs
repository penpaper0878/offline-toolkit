#!/usr/bin/env node
// Run the worker's Python (worker/.venv) with the worker on PYTHONPATH.
// Example: node scripts/run-python.mjs -m pytest -q worker/tests
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const win = process.platform === 'win32'
const venvPy = join(root, 'worker', '.venv', win ? 'Scripts/python.exe' : 'bin/python')
const py = process.env.OTK_PYTHON ?? (existsSync(venvPy) ? venvPy : null)
if (!py) {
  console.error('worker/.venv is missing. Run: npm run setup:py')
  process.exit(1)
}
const r = spawnSync(py, process.argv.slice(2), {
  stdio: 'inherit',
  cwd: root,
  env: { ...process.env, PYTHONPATH: join(root, 'worker'), PYTHONUTF8: '1' }
})
process.exit(r.status ?? 1)
