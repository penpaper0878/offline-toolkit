"""The worker as the app runs it: a subprocess speaking JSON-RPC on stdio."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from conftest import photo_array
from otk_worker import netguard

WORKER_DIR = Path(__file__).resolve().parents[1]


class Worker:
    def __init__(self):
        env = {**os.environ, "PYTHONPATH": str(WORKER_DIR), "PYTHONUTF8": "1"}
        self.p = subprocess.Popen([sys.executable, "-m", "otk_worker"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        self.next_id = 0
        self.messages: list[dict] = []
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.p.stdout:
            with self.lock:
                self.messages.append(json.loads(line))

    def send(self, method, params=None) -> int:
        self.next_id += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}) + "\n")
        self.p.stdin.flush()
        return self.next_id

    def wait(self, req_id, timeout=60) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for m in self.messages:
                    if m.get("id") == req_id:
                        return m
            time.sleep(0.02)
        raise TimeoutError(req_id)

    def call(self, method, params=None) -> dict:
        return self.wait(self.send(method, params))

    def close(self):
        self.p.stdin.close()
        self.p.wait(10)
        return self.p.stderr.read()


@pytest.fixture
def worker():
    w = Worker()
    yield w
    w.close()


def test_ping_and_guard(worker):
    r = worker.call("ping")["result"]
    assert r["pong"] and r["netguard"] is True and r["heif"] is True
    canary = worker.call("selftest.canary")["result"]
    assert canary["blocked"] and canary["recorded"] >= 1


def test_errors_are_reported_not_fatal(worker):
    assert worker.call("nope")["error"]["code"] == -32601
    bad = worker.call("image.probe", {"path": "/definitely/missing.jpg", "previewDir": "/tmp"})
    assert bad["error"]["data"]["code"] == "input"
    assert worker.call("ping")["result"]["pong"]


def test_probe_preview_run_with_progress_and_cancel(tmp_path, worker):
    src = tmp_path / "ছবি.png"
    Image.fromarray(photo_array(900, 600)).save(src)
    info = worker.call("image.probe", {"path": str(src), "previewDir": str(tmp_path / "cache"), "maxSide": 256})["result"]
    assert (info["width"], info["height"]) == (900, 600)
    assert Path(info["preview"]["path"]).exists() and info["preview"]["width"] == 256

    settings = {"width": 240, "height": 240, "unit": "px", "dpi": 200, "fit": "crop", "format": "jpeg",
                "sizeRange": {"min": 20, "max": 50, "unit": "KB"}}
    prev = worker.call("resizer.preview", {"item": {"path": str(src)}, "settings": settings,
                                           "previewDir": str(tmp_path / "cache")})["result"]
    assert prev["status"] == "ok" and Path(prev["previewPath"]).exists()

    items = [{"path": str(src)}] * 3
    run = worker.call("resizer.run", {"jobId": "job-1", "items": items, "settings": settings,
                                      "outputDir": str(tmp_path / "out"), "zip": True})["result"]
    assert run["counts"] == {"ok": 3} and Path(run["zipPath"]).exists()
    progress = [m for m in worker.messages if m.get("method") == "job.progress"]
    assert progress and progress[-1]["params"]["fraction"] == 1.0 and progress[0]["params"]["jobId"] == "job-1"

    many = [{"path": str(src)}] * 40
    rid = worker.send("resizer.run", {"jobId": "job-2", "items": many, "settings": settings,
                                      "outputDir": str(tmp_path / "out2")})
    time.sleep(0.3)
    worker.call("job.cancel", {"jobId": "job-2"})
    res = worker.wait(rid)["result"]
    assert res["counts"].get("cancelled", 0) > 0


def test_loopback_detection():
    assert netguard._is_loopback("127.0.0.1") and netguard._is_loopback("::1") and netguard._is_loopback("localhost")
    assert not netguard._is_loopback("example.com") and not netguard._is_loopback("8.8.8.8")
