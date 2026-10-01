"""Bundled command-line engines: finding them, and running them safely.

Engines are looked up in OTK_ENGINES (the app passes resources/engines in a
packaged build, engines/<platform> in development) and then on PATH. Every
engine runs:

- in its own process group (POSIX) or with a tree kill (Windows), so cancel
  and timeouts never leave orphaned soffice/gs processes;
- with a sanitised environment: proxies point at a dead port and Java proxy
  options from the user's environment are removed.
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from ..errors import Cancelled, ToolkitError

WIN = os.name == "nt"


class EngineMissing(ToolkitError):
    code = "engine_missing"


class EngineFailed(ToolkitError):
    code = "engine_failed"


def platform_tag() -> str:
    arch = {"x86_64": "x64", "AMD64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
    osname = "win" if WIN else ("mac" if os.uname().sysname == "Darwin" else "linux")
    return f"{osname}-{arch}"


def engines_dir() -> Path:
    env = os.environ.get("OTK_ENGINES")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "engines" / platform_tag()


# name -> (relative paths inside the engines dir, names to look for on PATH)
_BINARIES: dict[str, tuple[list[str], list[str]]] = {
    "soffice": (["libreoffice/program/soffice.exe", "libreoffice/program/soffice", "LibreOffice.app/Contents/MacOS/soffice"],
                ["soffice", "libreoffice"]),
    "pandoc": (["pandoc/pandoc.exe", "pandoc/pandoc", "pandoc/bin/pandoc"], ["pandoc"]),
    "gs": (["ghostscript/bin/gswin64c.exe", "ghostscript/bin/gs"], ["gswin64c", "gs"]),
    "tesseract": (["tesseract/tesseract.exe", "tesseract/tesseract", "tesseract/bin/tesseract"], ["tesseract"]),
    "java": (["jre/bin/java.exe", "jre/bin/java"], ["java"]),
    "resvg": (["resvg/resvg.exe", "resvg/resvg"], ["resvg"]),
}

_HINT = {
    "soffice": "LibreOffice",
    "pandoc": "Pandoc",
    "gs": "Ghostscript",
    "tesseract": "Tesseract OCR",
    "java": "the Java runtime (for veraPDF)",
    "resvg": "resvg",
}


@dataclass
class Found:
    name: str
    path: str
    bundled: bool


_cache: dict[str, Found | None] = {}
_cache_lock = threading.Lock()


def find(name: str) -> Found | None:
    with _cache_lock:
        if name in _cache:
            return _cache[name]
    rels, names = _BINARIES[name]
    root = engines_dir()
    hit: Found | None = None
    for rel in rels:
        p = root / rel
        if p.is_file():
            hit = Found(name, str(p), True)
            break
    if hit is None:
        for n in names:
            w = shutil.which(n)
            if w:
                hit = Found(name, w, False)
                break
    with _cache_lock:
        _cache[name] = hit
    return hit


def require(name: str) -> str:
    f = find(name)
    if not f:
        raise EngineMissing(f"{_HINT.get(name, name)} is not installed with this copy of the app, so this conversion "
                            "cannot run. Reinstall the app, or see README → Troubleshooting.")
    return f.path


def verapdf_classpath() -> str | None:
    lib = engines_dir() / "verapdf" / "lib"
    if lib.is_dir() and any(lib.glob("*.jar")):
        return str(lib / "*")
    env = os.environ.get("OTK_VERAPDF_LIB")
    return f"{env}{os.sep}*" if env else None


def tessdata_dir() -> str | None:
    p = engines_dir() / "tesseract" / "tessdata"
    return str(p) if p.is_dir() else None


# engine -> its entry in the build's manifest.json (scripts/fetch_engines.py)
_MANIFEST_KEY = {"soffice": "libreoffice", "pandoc": "pandoc", "gs": "ghostscript", "tesseract": "tesseract",
                 "java": "jre", "resvg": "resvg", "verapdf": "verapdf"}


def manifest() -> dict:
    """Versions recorded when the bundled engines were fetched ({} when there is no bundle)."""
    import json
    try:
        data = json.loads((engines_dir() / "manifest.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def status() -> dict:
    """What is available (Settings → Diagnostics and the converter pre-flight)."""
    out = {}
    for name in _BINARIES:
        f = find(name)
        out[name] = {"available": bool(f), "path": f.path if f else None, "bundled": bool(f and f.bundled)}
    cp = verapdf_classpath()
    out["verapdf"] = {"available": bool(cp and find("java")), "path": cp, "bundled": bool(cp)}
    versions = manifest()
    for name, entry in out.items():
        v = versions.get(_MANIFEST_KEY.get(name, name))
        if entry["bundled"] and isinstance(v, str):
            entry["version"] = v
    return out


def clean_env(extra: dict | None = None) -> dict:
    env = dict(os.environ)
    for k in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "http_proxy", "https_proxy", "no_proxy",
              "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(k, None)
    env.update({"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": ""})
    # Make bundled engines visible to each other (OCRmyPDF looks for tesseract and gs on PATH).
    root = engines_dir()
    bins = [root / "tesseract", root / "ghostscript" / "bin", root / "pandoc", root / "jre" / "bin"]
    env["PATH"] = os.pathsep.join([str(b) for b in bins if b.is_dir()] + [env.get("PATH", "")])
    td = tessdata_dir()
    if td:
        env["TESSDATA_PREFIX"] = td
    if extra:
        env.update(extra)
    return env


def java_net_blockers() -> list[str]:
    return ["-Djava.net.useSystemProxies=false", "-Dhttp.proxyHost=127.0.0.1", "-Dhttp.proxyPort=9",
            "-Dhttps.proxyHost=127.0.0.1", "-Dhttps.proxyPort=9", "-DsocksProxyHost=127.0.0.1", "-DsocksProxyPort=9",
            "-Djava.awt.headless=true"]


def _kill_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run(cmd: Sequence[str], *, check: Callable[[], None] = lambda: None, timeout: float = 600, cwd: str | None = None,
        env: dict | None = None, what: str | None = None, ok_codes: Sequence[int] = (0,)) -> subprocess.CompletedProcess:
    """Run an engine; cancel via `check()` (raises Cancelled) or timeout kills the whole process tree."""
    label = what or Path(cmd[0]).stem
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        kwargs: dict = dict(stdout=out, stderr=err, stdin=subprocess.DEVNULL, cwd=cwd, env=env or clean_env())
        if WIN:
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(list(map(str, cmd)), **kwargs)
        except FileNotFoundError as exc:
            raise EngineMissing(f"Could not start {label}: {exc}") from exc
        start = time.monotonic()
        try:
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                check()
                if time.monotonic() - start > timeout:
                    _kill_tree(proc)
                    raise EngineFailed(f"{label} did not finish within {int(timeout)} s and was stopped.", code="timeout")
        except Cancelled:
            _kill_tree(proc)
            raise
        if not WIN:  # anything the engine left behind in its process group (e.g. soffice.bin)
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", "replace")
        stderr = err.read().decode("utf-8", "replace")
    result = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if proc.returncode not in ok_codes:
        tail = (stderr.strip() or stdout.strip())[-800:]
        raise EngineFailed(f"{label} failed (exit code {proc.returncode}). {tail}", detail={"stderr": stderr[-4000:]})
    return result
