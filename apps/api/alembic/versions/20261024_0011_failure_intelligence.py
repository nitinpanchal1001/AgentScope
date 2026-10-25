"""Add failure intelligence records and clusters.

Revision ID: 20261024_0011
Revises: 20261024_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0011"
down_revision: str | None = "20261024_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "failure_records",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("failure_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("document", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("vector_point_id", sa.Uuid(), nullable=False),
        sa.Column("agent_version", sa.String(120), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_failure_records")),
        sa.UniqueConstraint("trace_id", name="uq_failure_records_trace_id"),
    )
    for column in (
        "detected_at",
        "failure_type",
        "organization_id",
        "project_id",
        "trace_id",
        "vector_point_id",
    ):
        op.create_index(op.f(f"ix_failure_records_{column}"), "failure_records", [column])
    op.create_index(
        "ix_failure_records_project_created", "failure_records", ["project_id", "created_at"]
    )
    op.create_index(
        "ix_failure_records_project_type", "failure_records", ["project_id", "failure_type"]
    )

    op.create_table(
        "failure_clusters",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("probable_cause", sa.Text(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("summary_source", sa.String(32), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("failure_percentage", sa.Numeric(7, 4), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "representative_failure_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_failure_clusters")),
    )
    for column in ("last_seen", "organization_id", "project_id"):
        op.create_index(op.f(f"ix_failure_clusters_{column}"), "failure_clusters", [column])
    op.create_index(
        "ix_failure_clusters_project_last_seen",
        "failure_clusters",
        ["project_id", "last_seen"],
    )

    op.create_table(
        "failure_cluster_members",
        sa.Column("cluster_id", sa.Uuid(), nullable=False),
        sa.Column("failure_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["failure_clusters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["failure_id"], ["failure_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "cluster_id", "failure_id", name=op.f("pk_failure_cluster_members")
        ),
    )
    op.create_index(
        op.f("ix_failure_cluster_members_failure_id"),
        "failure_cluster_members",
        ["failure_id"],
    )


def downgrade() -> None:
    op.drop_table("failure_cluster_members")
    op.drop_table("failure_clusters")
    op.drop_table("failure_records")
