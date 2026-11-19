'use strict';
// The desktop shell's work outside Electron: where things live, the server's command and environment, its port, its
// start and stop. Plain Node, so it is tested without a window (test/launcher.test.js).

const crypto = require('node:crypto');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

/**
 * Where the shell finds the server and the client, and keeps the user's data.
 * Packaged: the bundled server (PyInstaller) and client under the app's resources. From a checkout: the backend's
 * virtual environment (or CLP_PYTHON) and frontend/dist.
 */
function paths({ packaged, resourcesPath, appDir, dataDir, platform, env }) {
  const win = platform === 'win32';
  const backendDir = path.resolve(appDir, '..', 'backend');
  const python = env.CLP_PYTHON || path.join(backendDir, '.venv', win ? 'Scripts' : 'bin', win ? 'python.exe' : 'python');
  const serverDir = packaged ? path.join(resourcesPath, 'server') : backendDir;
  return {
    dataDir,
    logDir: path.join(dataDir, 'logs'),
    serverLog: path.join(dataDir, 'logs', 'server.log'),
    database: path.join(dataDir, 'civillabpro.db'),
    secretFile: path.join(dataDir, 'secret.key'),
    stateFile: path.join(dataDir, 'desktop.json'),
    staticDir: packaged ? path.join(resourcesPath, 'web') : path.resolve(appDir, '..', 'frontend', 'dist'),
    server: packaged
      ? { command: path.join(serverDir, win ? 'clp-server.exe' : 'clp-server'), args: [], cwd: serverDir }
      : { command: python, args: ['-m', 'app.serve'], cwd: serverDir },
  };
}

/** An SQLAlchemy URL for a file path on any platform: sqlite:////home/... or sqlite:///C:/Users/... */
function sqliteUrl(file) {
  return 'sqlite:///' + file.replace(/\\/g, '/');
}

/** The signing key for this install: created once, readable by the user only. */
function ensureSecret(file) {
  try {
    const s = fs.readFileSync(file, 'utf8').trim();
    if (/^[0-9a-f]{64,}$/.test(s)) return s;
  } catch { /* first start */ }
  const s = crypto.randomBytes(32).toString('hex');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, s + '\n', { mode: 0o600 });
  return s;
}

/** The server's environment: SQLite in the data folder, the bundled client, production settings, this install's key. */
function serverEnv(p, secret, base) {
  return {
    ...base,
    CLP_ENV: 'production',
    CLP_ALLOW_SQLITE: '1',
    CLP_DATABASE_URL: sqliteUrl(p.database),
    CLP_STATIC_DIR: p.staticDir,
    CLP_JWT_SECRET: secret,
    CLP_CORS_ORIGINS: '[]', // the window loads the client from the server itself
    PYTHONUNBUFFERED: '1',
    PYTHONDONTWRITEBYTECODE: '1',
  };
}

function canListen(port) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.listen({ port, host: '127.0.0.1', exclusive: true }, () => srv.close(() => resolve(true)));
  });
}

function anyPort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen({ port: 0, host: '127.0.0.1', exclusive: true }, () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/**
 * The port for this start. The last one is reused while it is free, so the window's origin, and with it the sign-in and
 * the saved panel layouts, stay the same from one start to the next.
 */
async function choosePort(stateFile) {
  let state = {};
  try { state = JSON.parse(fs.readFileSync(stateFile, 'utf8')); } catch { /* first start */ }
  if (Number.isInteger(state.port) && state.port > 1023 && (await canListen(state.port))) return state.port;
  const port = await anyPort();
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });
  fs.writeFileSync(stateFile, JSON.stringify({ ...state, port }, null, 2) + '\n');
  return port;
}

/** Start the server, its output appended to the log. It watches this process and stops if the shell ever dies without stopping it. */
function startServer(p, port, env, parentPid = process.pid) {
  fs.mkdirSync(p.logDir, { recursive: true });
  const log = fs.openSync(p.serverLog, 'a');
  fs.writeSync(log, `\n--- ${new Date().toISOString()} starting on 127.0.0.1:${port}\n`);
  const child = spawn(p.server.command, [...p.server.args, '--host', '127.0.0.1', '--port', String(port), '--parent-pid', String(parentPid)], {
    cwd: p.server.cwd, env, stdio: ['ignore', log, log], windowsHide: true,
  });
  child.once('exit', () => { try { fs.closeSync(log); } catch { /* already closed */ } });
  return child;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Wait until the server answers its health check; fail early if it exits. */
async function waitForHealth(origin, child, timeoutMs = 60000) {
  const until = Date.now() + timeoutMs;
  let spawnError = null;
  child.once('error', (e) => { spawnError = e; });
  while (Date.now() < until) {
    if (spawnError) throw new Error(`The server could not be started: ${spawnError.message}`);
    if (child.exitCode !== null) throw new Error(`The server stopped while starting (exit code ${child.exitCode}).`);
    try {
      const r = await fetch(`${origin}/api/v1/health`, { signal: AbortSignal.timeout(1000) });
      if (r.ok) return await r.json();
    } catch { /* not listening yet */ }
    await sleep(250);
  }
  throw new Error(`The server did not answer within ${Math.round(timeoutMs / 1000)} s.`);
}

/** Stop the server and anything it started; uvicorn finishes its requests on SIGTERM. */
function stopServer(child, platform = process.platform) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  if (platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
    return;
  }
  child.kill('SIGTERM');
  setTimeout(() => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); }, 5000).unref();
}

/** The page shown while the server starts, in the app's own colours. */
function splashHtml(version) {
  return `<!doctype html><html><head><meta charset="utf-8"><title>CivilLabPro OS</title><style>
html,body{height:100%;margin:0}body{display:flex;align-items:center;justify-content:center;background:#0f172a;color:#e2e8f0;
font:14px system-ui,-apple-system,"Segoe UI",sans-serif}.b{text-align:center}.t{font-size:20px;font-weight:600;margin-bottom:6px}
.s{color:#94a3b8}</style></head><body><div class="b"><div class="t">CivilLabPro OS</div>
<div class="s">Starting the calculation server&hellip; ${String(version).replace(/[^0-9a-z.+-]/gi, '')}</div></div></body></html>`;
}

module.exports = { paths, sqliteUrl, ensureSecret, serverEnv, choosePort, startServer, waitForHealth, stopServer, splashHtml };
