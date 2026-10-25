# AgentScope

AgentScope is an open-source engineering platform for tracing, evaluating, experimenting with, and regression-testing AI agents. The repository contains the complete production-hardening scope: secure multi-tenant control plane, telemetry and evaluation, experiments, release gates, immutable replay, failure intelligence, alerting, retention, runnable demo data, observability, CI, and AWS deployment configuration.

## What works today

- Email/password registration and login using Argon2id
- short-lived JWT access tokens and rotating, revocable refresh-token families
- organization membership and centralized OWNER / ADMIN / MEMBER / VIEWER permissions
- tenant-scoped project access that does not trust resource UUIDs alone
- transactional project creation with development, staging, and production environments
- one-time-display `as_live_…` / `as_test_…` project keys; only keyed hashes are stored
- security audit records for organization, project, key creation, and key revocation
- structured JSON logs, correlation IDs, normalized API errors, secure response headers
- liveness and dependency-aware readiness probes
- a Next.js onboarding control plane for the complete Phase 1 flow
- idempotent, rate-limited batch ingestion authenticated with project API keys
- trace and hierarchical span persistence with payload bounds and safe truncation
- a Python SDK with async-safe context propagation, bounded background batching, retry/backoff,
  deterministic sampling, graceful shutdown, and pre-transport redaction processors
- cursor-paginated trace explorer with environment/status/model/version/span/date filters
- trace detail views with safe JSON rendering, nested span timelines, and live SSE updates
- versioned provider/model pricing with project-specific overrides and historical cost attribution
- automatic span-to-trace token and cost roll-ups, including a safe historical backfill
- tenant-scoped analytics for volume, success/errors, P50/P95/P99 latency, tokens, cost, models,
  providers, tools, agents, and failure types
- an environment/time-filtered analytics dashboard with operational charts
- immutable evaluator versions and production bindings with deterministic sampling and filters
- ten deterministic evaluators, semantic similarity behind an embedding-provider boundary, and
  eight structured LLM-as-judge evaluator types with one strict repair attempt
- isolated Celery evaluation workers with bounded retry/backoff and durable failure state
- evaluation scores, reasons, and evidence in trace detail and aggregate quality in analytics
- explicit per-evaluator external-field allowlists before trace content can reach an LLM judge
- tenant-scoped golden datasets with immutable, sequential, content-hashed versions
- atomic JSON, JSONL, and CSV imports with complete validation before commit
- manual case authoring, version browsing, and paginated case inspection in the web UI
- experiments pinned to exact dataset and evaluator versions, with one durable run per case
- bounded-concurrency Celery execution against a strict HTTP agent contract
- experiment traces, asynchronous evaluation, live progress, cancellation, and supported metric aggregation
- outbound-agent safeguards: environment-referenced credentials, destination policy, response bounds, no redirects
- one completed experiment baseline per dataset lineage with atomic baseline replacement
- persisted candidate comparisons with absolute/percentage deltas and regression classification
- structured hard-fail and warning quality-gate rules with immutable result snapshots
- an installable `agentscope` CLI with YAML orchestration, JSON output, and stable CI exit codes
- a GitHub Actions quality-gate example and complete baseline/gate management UI
- replay executions linked explicitly to their unchanged original production traces
- model, prompt, temperature, agent-version, and parameter overrides with environment-only secrets
- replay-generated traces that reuse original evaluator versions and preserve evaluation history
- side-by-side output, score, latency, cost, token, tool-sequence, and span-structure comparison
- bounded canonical failure documents for technical, quality, and possible agent-loop failures
- a provider-neutral deterministic embedding boundary with rebuildable Qdrant indexing
- tenant-filtered semantic failure search with a PostgreSQL-scoped availability fallback
- windowed production alerts with cooldown deduplication and delivery history
- signed webhooks, SMTP email delivery, Celery beat scheduling, and hard telemetry retention
- authenticated live trace updates over server-sent events
- density-based clustering with noise support, representatives, and explicitly inferred summaries
- bounded-label Prometheus request, latency, and ingestion metrics at `/metrics`
- a direct-UUID tenant-isolation suite and a Playwright critical-path browser suite
- a configurable k6 profile for 100 concurrent 50-event ingestion batches by default
- a runnable customer-support V1/V2 demo with four tools and 12 checked-in golden cases
- production-fail-closed configuration, CodeQL/Dependabot, container-build CI, and security review
- Terraform for ECS/Fargate, encrypted RDS/ElastiCache, managed Qdrant credentials, ALB, and scaling

## Architecture

```text
Browser / Next.js  ───── JWT ─────► FastAPI control plane
                                         │
                                         ├── PostgreSQL
                                         └── Redis (readiness / Celery broker)

Developer agent ─► Python SDK ─► ingestion API ─► PostgreSQL traces + spans
                                                     │
Browser / Next.js ◄──── JWT query APIs + SSE ────────┘

                                                Celery workers
                                           ┌─────────┼─────────┐
                                           ▼         ▼         ▼
                                      evaluation   replay   analytics
                                           │
                                           ▼
                                     Provider APIs

Failed / low-quality traces ─► embeddings ─► Qdrant
```

The HTTP boundary follows **router → service → repository → database**. Tenant-owned lookups join through memberships; knowing a UUID is never sufficient authorization. PostgreSQL remains the source of truth. Qdrant is reserved for bounded failure vectors, and Redis is used only for coordination or caching with a clear purpose.

## Quick start

Requirements: Docker Compose v2.

```bash
docker compose up --build
```

Compose supplies local-only defaults. Copy `.env.example` to `.env` when you need overrides, and replace the two development secrets before using any shared environment.

Open the UI at `http://localhost:3000` and API documentation at `http://localhost:8000/docs`. Register, create an organization, create a project, then issue a key for one of its three environments. The key is shown once.

Install and run the instrumented deterministic example:

```bash
pip install -e packages/python-sdk
export AGENTSCOPE_API_KEY=as_test_your_one_time_key
python examples/customer-support-agent/demo.py
```

Open `http://localhost:3000/traces`, select the project, and inspect the emitted span hierarchy.

Seed and run the complete V1/V2 experiment demonstration:

```bash
make seed
```

This creates real resources through the public API, starts both deterministic experiments, and
prints their IDs. Open `http://localhost:3000/experiments` to watch measured results.

For host-based development, use Python 3.12+ and Node 20.9+:

```bash
make install
make migrate
cd apps/api && uv run uvicorn agentscope_api.main:app --reload
cd apps/web && npm run dev
```

## API overview

Product APIs are versioned under `/api/v1`:

- `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout`
- `GET /auth/me`
- `POST|GET /organizations`
- `GET /organizations/{id}` and `/organizations/{id}/members`
- `POST|GET /organizations/{id}/projects`
- `GET /projects/{id}` and `/projects/{id}/environments`
- `POST|GET /projects/{id}/api-keys`
- `DELETE /projects/{id}/api-keys/{key_id}`
- `POST /v1/ingest/batch` (project API key, intentionally outside the dashboard namespace)
- `GET /projects/{id}/traces`
- `GET /traces/{id}` and `/traces/{id}/events`
- `GET /projects/{id}/analytics`
- `GET|POST /projects/{id}/model-pricing`
- `GET|POST /projects/{id}/evaluators`
- `POST /projects/{id}/evaluators/{evaluator_id}/versions`
- `GET|POST|PATCH /projects/{id}/evaluation-bindings`
- `GET|POST /projects/{id}/traces/{trace_id}/evaluations`
- `GET|POST /projects/{id}/datasets`
- `GET /projects/{id}/datasets/{dataset_id}`
- `POST /projects/{id}/datasets/{dataset_id}/items`
- `POST /projects/{id}/datasets/{dataset_id}/versions`
- `POST /projects/{id}/datasets/{dataset_id}/versions/import`
- `GET /projects/{id}/datasets/{dataset_id}/versions/{version}`
- `GET|POST /projects/{id}/experiments`
- `GET /projects/{id}/experiments/{experiment_id}` and `/runs`
- `POST /projects/{id}/experiments/{experiment_id}/start` and `/cancel`
- `POST /projects/{id}/experiments/{experiment_id}/baseline`
- `GET /projects/{id}/baseline`
- `GET /projects/{id}/experiments/{experiment_id}/comparison`
- `GET|POST /projects/{id}/quality-gates`
- `POST /projects/{id}/quality-gates/{gate_id}/evaluate`
- `GET /projects/{id}/experiments/{experiment_id}/quality-gate-results`
- `GET|POST /projects/{id}/traces/{trace_id}/replays`
- `GET /projects/{id}/replays/{replay_id}` and `/comparison`
- `POST /projects/{id}/traces/{trace_id}/failure-analysis`
- `GET /projects/{id}/failures` and `POST /projects/{id}/failures/search`
- `GET /projects/{id}/failure-clusters` and `POST /failure-clusters/rebuild`
- `GET|POST /projects/{id}/alert-rules` and `PUT|DELETE /alert-rules/{rule_id}`
- `GET /projects/{id}/alerts`
- `PATCH /projects/{id}/retention`

All errors use `{ "error": { "code", "message", "request_id", "details" } }`.

## Testing and quality

```bash
make test-api
make test
make lint
make e2e
```

The API suite covers hashing, JWT validation, refresh rotation/reuse detection, RBAC, API-key storage, idempotent ingestion, trace hierarchy persistence, evaluator versioning, production scheduling, worker authentication/completion, dataset immutability/import atomicity, experiment concurrency/aggregation, baseline comparison, quality-gate outcomes, replay immutability/comparison, and cross-tenant direct-UUID denial. The evaluation package tests every deterministic evaluator, semantic scoring, and explicit LLM data disclosure. The CLI suite verifies configuration rules and its `0/1/2` process contract. The SDK suite proves concurrent async context isolation, error retention under sampling, built-in redaction, and host-application survival when transport is unavailable. CI applies all Alembic migrations to PostgreSQL and checks for model drift. The E2E suite covers registration, organization, project, key, trace, dataset, evaluator, experiment, baseline, comparison, and quality-gate flow. `make load-test` runs the documented k6 method; no load-performance result is claimed without its environment and raw output.

## Security model

- Access tokens expire after 15 minutes by default.
- Refresh tokens are opaque, HttpOnly, `SameSite=Lax`, hashed at rest, rotated on every use, and revoke their family when reuse is detected.
- Password and token/API-key hashes use separate mechanisms and configuration secrets.
- Production startup rejects default secrets and insecure refresh cookies.
- Authorization is permission-based; repositories scope tenant resources through membership joins.
- Logs and audit metadata never contain passwords, bearer tokens, or complete API keys.
- Evaluation workers receive only a result ID through Redis and authenticate separately to fetch a
  payload; LLM judges receive only evaluator-allowlisted fields.

See [Security](docs/security.md) and the [security review](docs/security-review.md) for trust
boundaries, verified controls, and residual operational risks.

## Deployment and scaling

The checked-in [Terraform stack](infrastructure/terraform/README.md) deploys Next.js, stateless
FastAPI, isolated workers, and singleton scheduling on ECS/Fargate with encrypted RDS PostgreSQL,
ElastiCache Redis, managed-Qdrant secrets, HTTPS ALB routing, logs, and autoscaling. High-volume
telemetry can split into Kafka, processors, ClickHouse, and S3 without moving identity/configuration
out of PostgreSQL. See [Scaling strategy](docs/scaling.md) and [load testing](docs/load-testing.md).

## Known limitations

- Semantic evaluation currently ships an OpenAI embedding provider; the interface is provider-neutral
  and additional providers can be added without changing evaluator persistence.
- Password-reset persistence exists, but token issuance/email delivery endpoints are deferred until a notification provider is selected.
- Member invitation and role mutation APIs are deferred; the schema and permission model support them.
- Readiness checks PostgreSQL and Redis. Qdrant becomes critical only when failure intelligence is enabled.
- Provider-hosted LLM output cannot be exactly reproducible; experiments preserve all controllable
  configuration and immutable input/evaluator versions.

## Operations references

- [Monitoring, alerts, and retention](docs/monitoring-alerts.md)
- [Experiments and HTTP agent contract](docs/experiments.md)
- [Quality gates and CI](docs/quality-gates.md)
- [AWS deployment](infrastructure/terraform/README.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). No secrets, fabricated metrics, or placeholder functionality described as complete will be accepted.

