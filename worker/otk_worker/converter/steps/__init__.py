"""Conversion steps, one function per edge id in routes.json.

A step gets the job's StepContext, the input Artifact and the edge's target
format id, and returns the output Artifact. Steps only write inside the job's
work folder.
"""

from __future__ import annotations

from typing import Callable

from ..context import Artifact, StepContext

StepFn = Callable[[StepContext, Artifact, str], Artifact]
STEPS: dict[str, StepFn] = {}


def step(*edge_ids: str) -> Callable[[StepFn], StepFn]:
    def deco(fn: StepFn) -> StepFn:
        for eid in edge_ids:
            if eid in STEPS:
                raise RuntimeError(f"step {eid} registered twice")
            STEPS[eid] = fn
        return fn
    return deco


def load_all() -> dict[str, StepFn]:
    """Import every step module (they register themselves)."""
    from . import docmodel_out, office, ocr_out, pdf, raster, sheets, slides, web  # noqa: F401
    return STEPS
