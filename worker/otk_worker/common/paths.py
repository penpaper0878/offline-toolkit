"""Safe, Unicode-preserving output names and collision-free paths."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_stem(stem: str, fallback: str = "image") -> str:
    """Keep any script (Devanagari, Arabic, ...), drop only characters Windows forbids."""
    s = _INVALID.sub("_", stem).strip().rstrip(". ")
    if not s:
        s = fallback
    if s.split(".")[0].upper() in _RESERVED:
        s = "_" + s
    return s[:180]


def render_name(template: str, **tokens) -> str:
    out = template
    for k, v in tokens.items():
        out = out.replace("{" + k + "}", str(v))
    return safe_stem(out)


def unique_path(directory: Path, stem: str, ext: str) -> Path:
    """name.ext, then 'name (1).ext', 'name (2).ext', ... Never overwrites."""
    candidate = directory / f"{stem}{ext}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){ext}"
        n += 1
    return candidate


def write_atomic(path: Path, data: bytes) -> None:
    """Write via a temp file in the same folder, then rename (no half-written outputs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".otk-", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if path.exists():
            raise FileExistsError(path)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
