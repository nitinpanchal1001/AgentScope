"""Backfill trace usage from already-recorded spans.

Revision ID: 20261024_0004
Revises: 20261024_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261024_0004"
down_revision: str | None = "20261024_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE traces AS trace
            SET
                input_tokens = CASE
                    WHEN trace.input_tokens = 0 THEN usage.input_tokens
                    ELSE trace.input_tokens
                END,
                output_tokens = CASE
                    WHEN trace.output_tokens = 0 THEN usage.output_tokens
                    ELSE trace.output_tokens
                END,
                total_tokens = CASE
                    WHEN trace.total_tokens = 0 THEN usage.total_tokens
                    ELSE trace.total_tokens
                END,
                total_cost = CASE
                    WHEN trace.total_cost = 0 THEN usage.total_cost
                    ELSE trace.total_cost
                END
            FROM (
                SELECT
                    trace_id,
                    COALESCE(SUM(input_tokens), 0) AS input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS output_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cost), 0) AS total_cost
                FROM spans
                WHERE total_tokens > 0 OR cost > 0
                GROUP BY trace_id
            ) AS usage
            WHERE trace.id = usage.trace_id
            """
        )
    )


def downgrade() -> None:
    # Historical aggregates cannot be distinguished from caller-supplied values after backfill.
    pass
