from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "agentscope_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
    registry=REGISTRY,
)
HTTP_REQUEST_DURATION = Histogram(
    "agentscope_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY,
)
INGESTION_BATCHES = Counter(
    "agentscope_ingestion_batches_total",
    "Telemetry ingestion batches by outcome.",
    ("outcome",),
    registry=REGISTRY,
)
INGESTION_EVENTS = Counter(
    "agentscope_ingestion_events_total",
    "Telemetry events processed by outcome.",
    ("outcome",),
    registry=REGISTRY,
)


def render_metrics() -> bytes:
    return generate_latest(REGISTRY)
