"""Add durable experiment orchestration and per-case runs.

Revision ID: 20261024_0008
Revises: 20261024_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0008"
down_revision: str | None = "20261024_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("agent_configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("completed_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("failed_cases", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "total_cases >= 0 AND completed_cases >= 0 AND passed_cases >= 0 AND failed_cases >= 0",
            name="ck_experiment_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 100",
            name="ck_experiment_max_concurrency",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiments")),
    )
    op.create_index(
        op.f("ix_experiments_dataset_version_id"), "experiments", ["dataset_version_id"]
    )
    op.create_index(op.f("ix_experiments_environment_id"), "experiments", ["environment_id"])
    op.create_index(op.f("ix_experiments_organization_id"), "experiments", ["organization_id"])
    op.create_index(op.f("ix_experiments_project_id"), "experiments", ["project_id"])
    op.create_index("ix_experiments_project_created", "experiments", ["project_id", "created_at"])
    op.create_index("ix_experiments_project_status", "experiments", ["project_id", "status"])

    op.create_table(
        "experiment_evaluator_versions",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("evaluator_version_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluator_version_id"], ["evaluator_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint(
            "experiment_id", "evaluator_version_id", name=op.f("pk_experiment_evaluator_versions")
        ),
    )
    op.create_index(
        op.f("ix_experiment_evaluator_versions_evaluator_version_id"),
        "experiment_evaluator_versions",
        ["evaluator_version_id"],
    )

    op.create_table(
        "experiment_runs",
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_item_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Numeric(20, 8), nullable=False),
        sa.Column("evaluation_score", sa.Numeric(7, 6), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("error_type", sa.String(120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("ordinal > 0", name="ck_experiment_run_ordinal"),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 AND total_cost >= 0",
            name="ck_experiment_run_usage_nonnegative",
        ),
        sa.ForeignKeyConstraint(["dataset_item_id"], ["dataset_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_runs")),
        sa.UniqueConstraint(
            "experiment_id",
            "dataset_item_id",
            name=op.f("uq_experiment_runs_experiment_id"),
        ),
    )
    op.create_index(
        op.f("ix_experiment_runs_dataset_item_id"), "experiment_runs", ["dataset_item_id"]
    )
    op.create_index(op.f("ix_experiment_runs_experiment_id"), "experiment_runs", ["experiment_id"])
    op.create_index(op.f("ix_experiment_runs_trace_id"), "experiment_runs", ["trace_id"])
    op.create_index(
        "ix_experiment_runs_experiment_ordinal", "experiment_runs", ["experiment_id", "ordinal"]
    )
    op.create_index(
        "ix_experiment_runs_experiment_status", "experiment_runs", ["experiment_id", "status"]
    )

    op.add_column("evaluation_results", sa.Column("experiment_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_evaluation_results_experiment_run_id_experiment_runs",
        "evaluation_results",
        "experiment_runs",
        ["experiment_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_evaluation_results_experiment_run_id"),
        "evaluation_results",
        ["experiment_run_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_results_experiment_run_id"), table_name="evaluation_results")
    op.drop_constraint(
        "fk_evaluation_results_experiment_run_id_experiment_runs",
        "evaluation_results",
        type_="foreignkey",
    )
    op.drop_column("evaluation_results", "experiment_run_id")
    op.drop_table("experiment_runs")
    op.drop_table("experiment_evaluator_versions")
    op.drop_table("experiments")
