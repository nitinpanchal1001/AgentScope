import asyncio
import binascii
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from agentscope_api.api.dependencies import (
    CurrentUser,
    ProjectAccessDependency,
    SessionDependency,
)
from agentscope_api.core.exceptions import AppError, NotFoundError
from agentscope_api.models import Span, SpanType, Trace, TraceStatus
from agentscope_api.repositories.tracing import TracingRepository, decode_cursor, encode_cursor
from agentscope_api.schemas.tracing import SpanResponse, TraceDetail, TracePage, TraceSummary
from agentscope_api.services.authorization import Permission, require_permission

router = APIRouter(tags=["Traces"])


def _summary(trace: Trace, environment: str) -> TraceSummary:
    return TraceSummary(
        id=trace.id,
        external_trace_id=trace.external_trace_id,
        project_id=trace.project_id,
        environment_id=trace.environment_id,
        environment=environment,
        name=trace.name,
        status=trace.status,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        latency_ms=trace.latency_ms,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        total_tokens=trace.total_tokens,
        total_cost=Decimal(trace.total_cost),
        agent_version=trace.agent_version,
        error_type=trace.error_type,
        created_at=trace.created_at,
    )


def _span(span: Span) -> SpanResponse:
    return SpanResponse(
        id=span.id,
        external_span_id=span.external_span_id,
        trace_id=span.trace_id,
        parent_span_id=span.parent_span_id,
        type=span.type,
        name=span.name,
        provider=span.provider,
        model=span.model,
        input=span.input,
        output=span.output,
        started_at=span.started_at,
        ended_at=span.ended_at,
        latency_ms=span.latency_ms,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        total_tokens=span.total_tokens,
        cost=Decimal(span.cost),
        status=span.status,
        error_type=span.error_type,
        error_message=span.error_message,
        metadata=span.span_metadata,
        tags=span.tags,
    )


async def _detail(repository: TracingRepository, trace: Trace, environment: str) -> TraceDetail:
    base = _summary(trace, environment)
    spans = await repository.list_spans(trace.id)
    return TraceDetail(
        **base.model_dump(),
        input=trace.input,
        output=trace.output,
        session_id=trace.session_id,
        user_identifier=trace.user_identifier,
        metadata=trace.trace_metadata,
        tags=trace.tags,
        error_message=trace.error_message,
        spans=[_span(span) for span in spans],
    )


@router.get("/projects/{project_id}/traces", response_model=TracePage)
async def list_traces(
    project_id: UUID,
    access: ProjectAccessDependency,
    session: SessionDependency,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
    environment_id: UUID | None = None,
    status: TraceStatus | None = None,
    agent_version: str | None = Query(default=None, max_length=120),
    model: str | None = Query(default=None, max_length=160),
    span_type: SpanType | None = None,
    tag: Annotated[list[str] | None, Query()] = None,
    started_after: datetime | None = None,
    started_before: datetime | None = None,
) -> TracePage:
    require_permission(access.membership.role, Permission.TRACE_READ)
    decoded_cursor = None
    if cursor:
        try:
            decoded_cursor = decode_cursor(cursor)
        except (binascii.Error, ValueError, UnicodeDecodeError) as error:
            raise AppError("INVALID_CURSOR", "Trace cursor is invalid", status_code=422) from error
    rows = await TracingRepository(session).list_traces(
        project_id=project_id,
        limit=limit,
        cursor=decoded_cursor,
        environment_id=environment_id,
        status=status,
        agent_version=agent_version,
        model=model,
        span_type=span_type,
        tags=tag,
        started_after=started_after,
        started_before=started_before,
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = None
    if has_more and visible:
        last = visible[-1][0]
        next_cursor = encode_cursor(last.created_at, last.id)
    return TracePage(
        items=[_summary(trace, environment) for trace, environment in visible],
        next_cursor=next_cursor,
    )


@router.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: UUID, session: SessionDependency, user: CurrentUser) -> TraceDetail:
    repository = TracingRepository(session)
    result = await repository.get_scoped_trace(trace_id, user.id)
    if result is None:
        raise NotFoundError("Trace")
    trace, environment = result
    return await _detail(repository, trace, environment)


@router.get("/traces/{trace_id}/events")
async def stream_trace(
    trace_id: UUID, request: Request, session: SessionDependency, user: CurrentUser
) -> StreamingResponse:
    repository = TracingRepository(session)
    result = await repository.get_scoped_trace(trace_id, user.id)
    if result is None:
        raise NotFoundError("Trace")
    trace, environment = result

    async def events():  # type: ignore[no-untyped-def]
        previous = ""
        for _ in range(300):
            if await request.is_disconnected():
                break
            await session.refresh(trace)
            detail = await _detail(repository, trace, environment)
            serialized = json.dumps(detail.model_dump(mode="json"), separators=(",", ":"))
            if serialized != previous:
                yield f"event: trace.updated\ndata: {serialized}\n\n"
                previous = serialized
            if trace.status is not TraceStatus.RUNNING:
                yield "event: trace.closed\ndata: {}\n\n"
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
