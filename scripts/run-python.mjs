#!/usr/bin/env node
// Run the worker's Python (worker/.venv) with the worker on PYTHONPATH.
// Example: node scripts/run-python.mjs -m pytest -q worker/tests
// worker/ on PYTHONPATH loads the network guard (worker/sitecustomize.py). Scripts that download at build
// time (fetch_fonts.py, fetch_models.py) need the internet: pass --online first to switch the guard off.
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
const args = process.argv.slice(2)
const online = args[0] === '--online'
const r = spawnSync(py, online ? args.slice(1) : args, {
  stdio: 'inherit',
  cwd: root,
  env: { ...process.env, PYTHONPATH: join(root, 'worker'), PYTHONUTF8: '1', ...(online ? { OTK_NETGUARD: '0' } : {}) }
})
process.exit(r.status ?? 1)
