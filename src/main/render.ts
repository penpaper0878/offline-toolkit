/**
 * Chromium print-to-PDF for the document converter (HTML/TXT/SVG/EPUB -> PDF).
 *
 * The worker asks for it with a `host.renderPdf` request. The page is loaded in
 * a hidden, offscreen, sandboxed window with JavaScript off, in its own session
 * where every request outside the job folder (and data:/blob: URLs) is blocked
 * and recorded. One print at a time. scripts/render-pdf.cjs does the same for
 * tests and the command line.
 */

import { writeFile } from 'node:fs/promises'
import { isAbsolute, relative, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { BrowserWindow, session } from 'electron'
import type { EventLog } from './log'

export interface RenderRequest {
  html: string
  pdf: string
  paper: string
  allowDir: string
  pageSize: [number, number] | null
}

const PAPER: Record<string, string> = { a4: 'A4', letter: 'Letter', legal: 'Legal', a3: 'A3', a5: 'A5' }
const PARTITION = 'otk-render'

let queue: Promise<unknown> = Promise.resolve()
let currentAllow: string | null = null
let blocked: string[] = []
let sessionReady = false

function inside(dir: string, p: string): boolean {
  const rel = relative(dir, p)
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel))
}

function renderSession(log: EventLog): Electron.Session {
  const ses = session.fromPartition(PARTITION)
  if (!sessionReady) {
    ses.setProxy({ proxyRules: '127.0.0.1:9', proxyBypassRules: '<-loopback>' }).catch(() => undefined)
    ses.setSpellCheckerEnabled(false)
    ses.webRequest.onBeforeRequest((details, cb) => {
      const u = details.url
      if (u.startsWith('data:') || u.startsWith('blob:')) return cb({})
      if (u.startsWith('file:') && currentAllow) {
        try {
          if (inside(currentAllow, resolve(fileURLToPath(u)))) return cb({})
        } catch {
          /* fall through */
        }
      }
      blocked.push(u)
      log.warn('render', `Blocked while printing: ${u.slice(0, 200)}`)
      cb({ cancel: true })
    })
    ses.setPermissionRequestHandler((_wc, _perm, cb) => cb(false))
    sessionReady = true
  }
  return ses
}

async function renderOnce(req: RenderRequest, log: EventLog): Promise<{ ok: true; blocked: string[] }> {
  const ses = renderSession(log)
  currentAllow = resolve(req.allowDir)
  blocked = []
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      session: ses, javascript: false, sandbox: true, contextIsolation: true, nodeIntegration: false,
      spellcheck: false, webSecurity: true, offscreen: true
    }
  })
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  win.webContents.on('will-navigate', (e) => e.preventDefault())
  try {
    await win.loadURL(pathToFileURL(req.html).href)
    const opts: Electron.PrintToPDFOptions = {
      printBackground: true, generateTaggedPDF: true, generateDocumentOutline: true, preferCSSPageSize: true
    }
    if (req.pageSize) {
      opts.pageSize = { width: req.pageSize[0] / 72, height: req.pageSize[1] / 72 }
      opts.margins = { top: 0, bottom: 0, left: 0, right: 0 }
    } else {
      opts.pageSize = (PAPER[req.paper] ?? 'A4') as Electron.PrintToPDFOptions['pageSize']
      opts.margins = { top: 0.5, bottom: 0.5, left: 0.5, right: 0.5 }
    }
    const pdf = await win.webContents.printToPDF(opts)
    await writeFile(req.pdf, pdf)
    return { ok: true, blocked: [...blocked] }
  } finally {
    currentAllow = null
    win.destroy()
  }
}

/** Queue a print; prints never overlap (the session's allow-list is per print). */
export function renderPdf(req: RenderRequest, log: EventLog): Promise<{ ok: true; blocked: string[] }> {
  const run = queue.then(() => renderOnce(req, log))
  queue = run.catch(() => undefined)
  return run
}
