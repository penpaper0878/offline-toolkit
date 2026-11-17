from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, TimestampMixin


class Project(IdMixin, TimestampMixin, Base):
    """The unit of work every module hangs its records on."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))  # job number
    name: Mapped[str] = mapped_column(String(200))
    client: Mapped[str] = mapped_column(String(200), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    state: Mapped[str] = mapped_column(String(60), default="")  # Indian state or union territory: selects the SOR later
    project_type: Mapped[str] = mapped_column(String(40), default="building")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
