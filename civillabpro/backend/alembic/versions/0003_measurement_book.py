"""Measurement book: entries of work done against an issued estimate's items (EST-004).

Each entry's measurement lines are a JSON document (JSONB on PostgreSQL); entry numbers are unique within an estimate.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21 05:32:41
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mb_entries",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("estimate_id", sa.Uuid(), nullable=False),
        sa.Column("entry_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=False),
        sa.Column("lines", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("measured_by_name", sa.String(length=200), nullable=False),
        sa.Column("checked_by_name", sa.String(length=200), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_mb_entries_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"], name=op.f("fk_mb_entries_estimate_id_estimates"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_mb_entries_org_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mb_entries")),
        sa.UniqueConstraint("estimate_id", "entry_no", name=op.f("uq_mb_entries_estimate_id")),
    )
    with op.batch_alter_table("mb_entries", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mb_entries_estimate_id"), ["estimate_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_mb_entries_org_id"), ["org_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("mb_entries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mb_entries_org_id"))
        batch_op.drop_index(batch_op.f("ix_mb_entries_estimate_id"))
    op.drop_table("mb_entries")
