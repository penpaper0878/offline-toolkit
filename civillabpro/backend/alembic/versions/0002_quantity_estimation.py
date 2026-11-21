"""Quantity estimation: schedules of rates and their items, rate analyses, and estimates.

Money in whole paise (BigInteger), exact on PostgreSQL and SQLite; an estimate's items and a rate analysis's constituents
are JSON documents (JSONB on PostgreSQL).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21 02:43:17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_analyses",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("doc", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("rate_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_rate_analyses_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_rate_analyses_org_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_analyses")),
    )
    with op.batch_alter_table("rate_analyses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_rate_analyses_org_id"), ["org_id"], unique=False)

    op.create_table(
        "sor_books",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("authority", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=60), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_sor_books_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_sor_books_org_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sor_books")),
        sa.UniqueConstraint("org_id", "title", name=op.f("uq_sor_books_org_id")),
    )
    with op.batch_alter_table("sor_books", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sor_books_org_id"), ["org_id"], unique=False)

    op.create_table(
        "estimates",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("doc", sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"), nullable=False),
        sa.Column("total_paise", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("prepared_by_name", sa.String(length=200), nullable=False),
        sa.Column("issued_by_name", sa.String(length=200), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_estimates_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_estimates_org_id_organizations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_estimates_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estimates")),
    )
    with op.batch_alter_table("estimates", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_estimates_org_id"), ["org_id"], unique=False)
        batch_op.create_index("ix_estimates_project", ["project_id"], unique=False)

    op.create_table(
        "sor_items",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("item_code", sa.String(length=40), nullable=False),
        sa.Column("chapter", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("rate_paise", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["sor_books.id"], name=op.f("fk_sor_items_book_id_sor_books"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sor_items")),
    )
    with op.batch_alter_table("sor_items", schema=None) as batch_op:
        batch_op.create_index("ix_sor_items_book_code", ["book_id", "item_code"], unique=False)
        batch_op.create_index(batch_op.f("ix_sor_items_book_id"), ["book_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("sor_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sor_items_book_id"))
        batch_op.drop_index("ix_sor_items_book_code")

    op.drop_table("sor_items")
    with op.batch_alter_table("estimates", schema=None) as batch_op:
        batch_op.drop_index("ix_estimates_project")
        batch_op.drop_index(batch_op.f("ix_estimates_org_id"))

    op.drop_table("estimates")
    with op.batch_alter_table("sor_books", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sor_books_org_id"))

    op.drop_table("sor_books")
    with op.batch_alter_table("rate_analyses", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rate_analyses_org_id"))

    op.drop_table("rate_analyses")
