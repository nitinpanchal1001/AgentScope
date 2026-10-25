# Security review

Reviewed scope: browser/API authentication, tenant authorization, telemetry ingestion, evaluation
and experiment workers, replay, failure vectors, alert delivery, retention, and deployment defaults.
This is a repository threat review, not a penetration-test certificate.

## Trust boundaries and abuse cases

- Browser users are untrusted and may submit another tenant's UUID. Every resource query must scope
  through membership/project ownership and return not-found for foreign objects.
- SDK API keys are untrusted bearer credentials. They are one-time display values, stored as keyed
  hashes, environment-scoped, revocable, rate limited, and unable to call control-plane routes.
- Telemetry, dataset imports, agent responses, and provider output are untrusted data. Pydantic
  contracts reject extra fields where practical; byte/count limits bound storage and parsing.
- Agent endpoints and webhooks are SSRF surfaces. Production permits HTTPS only, resolves every
  address before dispatch, rejects non-global addresses and redirects, and optionally allowlists
  hosts. Credentials are referenced by environment-variable name and never persisted inline.
- Redis/Celery messages carry opaque IDs, not prompts, credentials, or full evaluation payloads.
  Workers fetch scoped payloads with a separate internal credential and use bounded retries.
- Qdrant vectors carry organization and project payloads; all search filters require both fields.
  Retention removes Qdrant points before deleting PostgreSQL traces.

## Controls verified in code and tests

- Argon2id passwords; HMAC-hashed API/refresh tokens; short JWT access lifetime and rotating opaque
  refresh tokens in HttpOnly cookies.
- Central role/permission mapping and a direct-UUID tenant-isolation suite covering projects, keys,
  traces, datasets, experiments, failures, and vector filters.
- Idempotent ingestion event IDs, transactional trace writes, input limits, Redis rate limiting, and
  bounded Prometheus labels.
- Explicit LLM evaluator field allowlists; deterministic evaluators do not call external providers.
- Signed webhook bodies, query-secret masking, permanent/transient delivery classification, and
  cooldown/deduplication.
- Production startup refuses default secrets, insecure refresh cookies/CORS, non-TLS Redis/Qdrant,
  missing Qdrant authentication, and weakened outbound endpoint protections.
- CI runs Ruff security rules, type/tests, Python and npm dependency audits, CodeQL, container
  builds, migrations/drift checks, and the browser critical path. Dependabot tracks every package
  ecosystem in the repository.

## Residual and operational risks

- Rate-limit authentication at the ALB/WAF; the application limiter protects ingestion, not every
  login attempt across horizontally scaled instances.
- Provider-hosted LLMs and customer agent endpoints remain third parties. Use allowlists, data
  minimization, regional contracts, and egress controls appropriate to the deployment.
- Prometheus `/metrics` contains aggregate operational values but no tenant identifiers. The
  provided Nginx and Terraform deployments keep it off the public route; preserve private-only
  scraper access in equivalent deployments.
- Terraform-generated secrets are present in encrypted Terraform state. Protect state with KMS,
  versioning, locking, and a narrowly scoped CI role; rotate secrets after suspected state access.
- LiteLLM currently declares a conservative `filelock<4` cap even though that branch has published
  advisories. The uv lockfiles override it to audited `filelock` 4.x, and CI exercises the provider
  import boundary; remove the override after LiteLLM officially adopts the fixed series.
- Qdrant Cloud, SMTP, OpenAI, and DNS availability are outside the transaction boundary. The system
  surfaces failures and retries transient work but cannot make those services atomic with Postgres.
- A separate external penetration test, disaster-recovery exercise, restore test, and privacy review
  are required before handling regulated production data.
