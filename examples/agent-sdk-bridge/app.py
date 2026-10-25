import asyncio
import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class InvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    context: Any | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="AgentScope bridge for Agent SDK agents")


def _message(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("message", "prompt", "query", "input"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return json.dumps(value, ensure_ascii=False)


def _events(response: httpx.Response) -> list[dict[str, Any]]:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = response.json()
        return payload.get("events", []) if isinstance(payload, dict) else []
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def _usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = output_tokens = 0
    for event in events:
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("data", {}).get("usage", {})
        input_tokens += int(usage.get("inputTokens", 0))
        output_tokens += int(usage.get("outputTokens", 0))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "total_cost": 0,
    }


def _spans(events: list[dict[str, Any]], prompt: str, output: str) -> list[dict[str, Any]]:
    tool_inputs: dict[str, Any] = {}
    for event in events:
        if event.get("type") != "actions.requested":
            continue
        for call in event.get("data", {}).get("calls", []):
            if call_id := call.get("callId"):
                tool_inputs[call_id] = call.get("args")

    spans: list[dict[str, Any]] = [
        {
            "type": "AGENT",
            "name": "Agent SDK turn",
            "input": prompt,
            "output": output,
            "status": "SUCCESS",
        }
    ]
    for event in events:
        if event.get("type") != "action.result":
            continue
        data = event.get("data", {})
        call_id = data.get("callId")
        spans.append(
            {
                "type": "TOOL",
                "name": str(data.get("toolName") or data.get("name") or "tool"),
                "input": tool_inputs.get(call_id),
                "output": data.get("output") or data.get("result"),
                "status": "ERROR" if data.get("isError") else "SUCCESS",
                "metadata": {"call_id": call_id, "stubbed": bool(data.get("stubbed"))},
            }
        )
    return spans


async def _wait_for_turn(
    client: httpx.AsyncClient, session_id: str, timeout_seconds: float
) -> list[dict[str, Any]]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        response = await client.get(f"/v1/session/{session_id}/events?format=json")
        response.raise_for_status()
        events = _events(response)
        terminal = next(
            (
                event
                for event in reversed(events)
                if event.get("type") in {"turn.completed", "turn.failed", "session.failed"}
            ),
            None,
        )
        if terminal:
            if terminal.get("type") != "turn.completed":
                message = terminal.get("data", {}).get("message", "Agent SDK turn failed")
                raise HTTPException(status_code=502, detail=message)
            return events
        await asyncio.sleep(0.2)
    raise HTTPException(status_code=504, detail="Agent SDK turn timed out")


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "agent_sdk_url": os.getenv("AGENT_SDK_URL", "http://127.0.0.1:3000")}


@app.post("/invoke")
async def invoke(
    request: InvocationRequest,
    run_id: str | None = Header(default=None, alias="X-AgentScope-Run-ID"),
) -> dict[str, Any]:
    base_url = os.getenv("AGENT_SDK_URL", "http://127.0.0.1:3000").rstrip("/")
    timeout_seconds = float(os.getenv("AGENT_SDK_TIMEOUT_SECONDS", "180"))
    prompt = _message(request.input)
    headers = {}
    if token := os.getenv("AGENT_SDK_BEARER_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(timeout_seconds),
    ) as client:
        try:
            response = await client.post(
                "/v1/session",
                json={"message": prompt, "purpose": "eval", "dryRun": True},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"Agent SDK is unavailable: {error}") from error

        session_id = response.json().get("sessionId")
        if not session_id:
            raise HTTPException(status_code=502, detail="Agent SDK did not return a session ID")
        events = await _wait_for_turn(client, session_id, timeout_seconds)

    replies = [
        event.get("data", {}).get("text", "")
        for event in events
        if event.get("type") == "message.completed"
        and not event.get("data", {}).get("parentCallId")
        and event.get("data", {}).get("text")
    ]
    output = replies[-1] if replies else next(
        (
            event.get("data", {}).get("result", "")
            for event in reversed(events)
            if event.get("type") == "turn.completed"
        ),
        "",
    )
    return {
        "output": output,
        "metadata": {
            "agent_sdk_session_id": session_id,
            "agentscope_run_id": run_id,
        },
        "spans": _spans(events, prompt, output),
        "usage": _usage(events),
    }
