"""Add experiment baselines and quality gates.

Revision ID: 20261024_0009
Revises: 20261024_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261024_0009"
down_revision: str | None = "20261024_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiment_baselines",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiment_baselines")),
        sa.UniqueConstraint("dataset_id", name="uq_experiment_baselines_dataset"),
        sa.UniqueConstraint("experiment_id", name="uq_experiment_baselines_experiment"),
    )
    for column in ("dataset_id", "experiment_id", "organization_id", "project_id"):
        op.create_index(op.f(f"ix_experiment_baselines_{column}"), "experiment_baselines", [column])

    op.create_table(
        "quality_gates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_gates")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_quality_gates_project_id")),
    )
    op.create_index(op.f("ix_quality_gates_organization_id"), "quality_gates", ["organization_id"])
    op.create_index(op.f("ix_quality_gates_project_id"), "quality_gates", ["project_id"])

    op.create_table(
        "quality_gate_results",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("quality_gate_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_experiment_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_experiment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("comparisons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("violations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rule_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["baseline_experiment_id"], ["experiments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_experiment_id"], ["experiments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quality_gate_id"], ["quality_gates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quality_gate_results")),
    )
    for column in (
        "baseline_experiment_id",
        "candidate_experiment_id",
        "organization_id",
        "project_id",
        "quality_gate_id",
        "evaluated_at",
    ):
        op.create_index(op.f(f"ix_quality_gate_results_{column}"), "quality_gate_results", [column])
    op.create_index(
        "ix_quality_gate_results_candidate_evaluated",
        "quality_gate_results",
        ["candidate_experiment_id", "evaluated_at"],
    )


def downgrade() -> None:
    op.drop_table("quality_gate_results")
    op.drop_table("quality_gates")
    op.drop_table("experiment_baselines")
