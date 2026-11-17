from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ProjectType = Literal["building", "water_supply", "sewerage", "highway", "bridge", "irrigation", "industrial", "other"]
ProjectStatus = Literal["planning", "active", "on_hold", "completed"]


class ProjectBase(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _./-]*$", description="Job number")
    name: str = Field(min_length=2, max_length=200)
    client: str = Field("", max_length=200)
    location: str = Field("", max_length=200)
    state: str = Field("", max_length=60)
    project_type: ProjectType = "building"
    status: ProjectStatus = "active"
    description: str = Field("", max_length=4000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def _dates(self) -> ProjectBase:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("The end date is before the start date.")
        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=200)
    client: str | None = Field(None, max_length=200)
    location: str | None = Field(None, max_length=200)
    state: str | None = Field(None, max_length=60)
    project_type: ProjectType | None = None
    status: ProjectStatus | None = None
    description: str | None = Field(None, max_length=4000)
    start_date: date | None = None
    end_date: date | None = None


class ProjectOut(ProjectBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    design_count: int = 0


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
