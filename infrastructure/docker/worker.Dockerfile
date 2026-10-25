FROM python:3.12-slim
WORKDIR /workspace/apps/worker
RUN pip install --no-cache-dir uv==0.11.26
COPY packages/evaluation /workspace/packages/evaluation
COPY apps/worker/pyproject.toml apps/worker/uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/worker/ .
RUN uv sync --frozen --no-dev
RUN groupadd --system agentscope && useradd --system --gid agentscope \
    --home /workspace/apps/worker agentscope \
    && chown -R agentscope:agentscope /workspace
ENV PATH="/workspace/apps/worker/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER agentscope
CMD ["celery", "-A", "agentscope_worker.celery_app", "worker", "-l", "INFO"]

