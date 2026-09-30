#!/usr/bin/env bash
# Run the Python suite and the Electron end-to-end tests inside a Linux network
# namespace with no network interfaces at all (docs/ARCHITECTURE.md §4).
# Anything in the app that needed the internet would fail these tests.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(id -u)" = "0" ]; then NS=(unshare -n); else NS=(unshare -rn); fi
PY="worker/.venv/bin/python"
echo "== Network inside the namespace (should show a failure):"
"${NS[@]}" "$PY" -c "import socket; socket.setdefaulttimeout(3)
try:
    socket.create_connection(('1.1.1.1', 443)); print('UNEXPECTED: connected')
except OSError as e: print('no network:', e)" || true
echo "== Python tests (network guard OFF, so only the OS blocks the network):"
OTK_NETGUARD=0 "${NS[@]}" "$PY" -m pytest -q worker/tests
echo "== Electron end-to-end tests (loopback only, for Playwright's debugging connection):"
npm run -s build >/dev/null
"${NS[@]}" sh -c "python3 scripts/lo-up.py && xvfb-run -a -s '-screen 0 1600x1000x24' npx playwright test"
