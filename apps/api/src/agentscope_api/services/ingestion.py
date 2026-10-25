import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.api.dependencies import IngestionAccess
from agentscope_api.core.config import Settings
from agentscope_api.core.exceptions import IngestionError, PayloadTooLargeError
from agentscope_api.models import Span, TelemetryEventType, Trace, TraceStatus
from agentscope_api.repositories.pricing import PricingRepository
from agentscope_api.repositories.tracing import TracingRepository
from agentscope_api.schemas.tracing import IngestionBatch, IngestionResponse, TelemetryEvent
from agentscope_api.services.evaluations import EvaluationService
from agentscope_api.services.pricing import calculate_cost, normalize_pricing_key


def _bounded_json(value: Any, max_bytes: int) -> Any:
    if value is None:
        return None
    encoded = json.dumps(value, default=str, ensure_ascii=False).encode()
    if len(encoded) <= max_bytes:
        return value
    preview = encoded[: max(0, max_bytes - 100)].decode(errors="ignore")
    return {"_agentscope_truncated": True, "preview": preview}


def _latency_ms(started_at: datetime, ended_at: datetime | None) -> int | None:
    if ended_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=UTC)
    return max(0, int((ended_at - started_at).total_seconds() * 1000))


class IngestionService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = TracingRepository(session)
        self.pending_evaluation_dispatches: list[UUID] = []
        self.pending_failure_dispatches: list[UUID] = []

    async def ingest(
        self, batch: IngestionBatch, access: IngestionAccess, raw_size: int
    ) -> IngestionResponse:
        measured_size = max(raw_size, len(batch.model_dump_json().encode()))
        if measured_size > self.settings.ingest_max_batch_bytes:
            raise PayloadTooLargeError("Telemetry batch exceeds the configured byte limit")
        if len(batch.events) > self.settings.ingest_max_batch_events:
            raise PayloadTooLargeError("Telemetry batch contains too many events")

        accepted = 0
        duplicates = 0
        try:
            for event in batch.events:
                event_size = len(event.model_dump_json().encode())
                if event_size > self.settings.ingest_max_event_bytes:
                    raise PayloadTooLargeError(f"Event {event.event_id} exceeds the byte limit")
                inserted = await self.repository.record_event_once(
                    {
                        "event_id": event.event_id,
                        "project_id": access.project.id,
                        "event_type": event.type,
                        "received_at": datetime.now(UTC),
                    }
                )
                if not inserted:
                    duplicates += 1
                    continue
                await self._apply_event(event, access)
                accepted += 1
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        return IngestionResponse(accepted=accepted, duplicates=duplicates)

    async def _apply_event(self, event: TelemetryEvent, access: IngestionAccess) -> None:
        if event.type is TelemetryEventType.TRACE_START:
            await self._trace_start(event, access)
        elif event.type is TelemetryEventType.TRACE_END:
            await self._trace_end(event, access)
        elif event.type is TelemetryEventType.SPAN_START:
            await self._span_start(event, access)
        else:
            await self._span_end(event, access)

    async def _trace_start(self, event: TelemetryEvent, access: IngestionAccess) -> None:
        payload = event.payload
        existing = await self.repository.get_trace_by_external(access.project.id, event.trace_id)
        if existing is not None:
            return
        trace = Trace(
            id=uuid4(),
            external_trace_id=event.trace_id,
            organization_id=access.project.organization_id,
            project_id=access.project.id,
            environment_id=access.api_key.environment_id,
            name=payload.name or "agent-trace",
            input=_bounded_json(payload.input, self.settings.ingest_max_content_bytes),
            output=None,
            status=payload.status or TraceStatus.RUNNING,
            started_at=payload.started_at or event.timestamp,
            ended_at=None,
            latency_ms=None,
            input_tokens=payload.input_tokens or 0,
            output_tokens=payload.output_tokens or 0,
            total_tokens=payload.total_tokens or 0,
            total_cost=payload.cost or Decimal("0"),
            agent_version=payload.agent_version,
            session_id=payload.session_id,
            user_identifier=payload.user_identifier,
            trace_metadata=_bounded_json(payload.metadata, self.settings.ingest_max_metadata_bytes),
            tags=payload.tags,
            error_type=payload.error_type,
            error_message=payload.error_message,
            created_at=event.timestamp,
        )
        self.session.add(trace)
        await self.session.flush()

    async def _trace_end(self, event: TelemetryEvent, access: IngestionAccess) -> None:
        trace = await self.repository.get_trace_by_external(access.project.id, event.trace_id)
        if trace is None:
            raise IngestionError(
                "TRACE_END references an unknown trace", details={"trace_id": event.trace_id}
            )
        payload = event.payload
        trace.output = _bounded_json(payload.output, self.settings.ingest_max_content_bytes)
        trace.status = payload.status or TraceStatus.SUCCESS
        trace.ended_at = payload.ended_at or event.timestamp
        trace.latency_ms = (
            payload.latency_ms
            if payload.latency_ms is not None
            else _latency_ms(trace.started_at, trace.ended_at)
        )
        trace.input_tokens = (
            payload.input_tokens if payload.input_tokens is not None else trace.input_tokens
        )
        trace.output_tokens = (
            payload.output_tokens if payload.output_tokens is not None else trace.output_tokens
        )
        trace.total_tokens = (
            payload.total_tokens
            if payload.total_tokens is not None
            else trace.input_tokens + trace.output_tokens
        )
        trace.total_cost = payload.cost if payload.cost is not None else trace.total_cost
        trace.error_type = payload.error_type
        trace.error_message = payload.error_message
        await self.session.flush()
        usage = await self.repository.aggregate_span_usage(trace.id)
        if usage["usage_span_count"]:
            if payload.input_tokens is None:
                trace.input_tokens = int(usage["input_tokens"])
            if payload.output_tokens is None:
                trace.output_tokens = int(usage["output_tokens"])
            if payload.total_tokens is None:
                trace.total_tokens = int(usage["total_tokens"])
            if payload.cost is None:
                trace.total_cost = Decimal(str(usage["total_cost"]))
        if payload.metadata:
            trace.trace_metadata = _bounded_json(
                {**trace.trace_metadata, **payload.metadata},
                self.settings.ingest_max_metadata_bytes,
            )
        self.pending_evaluation_dispatches.extend(
            await EvaluationService(self.session).prepare_production(trace)
        )
        self.pending_failure_dispatches.append(trace.id)

    async def _span_start(self, event: TelemetryEvent, access: IngestionAccess) -> None:
        span_type = event.payload.span_type
        if event.span_id is None or span_type is None:
            raise IngestionError("SPAN_START requires span_id and payload.span_type")
        trace = await self.repository.get_trace_by_external(access.project.id, event.trace_id)
        if trace is None:
            raise IngestionError(
                "SPAN_START references an unknown trace", details={"trace_id": event.trace_id}
            )
        if await self.repository.get_span_by_external(trace.id, event.span_id) is not None:
            return
        parent_id = None
        if event.parent_span_id is not None:
            parent = await self.repository.get_span_by_external(trace.id, event.parent_span_id)
            if parent is None:
                raise IngestionError(
                    "SPAN_START references an unknown parent span",
                    details={"parent_span_id": event.parent_span_id},
                )
            parent_id = parent.id
        payload = event.payload
        span = Span(
            id=uuid4(),
            external_span_id=event.span_id,
            trace_id=trace.id,
            parent_span_id=parent_id,
            type=span_type,
            name=payload.name or span_type.value.lower(),
            provider=payload.provider,
            model=payload.model,
            input=_bounded_json(payload.input, self.settings.ingest_max_content_bytes),
            output=None,
            started_at=payload.started_at or event.timestamp,
            ended_at=None,
            latency_ms=None,
            input_tokens=payload.input_tokens or 0,
            output_tokens=payload.output_tokens or 0,
            total_tokens=payload.total_tokens or 0,
            cost=payload.cost or Decimal("0"),
            status=payload.status or TraceStatus.RUNNING,
            error_type=payload.error_type,
            error_message=payload.error_message,
            span_metadata=_bounded_json(payload.metadata, self.settings.ingest_max_metadata_bytes),
            tags=payload.tags,
        )
        self.session.add(span)
        await self.session.flush()

    async def _span_end(self, event: TelemetryEvent, access: IngestionAccess) -> None:
        if event.span_id is None:
            raise IngestionError("SPAN_END requires span_id")
        trace = await self.repository.get_trace_by_external(access.project.id, event.trace_id)
        if trace is None:
            raise IngestionError("SPAN_END references an unknown trace")
        span = await self.repository.get_span_by_external(trace.id, event.span_id)
        if span is None:
            raise IngestionError(
                "SPAN_END references an unknown span", details={"span_id": event.span_id}
            )
        payload = event.payload
        span.output = _bounded_json(payload.output, self.settings.ingest_max_content_bytes)
        span.status = payload.status or TraceStatus.SUCCESS
        span.ended_at = payload.ended_at or event.timestamp
        span.latency_ms = (
            payload.latency_ms
            if payload.latency_ms is not None
            else _latency_ms(span.started_at, span.ended_at)
        )
        span.input_tokens = (
            payload.input_tokens if payload.input_tokens is not None else span.input_tokens
        )
        span.output_tokens = (
            payload.output_tokens if payload.output_tokens is not None else span.output_tokens
        )
        span.total_tokens = (
            payload.total_tokens
            if payload.total_tokens is not None
            else span.input_tokens + span.output_tokens
        )
        if payload.cost is not None:
            span.cost = payload.cost
        elif span.provider and span.model:
            provider, model = normalize_pricing_key(span.provider, span.model)
            pricing = await PricingRepository(self.session).find_effective(
                project_id=access.project.id,
                provider=provider,
                model=model,
                at=span.started_at,
            )
            if pricing is not None:
                span.pricing_id = pricing.id
                span.cost = calculate_cost(
                    input_tokens=span.input_tokens,
                    output_tokens=span.output_tokens,
                    input_price_per_million_tokens=pricing.input_price_per_million_tokens,
                    output_price_per_million_tokens=pricing.output_price_per_million_tokens,
                )
        span.error_type = payload.error_type
        span.error_message = payload.error_message
        if payload.metadata:
            span.span_metadata = _bounded_json(
                {**span.span_metadata, **payload.metadata},
                self.settings.ingest_max_metadata_bytes,
            )
