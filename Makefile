.PHONY: dev up down install test test-api test-sdk lint format migrate migration seed e2e load-test clean

dev: up

up:
	docker compose up --build

down:
	docker compose down

install:
	cd apps/api && uv sync --all-groups
	cd packages/python-sdk && uv sync --all-groups
	cd apps/web && npm ci

test: test-api test-sdk
	cd apps/web && npm test -- --run

test-api:
	cd apps/api && uv run pytest

test-sdk:
	cd packages/python-sdk && uv run pytest

lint:
	cd apps/api && uv run ruff check .
	cd apps/api && uv run mypy src
	cd packages/python-sdk && uv run ruff check .
	cd packages/python-sdk && uv run mypy src
	cd apps/web && npm run lint
	cd apps/web && npm run typecheck

format:
	cd apps/api && uv run ruff format .
	cd apps/api && uv run ruff check --fix .
	cd packages/python-sdk && uv run ruff format .
	cd packages/python-sdk && uv run ruff check --fix .
	cd apps/web && npm run format

migrate:
	cd apps/api && uv run alembic upgrade head

migration:
	@test -n "$(name)" || (echo "Usage: make migration name=description" && exit 2)
	cd apps/api && uv run alembic revision --autogenerate -m "$(name)"

seed:
	@echo "Demo seeding is scheduled for the tracing/evaluation phases."

e2e:
	cd apps/web && npm run e2e

load-test:
	@echo "Run an environment-specific ingestion load profile; no benchmark claim is bundled."

clean:
	docker compose down --remove-orphans

