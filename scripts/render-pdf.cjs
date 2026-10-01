// Headless Chromium print (HTML -> PDF) for tests and the command line.
// The app does the same inside its main process (src/main/render.ts), with the same options.
// Usage: electron --headless scripts/render-pdf.cjs request.json
//   request: { html, pdf, paper: "a4"|"letter"|..., allowDir, pageSize: [wPt, hPt] | null }
// Prints one JSON line: { ok, blocked: [urls] }
const { app, BrowserWindow, session } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL, fileURLToPath } = require('node:url')

const req = JSON.parse(fs.readFileSync(process.argv[process.argv.length - 1], 'utf8'))
const PAPER = { a4: 'A4', letter: 'Letter', legal: 'Legal', a3: 'A3', a5: 'A5' }

app.disableHardwareAcceleration()
app.commandLine.appendSwitch('proxy-server', '127.0.0.1:9')
app.commandLine.appendSwitch('proxy-bypass-list', '<-loopback>')

function inside(dir, p) {
  const rel = path.relative(dir, p)
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel))
}

app.whenReady().then(async () => {
  const blocked = []
  try {
    const ses = session.fromPartition('otk-render')
    const allow = path.resolve(req.allowDir)
    ses.webRequest.onBeforeRequest((details, cb) => {
      const u = details.url
      if (u.startsWith('data:') || u.startsWith('blob:')) return cb({})
      if (u.startsWith('file:')) {
        try {
          if (inside(allow, path.resolve(fileURLToPath(u)))) return cb({})
        } catch { /* fall through */ }
      }
      blocked.push(u)
      cb({ cancel: true })
    })
    const win = new BrowserWindow({
      show: false,
      // offscreen: headless Linux has no display, and a normal (even hidden) window needs one.
      webPreferences: { session: ses, javascript: false, sandbox: true, spellcheck: false, webSecurity: true, offscreen: true }
    })
    await win.loadURL(pathToFileURL(req.html).href)
    const opts = { printBackground: true, generateTaggedPDF: true, generateDocumentOutline: true, preferCSSPageSize: true }
    if (req.pageSize) {
      opts.pageSize = { width: req.pageSize[0] / 72, height: req.pageSize[1] / 72 }
      opts.margins = { top: 0, bottom: 0, left: 0, right: 0 }
    } else {
      opts.pageSize = PAPER[req.paper] || 'A4'
      opts.margins = { top: 0.5, bottom: 0.5, left: 0.5, right: 0.5 }
    }
    const pdf = await win.webContents.printToPDF(opts)
    fs.writeFileSync(req.pdf, pdf)
    process.stdout.write(JSON.stringify({ ok: true, blocked }) + '\n')
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(err), blocked }) + '\n')
    process.exitCode = 1
  }
  app.quit()
})
