"""Resizer settings: schema validation (same schema the UI uses) and defaults."""

from __future__ import annotations

import copy

from jsonschema import Draft202012Validator

from ..errors import InputError
from ..resources import load_schema

SCHEMA_FILE = "resizer-settings.schema.json"


def _defaults(schema: dict) -> dict:
    return {k: copy.deepcopy(v["default"]) for k, v in schema["properties"].items() if "default" in v}


def validate(raw: dict) -> dict:
    """Validate and fill defaults. Raises InputError with every problem listed."""
    schema = load_schema(SCHEMA_FILE)
    if not isinstance(raw, dict):
        raise InputError("Settings must be an object.")
    errors = sorted(Draft202012Validator(schema).iter_errors(raw), key=lambda e: list(e.path))
    if errors:
        lines = [f"{'/'.join(str(p) for p in e.path) or '(settings)'}: {e.message}" for e in errors]
        raise InputError("Invalid resizer settings:\n" + "\n".join(lines), detail={"errors": lines})
    out = _defaults(schema)
    out.update(raw)
    rng = out.get("sizeRange")
    if rng and rng.get("min") is not None and rng.get("max") is not None and rng["min"] > rng["max"]:
        raise InputError("The minimum file size is larger than the maximum.")
    if out["unit"] == "px" and (out["width"] != int(out["width"]) or out["height"] != int(out["height"])):
        raise InputError("Pixel sizes must be whole numbers.")
    return out
