#!/usr/bin/env node
/**
 * FriBiDi for Windows. Pillow's wheels contain HarfBuzz and libraqm but load FriBiDi at run time
 * (fribidi-0.dll), and Windows has none. Without it Pillow lays text out without shaping: Indic scripts
 * lose their conjuncts and vowel signs, Arabic its joining and right-to-left order, Latin its kerning.
 * The design module measures fonts by drawing text with Pillow, so it needs shaping on Windows too.
 *
 * Source: conda-forge's build (LGPL-2.1-or-later, a separate replaceable DLL), pinned by SHA-256.
 * It needs only VCRUNTIME140.dll (shipped with Python) and the Universal C Runtime (part of Windows 10/11).
 *
 * Used by scripts/bundle-python-win.mjs (next to the bundled python.exe, where Windows finds it first)
 * and by CI (a folder put on PATH for the worker's virtual environment).
 * Usage: node scripts/fetch-fribidi-win.mjs <folder>
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zstdDecompressSync } from 'node:zlib'

const STEM = 'fribidi-1.0.17-hfd05255_0'
const URL = `https://conda.anaconda.org/conda-forge/win-64/${STEM}.conda`
const SHA256 = '30a93a5132923a5679e0729a02bf5b36052c84cc437decc14a35caee5e276f46'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const cache = join(root, 'build', 'cache')

/** Entries of a zip whose members are stored uncompressed (a .conda package is one). */
function readStoredZip(buf) {
  const eocd = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]))
  if (eocd < 0) throw new Error('not a zip file')
  const count = buf.readUInt16LE(eocd + 10)
  let p = buf.readUInt32LE(eocd + 16)
  const out = new Map()
  for (let i = 0; i < count; i++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('bad zip directory')
    const method = buf.readUInt16LE(p + 10)
    const size = buf.readUInt32LE(p + 20)
    const n = buf.readUInt16LE(p + 28), e = buf.readUInt16LE(p + 30), c = buf.readUInt16LE(p + 32)
    const local = buf.readUInt32LE(p + 42)
    const name = buf.toString('utf8', p + 46, p + 46 + n)
    if (method !== 0) throw new Error(`zip entry ${name} is compressed (method ${method})`)
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28)
    out.set(name, buf.subarray(start, start + size))
    p += 46 + n + e + c
  }
  return out
}

/** Regular files of a (ustar) tar archive. */
function readTar(buf) {
  const out = new Map()
  for (let p = 0; p + 512 <= buf.length;) {
    const h = buf.subarray(p, p + 512)
    const field = (a, b) => h.toString('utf8', a, b).replace(/\0.*$/s, '')
    const name = field(0, 100)
    if (!name) break
    const size = parseInt(field(124, 136).trim() || '0', 8)
    const type = field(156, 157)
    const prefix = h.toString('utf8', 257, 262) === 'ustar' ? field(345, 500) : ''
    if (type === '0' || type === '') out.set(prefix ? `${prefix}/${name}` : name, buf.subarray(p + 512, p + 512 + size))
    p += 512 + Math.ceil(size / 512) * 512
  }
  return out
}

export async function fetchFribidi(dest) {
  mkdirSync(cache, { recursive: true })
  const pkg = join(cache, `${STEM}.conda`)
  if (!existsSync(pkg)) {
    console.log(`Downloading ${URL}`)
    const res = await fetch(URL)
    if (!res.ok) throw new Error(`Download failed: ${res.status} ${res.statusText}`)
    writeFileSync(pkg, Buffer.from(await res.arrayBuffer()))
  }
  const data = readFileSync(pkg)
  const digest = createHash('sha256').update(data).digest('hex')
  if (digest !== SHA256) throw new Error(`SHA-256 mismatch for ${pkg}: ${digest}`)
  const zip = readStoredZip(data)
  const unpack = (part) => {
    const z = zip.get(`${part}-${STEM}.tar.zst`)
    if (!z) throw new Error(`${part} archive missing from ${STEM}.conda`)
    return readTar(zstdDecompressSync(z))
  }
  const dll = unpack('pkg').get('Library/bin/fribidi-0.dll')
  const licence = unpack('info').get('info/licenses/COPYING')
  if (!dll || !licence) throw new Error(`fribidi-0.dll or its licence missing from ${STEM}.conda`)
  mkdirSync(dest, { recursive: true })
  writeFileSync(join(dest, 'fribidi-0.dll'), dll) // one of the names Pillow's loader tries
  writeFileSync(join(dest, 'fribidi-COPYING.txt'), licence)
  console.log(`FriBiDi 1.0.17 (conda-forge ${STEM}, sha256 verified) -> ${dest}`)
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dest = process.argv[2]
  if (!dest) {
    console.error('Usage: node scripts/fetch-fribidi-win.mjs <folder>')
    process.exit(1)
  }
  fetchFribidi(resolve(dest)).catch((e) => {
    console.error(e)
    process.exit(1)
  })
}
