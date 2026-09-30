"""JSON-RPC 2.0 over stdin/stdout, one JSON object per line (UTF-8).

No sockets are involved. Requests run on a small thread pool so the reader
stays free to receive `job.cancel` while a long job is running. The worker
sends notifications (method without id) for job progress.
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TextIO

from .errors import Cancelled, ToolkitError

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
APP_ERROR = -32000


class Context:
    """Handed to handlers: progress notifications and cancellation for one job."""

    def __init__(self, server: "Server", job_id: str | None):
        self.server = server
        self.job_id = job_id
        self.cancel_event = server.job_event(job_id) if job_id else threading.Event()

    def progress(self, payload: dict) -> None:
        if self.job_id:
            self.server.notify("job.progress", {"jobId": self.job_id, **payload})

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()


class Server:
    def __init__(self, inp: TextIO, out: TextIO, workers: int = 4):
        self._in = inp
        self._out = out
        self._write_lock = threading.Lock()
        self._jobs_lock = threading.Lock()
        self._jobs: dict[str, threading.Event] = {}
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="otk-rpc")
        self.methods: dict[str, Callable[..., Any]] = {}
        self._inline: set[str] = set()
        self.running = True
        self.register("job.cancel", self._cancel, inline=True)

    # ---------------------------------------------------------------- plumbing
    def register(self, name: str, fn: Callable[..., Any], inline: bool = False) -> None:
        self.methods[name] = fn
        if inline:
            self._inline.add(name)

    def job_event(self, job_id: str) -> threading.Event:
        with self._jobs_lock:
            return self._jobs.setdefault(job_id, threading.Event())

    def _forget_job(self, job_id: str | None) -> None:
        if job_id:
            with self._jobs_lock:
                self._jobs.pop(job_id, None)

    def _cancel(self, params: dict, ctx: Context) -> dict:
        job_id = params.get("jobId")
        with self._jobs_lock:
            ev = self._jobs.get(job_id)
        if ev:
            ev.set()
        return {"cancelled": bool(ev)}

    def send(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock:
            self._out.write(line + "\n")
            self._out.flush()

    def notify(self, method: str, params: dict) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def _error(self, req_id, code: int, message: str, data: dict | None = None) -> None:
        err: dict = {"code": code, "message": message}
        if data:
            err["data"] = data
        self.send({"jsonrpc": "2.0", "id": req_id, "error": err})

    def _run(self, req_id, fn, params: dict) -> None:
        job_id = params.get("jobId") if isinstance(params, dict) else None
        ctx = Context(self, job_id)
        try:
            result = fn(params, ctx)
            if req_id is not None:
                self.send({"jsonrpc": "2.0", "id": req_id, "result": result})
        except Cancelled as exc:
            self._error(req_id, APP_ERROR, exc.message, exc.to_dict())
        except ToolkitError as exc:
            self._error(req_id, APP_ERROR, exc.message, exc.to_dict())
        except (KeyError, TypeError, ValueError) as exc:
            self._error(req_id, INVALID_PARAMS, f"Invalid request: {exc}",
                        {"code": "invalid_params", "trace": traceback.format_exc(limit=5)})
        except Exception as exc:  # report, never crash the worker
            self._error(req_id, APP_ERROR, f"Unexpected error: {exc}",
                        {"code": "internal", "trace": traceback.format_exc(limit=8)})
        finally:
            self._forget_job(job_id)

    def handle_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            self._error(None, PARSE_ERROR, f"Parse error: {exc}")
            return
        if not isinstance(req, dict) or req.get("jsonrpc") != "2.0" or "method" not in req:
            self._error(req.get("id") if isinstance(req, dict) else None, INVALID_REQUEST, "Invalid request")
            return
        req_id, method, params = req.get("id"), req["method"], req.get("params") or {}
        fn = self.methods.get(method)
        if fn is None:
            self._error(req_id, METHOD_NOT_FOUND, f"Unknown method {method}")
            return
        if isinstance(params, dict) and params.get("jobId"):
            self.job_event(params["jobId"])  # register before the job starts, so cancel can't be missed
        if method in self._inline:
            self._run(req_id, fn, params)
        else:
            self._pool.submit(self._run, req_id, fn, params)

    def serve_forever(self) -> None:
        for line in self._in:
            if not self.running:
                break
            self.handle_line(line)
        self._pool.shutdown(wait=True, cancel_futures=False)


def stdio_server() -> Server:
    """Server bound to the real stdio; anything else printed goes to stderr."""
    inp = sys.stdin
    out = sys.stdout
    for stream in (inp, out):
        try:
            stream.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    sys.stdout = sys.stderr  # keep library prints off the protocol channel
    return Server(inp, out)
