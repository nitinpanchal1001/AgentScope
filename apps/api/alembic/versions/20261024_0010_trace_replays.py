"""Add immutable trace replay records.

Revision ID: 20261024_0010
Revises: 20261024_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0010"
down_revision: str | None = "20261024_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trace_replays",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("original_trace_id", sa.Uuid(), nullable=False),
        sa.Column("replay_trace_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("agent_configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "effective_configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("error_type", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["original_trace_id"], ["traces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_trace_id"], ["traces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trace_replays")),
        sa.UniqueConstraint("replay_trace_id", name=op.f("uq_trace_replays_replay_trace_id")),
    )
    for column in (
        "environment_id",
        "organization_id",
        "original_trace_id",
        "project_id",
        "replay_trace_id",
    ):
        op.create_index(op.f(f"ix_trace_replays_{column}"), "trace_replays", [column])
    op.create_index(
        "ix_trace_replays_original_created",
        "trace_replays",
        ["original_trace_id", "created_at"],
    )
    op.create_index("ix_trace_replays_project_status", "trace_replays", ["project_id", "status"])


def downgrade() -> None:
    op.drop_table("trace_replays")
