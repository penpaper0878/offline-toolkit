'use strict';
// CivilLabPro OS desktop shell: starts the one-process server (API and client) against SQLite in the user's data folder,
// then shows the client in a window. Nothing leaves the computer: the server listens on 127.0.0.1 only.
//
//   npm start                  from a checkout (the backend's .venv and frontend/dist)
//   npm start -- --smoke-test  start, load the client, check it answers, quit (exit code 0 when all is well)

const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const launcher = require('./launcher');

const SMOKE = process.argv.includes('--smoke-test');
// The data folder: the platform's own (e.g. %APPDATA%\CivilLabPro OS, ~/.config/CivilLabPro OS), or CLP_DESKTOP_DATA for a
// portable install or a test.
if (process.env.CLP_DESKTOP_DATA) app.setPath('userData', process.env.CLP_DESKTOP_DATA);
let server = null;
let win = null;
let quitting = false;
let paths = null;

function fail(err) {
  const where = paths ? `\n\nServer log: ${paths.serverLog}` : '';
  if (SMOKE) {
    console.error('SMOKE FAILED', err && err.message);
  } else {
    dialog.showErrorBox('CivilLabPro OS could not start', `${err && err.message ? err.message : err}${where}`);
  }
  quitting = true;
  launcher.stopServer(server);
  app.exit(1);
}

/** Keep the window on the local server: other links open in the system browser. */
function lockToOrigin(contents, origin) {
  const external = (url) => { if (/^https?:\/\//.test(url) && !url.startsWith(origin)) shell.openExternal(url); };
  contents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  contents.on('will-navigate', (event, url) => {
    if (!url.startsWith(origin)) { event.preventDefault(); external(url); }
  });
}

function menu() {
  const dev = !app.isPackaged;
  return Menu.buildFromTemplate([
    { label: 'File', submenu: [
      { label: 'Open data folder', click: () => shell.openPath(paths.dataDir) },
      { label: 'Open server log', click: () => shell.openPath(paths.serverLog) },
      { type: 'separator' },
      { role: 'quit' },
    ] },
    { label: 'Edit', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' },
      { role: 'selectAll' }] },
    { label: 'View', submenu: [{ role: 'reload' }, { type: 'separator' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
      { type: 'separator' }, { role: 'togglefullscreen' }, ...(dev ? [{ role: 'toggleDevTools' }] : [])] },
    { label: 'Help', submenu: [{ label: 'About CivilLabPro OS', click: () => dialog.showMessageBox(win, {
      type: 'info', title: 'About CivilLabPro OS', message: `CivilLabPro OS ${app.getVersion()}`,
      detail: `Your projects and designs are kept on this computer, in\n${paths.dataDir}`,
    }) }] },
  ]);
}

/**
 * The smoke test, inside the window: the client's sign-in screen renders, then through the window's own origin an organisation is
 * registered, a project made, every element designed with its defaults (the continuous beam by both methods), and each design's
 * report, schedule and drawing fetched and recognised (PDF, XLSX, DXF). This proves the bundled server whole: its migrations,
 * engines, fonts and exporters.
 */
async function smoke(health) {
  const seen = await win.webContents.executeJavaScript(`(async () => {
    const t0 = Date.now();
    while (!document.querySelector('form input[type="password"]')) {
      if (Date.now() - t0 > 20000) throw new Error('the sign-in screen did not appear');
      await new Promise((r) => setTimeout(r, 200));
    }
    const api = async (path, opts = {}) => {
      const r = await fetch('/api/v1' + path, opts);
      if (!r.ok) throw new Error(path + ': ' + r.status + ' ' + (await r.text()).slice(0, 300));
      return r;
    };
    const json = { 'content-type': 'application/json' };
    const reg = await (await api('/auth/register', { method: 'POST', headers: json, body: JSON.stringify({
      organization_name: 'Desktop smoke test', full_name: 'Smoke Test', email: 'smoke' + Date.now() + '@desktop.example', password: 'Structure2026' }) })).json();
    const auth = { Authorization: 'Bearer ' + reg.access_token };
    const project = await (await api('/projects', { method: 'POST', headers: { ...auth, ...json }, body: JSON.stringify({
      code: 'SMOKE-' + Date.now() % 100000, name: 'Desktop smoke test', client: 'Self', state: 'Gujarat', project_type: 'building' }) })).json();
    const magic = { 'report.pdf': '%PDF', 'bbs.xlsx': 'PK', 'drawing.dxf': '  0' };
    const designs = {};
    for (const [type, inputs] of [['beam', {}], ['continuous_beam', {}], ['continuous_beam', { analysis: 'elastic' }], ['column', {}], ['slab', {}],
                                  ['footing', {}]]) {
      const d = await (await api('/projects/' + project.id + '/designs', { method: 'POST', headers: { ...auth, ...json },
        body: JSON.stringify({ element_type: type, name: type + (inputs.analysis ? '-' + inputs.analysis : ''), inputs }) })).json();
      if (d.status !== 'ok') throw new Error(type + ' designed ' + d.status);
      const files = {};
      for (const [file, head] of Object.entries(magic)) {
        const bytes = new Uint8Array(await (await api('/designs/' + d.id + '/' + file, { headers: auth })).arrayBuffer());
        if (!String.fromCharCode(...bytes.slice(0, head.length)).startsWith(head)) throw new Error(type + ' ' + file + ' is not what it should be');
        files[file] = bytes.length;
      }
      designs[type + (inputs.analysis ? ' (' + inputs.analysis + ')' : '')] = files;
    }
    return { path: location.pathname, title: document.title, designs };
  })()`);
  console.log('SMOKE OK', JSON.stringify({ server: health, window: seen, data: paths.dataDir }));
  quitting = true;
  launcher.stopServer(server);
  app.exit(0);
}

async function start() {
  paths = launcher.paths({ packaged: app.isPackaged, resourcesPath: process.resourcesPath, appDir: __dirname, dataDir: app.getPath('userData'),
    platform: process.platform, env: process.env });
  win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 1024, minHeight: 640, show: false, backgroundColor: '#0f172a', title: 'CivilLabPro OS',
    webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false },
  });
  win.once('ready-to-show', () => { if (!SMOKE) win.show(); });
  await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(launcher.splashHtml(app.getVersion())));

  const port = await launcher.choosePort(paths.stateFile);
  const origin = `http://127.0.0.1:${port}`;
  server = launcher.startServer(paths, port, launcher.serverEnv(paths, launcher.ensureSecret(paths.secretFile), process.env));
  server.once('exit', (code) => { if (!quitting) fail(new Error(`The calculation server stopped (exit code ${code}).`)); });
  const health = await launcher.waitForHealth(origin, server);

  lockToOrigin(win.webContents, origin);
  Menu.setApplicationMenu(menu());
  await win.loadURL(`${origin}/`);
  if (SMOKE) await smoke(health);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', () => { quitting = true; launcher.stopServer(server); });
  app.whenReady().then(start).catch(fail);
}
