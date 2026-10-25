FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.26
COPY apps/api/pyproject.toml apps/api/uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/ .
RUN uv sync --frozen --no-dev
RUN groupadd --system agentscope && useradd --system --gid agentscope --home /app agentscope \
    && chown -R agentscope:agentscope /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER agentscope
CMD ["sh", "-c", "alembic upgrade head && uvicorn agentscope_api.main:app --host 0.0.0.0 --port 8000"]

