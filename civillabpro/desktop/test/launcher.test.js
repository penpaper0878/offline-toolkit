'use strict';
// The shell's launcher without a window: paths, environment, key, port, and a real server started and stopped.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const launcher = require('../launcher');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'clp-desktop-'));

test('paths: packaged resources, or the checkout', () => {
  const packed = launcher.paths({ packaged: true, resourcesPath: '/opt/clp/resources', appDir: '/x', dataDir: '/d', platform: 'linux', env: {} });
  assert.equal(packed.server.command, '/opt/clp/resources/server/clp-server');
  assert.equal(packed.staticDir, '/opt/clp/resources/web');
  assert.equal(packed.database, '/d/civillabpro.db');
  const win = launcher.paths({ packaged: true, resourcesPath: 'C:\\clp\\resources', appDir: 'C:\\x', dataDir: 'C:\\d', platform: 'win32', env: {} });
  assert.match(win.server.command, /clp-server\.exe$/);
  const dev = launcher.paths({ packaged: false, resourcesPath: '', appDir: '/repo/desktop', dataDir: '/d', platform: 'linux', env: {} });
  assert.deepEqual([dev.server.command, dev.server.args, dev.server.cwd], ['/repo/backend/.venv/bin/python', ['-m', 'app.serve'], '/repo/backend']);
  assert.equal(dev.staticDir, '/repo/frontend/dist');
  const own = launcher.paths({ packaged: false, resourcesPath: '', appDir: '/repo/desktop', dataDir: '/d', platform: 'linux', env: { CLP_PYTHON: '/usr/bin/python3' } });
  assert.equal(own.server.command, '/usr/bin/python3');
});

test('SQLite URLs on both platforms, and the server environment', () => {
  assert.equal(launcher.sqliteUrl('/home/a/.config/CivilLabPro OS/civillabpro.db'), 'sqlite:////home/a/.config/CivilLabPro OS/civillabpro.db');
  assert.equal(launcher.sqliteUrl('C:\\Users\\a\\AppData\\Roaming\\CivilLabPro OS\\civillabpro.db'),
    'sqlite:///C:/Users/a/AppData/Roaming/CivilLabPro OS/civillabpro.db');
  const p = launcher.paths({ packaged: true, resourcesPath: '/r', appDir: '/x', dataDir: '/d', platform: 'linux', env: {} });
  const env = launcher.serverEnv(p, 'k'.repeat(64), { PATH: '/bin', CLP_DATABASE_URL: 'postgresql://elsewhere' });
  assert.equal(env.CLP_DATABASE_URL, 'sqlite:////d/civillabpro.db'); // never the developer's own database
  assert.equal(env.CLP_ENV, 'production');
  assert.equal(env.CLP_ALLOW_SQLITE, '1');
  assert.equal(env.CLP_STATIC_DIR, '/r/web');
  assert.equal(env.PATH, '/bin');
});

test('the key is made once, private, and kept', () => {
  const file = path.join(tmp(), 'secret.key');
  const a = launcher.ensureSecret(file);
  assert.match(a, /^[0-9a-f]{64}$/);
  assert.equal(launcher.ensureSecret(file), a);
  if (process.platform !== 'win32') assert.equal(fs.statSync(file).mode & 0o777, 0o600);
});

test('the port is kept from one start to the next while it is free', async () => {
  const state = path.join(tmp(), 'desktop.json');
  const first = await launcher.choosePort(state);
  assert.equal(await launcher.choosePort(state), first);
  const blocker = net.createServer();
  await new Promise((r) => blocker.listen({ port: first, host: '127.0.0.1' }, r));
  try {
    const other = await launcher.choosePort(state);
    assert.notEqual(other, first);
    assert.equal(JSON.parse(fs.readFileSync(state, 'utf8')).port, other);
  } finally {
    blocker.close();
  }
});

test('the splash page carries no markup from its input', () => {
  assert.doesNotMatch(launcher.splashHtml('<script>x</script>'), /<script>/);
});

// A real start: the backend from this checkout (skipped where its environment is not set up).
const dev = launcher.paths({ packaged: false, resourcesPath: '', appDir: path.resolve(__dirname, '..'), dataDir: tmp(), platform: process.platform,
  env: process.env });
test('the server starts on a fresh data folder, answers, and stops', { skip: !fs.existsSync(dev.server.command) && 'no backend environment' }, async () => {
  fs.mkdirSync(dev.staticDir, { recursive: true });
  const port = await launcher.choosePort(dev.stateFile);
  const child = launcher.startServer(dev, port, launcher.serverEnv(dev, launcher.ensureSecret(dev.secretFile), process.env));
  try {
    const health = await launcher.waitForHealth(`http://127.0.0.1:${port}`, child, 60000);
    assert.equal(health.status, 'ok');
    assert.ok(fs.existsSync(dev.database), 'the database is created in the data folder');
  } finally {
    launcher.stopServer(child);
    await new Promise((r) => (child.exitCode !== null || child.signalCode !== null ? r() : child.once('exit', r)));
  }
  assert.match(fs.readFileSync(dev.serverLog, 'utf8'), /starting on 127\.0\.0\.1/);
});

test('the server is told which process to outlive no longer', async () => {
  const seen = tmp();
  const echo = { ...dev, server: { command: process.execPath, args: ['-e', `require('fs').writeFileSync(${JSON.stringify(path.join(seen, 'argv'))}, JSON.stringify(process.argv.slice(1)))`, '--'], cwd: os.tmpdir() },
    logDir: seen, serverLog: path.join(seen, 'server.log') };
  const child = launcher.startServer(echo, 4321, process.env, 99999);
  await new Promise((r) => child.once('exit', r));
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(seen, 'argv'), 'utf8')), ['--host', '127.0.0.1', '--port', '4321', '--parent-pid', '99999']);
});

test('a server that cannot start is reported, not waited for', async () => {
  const bad = { ...dev, server: { command: process.execPath, args: ['-e', 'process.exit(3)', '--'], cwd: os.tmpdir() }, logDir: tmp() };
  bad.serverLog = path.join(bad.logDir, 'server.log');
  const child = launcher.startServer(bad, 1, process.env);
  await assert.rejects(launcher.waitForHealth('http://127.0.0.1:1', child, 10000), /stopped while starting \(exit code 3\)/);
});
