FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.26
COPY apps/worker/pyproject.toml apps/worker/uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/worker/ .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["celery", "-A", "agentscope_worker.celery_app", "worker", "-l", "INFO"]

