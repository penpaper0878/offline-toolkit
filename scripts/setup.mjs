#!/usr/bin/env node
/**
 * One command from a fresh clone to a working development copy:
 *
 *   npm run setup                  # everything this platform can bundle (about 1.5 GB of downloads on Windows)
 *   npm run setup -- --no-engines  # skip the conversion engines (the converter then reports them missing)
 *   npm run setup -- --force       # fetch fonts, models and engines again even if present
 *
 * Steps: npm packages (if missing), the worker's Python environment (worker/.venv), the design fonts and models,
 * the conversion engines (Windows: all of them, pinned in scripts/engines.lock.json; Linux: Pandoc, veraPDF and
 * resvg, plus the packages to install with apt), FriBiDi for Pillow on Windows, the build, the licence list and
 * a quick check. This is the only time anything is downloaded; the app itself never connects to the internet.
 */
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const args = new Set(process.argv.slice(2))
const force = args.has('--force')
const win = process.platform === 'win32'
const platform = win ? 'win-x64' : process.platform === 'linux' ? 'linux-x64' : null
const npm = win ? 'npm.cmd' : 'npm'
const started = Date.now()

function step(title) {
  console.log(`\n=== ${title}`)
}

function run(cmd, cmdArgs, opts = {}) {
  console.log(`> ${cmd} ${cmdArgs.join(' ')}`)
  const r = spawnSync(cmd, cmdArgs, { stdio: 'inherit', cwd: root, shell: win && cmd.endsWith('.cmd'), ...opts })
  if (r.status !== 0) {
    console.error(`\nSetup stopped: "${cmd} ${cmdArgs.join(' ')}" failed (exit ${r.status}). Fix the error above and run "npm run setup" again;`)
    console.error('finished steps are skipped.')
    process.exit(r.status ?? 1)
  }
}

const py = (...a) => run(process.execPath, [join(root, 'scripts', 'run-python.mjs'), ...a])

step('npm packages')
if (!existsSync(join(root, 'node_modules', 'electron'))) run(npm, ['ci'])
else console.log('present')
run(process.execPath, ['-e', "console.log('Electron binary:', require('electron'))"])

step('Python worker environment (worker/.venv)')
run(process.execPath, [join(root, 'scripts', 'setup-python.mjs')])

if (win) {
  step('FriBiDi for Pillow (text shaping for Indic and Arabic scripts)')
  const scriptsDir = join(root, 'worker', '.venv', 'Scripts')
  if (force || !existsSync(join(scriptsDir, 'fribidi-0.dll'))) run(process.execPath, [join(root, 'scripts', 'fetch-fribidi-win.mjs'), scriptsDir])
  else console.log('present')
}

step('Design fonts (73 open-source families, pinned) and models (super-resolution, cut-outs, faces)')
if (force || !existsSync(join(root, 'fonts', 'fonts.json'))) py('--online', 'scripts/fetch_fonts.py')
else console.log('fonts present')
if (force || !existsSync(join(root, 'models', 'manifest.json'))) py('--online', 'scripts/fetch_models.py')
else console.log('models present')

step('Conversion engines')
if (args.has('--no-engines')) {
  console.log('skipped (--no-engines)')
} else if (!platform) {
  console.log('Not bundled on this platform: install LibreOffice, Pandoc, Ghostscript, Tesseract, Java and resvg yourself;')
  console.log('the converter finds them on PATH.')
} else if (!force && existsSync(join(root, 'engines', platform, 'manifest.json'))) {
  console.log(`present in engines/${platform}`)
} else {
  if (win) console.log('Unpacks the official LibreOffice, Ghostscript and Tesseract installers (msiexec /a and 7-Zip); nothing is installed.')
  py('--online', 'scripts/fetch_engines.py', '--platform', platform)
  if (!win) {
    console.log('\nOn Linux, install the rest with your package manager, for example:')
    console.log('  sudo apt-get install libreoffice-core libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-draw \\')
    console.log('    ghostscript tesseract-ocr tesseract-ocr-hin tesseract-ocr-ara tesseract-ocr-heb tesseract-ocr-tam \\')
    console.log('    default-jre-headless fonts-noto-core fonts-crosextra-carlito fonts-crosextra-caladea libfribidi0')
  }
}

step('Build and licence list')
run(npm, ['run', 'build'])
run(npm, ['run', 'licenses'])

step('Quick check')
py('-c', [
  'from PIL import features',
  'from otk_worker.converter import engines',
  "found = {k: v['available'] for k, v in engines.status().items()}",
  "print('Pillow text shaping (raqm):', 'yes' if features.check('raqm') else 'NO - install FriBiDi')",
  "print('engines:', ', '.join(f\"{k} {'ok' if v else 'missing'}\" for k, v in found.items()))",
].join('\n'))

console.log(`\nReady in ${Math.round((Date.now() - started) / 1000)} s. Next:`)
console.log('  npm run dev        start the app (Settings → Check every module runs the full offline self-test)')
console.log('  npm run test:all   typecheck, unit, Python and end-to-end tests')
if (win) console.log('  npm run dist:win   build the installer (see README → Packaging)')
