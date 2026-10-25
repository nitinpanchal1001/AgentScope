.PHONY: dev up down install test test-api test-sdk test-evaluation test-worker test-cli lint format migrate migration seed e2e load-test clean

dev: up

up:
	docker compose up --build

down:
	docker compose down

install:
	cd apps/api && uv sync --all-groups
	cd apps/worker && uv sync --all-groups
	cd packages/evaluation && uv sync --all-groups
	cd packages/cli && uv sync --all-groups
	cd packages/python-sdk && uv sync --all-groups
	cd apps/web && npm ci

test: test-api test-sdk test-evaluation test-worker test-cli
	cd apps/web && npm test -- --run

test-api:
	cd apps/api && uv run pytest

test-sdk:
	cd packages/python-sdk && uv run pytest

test-evaluation:
	cd packages/evaluation && uv run pytest

test-worker:
	cd apps/worker && uv run pytest

test-cli:
	cd packages/cli && uv run pytest

lint:
	cd apps/api && uv run ruff check .
	cd apps/api && uv run mypy src
	cd packages/python-sdk && uv run ruff check .
	cd packages/python-sdk && uv run mypy src
	cd packages/evaluation && uv run ruff check .
	cd packages/evaluation && uv run mypy src tests
	cd packages/cli && uv run ruff check .
	cd packages/cli && uv run mypy src
	cd apps/worker && uv run ruff check .
	cd apps/worker && uv run mypy src
	cd apps/web && npm run lint
	cd apps/web && npm run typecheck

format:
	cd apps/api && uv run ruff format .
	cd apps/api && uv run ruff check --fix .
	cd packages/python-sdk && uv run ruff format .
	cd packages/python-sdk && uv run ruff check --fix .
	cd packages/cli && uv run ruff format .
	cd packages/cli && uv run ruff check --fix .
	cd apps/web && npm run format

migrate:
	cd apps/api && uv run alembic upgrade head

migration:
	@test -n "$(name)" || (echo "Usage: make migration name=description" && exit 2)
	cd apps/api && uv run alembic revision --autogenerate -m "$(name)"

seed:
	cd apps/api && uv run python ../../scripts/seed_demo.py

e2e:
	cd apps/web && npm run e2e

load-test:
	@command -v k6 >/dev/null || (echo "k6 is required: https://grafana.com/docs/k6/latest/set-up/install-k6/" && exit 2)
	k6 run tests/load/ingestion.js

clean:
	docker compose down --remove-orphans

