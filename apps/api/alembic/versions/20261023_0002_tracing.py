"""Create Phase 2 trace, span, and idempotency storage.

Revision ID: 20261023_0002
Revises: 20261023_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261023_0002"
down_revision: str | None = "20261023_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    trace_status = sa.Enum(
        "UNSET",
        "RUNNING",
        "SUCCESS",
        "ERROR",
        "CANCELLED",
        name="tracestatus",
        native_enum=False,
        length=16,
    )
    failure_type = sa.Enum(
        "LLM_ERROR",
        "TOOL_ERROR",
        "RETRIEVAL_ERROR",
        "TIMEOUT",
        "RATE_LIMIT",
        "AUTH_ERROR",
        "PARSING_ERROR",
        "AGENT_LOOP",
        "EVALUATION_FAILURE",
        "QUALITY_FAILURE",
        "UNKNOWN",
        name="failuretype",
        native_enum=False,
        length=32,
    )
    op.create_table(
        "traces",
        sa.Column("external_trace_id", sa.String(128), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", trace_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_cost", sa.Numeric(), nullable=False),
        sa.Column("agent_version", sa.String(120), nullable=True),
        sa.Column("session_id", sa.String(200), nullable=True),
        sa.Column("user_identifier", sa.String(200), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_type", failure_type, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_traces")),
        sa.UniqueConstraint("project_id", "external_trace_id", name=op.f("uq_traces_project_id")),
    )
    op.create_index("ix_traces_project_created", "traces", ["project_id", "created_at"])
    op.create_index(
        "ix_traces_environment_created",
        "traces",
        ["environment_id", "created_at"],
    )
    op.create_index("ix_traces_project_status", "traces", ["project_id", "status"])
    op.create_index("ix_traces_project_agent_version", "traces", ["project_id", "agent_version"])

    span_type = sa.Enum(
        "AGENT",
        "LLM",
        "TOOL",
        "RETRIEVAL",
        "EMBEDDING",
        "CHAIN",
        "CUSTOM",
        name="spantype",
        native_enum=False,
        length=16,
    )
    op.create_table(
        "spans",
        sa.Column("external_span_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("parent_span_id", sa.Uuid(), nullable=True),
        sa.Column("type", span_type, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider", sa.String(100), nullable=True),
        sa.Column("model", sa.String(160), nullable=True),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(), nullable=False),
        sa.Column("status", trace_status, nullable=False),
        sa.Column("error_type", failure_type, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["trace_id"], ["traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_span_id"], ["spans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spans")),
        sa.UniqueConstraint("trace_id", "external_span_id", name=op.f("uq_spans_trace_id")),
    )
    op.create_index("ix_spans_trace", "spans", ["trace_id"])
    op.create_index("ix_spans_parent", "spans", ["parent_span_id"])
    op.create_index("ix_spans_type", "spans", ["type"])
    op.create_index("ix_spans_model", "spans", ["model"])
    op.create_index("ix_spans_status", "spans", ["status"])

    event_type = sa.Enum(
        "TRACE_START",
        "TRACE_END",
        "SPAN_START",
        "SPAN_END",
        name="telemetryeventtype",
        native_enum=False,
        length=20,
    )
    op.create_table(
        "ingestion_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_ingestion_events")),
    )
    op.create_index(op.f("ix_ingestion_events_project_id"), "ingestion_events", ["project_id"])


def downgrade() -> None:
    op.drop_table("ingestion_events")
    op.drop_table("spans")
    op.drop_table("traces")
