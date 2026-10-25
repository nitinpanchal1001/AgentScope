from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="AgentScope customer-support demo agent", version="2.0.0")

ORDERS: dict[str, dict[str, Any]] = {
    "A100": {"status": "shipped", "delivered_days_ago": None},
    "B200": {"status": "processing", "delivered_days_ago": None},
    "C300": {"status": "delivered", "delivered_days_ago": 10},
    "D400": {"status": "delivered", "delivered_days_ago": 45},
    "E500": {"status": "cancelled", "delivered_days_ago": None},
}
POLICIES = {
    "cancellation": "Orders can be cancelled only while processing.",
    "refund_window": "Delivered orders are refundable within 30 days.",
    "shipping": "Shipped orders cannot be cancelled; contact support for delivery exceptions.",
}


class InvocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Any
    context: Any | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def get_order(order_id: str) -> dict[str, Any] | None:
    value = ORDERS.get(order_id)
    return {"order_id": order_id, **value} if value is not None else None


def cancel_order(order_id: str, *, enforce_policy: bool) -> dict[str, Any]:
    order = get_order(order_id)
    if order is None:
        return {"outcome": "not_found"}
    if enforce_policy and order["status"] != "processing":
        return {"outcome": "denied", "status": order["status"]}
    return {"outcome": "cancelled", "status": "cancelled"}


def refund_order(order_id: str, *, enforce_policy: bool) -> dict[str, Any]:
    order = get_order(order_id)
    if order is None:
        return {"outcome": "not_found"}
    within_window = (
        order["status"] == "delivered"
        and order["delivered_days_ago"] is not None
        and order["delivered_days_ago"] <= 30
    )
    if enforce_policy and not within_window:
        return {"outcome": "denied", "status": order["status"]}
    return {"outcome": "approved"}


def search_policy(topic: str, *, precise: bool) -> dict[str, str]:
    if precise and topic in POLICIES:
        return {"topic": topic, "policy": POLICIES[topic]}
    return {"topic": topic, "policy": "Contact customer support for policy details."}


def _tool_span(name: str, tool_input: dict[str, Any], output: Any) -> dict[str, Any]:
    return {
        "type": "TOOL",
        "name": name,
        "input": tool_input,
        "output": output,
        "status": "SUCCESS",
    }


def _not_found(order_id: str) -> dict[str, str]:
    return {"message": f"Order {order_id} was not found.", "order_id": order_id}


def run_agent(
    value: Any, version: Literal["support-v1", "support-v2"]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {"message": "Please provide a structured support request."}, []
    intent = str(value.get("intent", "unknown"))
    order_id = str(value.get("order_id", ""))
    improved = version == "support-v2"

    if intent == "get_order":
        order = get_order(order_id)
        spans = [_tool_span("get_order", {"order_id": order_id}, order)]
        if order is None:
            return _not_found(order_id), spans
        return {
            "message": f"Order {order_id} is {order['status']}.",
            "order_id": order_id,
            "status": order["status"],
        }, spans

    if intent == "cancel_order":
        result = cancel_order(order_id, enforce_policy=improved)
        spans = [_tool_span("cancel_order", {"order_id": order_id}, result)]
        if result["outcome"] == "not_found":
            return _not_found(order_id), spans
        if result["outcome"] == "denied":
            return {
                "message": f"Order {order_id} cannot be cancelled after shipping.",
                "order_id": order_id,
                "status": result["status"],
            }, spans
        return {
            "message": f"Order {order_id} was cancelled.",
            "order_id": order_id,
            "status": "cancelled",
        }, spans

    if intent == "refund_order":
        result = refund_order(order_id, enforce_policy=improved)
        spans = [_tool_span("refund_order", {"order_id": order_id}, result)]
        if result["outcome"] == "not_found":
            return _not_found(order_id), spans
        if result["outcome"] == "denied":
            return {
                "message": f"Order {order_id} is outside the 30-day refund window.",
                "order_id": order_id,
                "refund_status": "denied",
            }, spans
        return {
            "message": f"Refund approved for order {order_id}.",
            "order_id": order_id,
            "refund_status": "approved",
        }, spans

    if intent == "search_policy":
        topic = str(value.get("topic", ""))
        result = search_policy(topic, precise=improved)
        return result, [_tool_span("search_policy", {"topic": topic}, result)]

    return {
        "message": "I cannot safely complete that request; a support specialist can help.",
        "status": "escalated",
    }, []


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/invoke")
async def invoke(request: InvocationRequest) -> dict[str, Any]:
    configured = request.configuration.get("prompt_version", "support-v2")
    version: Literal["support-v1", "support-v2"] = (
        "support-v1" if configured == "support-v1" else "support-v2"
    )
    output, spans = run_agent(request.input, version)
    return {
        "output": output,
        "metadata": {"agent_version": version, "deterministic": True},
        "spans": spans,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0,
        },
    }
