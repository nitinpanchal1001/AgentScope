import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class EvaluatorType(enum.StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"
    JSON_SCHEMA = "JSON_SCHEMA"
    LATENCY_THRESHOLD = "LATENCY_THRESHOLD"
    COST_THRESHOLD = "COST_THRESHOLD"
    REQUIRED_TOOL = "REQUIRED_TOOL"
    FORBIDDEN_TOOL = "FORBIDDEN_TOOL"
    TOOL_ARGUMENTS = "TOOL_ARGUMENTS"
    CITATION_PRESENCE = "CITATION_PRESENCE"
    SEMANTIC_SIMILARITY = "SEMANTIC_SIMILARITY"
    CORRECTNESS = "CORRECTNESS"
    RELEVANCE = "RELEVANCE"
    FAITHFULNESS = "FAITHFULNESS"
    COMPLETENESS = "COMPLETENESS"
    HALLUCINATION = "HALLUCINATION"
    INSTRUCTION_FOLLOWING = "INSTRUCTION_FOLLOWING"
    TOOL_SELECTION = "TOOL_SELECTION"
    CUSTOM_RUBRIC = "CUSTOM_RUBRIC"


class EvaluationStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EvaluationSource(enum.StrEnum):
    PRODUCTION = "PRODUCTION"
    MANUAL = "MANUAL"
    EXPERIMENT = "EXPERIMENT"
    REPLAY = "REPLAY"


class ExperimentStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExperimentRunStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QualityGateStatus(enum.StrEnum):
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"


class ReplayStatus(enum.StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AlertMetric(enum.StrEnum):
    ERROR_RATE = "ERROR_RATE"
    HALLUCINATION_RATE = "HALLUCINATION_RATE"
    P95_LATENCY_MS = "P95_LATENCY_MS"
    AVERAGE_COST = "AVERAGE_COST"
    EVALUATION_SCORE = "EVALUATION_SCORE"
    TOOL_FAILURE_RATE = "TOOL_FAILURE_RATE"


class AlertOperator(enum.StrEnum):
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


class AlertSeverity(enum.StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NotificationChannel(enum.StrEnum):
    WEBHOOK = "WEBHOOK"
    EMAIL = "EMAIL"


class AlertEventStatus(enum.StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


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


class ModelPricing(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "model_pricing"
    __table_args__ = (
        UniqueConstraint("project_id", "provider", "model", "effective_from"),
        CheckConstraint(
            "input_price_per_million_tokens >= 0",
            name="ck_model_pricing_input_price_nonnegative",
        ),
        CheckConstraint(
            "output_price_per_million_tokens >= 0",
            name="ck_model_pricing_output_price_nonnegative",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_model_pricing_effective_window",
        ),
        Index(
            "ix_model_pricing_lookup",
            "project_id",
            "provider",
            "model",
            "effective_from",
            "effective_to",
        ),
    )

    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(160))
    input_price_per_million_tokens: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    output_price_per_million_tokens: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Trace(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "traces"
    __table_args__ = (
        UniqueConstraint("project_id", "external_trace_id"),
        Index("ix_traces_project_created", "project_id", "created_at"),
        Index(
            "ix_traces_project_environment_started",
            "project_id",
            "environment_id",
            "started_at",
        ),
        Index("ix_traces_project_started_status", "project_id", "started_at", "status"),
        Index("ix_traces_environment_created", "environment_id", "created_at"),
        Index("ix_traces_project_status", "project_id", "status"),
        Index("ix_traces_project_agent_version", "project_id", "agent_version"),
        Index("ix_traces_project_evaluation_score", "project_id", "evaluation_score"),
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
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 12), default=Decimal("0"))
    evaluation_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
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
        Index("ix_spans_trace_type_status", "trace_id", "type", "status"),
    )

    external_span_id: Mapped[str] = mapped_column(String(128))
    trace_id: Mapped[UUID] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"))
    pricing_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("model_pricing.id", ondelete="SET NULL"), nullable=True
    )
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
    cost: Mapped[Decimal] = mapped_column(Numeric(20, 12), default=Decimal("0"))
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


class Evaluator(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluators"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class EvaluatorVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evaluator_versions"
    __table_args__ = (
        UniqueConstraint("evaluator_id", "version"),
        CheckConstraint("threshold >= 0 AND threshold <= 1", name="ck_evaluator_threshold"),
        Index("ix_evaluator_versions_evaluator_created", "evaluator_id", "created_at"),
    )

    evaluator_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluators.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    type: Mapped[EvaluatorType] = mapped_column(Enum(EvaluatorType, native_enum=False, length=32))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    threshold: Mapped[Decimal] = mapped_column(Numeric(7, 6), default=Decimal("0.8"))
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProductionEvaluationBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "production_evaluation_bindings"
    __table_args__ = (
        UniqueConstraint("environment_id", "evaluator_version_id"),
        CheckConstraint("sample_rate >= 0 AND sample_rate <= 1", name="ck_binding_sample_rate"),
        CheckConstraint(
            "threshold IS NULL OR (threshold >= 0 AND threshold <= 1)",
            name="ck_binding_threshold",
        ),
        Index("ix_evaluation_bindings_project_enabled", "project_id", "enabled"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    evaluator_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluator_versions.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sample_rate: Mapped[Decimal] = mapped_column(Numeric(7, 6), default=Decimal("1"))
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class EvaluationResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("trace_id", "evaluator_version_id", "source"),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)", name="ck_evaluation_result_score"
        ),
        CheckConstraint("threshold >= 0 AND threshold <= 1", name="ck_evaluation_result_threshold"),
        Index("ix_evaluation_results_trace", "trace_id"),
        Index("ix_evaluation_results_project_created", "project_id", "created_at"),
        Index(
            "ix_evaluation_results_project_status_created",
            "project_id",
            "status",
            "created_at",
        ),
        Index("ix_evaluation_results_status_created", "status", "created_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    trace_id: Mapped[UUID] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"))
    experiment_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("experiment_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evaluator_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluator_versions.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[EvaluationSource] = mapped_column(
        Enum(EvaluationSource, native_enum=False, length=16)
    )
    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(EvaluationStatus, native_enum=False, length=16), default=EvaluationStatus.PENDING
    )
    threshold: Mapped[Decimal] = mapped_column(Numeric(7, 6))
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT, default=list)
    result_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DOCUMENT, default=dict)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class DatasetVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_dataset_versions_dataset_version"),
        UniqueConstraint(
            "dataset_id", "content_hash", name="uq_dataset_versions_dataset_content_hash"
        ),
        CheckConstraint("version > 0", name="ck_dataset_version_positive"),
        CheckConstraint("item_count >= 0", name="ck_dataset_version_item_count"),
        Index("ix_dataset_versions_dataset_created", "dataset_id", "created_at"),
    )

    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer)
    version_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetItem(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dataset_items"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "ordinal"),
        CheckConstraint("ordinal > 0", name="ck_dataset_item_ordinal"),
        Index("ix_dataset_items_dataset_version", "dataset_version_id"),
    )

    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    input: Mapped[Any] = mapped_column(JSON_DOCUMENT)
    expected_output: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    expected_tools: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)
    context: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    item_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_DOCUMENT, default=dict)


class Experiment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 100",
            name="ck_experiment_max_concurrency",
        ),
        CheckConstraint(
            "total_cases >= 0 AND completed_cases >= 0 AND passed_cases >= 0 AND failed_cases >= 0",
            name="ck_experiment_counts_nonnegative",
        ),
        Index("ix_experiments_project_created", "project_id", "created_at"),
        Index("ix_experiments_project_status", "project_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="RESTRICT"), index=True
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ExperimentStatus] = mapped_column(
        Enum(ExperimentStatus, native_enum=False, length=16), default=ExperimentStatus.PENDING
    )
    agent_configuration: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=5)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentEvaluatorVersion(Base):
    __tablename__ = "experiment_evaluator_versions"

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True
    )
    evaluator_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluator_versions.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )


class ExperimentRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (
        UniqueConstraint("experiment_id", "dataset_item_id"),
        CheckConstraint("ordinal > 0", name="ck_experiment_run_ordinal"),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND total_tokens >= 0 AND total_cost >= 0",
            name="ck_experiment_run_usage_nonnegative",
        ),
        Index("ix_experiment_runs_experiment_status", "experiment_id", "status"),
        Index("ix_experiment_runs_experiment_ordinal", "experiment_id", "ordinal"),
    )

    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    dataset_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("dataset_items.id", ondelete="RESTRICT"), index=True
    )
    trace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("traces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    status: Mapped[ExperimentRunStatus] = mapped_column(
        Enum(ExperimentRunStatus, native_enum=False, length=16),
        default=ExperimentRunStatus.PENDING,
    )
    output: Mapped[Any | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    evaluation_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExperimentBaseline(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiment_baselines"
    __table_args__ = (
        UniqueConstraint("dataset_id", name="uq_experiment_baselines_dataset"),
        UniqueConstraint("experiment_id", name="uq_experiment_baselines_experiment"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class QualityGate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quality_gates"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class QualityGateResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quality_gate_results"
    __table_args__ = (
        Index(
            "ix_quality_gate_results_candidate_evaluated", "candidate_experiment_id", "evaluated_at"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    quality_gate_id: Mapped[UUID] = mapped_column(
        ForeignKey("quality_gates.id", ondelete="RESTRICT"), index=True
    )
    baseline_experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="RESTRICT"), index=True
    )
    candidate_experiment_id: Mapped[UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[QualityGateStatus] = mapped_column(
        Enum(QualityGateStatus, native_enum=False, length=24)
    )
    comparisons: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT)
    violations: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT)
    warnings: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT)
    rule_snapshot: Mapped[list[Any]] = mapped_column(JSON_DOCUMENT)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class TraceReplay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trace_replays"
    __table_args__ = (
        UniqueConstraint("replay_trace_id", name="uq_trace_replays_replay_trace_id"),
        Index("ix_trace_replays_original_created", "original_trace_id", "created_at"),
        Index("ix_trace_replays_project_status", "project_id", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="RESTRICT"), index=True
    )
    original_trace_id: Mapped[UUID] = mapped_column(
        ForeignKey("traces.id", ondelete="RESTRICT"), index=True
    )
    replay_trace_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("traces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[ReplayStatus] = mapped_column(
        Enum(ReplayStatus, native_enum=False, length=16), default=ReplayStatus.PENDING
    )
    agent_configuration: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    effective_configuration: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    error_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FailureRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "failure_records"
    __table_args__ = (
        UniqueConstraint("trace_id", name="uq_failure_records_trace_id"),
        Index("ix_failure_records_project_created", "project_id", "created_at"),
        Index("ix_failure_records_project_type", "project_id", "failure_type"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    trace_id: Mapped[UUID] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"), index=True)
    failure_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(240))
    document: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict)
    embedding: Mapped[list[float]] = mapped_column(JSON_DOCUMENT, default=list)
    vector_point_id: Mapped[UUID] = mapped_column(index=True)
    agent_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class FailureCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "failure_clusters"
    __table_args__ = (Index("ix_failure_clusters_project_last_seen", "project_id", "last_seen"),)

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    probable_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_source: Mapped[str] = mapped_column(String(32), default="HEURISTIC")
    size: Mapped[int] = mapped_column(Integer)
    failure_percentage: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    representative_failure_ids: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list)


class FailureClusterMember(Base):
    __tablename__ = "failure_cluster_members"

    cluster_id: Mapped[UUID] = mapped_column(
        ForeignKey("failure_clusters.id", ondelete="CASCADE"), primary_key=True
    )
    failure_id: Mapped[UUID] = mapped_column(
        ForeignKey("failure_records.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("window_minutes > 0", name="ck_alert_rules_positive_window"),
        CheckConstraint("cooldown_minutes > 0", name="ck_alert_rules_positive_cooldown"),
        Index("ix_alert_rules_project_enabled", "project_id", "enabled"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    metric: Mapped[AlertMetric] = mapped_column(Enum(AlertMetric, native_enum=False, length=32))
    operator: Mapped[AlertOperator] = mapped_column(
        Enum(AlertOperator, native_enum=False, length=32)
    )
    threshold: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    window_minutes: Mapped[int] = mapped_column(Integer)
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, native_enum=False, length=16)
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, length=16)
    )
    channel_target: Mapped[str] = mapped_column(Text)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=30)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class AlertEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="uq_alert_events_deduplication_key"),
        Index("ix_alert_events_project_triggered", "project_id", "triggered_at"),
        Index("ix_alert_events_rule_triggered", "rule_id", "triggered_at"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    environment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL"), nullable=True
    )
    rule_name: Mapped[str] = mapped_column(String(160))
    metric: Mapped[AlertMetric] = mapped_column(Enum(AlertMetric, native_enum=False, length=32))
    operator: Mapped[AlertOperator] = mapped_column(
        Enum(AlertOperator, native_enum=False, length=32)
    )
    observed_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    threshold: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, native_enum=False, length=16)
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, native_enum=False, length=16)
    )
    channel_target: Mapped[str] = mapped_column(Text)
    status: Mapped[AlertEventStatus] = mapped_column(
        Enum(AlertEventStatus, native_enum=False, length=16),
        default=AlertEventStatus.PENDING,
    )
    deduplication_key: Mapped[str] = mapped_column(String(200))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


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
