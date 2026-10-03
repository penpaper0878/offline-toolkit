#!/usr/bin/env node
// Create worker/.venv with Python 3.11+ and install the worker's dependencies.
// Usage: npm run setup:py   (set OTK_PYTHON_BOOTSTRAP to choose the interpreter)
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const win = process.platform === 'win32'
const venv = join(root, 'worker', '.venv')
const venvPy = join(venv, win ? 'Scripts/python.exe' : 'bin/python')

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts })
  if (r.status !== 0) {
    console.error(`\nFailed: ${cmd} ${args.join(' ')}`)
    process.exit(r.status ?? 1)
  }
}

function version(cmd, pre) {
  const r = spawnSync(cmd, [...pre, '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], { encoding: 'utf-8' })
  if (r.status !== 0) return null
  const [maj, min] = r.stdout.trim().split('.').map(Number)
  return maj === 3 && min >= 11 ? `${maj}.${min}` : null
}

if (!existsSync(venvPy)) {
  const candidates = process.env.OTK_PYTHON_BOOTSTRAP
    ? [[process.env.OTK_PYTHON_BOOTSTRAP, []]]
    : win ? [['py', ['-3.11']], ['py', ['-3']], ['python', []]] : [['python3.11', []], ['python3', []], ['python', []]]
  const found = candidates.find(([cmd, pre]) => version(cmd, pre))
  if (!found) {
    console.error('Python 3.11 or newer was not found. Install it from python.org, or set OTK_PYTHON_BOOTSTRAP.')
    process.exit(1)
  }
  console.log(`Creating worker/.venv with ${found[0]} ${found[1].join(' ')} (Python ${version(...found)})`)
  run(found[0], [...found[1], '-m', 'venv', venv])
}
run(venvPy, ['-m', 'pip', 'install', '--upgrade', 'pip'])
run(venvPy, ['-m', 'pip', 'install', '-r', join(root, 'worker', 'requirements.txt'), '-r', join(root, 'worker', 'requirements-dev.txt')])
run(venvPy, ['-m', 'pip', 'install', '--no-deps', '-r', join(root, 'worker', 'requirements-nodeps.txt')])
console.log('\nPython worker environment is ready:', venvPy)
