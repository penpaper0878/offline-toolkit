"""The project archive: a portable JSON file of one project, its designs and their revision history, and its estimates.

Version 2 adds the estimates (and each design's reference, to which their quantities link); version 1 files still import. A reader
refuses a format or version it does not know. Results travel as they were calculated, with the engine
version that made them, so an issued calculation can be reproduced wherever the archive is opened.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.schemas import ProjectBase, ProjectOut

FORMAT = "civillabpro.project"
FORMAT_VERSION = 2
MAX_DESIGNS = 2000
MAX_ESTIMATES = 500


class RevisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    status: Literal["ok", "not_ok", "stopped"]
    review_status: Literal["draft", "approved"]
    engine_version: str = Field(min_length=1, max_length=20)
    inputs: dict[str, Any]
    result: dict[str, Any]
    saved_by_name: str = Field("", max_length=200)
    created_at: datetime


class DesignRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str | None = Field(None, max_length=40)  # the design's identifier where it was exported: estimates link to it
    element_type: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    status: Literal["ok", "not_ok", "stopped"]
    review_status: Literal["draft", "approved"]
    revision: int = Field(ge=0)
    engine_version: str = Field(min_length=1, max_length=20)
    max_utilisation: float | None = None
    inputs: dict[str, Any]
    result: dict[str, Any]
    designed_by_name: str = Field("", max_length=200)
    approved_by_name: str = Field("", max_length=200)
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    revisions: list[RevisionRecord] = Field(default_factory=list, max_length=500)


class EstimateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    status: Literal["draft", "issued"]
    revision: int = Field(ge=0)
    doc: dict[str, Any]
    notes: str = Field("", max_length=4000)
    prepared_by_name: str = Field("", max_length=200)
    issued_by_name: str = Field("", max_length=200)
    issued_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectRecord(ProjectBase):
    model_config = ConfigDict(extra="forbid")
    start_date: date | None = None
    end_date: date | None = None


class ProjectArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["civillabpro.project"]
    format_version: Literal[1, 2]
    app_version: str = Field(max_length=40)
    exported_at: datetime
    organization: str = Field("", max_length=200)
    exported_by: str = Field("", max_length=200)
    project: ProjectRecord
    designs: list[DesignRecord] = Field(default_factory=list, max_length=MAX_DESIGNS)
    estimates: list[EstimateRecord] = Field(default_factory=list, max_length=MAX_ESTIMATES)


class ImportResult(BaseModel):
    project: ProjectOut
    designs: int
    revisions: int
    estimates: int = 0
    code_changed: bool
    note: str
