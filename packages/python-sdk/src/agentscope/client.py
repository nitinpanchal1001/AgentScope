import atexit
import functools
import hashlib
import inspect
import json
from collections.abc import Callable, Coroutine, Sequence
from contextvars import Token
from types import TracebackType
from typing import Any, Literal, ParamSpec, TypeVar, cast
from uuid import uuid4

from agentscope.context import TraceContext, current_span_id, current_trace
from agentscope.events import telemetry_event
from agentscope.processors import EventProcessor
from agentscope.transport import BackgroundSender

P = ParamSpec("P")
R = TypeVar("R")


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=repr, ensure_ascii=False))


class Span:
    def __init__(
        self,
        client: "AgentScope",
        *,
        name: str,
        span_type: str,
        input: Any = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self._client = client
        self.name = name
        normalized_type = span_type.upper()
        self.span_type = (
            normalized_type
            if normalized_type
            in {"AGENT", "LLM", "TOOL", "RETRIEVAL", "EMBEDDING", "CHAIN", "CUSTOM"}
            else "CUSTOM"
        )
        self.input = input
        self.output: Any = None
        self.provider = provider
        self.model = model
        self.metadata = metadata or {}
        self.tags = tags or []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        self._span_id: str | None = None
        self._token: Token[str | None] | None = None

    def set_output(self, output: Any) -> None:
        self.output = output

    def set_usage(self, *, input_tokens: int = 0, output_tokens: int = 0, cost: float = 0) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost = cost

    def __enter__(self) -> "Span":
        trace = current_trace.get()
        if trace is None:
            return self
        self._span_id = str(uuid4())
        parent = current_span_id.get()
        self._token = current_span_id.set(self._span_id)
        self._client._emit(
            telemetry_event(
                "SPAN_START",
                trace.trace_id,
                {
                    "name": self.name,
                    "span_type": self.span_type,
                    "input": _json_safe(self.input),
                    "provider": self.provider,
                    "model": self.model,
                    "metadata": _json_safe(self.metadata),
                    "tags": self.tags,
                },
                span_id=self._span_id,
                parent_span_id=parent,
            )
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        trace = current_trace.get()
        if trace is not None and self._span_id is not None:
            payload: dict[str, Any] = {
                "status": "ERROR" if exc is not None else "SUCCESS",
                "output": _json_safe(self.output),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.input_tokens + self.output_tokens,
                "cost": self.cost,
            }
            if exc is not None:
                payload.update({"error_type": "UNKNOWN", "error_message": str(exc)})
            self._client._emit(
                telemetry_event("SPAN_END", trace.trace_id, payload, span_id=self._span_id)
            )
        if self._token is not None:
            current_span_id.reset(self._token)
        return False

    async def __aenter__(self) -> "Span":
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return self.__exit__(exc_type, exc, traceback)


class AgentScope:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "http://localhost:8000",
        processors: Sequence[EventProcessor] = (),
        trace_sample_rate: float = 1.0,
        always_sample_errors: bool = True,
        batch_size: int = 50,
        flush_interval: float = 5.0,
        max_queue_size: int = 10_000,
        timeout: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        if not 0 <= trace_sample_rate <= 1:
            raise ValueError("trace_sample_rate must be between 0 and 1")
        if batch_size < 1 or max_queue_size < batch_size:
            raise ValueError("queue capacity must be at least the batch size")
        self.trace_sample_rate = trace_sample_rate
        self.always_sample_errors = always_sample_errors
        self._sender = BackgroundSender(
            endpoint=endpoint,
            api_key=api_key,
            batch_size=batch_size,
            flush_interval=flush_interval,
            max_queue_size=max_queue_size,
            timeout=timeout,
            max_retries=max_retries,
            processors=processors,
        )
        self._closed = False
        atexit.register(self.close)

    def _sampled(self, trace_id: str) -> bool:
        bucket = int.from_bytes(hashlib.sha256(trace_id.encode()).digest()[:8], "big")
        return bucket / (2**64 - 1) < self.trace_sample_rate

    def _emit(self, event: dict[str, Any]) -> None:
        trace = current_trace.get()
        if trace is None:
            return
        if trace.sampled:
            self._sender.enqueue(event)
        else:
            trace.pending.append(event)

    def _begin_trace(
        self,
        *,
        name: str,
        input: Any,
        agent_version: str | None,
        session_id: str | None,
        user_identifier: str | None,
        metadata: dict[str, Any],
        tags: list[str],
    ) -> tuple[TraceContext, Token[TraceContext | None], Token[str | None]]:
        trace_id = str(uuid4())
        state = TraceContext(trace_id=trace_id, sampled=self._sampled(trace_id))
        trace_token = current_trace.set(state)
        span_token = current_span_id.set(None)
        self._emit(
            telemetry_event(
                "TRACE_START",
                trace_id,
                {
                    "name": name,
                    "input": _json_safe(input),
                    "agent_version": agent_version,
                    "session_id": session_id,
                    "user_identifier": user_identifier,
                    "metadata": _json_safe(metadata),
                    "tags": tags,
                },
            )
        )
        return state, trace_token, span_token

    def _end_trace(
        self,
        state: TraceContext,
        trace_token: Token[TraceContext | None],
        span_token: Token[str | None],
        *,
        output: Any = None,
        error: BaseException | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "status": "ERROR" if error is not None else "SUCCESS",
            "output": _json_safe(output),
        }
        if error is not None:
            payload.update({"error_type": "UNKNOWN", "error_message": str(error)})
        self._emit(telemetry_event("TRACE_END", state.trace_id, payload))
        if error is not None and self.always_sample_errors and not state.sampled:
            for event in state.pending:
                self._sender.enqueue(event)
        current_span_id.reset(span_token)
        current_trace.reset(trace_token)

    def trace(
        self,
        *,
        name: str,
        agent_version: str | None = None,
        session_id: str | None = None,
        user_identifier: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def decorate(function: Callable[P, R]) -> Callable[P, R]:
            if inspect.iscoroutinefunction(function):

                @functools.wraps(function)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                    state, trace_token, span_token = self._begin_trace(
                        name=name,
                        input={"args": args, "kwargs": kwargs},
                        agent_version=agent_version,
                        session_id=session_id,
                        user_identifier=user_identifier,
                        metadata=metadata or {},
                        tags=tags or [],
                    )
                    try:
                        result = await cast(Callable[P, Coroutine[Any, Any, Any]], function)(
                            *args, **kwargs
                        )
                    except BaseException as error:
                        self._end_trace(state, trace_token, span_token, error=error)
                        raise
                    self._end_trace(state, trace_token, span_token, output=result)
                    return result

                return cast(Callable[P, R], async_wrapper)

            @functools.wraps(function)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                state, trace_token, span_token = self._begin_trace(
                    name=name,
                    input={"args": args, "kwargs": kwargs},
                    agent_version=agent_version,
                    session_id=session_id,
                    user_identifier=user_identifier,
                    metadata=metadata or {},
                    tags=tags or [],
                )
                try:
                    result = function(*args, **kwargs)
                except BaseException as error:
                    self._end_trace(state, trace_token, span_token, error=error)
                    raise
                self._end_trace(state, trace_token, span_token, output=result)
                return result

            return cast(Callable[P, R], sync_wrapper)

        return decorate

    def span(
        self,
        *,
        name: str,
        span_type: str = "custom",
        input: Any = None,
        provider: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Span:
        return Span(
            self,
            name=name,
            span_type=span_type,
            input=input,
            provider=provider,
            model=model,
            metadata=metadata,
            tags=tags,
        )

    def flush(self, timeout: float = 5.0) -> bool:
        return self._sender.flush(timeout)

    def close(self, timeout: float = 5.0) -> None:
        if self._closed:
            return
        self._closed = True
        self._sender.close(timeout)

    def __enter__(self) -> "AgentScope":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.close()
        return False
