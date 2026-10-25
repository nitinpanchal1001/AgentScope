# Metrics and cost architecture

Phase 3 turns stored telemetry into reproducible operational metrics without changing historical
records when provider prices change.

## Pricing

`model_pricing` stores provider/model input and output rates per million tokens with an effective
time window. A project-specific version takes precedence over the global catalogue. Creating a new
project version closes the preceding interval and is recorded in the audit log.

The initial OpenAI standard short-context entries are effective from 24 October 2026 and are sourced
from the [official OpenAI API pricing page](https://developers.openai.com/api/docs/pricing). Pricing
is time-sensitive: operators should add a new version when a provider changes a rate rather than
editing an existing row.

At `SPAN_END`, AgentScope uses the span start time to select the effective rate. Explicit SDK cost
values take precedence; otherwise the server calculates:

```text
(input tokens × input rate + output tokens × output rate) / 1,000,000
```

The selected pricing row is stored on the span. Completed span usage is rolled into the trace when
the trace closes. Event idempotency prevents retries from adding usage twice. Migration
`20261024_0004` backfills zero-valued historical summaries from their recorded spans without
overwriting nonzero caller-supplied totals.

## Analytics

`GET /api/v1/projects/{project_id}/analytics` is tenant-scoped through the normal project membership
guard. It supports environment, time-range, and bucket filters. Ranges are capped at 90 days to
protect the transactional store. Automatic buckets select five minutes, one hour, or one day.

The response contains:

- trace volume, success/error rates, and token/cost totals;
- average and P50/P95/P99 latency;
- time-series volume, errors, latency, tokens, and cost;
- model, provider, tool, agent, and failure-type breakdowns.

PostgreSQL performs aggregates and percentiles. SQLite uses a deterministic percentile fallback for
unit tests. At higher telemetry volume, the repository boundary can move time-series analytics to a
columnar store without changing the API contract.

