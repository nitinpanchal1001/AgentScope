"""Add versioned evaluators, production bindings, and evaluation results.

Revision ID: 20261024_0005
Revises: 20261024_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0005"
down_revision: str | None = "20261024_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("traces", sa.Column("evaluation_score", sa.Numeric(7, 6), nullable=True))
    op.create_index(
        "ix_traces_project_evaluation_score",
        "traces",
        ["project_id", "evaluation_score"],
    )

    op.create_table(
        "evaluators",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluators")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_evaluators_project_id")),
    )
    op.create_index(op.f("ix_evaluators_organization_id"), "evaluators", ["organization_id"])
    op.create_index(op.f("ix_evaluators_project_id"), "evaluators", ["project_id"])

    op.create_table(
        "evaluator_versions",
        sa.Column("evaluator_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("threshold", sa.Numeric(7, 6), nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("rubric", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("threshold >= 0 AND threshold <= 1", name="ck_evaluator_threshold"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["evaluator_id"], ["evaluators.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluator_versions")),
        sa.UniqueConstraint(
            "evaluator_id", "version", name=op.f("uq_evaluator_versions_evaluator_id")
        ),
    )
    op.create_index(
        "ix_evaluator_versions_evaluator_created",
        "evaluator_versions",
        ["evaluator_id", "created_at"],
    )
    op.create_index(
        op.f("ix_evaluator_versions_evaluator_id"),
        "evaluator_versions",
        ["evaluator_id"],
    )

    op.create_table(
        "production_evaluation_bindings",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_version_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sample_rate", sa.Numeric(7, 6), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sample_rate >= 0 AND sample_rate <= 1", name="ck_binding_sample_rate"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evaluator_version_id"], ["evaluator_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_production_evaluation_bindings")),
        sa.UniqueConstraint(
            "environment_id",
            "evaluator_version_id",
            name=op.f("uq_production_evaluation_bindings_environment_id"),
        ),
    )
    op.create_index(
        "ix_evaluation_bindings_project_enabled",
        "production_evaluation_bindings",
        ["project_id", "enabled"],
    )
    op.create_index(
        op.f("ix_production_evaluation_bindings_environment_id"),
        "production_evaluation_bindings",
        ["environment_id"],
    )
    op.create_index(
        op.f("ix_production_evaluation_bindings_evaluator_version_id"),
        "production_evaluation_bindings",
        ["evaluator_version_id"],
    )
    op.create_index(
        op.f("ix_production_evaluation_bindings_project_id"),
        "production_evaluation_bindings",
        ["project_id"],
    )

    op.create_table(
        "evaluation_results",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_version_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Numeric(7, 6), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_type", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name="ck_evaluation_result_score",
        ),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evaluator_version_id"], ["evaluator_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_results")),
        sa.UniqueConstraint(
            "trace_id",
            "evaluator_version_id",
            "source",
            name=op.f("uq_evaluation_results_trace_id"),
        ),
    )
    op.create_index(
        op.f("ix_evaluation_results_environment_id"),
        "evaluation_results",
        ["environment_id"],
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluator_version_id"),
        "evaluation_results",
        ["evaluator_version_id"],
    )
    op.create_index(
        op.f("ix_evaluation_results_organization_id"),
        "evaluation_results",
        ["organization_id"],
    )
    op.create_index(op.f("ix_evaluation_results_project_id"), "evaluation_results", ["project_id"])
    op.create_index(
        "ix_evaluation_results_project_created",
        "evaluation_results",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_evaluation_results_status_created",
        "evaluation_results",
        ["status", "created_at"],
    )
    op.create_index("ix_evaluation_results_trace", "evaluation_results", ["trace_id"])


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("production_evaluation_bindings")
    op.drop_table("evaluator_versions")
    op.drop_table("evaluators")
    op.drop_index("ix_traces_project_evaluation_score", table_name="traces")
    op.drop_column("traces", "evaluation_score")
