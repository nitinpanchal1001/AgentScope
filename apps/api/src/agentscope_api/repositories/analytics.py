from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.models import FailureType, Span, SpanType, Trace, TraceStatus


def _decimal(value: object | None) -> Decimal:
    return Decimal(str(value or 0))


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _trace_filters(
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
    ) -> list[Any]:
        filters: list[Any] = [
            Trace.project_id == project_id,
            Trace.started_at >= started_after,
            Trace.started_at < started_before,
        ]
        if environment_id is not None:
            filters.append(Trace.environment_id == environment_id)
        return filters

    async def summary(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
    ) -> dict[str, Any]:
        filters = self._trace_filters(project_id, environment_id, started_after, started_before)
        row = (
            await self.session.execute(
                select(
                    func.count(Trace.id),
                    func.sum(case((Trace.status == TraceStatus.SUCCESS, 1), else_=0)),
                    func.sum(case((Trace.status == TraceStatus.ERROR, 1), else_=0)),
                    func.avg(Trace.latency_ms),
                    func.sum(Trace.input_tokens),
                    func.sum(Trace.output_tokens),
                    func.sum(Trace.total_tokens),
                    func.sum(Trace.total_cost),
                    func.avg(Trace.evaluation_score),
                ).where(*filters)
            )
        ).one()
        percentiles = await self._latency_percentiles(filters)
        return {
            "total_traces": int(row[0] or 0),
            "successful_traces": int(row[1] or 0),
            "error_traces": int(row[2] or 0),
            "average_latency_ms": float(row[3]) if row[3] is not None else None,
            "input_tokens": int(row[4] or 0),
            "output_tokens": int(row[5] or 0),
            "total_tokens": int(row[6] or 0),
            "total_cost": _decimal(row[7]),
            "average_evaluation_score": (float(row[8]) if row[8] is not None else None),
            **percentiles,
        }

    async def _latency_percentiles(self, filters: list[Any]) -> dict[str, float | None]:
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        if dialect == "postgresql":
            row = (
                await self.session.execute(
                    select(
                        func.percentile_cont(0.50).within_group(Trace.latency_ms),
                        func.percentile_cont(0.95).within_group(Trace.latency_ms),
                        func.percentile_cont(0.99).within_group(Trace.latency_ms),
                    ).where(*filters, Trace.latency_ms.is_not(None))
                )
            ).one()
            values = [float(value) if value is not None else None for value in row]
        else:
            values_raw = list(
                await self.session.scalars(
                    select(Trace.latency_ms)
                    .where(*filters, Trace.latency_ms.is_not(None))
                    .order_by(Trace.latency_ms)
                )
            )
            values = [self._percentile(values_raw, quantile) for quantile in (0.50, 0.95, 0.99)]
        return {
            "p50_latency_ms": values[0],
            "p95_latency_ms": values[1],
            "p99_latency_ms": values[2],
        }

    @staticmethod
    def _percentile(values: list[int | None], quantile: float) -> float | None:
        clean = [value for value in values if value is not None]
        if not clean:
            return None
        position = (len(clean) - 1) * quantile
        lower = int(position)
        upper = min(lower + 1, len(clean) - 1)
        fraction = position - lower
        return float(clean[lower] + (clean[upper] - clean[lower]) * fraction)

    async def timeseries(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
        bucket_seconds: int,
    ) -> list[dict[str, Any]]:
        filters = self._trace_filters(project_id, environment_id, started_after, started_before)
        dialect = self.session.bind.dialect.name if self.session.bind is not None else ""
        if dialect == "postgresql":
            bucket = func.to_timestamp(
                func.floor(func.extract("epoch", Trace.started_at) / bucket_seconds)
                * bucket_seconds
            )
        else:
            epoch_bucket = (
                cast(
                    cast(func.strftime("%s", Trace.started_at), Integer) / bucket_seconds,
                    Integer,
                )
                * bucket_seconds
            )
            bucket = func.datetime(epoch_bucket, "unixepoch")
        rows = await self.session.execute(
            select(
                bucket.label("bucket"),
                func.count(Trace.id),
                func.sum(case((Trace.status == TraceStatus.SUCCESS, 1), else_=0)),
                func.sum(case((Trace.status == TraceStatus.ERROR, 1), else_=0)),
                func.avg(Trace.latency_ms),
                func.sum(Trace.total_tokens),
                func.sum(Trace.total_cost),
            )
            .where(*filters)
            .group_by(bucket)
            .order_by(bucket)
        )
        output: list[dict[str, Any]] = []
        for row in rows.all():
            started_at = row[0]
            if isinstance(started_at, str):
                started_at = datetime.fromisoformat(started_at).replace(tzinfo=UTC)
            elif started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            output.append(
                {
                    "started_at": started_at,
                    "trace_count": int(row[1] or 0),
                    "success_count": int(row[2] or 0),
                    "error_count": int(row[3] or 0),
                    "average_latency_ms": float(row[4]) if row[4] is not None else None,
                    "total_tokens": int(row[5] or 0),
                    "total_cost": _decimal(row[6]),
                }
            )
        return output

    async def span_breakdown(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
        dimension: str,
        span_type: SpanType | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        filters = self._trace_filters(project_id, environment_id, started_after, started_before)
        column = Span.model if dimension == "model" else Span.provider
        if dimension == "tool":
            column = Span.name
            span_type = SpanType.TOOL
        statement = (
            select(
                column,
                func.count(Span.id).label("usage_count"),
                func.sum(case((Span.status == TraceStatus.ERROR, 1), else_=0)),
                func.sum(Span.total_tokens),
                func.sum(Span.cost),
            )
            .join(Trace, Trace.id == Span.trace_id)
            .where(*filters, column.is_not(None))
        )
        if span_type is not None:
            statement = statement.where(Span.type == span_type)
        rows = await self.session.execute(
            statement.group_by(column).order_by(func.count(Span.id).desc()).limit(limit)
        )
        return [
            {
                "name": str(row[0]),
                "count": int(row[1] or 0),
                "error_count": int(row[2] or 0),
                "total_tokens": int(row[3] or 0),
                "total_cost": _decimal(row[4]),
            }
            for row in rows.all()
        ]

    async def trace_breakdown(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        started_after: datetime,
        started_before: datetime,
        dimension: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        filters = self._trace_filters(project_id, environment_id, started_after, started_before)
        column = Trace.name if dimension == "agent" else Trace.error_type
        if dimension == "failure":
            filters.append(Trace.error_type.is_not(None))
        rows = await self.session.execute(
            select(
                column,
                func.count(Trace.id),
                func.sum(case((Trace.status == TraceStatus.ERROR, 1), else_=0)),
                func.sum(Trace.total_tokens),
                func.sum(Trace.total_cost),
            )
            .where(*filters)
            .group_by(column)
            .order_by(func.count(Trace.id).desc())
            .limit(limit)
        )
        output = []
        for row in rows.all():
            name = row[0]
            if isinstance(name, FailureType):
                name = name.value
            output.append(
                {
                    "name": str(name),
                    "count": int(row[1] or 0),
                    "error_count": int(row[2] or 0),
                    "total_tokens": int(row[3] or 0),
                    "total_cost": _decimal(row[4]),
                }
            )
        return output
