"""Platform core (organisations, users, sessions, audit, projects) and structural designs.

Portable across PostgreSQL and SQLite: UUID keys, timezone-aware timestamps, JSON documents
(JSONB on PostgreSQL).

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-16 08:13:12.171775
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "users",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("designation", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_users_org_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)
        batch_op.create_index(batch_op.f("ix_users_org_id"), ["org_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_name", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_audit_log_org_id_organizations"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_audit_log_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.create_index("ix_audit_log_org_created", ["org_id", "created_at"], unique=False)

    op.create_table(
        "projects",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("client", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=60), nullable=False),
        sa.Column("project_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_projects_created_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], name=op.f("fk_projects_org_id_organizations"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("org_id", "code", name=op.f("uq_projects_org_id")),
    )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_projects_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_projects_status"), ["status"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_refresh_tokens_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_refresh_tokens_user_id"), ["user_id"], unique=False)

    op.create_table(
        "structural_designs",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("element_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("review_status", sa.String(length=12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column("max_utilisation", sa.Float(), nullable=True),
        sa.Column("inputs", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("designed_by", sa.Uuid(), nullable=True),
        sa.Column("designed_by_name", sa.String(length=200), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_by_name", sa.String(length=200), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name=op.f("fk_structural_designs_approved_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["designed_by"], ["users.id"], name=op.f("fk_structural_designs_designed_by_users"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_structural_designs_org_id_organizations"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_structural_designs_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_structural_designs")),
    )
    with op.batch_alter_table("structural_designs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_structural_designs_org_id"), ["org_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_structural_designs_project_id"), ["project_id"], unique=False)
        batch_op.create_index("ix_structural_designs_project_type", ["project_id", "element_type"], unique=False)

    op.create_table(
        "structural_design_revisions",
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("review_status", sa.String(length=12), nullable=False),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column("inputs", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("result", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("saved_by_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["design_id"],
            ["structural_designs.id"],
            name=op.f("fk_structural_design_revisions_design_id_structural_designs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_structural_design_revisions")),
        sa.UniqueConstraint("design_id", "revision", name=op.f("uq_structural_design_revisions_design_id")),
    )
    with op.batch_alter_table("structural_design_revisions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_structural_design_revisions_design_id"), ["design_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("structural_design_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_structural_design_revisions_design_id"))

    op.drop_table("structural_design_revisions")
    with op.batch_alter_table("structural_designs", schema=None) as batch_op:
        batch_op.drop_index("ix_structural_designs_project_type")
        batch_op.drop_index(batch_op.f("ix_structural_designs_project_id"))
        batch_op.drop_index(batch_op.f("ix_structural_designs_org_id"))

    op.drop_table("structural_designs")
    with op.batch_alter_table("refresh_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_refresh_tokens_user_id"))

    op.drop_table("refresh_tokens")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_projects_status"))
        batch_op.drop_index(batch_op.f("ix_projects_org_id"))

    op.drop_table("projects")
    with op.batch_alter_table("audit_log", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_log_org_created")

    op.drop_table("audit_log")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_org_id"))
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
    op.drop_table("organizations")
