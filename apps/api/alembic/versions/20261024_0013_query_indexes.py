"""Add composite indexes for analytics and evaluation queries.

Revision ID: 20261024_0013
Revises: 20261024_0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0013"
down_revision: str | None = "20261024_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_traces_project_environment_started",
        "traces",
        ["project_id", "environment_id", "started_at"],
    )
    op.create_index(
        "ix_traces_project_started_status",
        "traces",
        ["project_id", "started_at", "status"],
    )
    op.create_index(
        "ix_spans_trace_type_status",
        "spans",
        ["trace_id", "type", "status"],
    )
    op.create_index(
        "ix_evaluation_results_project_status_created",
        "evaluation_results",
        ["project_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_project_status_created", table_name="evaluation_results")
    op.drop_index("ix_spans_trace_type_status", table_name="spans")
    op.drop_index("ix_traces_project_started_status", table_name="traces")
    op.drop_index("ix_traces_project_environment_started", table_name="traces")
