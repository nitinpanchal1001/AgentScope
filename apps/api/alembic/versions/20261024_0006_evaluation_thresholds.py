"""Persist production threshold overrides on evaluation results.

Revision ID: 20261024_0006
Revises: 20261024_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261024_0006"
down_revision: str | None = "20261024_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "production_evaluation_bindings",
        sa.Column("threshold", sa.Numeric(7, 6), nullable=True),
    )
    op.create_check_constraint(
        "ck_binding_threshold",
        "production_evaluation_bindings",
        "threshold IS NULL OR (threshold >= 0 AND threshold <= 1)",
    )
    op.add_column(
        "evaluation_results",
        sa.Column("threshold", sa.Numeric(7, 6), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE evaluation_results AS result
            SET threshold = version.threshold
            FROM evaluator_versions AS version
            WHERE result.evaluator_version_id = version.id
            """
        )
    )
    op.alter_column(
        "evaluation_results",
        "threshold",
        existing_type=sa.Numeric(7, 6),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_evaluation_result_threshold",
        "evaluation_results",
        "threshold >= 0 AND threshold <= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_evaluation_result_threshold", "evaluation_results", type_="check")
    op.drop_column("evaluation_results", "threshold")
    op.drop_constraint("ck_binding_threshold", "production_evaluation_bindings", type_="check")
    op.drop_column("production_evaluation_bindings", "threshold")
