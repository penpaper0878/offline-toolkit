"""The one-process entry point the desktop shell starts: a fresh SQLite file is migrated, then the API and client are served."""

import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

from app.serve import alembic_dir, migrate


def test_migrate_creates_the_schema_in_a_fresh_file(tmp_path):
    db = tmp_path / "fresh.db"
    migrate(f"sqlite:///{db}")
    tables = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type = 'table'")}
    assert {"alembic_version", "organizations", "users", "projects", "structural_designs"} <= tables
    migrate(f"sqlite:///{db}")  # a second start finds it at head and changes nothing
    assert (alembic_dir() / "env.py").is_file()


def test_server_process_migrates_and_serves_api_and_client(tmp_path):
    client = tmp_path / "web"
    client.mkdir()
    (client / "index.html").write_text("<!doctype html><title>CivilLabPro OS</title>")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "CLP_DATABASE_URL": f"sqlite:///{tmp_path / 'desk.db'}", "CLP_STATIC_DIR": str(client), "CLP_ENV": "production",
           "CLP_ALLOW_SQLITE": "1", "CLP_JWT_SECRET": "x" * 64, "CLP_CORS_ORIGINS": "[]"}
    proc = subprocess.Popen([sys.executable, "-m", "app.serve", "--port", str(port)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(150):
            try:
                with urllib.request.urlopen(f"{base}/api/v1/health", timeout=1) as r:
                    health = r.read().decode()
                break
            except OSError:
                if proc.poll() is not None:
                    raise AssertionError(proc.stdout.read().decode()) from None
                time.sleep(0.1)
        else:
            raise AssertionError("the server did not answer")
        assert '"database"' in health or "ok" in health
        with urllib.request.urlopen(f"{base}/projects/anything", timeout=2) as r:  # client routes fall back to index.html
            assert "<title>CivilLabPro OS</title>" in r.read().decode()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_server_stops_when_the_process_that_started_it_ends(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    env = {**os.environ, "CLP_DATABASE_URL": f"sqlite:///{tmp_path / 'w.db'}"}
    proc = subprocess.Popen([sys.executable, "-m", "app.serve", "--port", str(port), "--parent-pid", str(parent.pid)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).close()
                break
            except OSError:
                time.sleep(0.1)
        assert proc.poll() is None
        parent.kill()
        parent.wait()
        assert proc.wait(timeout=15) == 0  # a clean shutdown, not a kill
    finally:
        parent.kill()
        if proc.poll() is None:
            proc.kill()
