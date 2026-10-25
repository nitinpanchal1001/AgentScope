import base64
import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import String, and_, exists, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import (
    Environment,
    IngestionEvent,
    Membership,
    Span,
    SpanType,
    Trace,
    TraceStatus,
)


def encode_cursor(created_at: datetime, trace_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{trace_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, UUID]:
    padded = value + "=" * (-len(value) % 4)
    timestamp, trace_id = base64.urlsafe_b64decode(padded).decode().split("|", 1)
    return datetime.fromisoformat(timestamp), UUID(trace_id)


class TracingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_event_once(self, values: dict[str, Any]) -> bool:
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        statement: Any
        if dialect == "postgresql":
            statement = (
                postgresql_insert(IngestionEvent)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[IngestionEvent.event_id])
            )
        elif dialect == "sqlite":
            statement = (
                sqlite_insert(IngestionEvent)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[IngestionEvent.event_id])
            )
        else:
            if await self.session.get(IngestionEvent, values["event_id"]) is not None:
                return False
            self.session.add(IngestionEvent(**values))
            await self.session.flush()
            return True
        result = cast(CursorResult[Any], await self.session.execute(statement))
        return result.rowcount == 1

    async def get_trace_by_external(self, project_id: UUID, external_id: str) -> Trace | None:
        return await self.session.scalar(
            select(Trace).where(
                Trace.project_id == project_id, Trace.external_trace_id == external_id
            )
        )

    async def get_span_by_external(self, trace_id: UUID, external_id: str) -> Span | None:
        return await self.session.scalar(
            select(Span).where(Span.trace_id == trace_id, Span.external_span_id == external_id)
        )

    async def list_traces(
        self,
        *,
        project_id: UUID,
        limit: int,
        cursor: tuple[datetime, UUID] | None = None,
        environment_id: UUID | None = None,
        status: TraceStatus | None = None,
        agent_version: str | None = None,
        model: str | None = None,
        span_type: SpanType | None = None,
        tags: list[str] | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ) -> list[tuple[Trace, str]]:
        statement = (
            select(Trace, Environment.slug)
            .join(Environment, Environment.id == Trace.environment_id)
            .where(Trace.project_id == project_id)
        )
        if environment_id is not None:
            statement = statement.where(Trace.environment_id == environment_id)
        if status is not None:
            statement = statement.where(Trace.status == status)
        if agent_version:
            statement = statement.where(Trace.agent_version == agent_version)
        if started_after is not None:
            statement = statement.where(Trace.started_at >= started_after)
        if started_before is not None:
            statement = statement.where(Trace.started_at <= started_before)
        if model or span_type:
            conditions = [Span.trace_id == Trace.id]
            if model:
                conditions.append(Span.model == model)
            if span_type:
                conditions.append(Span.type == span_type)
            statement = statement.where(exists(select(Span.id).where(and_(*conditions))))
        for tag in tags or []:
            encoded_tag = json.dumps(tag, ensure_ascii=False)
            pattern = encoded_tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            statement = statement.where(
                sql_cast(Trace.tags, String).like(f"%{pattern}%", escape="\\")
            )
        if cursor is not None:
            created_at, trace_id = cursor
            statement = statement.where(
                or_(
                    Trace.created_at < created_at,
                    and_(Trace.created_at == created_at, Trace.id < trace_id),
                )
            )
        rows = await self.session.execute(
            statement.order_by(Trace.created_at.desc(), Trace.id.desc()).limit(limit + 1)
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def get_scoped_trace(self, trace_id: UUID, user_id: UUID) -> tuple[Trace, str] | None:
        row = await self.session.execute(
            select(Trace, Environment.slug)
            .join(Environment, Environment.id == Trace.environment_id)
            .join(Membership, Membership.organization_id == Trace.organization_id)
            .where(Trace.id == trace_id, Membership.user_id == user_id)
        )
        return row.one_or_none()

    async def list_spans(self, trace_id: UUID) -> list[Span]:
        rows = await self.session.scalars(
            select(Span)
            .where(Span.trace_id == trace_id)
            .order_by(Span.started_at, Span.id)
            .execution_options(populate_existing=True)
        )
        return list(rows)

    async def aggregate_span_usage(self, trace_id: UUID) -> dict[str, int | Any]:
        row = (
            await self.session.execute(
                select(
                    func.sum(Span.input_tokens),
                    func.sum(Span.output_tokens),
                    func.sum(Span.total_tokens),
                    func.sum(Span.cost),
                    func.count(Span.id),
                ).where(
                    Span.trace_id == trace_id,
                    or_(Span.total_tokens > 0, Span.cost > 0),
                )
            )
        ).one()
        return {
            "input_tokens": int(row[0] or 0),
            "output_tokens": int(row[1] or 0),
            "total_tokens": int(row[2] or 0),
            "total_cost": row[3] or 0,
            "usage_span_count": int(row[4] or 0),
        }
