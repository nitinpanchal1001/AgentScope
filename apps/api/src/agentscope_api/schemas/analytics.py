from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AnalyticsSummary(BaseModel):
    total_traces: int
    successful_traces: int
    error_traces: int
    success_rate: float
    error_rate: float
    average_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: Decimal
    average_evaluation_score: float | None = None


class AnalyticsBucket(BaseModel):
    started_at: datetime
    trace_count: int
    success_count: int
    error_count: int
    average_latency_ms: float | None
    total_tokens: int
    total_cost: Decimal


class UsageBreakdown(BaseModel):
    name: str
    count: int
    error_count: int = 0
    total_tokens: int = 0
    total_cost: Decimal = Decimal("0")


class AnalyticsResponse(BaseModel):
    started_after: datetime
    started_before: datetime
    bucket: Literal["5m", "1h", "1d"]
    summary: AnalyticsSummary
    timeseries: list[AnalyticsBucket]
    models: list[UsageBreakdown]
    providers: list[UsageBreakdown]
    tools: list[UsageBreakdown]
    agents: list[UsageBreakdown]
    failure_types: list[UsageBreakdown]
