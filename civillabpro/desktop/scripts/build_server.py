#!/usr/bin/env python3
"""Bundle the backend into one self-contained folder for the desktop installer: desktop/build/clp-server.

PyInstaller, one folder (starts faster than one file and is what the installer copies). Run it with the Python of the
backend's environment, on the platform the installer is for:

    python -m pip install -e "backend[desktop]"
    python desktop/scripts/build_server.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]  # civillabpro/
BACKEND = ROOT / "backend"
BUILD = ROOT / "desktop" / "build"
SEP = ";" if os.name == "nt" else ":"


def main() -> int:
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console", "--name", "clp-server",
        "--distpath", str(BUILD), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD / "pyinstaller"),
        "--paths", str(BACKEND),
        # the migration history is read from disk by Alembic, so it travels as data
        "--add-data", f"{BACKEND / 'alembic'}{SEP}alembic",
        # the app imports its modules by name (routers, the model registry, the engines) and reads its own fonts
        "--collect-submodules", "app", "--collect-data", "app",
        "--collect-submodules", "uvicorn", "--collect-data", "reportlab", "--collect-data", "ezdxf",
        # not used by a desktop install: PostgreSQL's driver, uvicorn's optional event loop, reloader and websockets, test tools
        "--exclude-module", "psycopg", "--exclude-module", "psycopg_binary", "--exclude-module", "uvloop", "--exclude-module", "watchfiles",
        "--exclude-module", "websockets", "--exclude-module", "pytest", "--exclude-module", "tkinter",
        str(ROOT / "desktop" / "server_entry.py"),
    ]
    print(" ".join(args), flush=True)
    done = subprocess.run(args, cwd=BACKEND)
    if done.returncode:
        return done.returncode
    exe = BUILD / "clp-server" / ("clp-server.exe" if os.name == "nt" else "clp-server")
    print(f"built {exe} ({sum(f.stat().st_size for f in exe.parent.rglob('*') if f.is_file()) / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
