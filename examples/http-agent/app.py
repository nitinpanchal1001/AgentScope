from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="AgentScope deterministic experiment fixture")
received_alerts: list[dict[str, Any]] = []


class InvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    context: Any | None = None
    configuration: dict[str, Any]
    metadata: dict[str, Any]


@app.post("/invoke")
async def invoke(request: InvocationRequest) -> dict[str, Any]:
    if isinstance(request.input, dict) and "expected_response" in request.input:
        output = request.input["expected_response"]
    else:
        output = request.input
    return {
        "output": output,
        "metadata": {"fixture": True},
        "spans": [
            {
                "type": "AGENT",
                "name": "deterministic fixture",
                "input": request.input,
                "output": output,
                "status": "SUCCESS",
            }
        ],
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0,
        },
    }


@app.post("/alerts")
async def receive_alert(
    payload: dict[str, Any],
    signature: str = Header(alias="X-AgentScope-Signature-256"),
) -> dict[str, bool]:
    received_alerts.append({"payload": payload, "signature": signature})
    return {"accepted": True}


@app.get("/alerts/latest")
async def latest_alert() -> dict[str, Any] | None:
    return received_alerts[-1] if received_alerts else None
