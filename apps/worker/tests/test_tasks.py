import asyncio
import hashlib
import hmac
import json
import smtplib

import httpx
import pytest

from agentscope_worker.celery_app import settings
from agentscope_worker.tasks import (
    AgentResponse,
    _deliver_alert,
    _experiment_headers,
    _is_retryable,
    _replay_headers,
    _validate_experiment_endpoint,
)


class ProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_retryable_external_failures_are_bounded_by_task_policy() -> None:
    assert _is_retryable(httpx.ConnectTimeout("timed out")) is True
    assert _is_retryable(ProviderError(429)) is True
    assert _is_retryable(ProviderError(503)) is True
    assert _is_retryable(ProviderError(400)) is False
    assert _is_retryable(ValueError("invalid evaluator configuration")) is False
    assert _is_retryable(smtplib.SMTPServerDisconnected("lost connection")) is True
    assert _is_retryable(smtplib.SMTPResponseException(450, b"mailbox busy")) is True
    assert _is_retryable(smtplib.SMTPResponseException(550, b"rejected")) is False


def test_experiment_endpoint_policy_and_environment_header_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "experiment_allow_http", False)
    monkeypatch.setattr(settings, "experiment_allow_private_endpoints", False)
    with pytest.raises(ValueError, match="Plain HTTP"):
        asyncio.run(_validate_experiment_endpoint("http://127.0.0.1/invoke"))

    monkeypatch.setenv("TEST_AGENT_AUTH", "Bearer secret-value")
    assert _experiment_headers("run-1", {"Authorization": "TEST_AGENT_AUTH"}) == {
        "X-AgentScope-Run-ID": "run-1",
        "Authorization": "Bearer secret-value",
    }
    assert "secret-value" not in str({"Authorization": "TEST_AGENT_AUTH"})
    with pytest.raises(ValueError, match="environment variable is missing"):
        _experiment_headers("run-1", {"Authorization": "MISSING_AGENT_AUTH"})
    assert _replay_headers("replay-1", {"Authorization": "TEST_AGENT_AUTH"}) == {
        "X-AgentScope-Replay-ID": "replay-1",
        "Authorization": "Bearer secret-value",
    }


def test_agent_response_contract_is_strict_and_bounded() -> None:
    response = AgentResponse.model_validate(
        {
            "output": {"answer": "ok"},
            "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        }
    )
    assert response.usage.total_tokens == 3
    with pytest.raises(ValueError):
        AgentResponse.model_validate({"output": "ok", "unexpected": True})


def test_webhook_delivery_is_signed_and_target_is_not_in_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, bytes, dict[str, str]]] = []

    class TestClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "TestClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, **kwargs: object) -> httpx.Response:
            content = kwargs.get("content", b"")
            headers = kwargs.get("headers", {})
            requests.append((url, content, headers))  # type: ignore[arg-type]
            target = url if url.startswith("http") else f"http://test{url}"
            return httpx.Response(200, request=httpx.Request("POST", target))

    monkeypatch.setattr(httpx, "AsyncClient", TestClient)
    monkeypatch.setattr(settings, "notification_allow_http", True)
    monkeypatch.setattr(settings, "notification_allow_private_endpoints", True)
    monkeypatch.setattr(settings, "notification_signing_secret", "test-signing-secret")
    event = {
        "id": "event-1",
        "rule_name": "Error rate",
        "metric": "ERROR_RATE",
        "observed_value": "25",
        "threshold": "5",
        "severity": "CRITICAL",
        "channel": "WEBHOOK",
        "channel_target": "http://127.0.0.1/hook?secret=value",
        "window_ended_at": "2026-10-24T12:00:00Z",
    }

    assert asyncio.run(_deliver_alert(event)) == "DELIVERED"
    webhook = requests[0]
    payload = json.loads(webhook[1])
    assert "channel_target" not in payload
    expected = hmac.new(b"test-signing-secret", webhook[1], hashlib.sha256).hexdigest()
    assert webhook[2]["X-AgentScope-Signature-256"] == f"sha256={expected}"
    assert requests[1][0] == "/internal/v1/alerts/event-1/delivery"
