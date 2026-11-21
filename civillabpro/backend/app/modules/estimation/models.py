"""Quantity estimation: schedules of rates, rate analyses and estimates.

Money is kept in whole paise (exact on every database). An estimate's items, with their measurements and the links of their
quantities to designs, are one document beside the columns lists read, as a design's inputs are.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, IdMixin, JSONDoc, TimestampMixin, UTCDateTime


class SorBook(IdMixin, TimestampMixin, Base):
    """An edition of a schedule of rates, imported by the organisation (CPWD DSR, a state's SOR, its own)."""

    __tablename__ = "sor_books"
    __table_args__ = (UniqueConstraint("org_id", "title"),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    authority: Mapped[str] = mapped_column(String(120), default="")
    state: Mapped[str] = mapped_column(String(60), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")  # the file it was imported from
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class SorItem(IdMixin, Base):
    __tablename__ = "sor_items"
    __table_args__ = (Index("ix_sor_items_book_code", "book_id", "item_code"),)

    book_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sor_books.id", ondelete="CASCADE"), index=True)
    item_code: Mapped[str] = mapped_column(String(40))
    chapter: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(20))
    rate_paise: Mapped[int] = mapped_column(BigInteger)
    seq: Mapped[int] = mapped_column(Integer, default=0)  # the order in the schedule


class RateAnalysis(IdMixin, TimestampMixin, Base):
    """An analysed rate of the organisation: its constituents and percentages are a document; the rate is kept for lists."""

    __tablename__ = "rate_analyses"

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    unit: Mapped[str] = mapped_column(String(20))
    doc: Mapped[dict[str, Any]] = mapped_column(JSONDoc)  # output_qty, water_pct, overheads_profit_pct, lines
    rate_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Estimate(IdMixin, TimestampMixin, Base):
    """A project's estimate: items, their measurements and design links, and the additions of the abstract."""

    __tablename__ = "estimates"
    __table_args__ = (Index("ix_estimates_project", "project_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft, issued
    revision: Mapped[int] = mapped_column(Integer, default=0)
    doc: Mapped[dict[str, Any]] = mapped_column(JSONDoc)  # items, additions
    total_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    prepared_by_name: Mapped[str] = mapped_column(String(200), default="")
    issued_by_name: Mapped[str] = mapped_column(String(200), default="")
    issued_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class MbEntry(IdMixin, TimestampMixin, Base):
    """An entry of the measurement book: work done on one item of an issued estimate, measured on a date and checked by a
    second person. A checked entry is not changed."""

    __tablename__ = "mb_entries"
    __table_args__ = (UniqueConstraint("estimate_id", "entry_no"),)

    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    estimate_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("estimates.id", ondelete="CASCADE"), index=True)
    entry_no: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[str] = mapped_column(String(40))  # the item's identifier in the estimate's document
    measured_on: Mapped[date] = mapped_column(Date)
    location: Mapped[str] = mapped_column(String(300), default="")
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONDoc)  # description, nos, length, breadth, depth, deduct
    status: Mapped[str] = mapped_column(String(12), default="recorded")  # recorded, checked
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    measured_by_name: Mapped[str] = mapped_column(String(200), default="")
    checked_by_name: Mapped[str] = mapped_column(String(200), default="")
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
