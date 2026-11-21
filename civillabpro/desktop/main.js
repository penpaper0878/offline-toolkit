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
let restarting = false; // the server is being stopped on purpose (a restore), not lost
let paths = null;
let origin = null;

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

/** Keep the window on the local server (wherever it is now listening): other links open in the system browser. */
function lockToOrigin(contents) {
  const local = (url) => origin !== null && url.startsWith(`${origin}/`);
  const external = (url) => { if (/^https?:\/\//.test(url) && !local(url)) shell.openExternal(url); };
  contents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  contents.on('will-navigate', (event, url) => {
    if (!local(url)) { event.preventDefault(); external(url); }
  });
}

function menu() {
  const dev = !app.isPackaged;
  return Menu.buildFromTemplate([
    { label: 'File', submenu: [
      { label: 'Back up data...', click: () => win.loadURL(`${origin}/admin/data`) },
      { label: 'Restore from backup...', click: () => restore().catch(fail) },
      { type: 'separator' },
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
                                  ['footing', {}], ['combined_footing', {}], ['strap_footing', {}]]) {
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
    return { path: location.pathname, title: document.title, designs, token: reg.access_token, project: project.id };
  })()`);
  const restored = await smokeRestore(seen.token, seen.project, Object.keys(seen.designs).length);
  delete seen.token;
  console.log('SMOKE OK', JSON.stringify({ server: health, window: seen, restore: restored, data: paths.dataDir }));
  quitting = true;
  launcher.stopServer(server);
  app.exit(0);
}

/** Start the server on the kept port and wait for it; its unplanned end is fatal. */
async function launch() {
  const port = await launcher.choosePort(paths.stateFile);
  origin = `http://127.0.0.1:${port}`;
  const child = launcher.startServer(paths, port, launcher.serverEnv(paths, launcher.ensureSecret(paths.secretFile), process.env));
  server = child;
  child.once('exit', (code) => { if (!quitting && !restarting && server === child) fail(new Error(`The calculation server stopped (exit code ${code}).`)); });
  return launcher.waitForHealth(origin, child);
}

async function stopAndWait() {
  const child = server;
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const gone = new Promise((resolve) => child.once('exit', resolve));
  launcher.stopServer(child);
  await gone;
}

/**
 * File, Restore from backup: stop the server, put the chosen backup in the database's place (the current data kept in the data folder),
 * start again (the server brings an older backup up to date). If the backup will not start, the previous data is put back.
 */
async function restore() {
  const pick = await dialog.showOpenDialog(win, { title: 'Restore from a backup', properties: ['openFile'],
    filters: [{ name: 'CivilLabPro OS backup', extensions: ['db'] }, { name: 'All files', extensions: ['*'] }] });
  if (pick.canceled || !pick.filePaths[0]) return;
  const answer = await dialog.showMessageBox(win, {
    type: 'warning', buttons: ['Restore', 'Cancel'], defaultId: 1, cancelId: 1, title: 'Restore from a backup',
    message: 'Replace all the data on this computer with this backup?',
    detail: 'Everything entered since the backup was made is set aside: the current data is kept in the data folder as '
      + 'civillabpro.before-restore-<date>.db, and can be put back the same way.',
  });
  if (answer.response !== 0) return;
  const outcome = await restoreFrom(pick.filePaths[0]);
  if (outcome.ok) {
    await win.loadURL(`${origin}/login`);
    dialog.showMessageBox(win, { type: 'info', title: 'Restored', message: 'The backup has been restored. Sign in again.' });
  } else {
    await win.loadURL(`${origin}/`);
    dialog.showErrorBox(outcome.title, outcome.message);
  }
}

/** The restore itself, without dialogs: { ok } or { ok: false, title, message }; the server is running again either way. */
async function restoreFrom(file) {
  restarting = true;
  try {
    await stopAndWait();
    let undo;
    try {
      ({ undo } = launcher.restoreDatabase(paths, file, new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)));
    } catch (e) {
      await launch();
      return { ok: false, title: 'Nothing was restored', message: e.message };
    }
    try {
      await launch();
      return { ok: true };
    } catch (e) {
      await stopAndWait();
      undo();
      await launch();
      return { ok: false, title: 'The backup could not be opened',
        message: `The previous data has been put back.\n\n${e.message}\n\nServer log: ${paths.serverLog}` };
    }
  } finally {
    restarting = false;
  }
}

/** The smoke test's second half: a backup, a project added after it, a restore, and the project gone with the designs back. */
async function smokeRestore(token, projectId, expected) {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const call = async (p, init = {}) => {
    const r = await fetch(`${origin}/api/v1${p}`, { ...init, headers: { Authorization: `Bearer ${token}`, 'content-type': 'application/json', ...(init.headers || {}) } });
    if (!r.ok) throw new Error(`${p}: ${r.status} ${(await r.text()).slice(0, 300)}`);
    return r;
  };
  const bytes = Buffer.from(await (await call('/admin/backup')).arrayBuffer());
  const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'clp-smoke-')), 'backup.db');
  fs.writeFileSync(file, bytes);
  await call('/projects', { method: 'POST', body: JSON.stringify({ code: 'AFTER-BACKUP', name: 'Made after the backup', project_type: 'building' }) });
  const outcome = await restoreFrom(file);
  if (!outcome.ok) throw new Error(`restore: ${outcome.message}`);
  const projects = await (await call('/projects')).json();
  const designs = await (await call(`/projects/${projectId}/designs`)).json();
  if (projects.items.some((p) => p.code === 'AFTER-BACKUP')) throw new Error('restore: the project made after the backup is still there');
  if (designs.length !== expected) throw new Error(`restore: ${designs.length} designs after the restore, ${expected} before`);
  return { backup_bytes: bytes.length, projects: projects.total, designs: designs.length };
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

  const health = await launch();
  lockToOrigin(win.webContents);
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
