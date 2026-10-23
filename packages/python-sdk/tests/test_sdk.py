import asyncio
from typing import Any

import pytest

from agentscope import AgentScope, default_redaction


class CaptureSender:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def enqueue(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 5.0) -> bool:
        return True

    def close(self, timeout: float = 5.0) -> None:
        return None


def capture_client(**kwargs: Any) -> tuple[AgentScope, CaptureSender]:
    client = AgentScope(api_key="as_test_testing", **kwargs)
    client._sender.close()  # noqa: SLF001
    sender = CaptureSender()
    client._sender = sender  # type: ignore[assignment]  # noqa: SLF001
    return client, sender


async def test_async_context_does_not_leak_between_concurrent_traces() -> None:
    client, sender = capture_client()

    @client.trace(name="concurrent-agent")
    async def run(label: str) -> str:
        async with client.span(name=f"agent-{label}", span_type="agent"):
            async with client.span(name=f"tool-{label}", span_type="tool"):
                await asyncio.sleep(0)
        return label

    assert await asyncio.gather(run("a"), run("b")) == ["a", "b"]
    starts = [event for event in sender.events if event["type"] == "TRACE_START"]
    assert len({event["trace_id"] for event in starts}) == 2
    for label in ("a", "b"):
        span = next(
            event
            for event in sender.events
            if event["type"] == "SPAN_START" and event["payload"]["name"] == f"tool-{label}"
        )
        trace = next(event for event in starts if event["payload"]["input"]["args"][0] == label)
        assert span["trace_id"] == trace["trace_id"]
        parent = next(
            event
            for event in sender.events
            if event["type"] == "SPAN_START" and event["payload"]["name"] == f"agent-{label}"
        )
        assert span["parent_span_id"] == parent["span_id"]


def test_unsampled_errors_are_retained() -> None:
    client, sender = capture_client(trace_sample_rate=0, always_sample_errors=True)

    @client.trace(name="failing-agent")
    def fail() -> None:
        raise RuntimeError("provider unavailable")

    with pytest.raises(RuntimeError):
        fail()
    assert [event["type"] for event in sender.events] == ["TRACE_START", "TRACE_END"]
    assert sender.events[-1]["payload"]["status"] == "ERROR"


def test_redaction_processors_remove_sensitive_values() -> None:
    event = {
        "payload": {
            "input": {
                "email": "person@example.com",
                "authorization": "Bearer secret-token-value",
                "key": "as_live_abcdefghijklmnopqrstuvwxyz",
                "card": "4242 4242 4242 4242",
            }
        }
    }
    for processor in default_redaction():
        event = processor(event)
    serialized = str(event)
    assert "person@example.com" not in serialized
    assert "secret-token-value" not in serialized
    assert "as_live_abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "4242 4242 4242 4242" not in serialized
    assert event["payload"]["metadata"]["agentscope.redacted"] is True


def test_transport_failure_never_breaks_host_application() -> None:
    client = AgentScope(
        api_key="as_test_unreachable",
        endpoint="http://127.0.0.1:1",
        batch_size=1,
        flush_interval=0.01,
        timeout=0.01,
        max_retries=0,
    )

    @client.trace(name="healthy-host")
    def host() -> int:
        return 42

    assert host() == 42
    client.close(timeout=0.5)
