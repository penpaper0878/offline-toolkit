from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, JSONDoc, TimestampMixin, UTCDateTime, utcnow


class StructuralDesign(IdMixin, TimestampMixin, Base):
    """One designed element. Inputs and the full result are stored as documents so every
    element type shares this table; the columns beside them are what lists and dashboards query."""

    __tablename__ = "structural_designs"
    __table_args__ = (Index("ix_structural_designs_project_type", "project_id", "element_type"),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    element_type: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12))  # ok, not_ok, stopped
    review_status: Mapped[str] = mapped_column(String(12), default="draft")  # draft, approved
    revision: Mapped[int] = mapped_column(Integer, default=0)
    engine_version: Mapped[str] = mapped_column(String(20))
    max_utilisation: Mapped[float | None] = mapped_column(Float, nullable=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONDoc)
    result: Mapped[dict[str, Any]] = mapped_column(JSONDoc)
    designed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    designed_by_name: Mapped[str] = mapped_column(String(200), default="")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_name: Mapped[str] = mapped_column(String(200), default="")
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class StructuralDesignRevision(IdMixin, Base):
    """Superseded states of a design, kept so an issued calculation can always be reproduced."""

    __tablename__ = "structural_design_revisions"
    __table_args__ = (UniqueConstraint("design_id", "revision"),)

    design_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("structural_designs.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12))
    review_status: Mapped[str] = mapped_column(String(12))
    engine_version: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONDoc)
    result: Mapped[dict[str, Any]] = mapped_column(JSONDoc)
    saved_by_name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
