from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.exceptions import ConflictError, NotFoundError
from agentscope_api.models import (
    EvaluationStatus,
    FailureType,
    Membership,
    Project,
    ReplayStatus,
    Span,
    SpanType,
    Trace,
    TraceReplay,
    TraceStatus,
    User,
)
from agentscope_api.repositories.replays import ReplayRepository
from agentscope_api.schemas.experiments import ExperimentAgentSpan
from agentscope_api.schemas.replays import (
    ReplayComparison,
    ReplayCreate,
    ReplaySnapshot,
    ReplaySpanStructure,
    WorkerReplayCompletion,
    WorkerReplayCompletionResponse,
    WorkerReplayPayload,
)
from agentscope_api.services.audit import record_audit
from agentscope_api.services.authorization import Permission, require_permission

TERMINAL_EVALUATIONS = {
    EvaluationStatus.SUCCESS,
    EvaluationStatus.FAILED,
    EvaluationStatus.SKIPPED,
}


def _failure_type(value: str | None) -> FailureType | None:
    if value is None:
        return None
    try:
        return FailureType(value)
    except ValueError:
        return FailureType.UNKNOWN


def _original_configuration(trace: Trace, spans: list[Span]) -> dict[str, Any]:
    stored = trace.trace_metadata.get("configuration")
    source = stored if isinstance(stored, dict) else {}
    model_span = next((span for span in spans if span.model), None)
    return {
        "provider": source.get("provider") or (model_span.provider if model_span else None),
        "model": source.get("model") or (model_span.model if model_span else None),
        "prompt_version": source.get("prompt_version") or trace.agent_version,
        "temperature": source.get("temperature"),
        "agent_version": trace.agent_version,
        "parameters": source.get("parameters", {}),
    }


def _effective_configuration(original: dict[str, Any], request: ReplayCreate) -> dict[str, Any]:
    value = dict(original)
    for field in ("provider", "model", "prompt_version", "temperature"):
        candidate = getattr(request.agent, field)
        if candidate is not None:
            value[field] = candidate
    if "parameters" in request.agent.model_fields_set:
        value["parameters"] = request.agent.parameters
    for field in ("model", "prompt_version", "temperature", "agent_version", "parameters"):
        candidate = getattr(request.overrides, field)
        if candidate is not None:
            value[field] = candidate
    return value


class ReplayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ReplayRepository(session)

    async def create(
        self,
        project: Project,
        membership: Membership,
        original_trace_id: UUID,
        request: ReplayCreate,
        user: User,
    ) -> TraceReplay:
        require_permission(membership.role, Permission.REPLAY_RUN)
        original = await self.repository.trace(original_trace_id, project.id)
        if original is None:
            raise NotFoundError("Trace")
        if original.status is TraceStatus.RUNNING:
            raise ConflictError("A running trace cannot be replayed")
        spans = await self.repository.spans(original.id)
        now = datetime.now(UTC)
        replay = TraceReplay(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            environment_id=original.environment_id,
            original_trace_id=original.id,
            replay_trace_id=None,
            status=ReplayStatus.RUNNING,
            agent_configuration=request.agent.model_dump(mode="json"),
            overrides=request.overrides.model_dump(mode="json", exclude_none=True),
            effective_configuration=_effective_configuration(
                _original_configuration(original, spans), request
            ),
            error_type=None,
            error_message=None,
            created_by=user.id,
            started_at=now,
            completed_at=None,
        )
        self.session.add(replay)
        record_audit(
            self.session,
            organization_id=project.organization_id,
            actor_id=user.id,
            action="trace.replay_started",
            resource_type="trace_replay",
            resource_id=replay.id,
            metadata={"original_trace_id": str(original.id)},
        )
        await self.session.commit()
        return replay

    async def dispatch_failed(self, replay_id: UUID) -> None:
        replay = await self.repository.lock_replay(replay_id)
        if replay is None or replay.status is not ReplayStatus.RUNNING:
            return
        replay.status = ReplayStatus.FAILED
        replay.error_type = "DISPATCH_FAILED"
        replay.error_message = "The replay queue was unavailable"
        replay.completed_at = datetime.now(UTC)
        await self.session.commit()

    async def worker_payload(self, replay_id: UUID) -> WorkerReplayPayload:
        replay = await self.repository.lock_replay(replay_id)
        if replay is None:
            raise NotFoundError("Replay")
        original = await self.repository.trace(replay.original_trace_id, replay.project_id)
        if original is None:
            raise NotFoundError("Original trace")
        agent = replay.agent_configuration
        evaluation_result_ids = (
            [
                result.id
                for result in await self.repository.evaluations(replay.replay_trace_id)
                if result.status not in TERMINAL_EVALUATIONS
            ]
            if replay.replay_trace_id is not None
            else []
        )
        return WorkerReplayPayload(
            replay_id=replay.id,
            status=replay.status,
            endpoint=agent["endpoint"],
            timeout_seconds=agent["timeout_seconds"],
            headers_from_env=agent.get("headers_from_env", {}),
            request={
                "input": original.input,
                "context": original.trace_metadata.get("context"),
                "configuration": replay.effective_configuration,
                "metadata": {
                    "replay_id": str(replay.id),
                    "original_trace_id": str(original.id),
                    "original_external_trace_id": original.external_trace_id,
                },
            },
            evaluation_result_ids=evaluation_result_ids,
        )

    async def complete(
        self, replay_id: UUID, completion: WorkerReplayCompletion
    ) -> WorkerReplayCompletionResponse:
        replay = await self.repository.lock_replay(replay_id)
        if replay is None:
            raise NotFoundError("Replay")
        if replay.replay_trace_id is not None or replay.status in {
            ReplayStatus.COMPLETED,
            ReplayStatus.FAILED,
        }:
            return WorkerReplayCompletionResponse(
                status=replay.status,
                replay_trace_id=replay.replay_trace_id,
                evaluation_result_ids=[],
            )
        original = await self.repository.trace(replay.original_trace_id, replay.project_id)
        if original is None:
            raise NotFoundError("Original trace")
        now = datetime.now(UTC)
        if completion.status == "FAILED":
            replay.status = ReplayStatus.FAILED
            replay.error_type = completion.error_type or "REPLAY_INVOCATION_FAILED"
            replay.error_message = completion.error_message
            replay.completed_at = now
            await self.session.commit()
            return WorkerReplayCompletionResponse(
                status=replay.status,
                replay_trace_id=None,
                evaluation_result_ids=[],
            )

        trace = self._create_trace(replay, original, completion, now)
        self.session.add(trace)
        await self.session.flush()
        self._create_spans(replay, original, trace, completion, now)
        await self.session.flush()
        replay.replay_trace_id = trace.id

        from agentscope_api.services.evaluations import EvaluationService

        results = await EvaluationService(self.session).prepare_replay(original, trace)
        replay.status = ReplayStatus.EVALUATING if results else ReplayStatus.COMPLETED
        replay.completed_at = None if results else now
        await self.session.commit()
        return WorkerReplayCompletionResponse(
            status=replay.status,
            replay_trace_id=trace.id,
            evaluation_result_ids=[result.id for result in results],
        )

    async def refresh_from_evaluations(self, trace_id: UUID) -> None:
        replay = await self.repository.replay_by_trace(trace_id)
        if replay is None or replay.status is not ReplayStatus.EVALUATING:
            return
        results = await self.repository.evaluations(trace_id)
        if results and all(result.status in TERMINAL_EVALUATIONS for result in results):
            replay.status = ReplayStatus.COMPLETED
            replay.completed_at = datetime.now(UTC)

    async def comparison(
        self, project: Project, membership: Membership, replay_id: UUID
    ) -> ReplayComparison:
        require_permission(membership.role, Permission.REPLAY_READ)
        replay = await self.repository.replay(replay_id, project.id)
        if replay is None:
            raise NotFoundError("Replay")
        if replay.replay_trace_id is None:
            raise ConflictError("Replay has not produced a trace")
        original = await self.repository.trace(replay.original_trace_id, project.id)
        generated = await self.repository.trace(replay.replay_trace_id, project.id)
        if original is None or generated is None:
            raise NotFoundError("Replay trace")
        original_snapshot = await self._snapshot(original)
        replay_snapshot = await self._snapshot(generated)
        return ReplayComparison(
            replay_id=replay.id,
            original=original_snapshot,
            replay=replay_snapshot,
            differences={
                "output_changed": original.output != generated.output,
                "evaluation_score_delta": self._decimal_delta(
                    generated.evaluation_score, original.evaluation_score
                ),
                "latency_ms_delta": self._number_delta(generated.latency_ms, original.latency_ms),
                "total_cost_delta": float(generated.total_cost - original.total_cost),
                "total_tokens_delta": generated.total_tokens - original.total_tokens,
                "tool_sequence_changed": (
                    original_snapshot.tool_sequence != replay_snapshot.tool_sequence
                ),
                "span_structure_changed": (
                    original_snapshot.span_structure != replay_snapshot.span_structure
                ),
            },
        )

    async def _snapshot(self, trace: Trace) -> ReplaySnapshot:
        spans = await self.repository.spans(trace.id)
        ordinals = {span.id: index for index, span in enumerate(spans, start=1)}
        structure = [
            ReplaySpanStructure(
                ordinal=index,
                parent_ordinal=(
                    ordinals.get(span.parent_span_id) if span.parent_span_id is not None else None
                ),
                type=span.type,
                name=span.name,
                status=span.status,
            )
            for index, span in enumerate(spans, start=1)
        ]
        return ReplaySnapshot(
            trace_id=trace.id,
            output=trace.output,
            evaluation_score=trace.evaluation_score,
            latency_ms=trace.latency_ms,
            total_cost=trace.total_cost,
            total_tokens=trace.total_tokens,
            tool_sequence=[span.name for span in spans if span.type is SpanType.TOOL],
            span_structure=structure,
        )

    @staticmethod
    def _number_delta(candidate: int | None, original: int | None) -> int | None:
        if candidate is None or original is None:
            return None
        return candidate - original

    @staticmethod
    def _decimal_delta(candidate: Decimal | None, original: Decimal | None) -> float | None:
        if candidate is None or original is None:
            return None
        return float(candidate - original)

    @staticmethod
    def _create_trace(
        replay: TraceReplay,
        original: Trace,
        completion: WorkerReplayCompletion,
        now: datetime,
    ) -> Trace:
        started_at = replay.started_at or now
        return Trace(
            id=uuid4(),
            external_trace_id=f"replay:{replay.id}",
            organization_id=replay.organization_id,
            project_id=replay.project_id,
            environment_id=replay.environment_id,
            name=f"Replay / {original.name}",
            input=original.input,
            output=completion.output,
            status=TraceStatus.SUCCESS,
            started_at=started_at,
            ended_at=now,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            total_tokens=completion.total_tokens,
            total_cost=completion.total_cost,
            evaluation_score=None,
            agent_version=(
                replay.effective_configuration.get("agent_version")
                or replay.effective_configuration.get("prompt_version")
            ),
            session_id=original.session_id,
            user_identifier=original.user_identifier,
            trace_metadata={
                **completion.metadata,
                "replay_id": str(replay.id),
                "original_trace_id": str(original.id),
                "configuration": replay.effective_configuration,
            },
            tags=[*original.tags, "replay", f"replay:{replay.id}"],
            error_type=None,
            error_message=None,
            created_at=now,
        )

    def _create_spans(
        self,
        replay: TraceReplay,
        original: Trace,
        trace: Trace,
        completion: WorkerReplayCompletion,
        now: datetime,
    ) -> None:
        started_at = replay.started_at or now
        spans = completion.spans or [
            ExperimentAgentSpan(
                type=SpanType.AGENT,
                name="replay agent invocation",
                provider=replay.effective_configuration.get("provider"),
                model=replay.effective_configuration.get("model"),
                input=original.input,
                output=completion.output,
                latency_ms=completion.latency_ms,
                input_tokens=completion.input_tokens,
                output_tokens=completion.output_tokens,
                total_tokens=completion.total_tokens,
                cost=completion.total_cost,
            )
        ]
        for index, span in enumerate(spans, start=1):
            ended_at = (
                started_at + timedelta(milliseconds=span.latency_ms)
                if span.latency_ms is not None
                else now
            )
            self.session.add(
                Span(
                    id=uuid4(),
                    external_span_id=f"replay-span:{replay.id}:{index}",
                    trace_id=trace.id,
                    pricing_id=None,
                    parent_span_id=None,
                    type=span.type,
                    name=span.name,
                    provider=span.provider,
                    model=span.model,
                    input=span.input,
                    output=span.output,
                    started_at=started_at,
                    ended_at=ended_at,
                    latency_ms=span.latency_ms,
                    input_tokens=span.input_tokens,
                    output_tokens=span.output_tokens,
                    total_tokens=span.total_tokens,
                    cost=span.cost,
                    status=span.status,
                    error_type=_failure_type(span.error_type),
                    error_message=span.error_message,
                    span_metadata=span.metadata,
                    tags=span.tags,
                )
            )
