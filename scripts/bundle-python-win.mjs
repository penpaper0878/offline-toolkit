#!/usr/bin/env node
/**
 * Build the Python runtime that ships inside the Windows app:
 * build/python-win = official CPython 3.11 embeddable package + the worker's
 * wheels (win_amd64) in Lib/site-packages + FriBiDi for Pillow's text shaping.
 *
 * The embeddable package uses python311._pth instead of PYTHONPATH: it lists
 * the worker folder (resources/worker, two levels up from
 * resources/engines/python) and enables `import site`, so the worker's
 * sitecustomize.py (the network guard) loads at start-up.
 *
 * Needs the internet (python.org + PyPI) once, at build time only.
 * Usage: node scripts/bundle-python-win.mjs
 */
import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'
import { fileURLToPath } from 'node:url'
import { fetchFribidi } from './fetch-fribidi-win.mjs'

const PY_VERSION = '3.11.9' // last 3.11 release with Windows binaries (scripts/fetch_engines.py PYTHON_EMBED)
const SOURCE_ONLY = ['antlr4-python3-runtime==4.9.3'] // needed by omegaconf (rapidocr's configuration)

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
// URL and SHA-256 pinned in scripts/engines.lock.json (written by `fetch_engines.py --relock`); the build fails
// if the file differs.
const pinned = JSON.parse(readFileSync(join(root, 'scripts', 'engines.lock.json'), 'utf-8'))['win-x64']?.python?.files?.[0]
if (!pinned?.sha256 || !pinned.name.includes(PY_VERSION)) throw new Error(`Python ${PY_VERSION} is not pinned in scripts/engines.lock.json`)
const URL = pinned.url
const SHA256 = pinned.sha256
const cache = join(root, 'build', 'cache')
const target = join(root, 'build', 'python-win')
const zip = join(cache, `python-${PY_VERSION}-embed-amd64.zip`)

function run(cmd, args) {
  console.log(`> ${cmd} ${args.join(' ')}`)
  const r = spawnSync(cmd, args, { stdio: 'inherit' })
  if (r.status !== 0) throw new Error(`${cmd} failed (${r.status})`)
}

function dirSize(p) {
  let total = 0
  for (const e of readdirSync(p, { withFileTypes: true })) {
    const f = join(p, e.name)
    total += e.isDirectory() ? dirSize(f) : statSync(f).size
  }
  return total
}

async function main() {
  mkdirSync(cache, { recursive: true })
  if (!existsSync(zip)) {
    console.log(`Downloading ${URL}`)
    const res = await fetch(URL)
    if (!res.ok) throw new Error(`Download failed: ${res.status} ${res.statusText}`)
    await pipeline(Readable.fromWeb(res.body), createWriteStream(zip))
  }
  const digest = createHash('sha256').update(readFileSync(zip)).digest('hex')
  if (digest !== SHA256) {
    rmSync(zip, { force: true })
    throw new Error(`SHA-256 mismatch for ${URL}: ${digest}, the lock says ${SHA256}`)
  }
  console.log(`python-${PY_VERSION}-embed-amd64.zip sha256=${digest} (verified)`)

  rmSync(target, { recursive: true, force: true })
  mkdirSync(target, { recursive: true })
  if (process.platform === 'win32') run('tar', ['-xf', zip, '-C', target]) // bsdtar reads zip
  else run('unzip', ['-q', zip, '-d', target])

  const pth = readdirSync(target).find((f) => f.endsWith('._pth'))
  if (!pth) throw new Error('python*._pth not found in the embeddable package')
  const stdlibZip = readdirSync(target).find((f) => /^python3\d+\.zip$/.test(f))
  writeFileSync(join(target, pth), [
    stdlibZip,
    '.',
    'Lib\\site-packages',
    '..\\..\\worker',
    'import site',
    ''
  ].join('\r\n'))

  // Install win_amd64 wheels for CPython 3.11 into Lib/site-packages (works from any OS).
  const host = process.env.OTK_PYTHON_BOOTSTRAP ?? (process.platform === 'win32' ? 'python' : 'python3')
  // Pure-Python packages published as source only: build their (platform-independent) wheels first so the
  // install below stays binary-only. The versions match worker/requirements.txt.
  const wheels = join(cache, 'wheels')
  rmSync(wheels, { recursive: true, force: true })
  run(host, ['-m', 'pip', 'wheel', '--no-cache-dir', '--disable-pip-version-check', '--no-deps', '--use-pep517', '-w', wheels, ...SOURCE_ONLY])
  run(host, ['-m', 'pip', 'install', '--no-cache-dir', '--disable-pip-version-check',
    '--target', join(target, 'Lib', 'site-packages'),
    '--platform', 'win_amd64', '--python-version', '3.11', '--implementation', 'cp', '--abi', 'cp311',
    '--only-binary=:all:', '--find-links', wheels, '-r', join(root, 'worker', 'requirements.txt')])
  run(host, ['-m', 'pip', 'install', '--no-cache-dir', '--disable-pip-version-check', '--no-deps',
    '--target', join(target, 'Lib', 'site-packages'),
    '--platform', 'win_amd64', '--python-version', '3.11', '--implementation', 'cp', '--abi', 'cp311',
    '--only-binary=:all:', '--find-links', wheels, '-r', join(root, 'worker', 'requirements-nodeps.txt')])

  // FriBiDi next to python.exe, where Windows looks first: Pillow needs it to shape text (see the script).
  await fetchFribidi(target)

  // Drop caches and bundled test suites (not needed at run time).
  const prune = (p) => {
    for (const e of readdirSync(p, { withFileTypes: true })) {
      const f = join(p, e.name)
      if (!e.isDirectory()) continue
      if (e.name === '__pycache__' || e.name === 'tests' || e.name === 'test') rmSync(f, { recursive: true, force: true })
      else prune(f)
    }
  }
  prune(join(target, 'Lib', 'site-packages'))
  writeFileSync(join(target, 'OTK_BUNDLE.txt'), `CPython ${PY_VERSION} embeddable (python.org), sha256 ${digest}\r\nPackages: see Lib\\site-packages\\*.dist-info\r\n`)
  console.log(`Bundled Python ready in ${target} (${(dirSize(target) / 1048576).toFixed(1)} MB)`)
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
