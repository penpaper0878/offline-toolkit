from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ----------------------------------------------------------------------------- schedules of rates


class SorBookImport(BaseModel):
    """A schedule of rates read from a CSV or Excel file by the client: CSV as text, Excel as base64."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    authority: str = Field("", max_length=120)
    state: str = Field("", max_length=60)
    year: int | None = Field(None, ge=1950, le=2100)
    filename: str = Field(min_length=1, max_length=200)
    content: str | None = Field(None, max_length=20_000_000)
    content_base64: str | None = Field(None, max_length=30_000_000)


class SorBookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authority: str
    state: str
    year: int | None
    source_name: str
    created_at: datetime
    item_count: int = 0


class SorImportResult(BaseModel):
    book: SorBookOut
    imported: int
    headings: int
    skipped: list[str]  # "row 12: no rate", and so on


class SorItemOut(BaseModel):
    id: uuid.UUID
    item_code: str
    chapter: str
    description: str
    unit: str
    rate: float


class SorItemPage(BaseModel):
    items: list[SorItemOut]
    total: int


# ----------------------------------------------------------------------------- rate analyses


class AnalysisLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["material", "labour", "plant", "sundries"]
    description: str = Field(min_length=1, max_length=300)
    unit: str = Field("", max_length=20)
    quantity: float = Field(ge=0, le=1e7)
    rate: float = Field(ge=0, le=1e9)


class RateAnalysisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=20)
    output_qty: float = Field(1.0, gt=0, le=1e6, description="The quantity of the item the lines produce")
    water_pct: float = Field(1.0, ge=0, le=10)
    overheads_profit_pct: float = Field(15.0, ge=0, le=50)
    lines: list[AnalysisLineIn] = Field(default_factory=list, max_length=200)


class RateAnalysisOut(RateAnalysisIn):
    id: uuid.UUID
    rate: float
    result: dict[str, Any]  # material, labour, plant, sundries, cost, water, overheads_profit, total, rate; lines: each line's amount
    updated_at: datetime


# ----------------------------------------------------------------------------- estimates


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field("", max_length=300)
    nos: float = Field(1.0, ge=0, le=1e6)
    length: float | None = Field(None, ge=0, le=1e5)
    breadth: float | None = Field(None, ge=0, le=1e5)
    depth: float | None = Field(None, ge=0, le=1e5)
    deduct: bool = False


class RateSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["sor", "analysis", "manual"] = "manual"
    sor_item_id: uuid.UUID | None = None
    book_title: str = Field("", max_length=200)
    item_code: str = Field("", max_length=40)
    analysis_id: uuid.UUID | None = None


class DesignLink(BaseModel):
    """A quantity taken from a design's result; the revision and value it was taken at are recorded."""

    model_config = ConfigDict(extra="forbid")

    design_id: uuid.UUID
    key: Literal["concrete_m3", "formwork_m2", "steel_kg"]
    revision: int | None = None
    value: float | None = None
    label: str = Field("", max_length=200)


class EstimateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    item_no: str = Field("", max_length=20)
    description: str = Field(min_length=1, max_length=4000)
    unit: str = Field(min_length=1, max_length=20)
    rate: float = Field(ge=0, le=1e9)
    rate_source: RateSource = Field(default_factory=RateSource)
    quantity_mode: Literal["measured", "design", "direct"] = "direct"
    quantity: float = Field(0.0, ge=-1e9, le=1e9)
    measurements: list[Measurement] = Field(default_factory=list, max_length=500)
    design: DesignLink | None = None


class AdditionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    pct: float = Field(ge=-100, le=100)


class EstimateDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EstimateItem] = Field(default_factory=list, max_length=2000)
    additions: list[AdditionIn] = Field(default_factory=list, max_length=20)


class EstimateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)


class EstimateSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    notes: str = Field("", max_length=4000)
    doc: EstimateDoc


class EstimateSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    revision: int
    total: float = 0.0
    item_count: int = 0
    prepared_by_name: str
    issued_by_name: str
    issued_at: datetime | None
    updated_at: datetime


class EstimateOut(EstimateSummary):
    notes: str
    doc: EstimateDoc
    result: dict  # type: ignore[type-arg]  # quantities, amounts, abstract, stale design links


class DesignQuantities(BaseModel):
    design_id: uuid.UUID
    name: str
    element_type: str
    title: str
    revision: int
    status: str
    quantities: dict[str, float]


# ----------------------------------------------------------------------------- measurement book


class MbEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1, max_length=40)
    measured_on: date
    location: str = Field("", max_length=300)
    lines: list[Measurement] = Field(min_length=1, max_length=200)


class MbLinesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[Measurement] = Field(max_length=200)


class MbEntryOut(BaseModel):
    id: uuid.UUID
    entry_no: int
    item_id: str
    measured_on: date
    location: str
    lines: list[Measurement]
    line_quantities: list[float]
    quantity: float
    status: Literal["recorded", "checked"]
    measured_by_name: str
    checked_by_name: str
    checked_at: datetime | None
    updated_at: datetime


class ItemProgressOut(BaseModel):
    item_id: str
    no: str
    description: str
    unit: str
    rate: float
    in_estimate: bool  # False for an item measured but no longer in the estimate's current revision
    estimated: float
    measured: float
    checked: float
    balance: float
    excess: float
    percent: float | None
    value_measured: float
    value_checked: float
    value_excess: float
    entries: int


class MeasurementBook(BaseModel):
    estimate_id: uuid.UUID
    open: bool  # entries can be recorded: the estimate is issued, or is a revision of an issued one
    entries: list[MbEntryOut]
    items: list[ItemProgressOut]
    value_measured: float
    value_checked: float
    value_excess: float
