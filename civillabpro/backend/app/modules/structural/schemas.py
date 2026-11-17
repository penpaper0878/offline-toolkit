from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KeyResult(BaseModel):
    label: str
    sym: str = ""
    value: float | str | None
    unit: str = ""
    dp: int = 2


class DesignResult(BaseModel):
    """What every structural engine returns, whatever the element."""

    element_type: str
    engine_version: str
    code_basis: list[str]
    status: Literal["ok", "not_ok", "stopped"]
    stop_message: str | None
    checks_passed: int
    checks_total: int
    max_utilisation: float | None
    key_results: list[KeyResult]
    data: dict[str, Any] = Field(description="Element-specific numbers, for hand checks and integrations")
    reinforcement: dict[str, Any] | None
    sheet: dict[str, Any] = Field(description="Calculation sheet: sections of steps and checks, plus flags")
    bbs: dict[str, Any] | None = Field(description="Bar bending schedule")
    quantities: dict[str, Any] | None
    drawing: dict[str, Any] | None = Field(description="Drawing model: views of primitives in millimetres")


class ElementOut(BaseModel):
    type: str
    title: str
    description: str
    engine_version: str
    code_basis: list[str]
    limitations: list[str]
    defaults: dict[str, Any]
    input_schema: dict[str, Any]


class DesignSave(BaseModel):
    element_type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    inputs: dict[str, Any]


class DesignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    inputs: dict[str, Any] | None = None


class DesignSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    project_id: uuid.UUID
    element_type: str
    name: str
    status: str
    review_status: str
    revision: int
    engine_version: str
    max_utilisation: float | None
    designed_by_name: str
    approved_by_name: str
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DesignOut(DesignSummary):
    inputs: dict[str, Any]
    result: DesignResult


class RevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    revision: int
    status: str
    review_status: str
    engine_version: str
    saved_by_name: str
    created_at: datetime
