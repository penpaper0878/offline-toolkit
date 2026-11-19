"""Run CivilLabPro OS as one process: bring the database to the latest schema, then serve the API and the built client.

This is what the desktop shell starts (SQLite in the user's data folder, the client bundled beside the server) and what a
small server can run behind a reverse proxy. Configuration comes from the usual ``CLP_*`` environment variables.

    python -m app.serve --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def alembic_dir() -> Path:
    """The migration scripts: beside the package in a checkout, inside the bundle when frozen (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "alembic"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[1] / "alembic"


def migrate(url: str) -> None:
    """Upgrade the database at ``url`` to the head of the one migration history (PostgreSQL or SQLite)."""
    from alembic.config import Config

    from alembic import command

    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir()))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))  # the option is interpolated
    command.upgrade(cfg, "head")


def alive(pid: int) -> bool:
    """Whether process ``pid`` is still running (Windows and POSIX)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)  # WAIT_TIMEOUT: not signalled, still running
        finally:
            kernel32.CloseHandle(handle)
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(pid: int, server: Any, every: float = 1.0) -> None:
    """Stop the server when the process that started it (the desktop shell) is gone, so it never outlives the window."""
    import threading
    import time

    def run() -> None:
        while not server.should_exit:
            if not alive(pid):
                server.should_exit = True
                return
            time.sleep(every)

    threading.Thread(target=run, name="watch-parent", daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clp-server", description="CivilLabPro OS: the API and the web client in one process.")
    parser.add_argument("--host", default="127.0.0.1", help="interface to listen on (default: this computer only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-migrate", action="store_true", help="serve without upgrading the database first")
    parser.add_argument("--parent-pid", type=int, help="stop when this process ends (the desktop shell passes its own)")
    args = parser.parse_args(argv)

    from app.core.config import get_settings

    settings = get_settings()  # validates the configuration before anything is touched
    if not args.no_migrate:
        migrate(settings.database_url)

    import uvicorn

    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info", access_log=False))
    if args.parent_pid:
        watch_parent(args.parent_pid, server)
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
