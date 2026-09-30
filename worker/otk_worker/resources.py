"""Location of shipped resources (schemas, defaults)."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def resources_dir() -> Path:
    env = os.environ.get("OTK_RESOURCES")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "resources"


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    with open(resources_dir() / "schemas" / name, encoding="utf-8") as fh:
        return json.load(fh)
