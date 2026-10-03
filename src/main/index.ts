import { mkdir, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { app, BrowserWindow, Menu, nativeTheme, session } from 'electron'
import { registerDesignIpc } from './design'
import { registerIpc } from './ipc'
import { EventLog } from './log'
import { applyOfflineSwitches, guardNode, guardSession } from './offline-guard'
import { cacheDir, dataDir, enginesDir, fontsDir, logsDir, modelsDir, previewDir, pythonExecutable, rendererDir, resourcesDir, workerDir } from './paths'
import { handleProtocol, registerSchemes } from './protocol'
import { type RenderRequest, renderPdf } from './render'
import { Store } from './store'
import { WorkerPool } from './worker'

const devServer = !app.isPackaged ? process.env.ELECTRON_RENDERER_URL : undefined

if (process.env.OTK_DATA_DIR) app.setPath('userData', process.env.OTK_DATA_DIR)
registerSchemes()
applyOfflineSwitches(devServer)
// Every renderer is sandboxed. The only exception is an explicit --no-sandbox,
// which Chromium needs when running as root (CI containers); never on a normal install.
if (!app.commandLine.hasSwitch('no-sandbox')) app.enableSandbox()

let mainWindow: BrowserWindow | null = null
let pool: WorkerPool | null = null

function createWindow(dark: boolean): BrowserWindow {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 640,
    show: false,
    title: 'Offline Toolkit',
    backgroundColor: dark ? '#14161a' : '#f6f7f9',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
      webSecurity: true
    }
  })
  win.once('ready-to-show', () => win.show())
  win.webContents.on('will-navigate', (e) => e.preventDefault())
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  if (devServer) void win.loadURL(devServer)
  else void win.loadURL('otk://app/index.html')
  return win
}

function buildMenu(): void {
  const isMac = process.platform === 'darwin'
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(isMac ? [{ role: 'appMenu' as const }] : []),
    { role: 'fileMenu' },
    { role: 'editMenu' },
    {
      label: 'View',
      submenu: [
        ...(app.isPackaged ? [] : [{ role: 'reload' as const }, { role: 'toggleDevTools' as const }, { type: 'separator' as const }]),
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { type: 'separator' }, { role: 'togglefullscreen' }
      ]
    },
    { role: 'windowMenu' }
  ]))
}

app.whenReady().then(async () => {
  const log = new EventLog(logsDir())
  await log.init()
  guardNode(log)
  guardSession(session.defaultSession, devServer)
  handleProtocol(rendererDir())
  await rm(previewDir(), { recursive: true, force: true })
  await mkdir(previewDir(), { recursive: true })

  const store = new Store(resourcesDir(), dataDir(), log)
  await store.init()
  const settings = store.getSettings()
  log.hashPaths = settings.logging.hashPaths
  nativeTheme.themeSource = settings.theme

  pool = new WorkerPool({
    python: pythonExecutable(), workerDir: workerDir(), resourcesDir: resourcesDir(), enginesDir: enginesDir(),
    cacheDir: cacheDir(), fontsDir: fontsDir(), modelsDir: modelsDir(), log,
    hostHandler: async (method, params) => {
      if (method === 'host.renderPdf') return renderPdf(params as RenderRequest, log)
      throw new Error(`Unknown request ${method}`)
    }
  })
  registerIpc({ store, pool, log, getWindow: () => mainWindow })
  registerDesignIpc({ store, pool, log, getWindow: () => mainWindow })
  log.info('app', `Offline Toolkit ${app.getVersion()} started`, { data: dataDir(), python: pythonExecutable() })

  buildMenu()
  mainWindow = createWindow(nativeTheme.shouldUseDarkColors)
  mainWindow.on('closed', () => (mainWindow = null))
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) mainWindow = createWindow(nativeTheme.shouldUseDarkColors)
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

let quitting = false
app.on('before-quit', (e) => {
  if (quitting || !pool) return
  quitting = true
  e.preventDefault()
  void pool.stop().finally(async () => {
    await rm(previewDir(), { recursive: true, force: true }).catch(() => undefined)
    app.quit()
  })
})
