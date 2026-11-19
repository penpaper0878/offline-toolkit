# CivilLabPro OS desktop

The whole platform on one computer, without a network: an Electron window over the one-process server (API and web
client), with the data in a SQLite file in the user's own folder.

## How it works

1. The shell (`main.js`) shows a starting page and picks a port on `127.0.0.1`. It keeps the port from the last start
   while it is free, so that the sign-in and the saved panel layouts carry over.
2. It starts the server (`launcher.js`): the bundled `clp-server` in an installed copy, or the backend's virtual
   environment in a checkout. The server runs with `CLP_ENV=production`, SQLite in the data folder, the bundled web
   client, and a signing key made once for this install.
3. The server brings the database to the latest schema (`app/serve.py`, Alembic), then serves. The shell waits for
   `/api/v1/health` and loads the client.
4. On quit, the shell stops the server. The server also watches the shell (`--parent-pid`) and shuts itself down if
   the shell ever dies without stopping it.

The window stays on the local server; links elsewhere open in the system browser. Nothing listens beyond this computer.

| What | Where |
|---|---|
| Database | `civillabpro.db` in the data folder |
| Server log | `logs/server.log` in the data folder (File, Open server log) |
| Data folder | Windows `%APPDATA%\CivilLabPro OS`; Linux `~/.config/CivilLabPro OS`; or `CLP_DESKTOP_DATA` (a portable copy, a test) |

On the first start, create an organisation as on the web. Approving a design still needs a second person (the
four-eyes rule): add a reviewer under Users and roles. To back up, close the app and copy the data folder.

## Run from a checkout

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"   # once
cd ../frontend && npm ci && npm run build
cd ../desktop && npm ci && npm start
```

`npm run smoke` starts the app and checks it whole, without showing the window. It signs up, designs every element (the
continuous beam by both methods), and fetches each design's PDF, Excel and DXF through the window. It exits 0 when all is
well.

## Build an installer

Build on the platform the installer is for: PyInstaller does not cross-compile.

```bash
cd frontend && npm ci && npm run build                   # the web client
cd .. && python -m pip install -e "./backend[desktop]"
python desktop/scripts/build_server.py                    # desktop/build/clp-server
cd desktop && npm ci
npm run dist:linux                                        # dist/CivilLabPro-OS-<version>-linux-x86_64.AppImage
npm run dist:win                                          # dist/CivilLabPro-OS-<version>-win-x64.exe (NSIS), on Windows
```

`.github/workflows/civillabpro-desktop.yml` does all of this on Ubuntu and Windows. It runs the smoke test on each
packaged app and keeps the installers as build artifacts for 14 days.

## Limits

* The installers are not code-signed, so Windows SmartScreen warns on the first run (PLAT-022).
* No automatic updates: install the new version over the old one; the data folder is kept and migrated on start
  (PLAT-011).
* No macOS build yet.
* One computer, one database: no sync with a server (designed in ARCHITECTURE.md, phase 2).
