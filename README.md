# AgentScope

AgentScope is an open-source engineering platform for tracing, evaluating, experimenting with, and regression-testing AI agents. The repository currently contains the **Phase 2 tracing platform**: the secure control plane from Phase 1 plus end-to-end Python telemetry, ingestion, storage, and trace inspection.

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
- separate Celery queue topology, ready for later phase task implementations

## Architecture

```text
Browser / Next.js  ───── JWT ─────► FastAPI control plane
                                         │
                                         ├── PostgreSQL
                                         └── Redis (readiness / Celery broker)

Future Phase 2:
Developer agent ─► Python SDK ─► ingestion API ─► PostgreSQL traces + spans
                                                     │
Browser / Next.js ◄──── JWT query APIs + SSE ────────┘

Future phases:                                  Celery workers
                                           ┌─────────┼─────────┐
                                           ▼         ▼         ▼
                                      evaluation   replay   analytics
                                           │
                                           ▼
                                        LiteLLM

Failed / low-quality traces ─► embeddings ─► Qdrant (Phase 9)
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

All errors use `{ "error": { "code", "message", "request_id", "details" } }`.

## Testing and quality

```bash
make test-api
make test
make lint
```

The API suite covers hashing, JWT validation, refresh rotation/reuse detection, RBAC, API-key storage, idempotent ingestion, trace hierarchy persistence, and cross-tenant direct-UUID denial. The SDK suite proves concurrent async context isolation, error retention under sampling, built-in redaction, and host-application survival when transport is unavailable. CI applies all Alembic migrations to PostgreSQL and checks for model drift. No load-performance claim is made.

## Security model

- Access tokens expire after 15 minutes by default.
- Refresh tokens are opaque, HttpOnly, `SameSite=Lax`, hashed at rest, rotated on every use, and revoke their family when reuse is detected.
- Password and token/API-key hashes use separate mechanisms and configuration secrets.
- Production startup rejects default secrets and insecure refresh cookies.
- Authorization is permission-based; repositories scope tenant resources through membership joins.
- Logs and audit metadata never contain passwords, bearer tokens, or complete API keys.

See [Security](docs/security.md) for trust boundaries and operational considerations.

## Deployment and scaling

V1 targets Next.js + stateless FastAPI on ECS/Fargate, RDS PostgreSQL, ElastiCache Redis, and managed Qdrant. High-volume telemetry can later split from the control plane into stateless ingestion, Kafka, processors, ClickHouse, and S3 without moving identity/configuration out of PostgreSQL. See [Scaling strategy](docs/scaling.md).

## Known limitations

- Evaluations, datasets, experiments, regression gates, replay, failure intelligence, alerts, and the CLI are later phases and are not implemented.
- Phase 2 records caller-supplied token/cost values but does not yet provide Phase 3 pricing or aggregate analytics.
- Password-reset persistence exists, but token issuance/email delivery endpoints are deferred until a notification provider is selected.
- Member invitation and role mutation APIs are deferred; the schema and permission model support them.
- Readiness checks PostgreSQL and Redis. Qdrant becomes critical only when failure intelligence is enabled.
- Exact reproducibility of provider-hosted LLM outputs cannot be guaranteed; later experiment storage will preserve all controllable configuration.

## Roadmap

The next implementation phase is metrics and cost analytics, followed by evaluation → datasets → experiments → regression/CLI → replay → failure intelligence → monitoring/alerts → hardening. Each phase must add migrations, tests, documentation, and a complete verified exit path before the next begins.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). No secrets, fabricated metrics, or placeholder functionality described as complete will be accepted.

