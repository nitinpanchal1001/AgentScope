import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import smtplib
import socket
import time
from email.message import EmailMessage
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from agentscope_evaluation import EvaluationEngine, EvaluationRequest, EvaluationType
from agentscope_evaluation.providers import OpenAIEmbeddingProvider
from pydantic import BaseModel, ConfigDict, Field

from agentscope_worker.celery_app import celery_app, settings

TERMINAL_STATUSES = {"SUCCESS", "FAILED", "SKIPPED"}
logger = logging.getLogger("agentscope.worker.evaluation")
experiment_logger = logging.getLogger("agentscope.worker.experiment")
replay_logger = logging.getLogger("agentscope.worker.replay")
failure_logger = logging.getLogger("agentscope.worker.failure")
alert_logger = logging.getLogger("agentscope.worker.alert")


class AgentUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0, ge=0)


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    spans: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    usage: AgentUsage = Field(default_factory=AgentUsage)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(error, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)):
        return True
    if isinstance(error, smtplib.SMTPResponseException):
        return 400 <= error.smtp_code < 500
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    status_code = (
        error.response.status_code
        if isinstance(error, httpx.HTTPStatusError)
        else getattr(error, "status_code", None)
    )
    return status_code == 429 or (isinstance(status_code, int) and status_code >= 500)


async def _post_completion(client: httpx.AsyncClient, result_id: str, body: dict[str, Any]) -> None:
    response = await client.post(
        f"/internal/v1/evaluation-results/{result_id}/complete",
        json=body,
    )
    response.raise_for_status()


async def _evaluate(result_id: str) -> str:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=headers,
        timeout=httpx.Timeout(45),
    ) as client:
        response = await client.get(f"/internal/v1/evaluation-results/{result_id}/payload")
        response.raise_for_status()
        payload = response.json()
        if payload["status"] in TERMINAL_STATUSES:
            return str(payload["status"])

        evaluator_type = EvaluationType(payload["evaluator_type"])
        embedding_provider = None
        if evaluator_type is EvaluationType.SEMANTIC_SIMILARITY:
            if not settings.openai_api_key:
                await _post_completion(
                    client,
                    result_id,
                    {
                        "status": "FAILED",
                        "error_type": "CONFIGURATION_ERROR",
                        "error_message": "OPENAI_API_KEY is required for semantic evaluation",
                    },
                )
                return "FAILED"
            embedding_provider = OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key,
                model=payload["model"],
            )

        request = EvaluationRequest(
            evaluator_type=evaluator_type,
            input=payload.get("input"),
            output=payload.get("output"),
            expected_output=payload.get("expected_output"),
            context=payload.get("context"),
            trace=payload["trace"],
            configuration=payload["configuration"],
            threshold=float(payload["threshold"]),
            provider=payload.get("provider"),
            model=payload.get("model"),
            rubric=payload.get("rubric"),
        )
        try:
            outcome = await EvaluationEngine(embedding_provider=embedding_provider).evaluate(
                request
            )
        except Exception as error:
            if _is_retryable(error):
                raise
            await _post_completion(
                client,
                result_id,
                {
                    "status": "FAILED",
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:8000],
                },
            )
            return "FAILED"

        await _post_completion(
            client,
            result_id,
            {
                "status": "SUCCESS",
                "score": outcome.score,
                "passed": outcome.passed,
                "label": outcome.label,
                "reason": outcome.reason,
                "evidence": outcome.evidence,
                "metadata": outcome.metadata,
            },
        )
        return "SUCCESS"


async def _fail_evaluation(result_id: str, error: Exception) -> str:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=headers,
        timeout=httpx.Timeout(45),
    ) as client:
        await _post_completion(
            client,
            result_id,
            {
                "status": "FAILED",
                "error_type": type(error).__name__,
                "error_message": str(error)[:8000],
            },
        )
    return "FAILED"


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.evaluate_trace",
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def evaluate_trace(self: Any, result_id: str) -> str:
    try:
        outcome = asyncio.run(_evaluate(result_id))
        logger.info(
            "evaluation.completed",
            extra={"result_id": result_id, "status": outcome},
        )
        return outcome
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            raise self.retry(exc=error) from error
        logger.exception("evaluation.task_failed", extra={"result_id": result_id})
        return asyncio.run(_fail_evaluation(result_id, error))


async def _validate_experiment_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Agent endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and not settings.experiment_allow_http:
        raise ValueError("Plain HTTP agent endpoints are disabled")
    hostname = parsed.hostname.lower()
    allowed_hosts = {host.lower() for host in settings.experiment_allowed_hosts}
    if allowed_hosts and hostname not in allowed_hosts:
        raise ValueError("Agent endpoint host is not in AGENTSCOPE_EXPERIMENT_ALLOWED_HOSTS")
    if settings.experiment_allow_private_endpoints:
        return
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(hostname, parsed.port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Agent endpoint host did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Agent endpoint resolves to a private or reserved address")


def _experiment_headers(run_id: str, references: dict[str, str]) -> dict[str, str]:
    headers = {"X-AgentScope-Run-ID": run_id}
    for header, variable_name in references.items():
        value = os.getenv(variable_name)
        if value is None:
            raise ValueError(
                f"Required agent credential environment variable is missing: {variable_name}"
            )
        headers[header] = value
    return headers


def _replay_headers(replay_id: str, references: dict[str, str]) -> dict[str, str]:
    headers = _experiment_headers(replay_id, references)
    headers["X-AgentScope-Replay-ID"] = replay_id
    headers.pop("X-AgentScope-Run-ID")
    return headers


async def _post_experiment_completion(
    client: httpx.AsyncClient, run_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(f"/internal/v1/experiment-runs/{run_id}/complete", json=body)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def _dispatch_follow_up(completion: dict[str, Any]) -> None:
    for result_id in completion.get("evaluation_result_ids", []):
        celery_app.send_task(
            "agentscope.evaluate_trace",
            args=[str(result_id)],
            queue="evaluation",
        )
    for next_run_id in completion.get("next_run_ids", []):
        celery_app.send_task(
            "agentscope.execute_experiment_run",
            args=[str(next_run_id)],
            queue="experiment",
        )


async def _execute_experiment_run(run_id: str) -> str:
    worker_headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=worker_headers,
        timeout=httpx.Timeout(45),
    ) as internal_client:
        payload_response = await internal_client.get(
            f"/internal/v1/experiment-runs/{run_id}/payload"
        )
        payload_response.raise_for_status()
        payload = payload_response.json()
        if payload["status"] == "EVALUATING":
            for result_id in payload.get("evaluation_result_ids", []):
                celery_app.send_task(
                    "agentscope.evaluate_trace",
                    args=[str(result_id)],
                    queue="evaluation",
                )
            return "EVALUATING"
        if payload["status"] != "RUNNING":
            return str(payload["status"])

        endpoint = str(payload["endpoint"])
        await _validate_experiment_endpoint(endpoint)
        agent_headers = _experiment_headers(run_id, payload.get("headers_from_env", {}))
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(payload["timeout_seconds"]),
            follow_redirects=False,
        ) as agent_client:
            response = await agent_client.post(
                endpoint,
                json=payload["request"],
                headers=agent_headers,
            )
            response.raise_for_status()
            if len(response.content) > settings.experiment_max_response_bytes:
                raise ValueError("Agent response exceeds the configured byte limit")
            parsed = AgentResponse.model_validate_json(response.content)
        latency_ms = round((time.perf_counter() - started) * 1000)
        completion = await _post_experiment_completion(
            internal_client,
            run_id,
            {
                "status": "SUCCESS",
                "output": parsed.output,
                "metadata": parsed.metadata,
                "spans": parsed.spans,
                "latency_ms": latency_ms,
                **parsed.usage.model_dump(),
            },
        )
        _dispatch_follow_up(completion)
        return "EVALUATING" if completion.get("evaluation_result_ids") else "COMPLETED"


async def _fail_experiment_run(run_id: str, error: Exception, latency_ms: int) -> str:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=headers,
        timeout=httpx.Timeout(45),
    ) as client:
        completion = await _post_experiment_completion(
            client,
            run_id,
            {
                "status": "FAILED",
                "latency_ms": latency_ms,
                "error_type": type(error).__name__,
                "error_message": str(error)[:8000],
            },
        )
    _dispatch_follow_up(completion)
    return "FAILED"


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.execute_experiment_run",
    max_retries=3,
    acks_late=True,
)
def execute_experiment_run(self: Any, run_id: str) -> str:
    started = time.perf_counter()
    try:
        outcome = asyncio.run(_execute_experiment_run(run_id))
        experiment_logger.info(
            "experiment_run.completed",
            extra={"run_id": run_id, "status": outcome},
        )
        return outcome
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            countdown = min(60, 2 ** (self.request.retries + 1))
            raise self.retry(exc=error, countdown=countdown) from error
        experiment_logger.exception("experiment_run.failed", extra={"run_id": run_id})
        return asyncio.run(
            _fail_experiment_run(
                run_id,
                error,
                round((time.perf_counter() - started) * 1000),
            )
        )


async def _post_replay_completion(
    client: httpx.AsyncClient, replay_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    response = await client.post(f"/internal/v1/replays/{replay_id}/complete", json=body)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def _execute_replay(replay_id: str) -> str:
    worker_headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=worker_headers,
        timeout=httpx.Timeout(45),
    ) as internal_client:
        payload_response = await internal_client.get(f"/internal/v1/replays/{replay_id}/payload")
        payload_response.raise_for_status()
        payload = payload_response.json()
        if payload["status"] != "RUNNING":
            return str(payload["status"])

        endpoint = str(payload["endpoint"])
        await _validate_experiment_endpoint(endpoint)
        agent_headers = _replay_headers(replay_id, payload.get("headers_from_env", {}))
        started = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(payload["timeout_seconds"]),
            follow_redirects=False,
        ) as agent_client:
            response = await agent_client.post(
                endpoint,
                json=payload["request"],
                headers=agent_headers,
            )
            response.raise_for_status()
            if len(response.content) > settings.experiment_max_response_bytes:
                raise ValueError("Agent response exceeds the configured byte limit")
            parsed = AgentResponse.model_validate_json(response.content)
        completion = await _post_replay_completion(
            internal_client,
            replay_id,
            {
                "status": "SUCCESS",
                "output": parsed.output,
                "metadata": parsed.metadata,
                "spans": parsed.spans,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                **parsed.usage.model_dump(),
            },
        )
        for result_id in completion.get("evaluation_result_ids", []):
            celery_app.send_task(
                "agentscope.evaluate_trace",
                args=[str(result_id)],
                queue="evaluation",
            )
        return str(completion["status"])


async def _fail_replay(replay_id: str, error: Exception, latency_ms: int) -> str:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=headers,
        timeout=httpx.Timeout(45),
    ) as client:
        await _post_replay_completion(
            client,
            replay_id,
            {
                "status": "FAILED",
                "latency_ms": latency_ms,
                "error_type": type(error).__name__,
                "error_message": str(error)[:8000],
            },
        )
    return "FAILED"


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.execute_replay",
    max_retries=3,
    acks_late=True,
)
def execute_replay(self: Any, replay_id: str) -> str:
    started = time.perf_counter()
    try:
        outcome = asyncio.run(_execute_replay(replay_id))
        replay_logger.info(
            "replay.completed",
            extra={"replay_id": replay_id, "status": outcome},
        )
        return outcome
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            countdown = min(60, 2 ** (self.request.retries + 1))
            raise self.retry(exc=error, countdown=countdown) from error
        replay_logger.exception("replay.failed", extra={"replay_id": replay_id})
        return asyncio.run(
            _fail_replay(
                replay_id,
                error,
                round((time.perf_counter() - started) * 1000),
            )
        )


async def _analyze_failure(trace_id: str) -> str:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url,
        headers=headers,
        timeout=httpx.Timeout(45),
    ) as client:
        response = await client.post(f"/internal/v1/failures/analyze/{trace_id}")
        response.raise_for_status()
        value = response.json()
        return "NO_FAILURE" if value is None else str(value["id"])


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.analyze_failure",
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    acks_late=True,
)
def analyze_failure(self: Any, trace_id: str) -> str:
    try:
        outcome = asyncio.run(_analyze_failure(trace_id))
        failure_logger.info(
            "failure_analysis.completed",
            extra={"trace_id": trace_id, "outcome": outcome},
        )
        return outcome
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            raise self.retry(exc=error) from error
        failure_logger.exception("failure_analysis.failed", extra={"trace_id": trace_id})
        raise


async def _validate_notification_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Webhook endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and not settings.notification_allow_http:
        raise ValueError("Plain HTTP webhook endpoints are disabled")
    if settings.notification_allow_private_endpoints:
        return
    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    if not addresses:
        raise ValueError("Webhook endpoint host did not resolve")
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Webhook endpoint resolves to a private or reserved address")


def _send_email(target: str, event: dict[str, Any]) -> None:
    if not settings.smtp_host:
        raise ValueError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = target
    message["Subject"] = f"[{event['severity']}] AgentScope alert: {event['rule_name']}"
    message.set_content(
        "\n".join(
            (
                f"Rule: {event['rule_name']}",
                f"Metric: {event['metric']}",
                f"Observed: {event['observed_value']}",
                f"Threshold: {event['threshold']}",
                f"Window ended: {event['window_ended_at']}",
            )
        )
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def _record_alert_delivery(event_id: str, delivered: bool, error: str | None) -> None:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url, headers=headers, timeout=httpx.Timeout(45)
    ) as client:
        response = await client.post(
            f"/internal/v1/alerts/{event_id}/delivery",
            json={"delivered": delivered, "error": error},
        )
        response.raise_for_status()


async def _deliver_alert(event: dict[str, Any]) -> str:
    if event["channel"] == "WEBHOOK":
        endpoint = str(event["channel_target"])
        await _validate_notification_endpoint(endpoint)
        body = json.dumps(
            {key: value for key, value in event.items() if key != "channel_target"},
            separators=(",", ":"),
        ).encode()
        signature = hmac.new(
            settings.notification_signing_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        async with httpx.AsyncClient(timeout=httpx.Timeout(20), follow_redirects=False) as client:
            response = await client.post(
                endpoint,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-AgentScope-Signature-256": f"sha256={signature}",
                },
            )
            response.raise_for_status()
    else:
        await asyncio.to_thread(_send_email, str(event["channel_target"]), event)
    await _record_alert_delivery(str(event["id"]), True, None)
    return "DELIVERED"


async def _evaluate_alerts() -> dict[str, int]:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url, headers=headers, timeout=httpx.Timeout(45)
    ) as client:
        response = await client.post("/internal/v1/alerts/evaluate")
        response.raise_for_status()
        payload = response.json()
    for event in payload["triggered"]:
        celery_app.send_task("agentscope.deliver_alert", args=[event], queue="alerts")
    return {"evaluated": int(payload["evaluated_rules"]), "triggered": len(payload["triggered"])}


@celery_app.task(name="agentscope.evaluate_alerts", acks_late=True)  # type: ignore[untyped-decorator]
def evaluate_alerts() -> dict[str, int]:
    result = asyncio.run(_evaluate_alerts())
    alert_logger.info("alerts.evaluated", extra=result)
    return result


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.deliver_alert",
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    acks_late=True,
)
def deliver_alert(self: Any, event: dict[str, Any]) -> str:
    try:
        return asyncio.run(_deliver_alert(event))
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            raise self.retry(exc=error) from error
        asyncio.run(_record_alert_delivery(str(event["id"]), False, str(error)[:2000]))
        alert_logger.exception("alert.delivery_failed", extra={"event_id": event["id"]})
        return "FAILED"


async def _expire_telemetry() -> dict[str, Any]:
    headers = {"X-AgentScope-Worker-Key": settings.worker_api_key}
    async with httpx.AsyncClient(
        base_url=settings.worker_api_url, headers=headers, timeout=httpx.Timeout(120)
    ) as client:
        response = await client.post("/internal/v1/maintenance/retention")
        response.raise_for_status()
        return cast(dict[str, Any], response.json())


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="agentscope.expire_telemetry",
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    acks_late=True,
)
def expire_telemetry(self: Any) -> dict[str, Any]:
    try:
        result = asyncio.run(_expire_telemetry())
        alert_logger.info(
            "maintenance.retention_completed",
            extra={"deleted_traces": result["deleted_traces"]},
        )
        return result
    except Exception as error:
        if _is_retryable(error) and self.request.retries < self.max_retries:
            raise self.retry(exc=error) from error
        raise
