"""Add versioned model pricing and cost attribution.

Revision ID: 20261024_0003
Revises: 20261023_0002
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision: str = "20261024_0003"
down_revision: str | None = "20261023_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("input_price_per_million_tokens", sa.Numeric(20, 8), nullable=False),
        sa.Column("output_price_per_million_tokens", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "input_price_per_million_tokens >= 0",
            name="ck_model_pricing_input_price_nonnegative",
        ),
        sa.CheckConstraint(
            "output_price_per_million_tokens >= 0",
            name="ck_model_pricing_output_price_nonnegative",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_model_pricing_effective_window",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_pricing")),
        sa.UniqueConstraint(
            "project_id",
            "provider",
            "model",
            "effective_from",
            name=op.f("uq_model_pricing_project_id"),
        ),
    )
    op.create_index(
        "ix_model_pricing_lookup",
        "model_pricing",
        ["project_id", "provider", "model", "effective_from", "effective_to"],
    )
    op.add_column("spans", sa.Column("pricing_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_spans_pricing_id_model_pricing"),
        "spans",
        "model_pricing",
        ["pricing_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "traces",
        "total_cost",
        existing_type=sa.Numeric(),
        type_=sa.Numeric(20, 12),
        existing_nullable=False,
    )
    op.alter_column(
        "spans",
        "cost",
        existing_type=sa.Numeric(),
        type_=sa.Numeric(20, 12),
        existing_nullable=False,
    )

    pricing = sa.table(
        "model_pricing",
        sa.column("id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
        sa.column("provider", sa.String()),
        sa.column("model", sa.String()),
        sa.column("input_price_per_million_tokens", sa.Numeric()),
        sa.column("output_price_per_million_tokens", sa.Numeric()),
        sa.column("currency", sa.String()),
        sa.column("source_url", sa.Text()),
        sa.column("effective_from", sa.DateTime(timezone=True)),
        sa.column("effective_to", sa.DateTime(timezone=True)),
        sa.column("created_by", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    effective_from = datetime(2026, 10, 24, tzinfo=UTC)
    created_at = datetime(2026, 10, 24, tzinfo=UTC)
    op.bulk_insert(
        pricing,
        [
            {
                "id": UUID("10000000-0000-4000-8000-000000000001"),
                "project_id": None,
                "provider": "openai",
                "model": "gpt-6-astra",
                "input_price_per_million_tokens": Decimal("10"),
                "output_price_per_million_tokens": Decimal("50"),
                "currency": "USD",
                "source_url": OPENAI_PRICING_SOURCE,
                "effective_from": effective_from,
                "effective_to": None,
                "created_by": None,
                "created_at": created_at,
            },
            {
                "id": UUID("10000000-0000-4000-8000-000000000002"),
                "project_id": None,
                "provider": "openai",
                "model": "gpt-6.1-sol",
                "input_price_per_million_tokens": Decimal("2"),
                "output_price_per_million_tokens": Decimal("10"),
                "currency": "USD",
                "source_url": OPENAI_PRICING_SOURCE,
                "effective_from": effective_from,
                "effective_to": None,
                "created_by": None,
                "created_at": created_at,
            },
            {
                "id": UUID("10000000-0000-4000-8000-000000000003"),
                "project_id": None,
                "provider": "openai",
                "model": "gpt-6-luna",
                "input_price_per_million_tokens": Decimal("0.1"),
                "output_price_per_million_tokens": Decimal("0.5"),
                "currency": "USD",
                "source_url": OPENAI_PRICING_SOURCE,
                "effective_from": effective_from,
                "effective_to": None,
                "created_by": None,
                "created_at": created_at,
            },
        ],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_spans_pricing_id_model_pricing"), "spans", type_="foreignkey")
    op.drop_column("spans", "pricing_id")
    op.alter_column(
        "spans",
        "cost",
        existing_type=sa.Numeric(20, 12),
        type_=sa.Numeric(),
        existing_nullable=False,
    )
    op.alter_column(
        "traces",
        "total_cost",
        existing_type=sa.Numeric(20, 12),
        type_=sa.Numeric(),
        existing_nullable=False,
    )
    op.drop_table("model_pricing")
