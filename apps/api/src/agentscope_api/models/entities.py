import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentscope_api.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Role(enum.StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class TraceStatus(enum.StrEnum):
    UNSET = "UNSET"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class SpanType(enum.StrEnum):
    AGENT = "AGENT"
    LLM = "LLM"
    TOOL = "TOOL"
    RETRIEVAL = "RETRIEVAL"
    EMBEDDING = "EMBEDDING"
    CHAIN = "CHAIN"
    CUSTOM = "CUSTOM"


class FailureType(enum.StrEnum):
    LLM_ERROR = "LLM_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    PARSING_ERROR = "PARSING_ERROR"
    AGENT_LOOP = "AGENT_LOOP"
    EVALUATION_FAILURE = "EVALUATION_FAILURE"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    UNKNOWN = "UNKNOWN"


class TelemetryEventType(enum.StrEnum):
    TRACE_START = "TRACE_START"
    TRACE_END = "TRACE_END"
    SPAN_START = "SPAN_START"
    SPAN_END = "SPAN_END"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16))
    organization: Mapped[Organization] = relationship(lazy="raise")
    user: Mapped[User] = relationship(lazy="raise")


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    retention_days: Mapped[int] = mapped_column(default=30)


class Environment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(40))


class ApiKey(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_project_revoked", "project_id", "revoked_at"),)

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    environment_id: Mapped[UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(20), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class Trace(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "external_trace_id"),
        Index("ix_traces_project_created", "project_id", "created_at"),
        Index("ix_traces_environment_created", "environment_id", "created_at"),
        Index("ix_traces_project_status", "project_id", "status"),
        Index("ix_traces_project_agent_version", "project_id", "agent_version"),
    )

    external_trace_id: Mapped[str] = mapped_column(String(128))
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    environment_id: Mapped[UUID] = mapped_column(ForeignKey("environments.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    input: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    status: Mapped[TraceStatus] = mapped_column(
        Enum(TraceStatus, native_enum=False, length=16), default=TraceStatus.UNSET
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    agent_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DOCUMENT, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)
    error_type: Mapped[FailureType | None] = mapped_column(
        Enum(FailureType, native_enum=False, length=32), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Span(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "spans"
    __table_args__ = (
        UniqueConstraint("trace_id", "external_span_id"),
        Index("ix_spans_trace", "trace_id"),
        Index("ix_spans_parent", "parent_span_id"),
        Index("ix_spans_type", "type"),
        Index("ix_spans_model", "model"),
        Index("ix_spans_status", "status"),
    )

    external_span_id: Mapped[str] = mapped_column(String(128))
    trace_id: Mapped[UUID] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"))
    parent_span_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("spans.id", ondelete="CASCADE"), nullable=True
    )
    type: Mapped[SpanType] = mapped_column(Enum(SpanType, native_enum=False, length=16))
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    output: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    status: Mapped[TraceStatus] = mapped_column(
        Enum(TraceStatus, native_enum=False, length=16), default=TraceStatus.UNSET
    )
    error_type: Mapped[FailureType | None] = mapped_column(
        Enum(FailureType, native_enum=False, length=32), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    span_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DOCUMENT, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[TelemetryEventType] = mapped_column(
        Enum(TelemetryEventType, native_enum=False, length=20)
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family", "family_id"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[UUID] = mapped_column()
    parent_token_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID] = mapped_column(index=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
