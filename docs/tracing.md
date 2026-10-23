# Tracing architecture

Phase 2 separates dashboard traffic from telemetry ingestion:

```text
instrumented Python process
  -> bounded SDK queue
  -> POST /v1/ingest/batch (project API key)
  -> idempotent event transaction
  -> traces + hierarchical spans in PostgreSQL
  -> JWT-scoped query API and SSE
  -> trace explorer and detail timeline
```

## Event lifecycle

The SDK emits `TRACE_START`, `SPAN_START`, `SPAN_END`, and `TRACE_END`. Every event has a UUID
`event_id`; the database records that identifier in the same transaction as the trace mutation. A
retry of a complete or partial batch therefore cannot create a duplicate trace or span.

Span parentage is carried as an external span identifier and resolved to the internal foreign key at
ingestion. An end event must follow its corresponding start event. Invalid references reject and roll
back the whole batch so a caller can safely retry it.

## Safety boundaries

- Project API keys resolve the organization, project, and environment on the server. The payload
  cannot choose or override its tenant.
- Redis enforces a per-key fixed-window request limit. Ingestion fails open if Redis is unavailable so
  telemetry coordination does not become a host-application outage; upstream/WAF limiting remains
  recommended for shared deployments.
- Batch, event, content, and metadata sizes are configurable. Oversized input/output values are
  replaced with a bounded preview and `_agentscope_truncated: true`.
- SDK processors run before enqueueing or network transport. Built-ins redact email, payment-card,
  API-key, and bearer-token patterns and mark event metadata when redaction occurs.
- A bounded queue drops telemetry under sustained backpressure instead of growing without limit.
  Transport and processor failures never propagate into instrumented application code.

## Sampling and delivery

Sampling is deterministic from the trace UUID, so a normal trace and all of its spans share one
decision. Unsampled events stay local only until the trace finishes; when `always_sample_errors` is
enabled, failed traces are retained. The sender batches by count or interval, retries with bounded
exponential backoff, and attempts a bounded final drain on `close()`.

## Query and live updates

Trace lists use a stable `(created_at, id)` cursor and can filter by project, environment, status,
date range, model, agent version, span type, and tag. Detail responses return ordered spans; the web
client reconstructs the parent/child tree. Active trace pages consume authenticated server-sent events
from `/api/v1/traces/{id}/events` until the trace reaches a terminal state.
