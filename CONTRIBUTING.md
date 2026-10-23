# Contributing to AgentScope

## Development principles

Keep changes within the current phase, preserve router/service/repository boundaries, and make every tenant-owned query prove its organization or project scope. Database changes require an Alembic migration. New behavior requires focused tests and documentation that describes only behavior that actually exists.

## Local checks

```bash
make format
make lint
make test
```

Commit `.env.example` changes but never `.env`, provider credentials, access tokens, refresh tokens, or generated API keys. Use UTC-aware timestamps and UUIDs. Keep external provider calls behind an interface and classify retryable failures explicitly.

## Migration workflow

Start PostgreSQL, update SQLAlchemy models, then run:

```bash
make migration name=describe_change
make migrate
cd apps/api && uv run alembic check
```

Review generated migrations; generation is not a correctness proof.

