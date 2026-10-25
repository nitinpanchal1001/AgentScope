# Experiments

An AgentScope experiment executes one immutable dataset version against one explicit agent
configuration and a fixed set of evaluator versions. Creation snapshots those references and
creates one durable `ExperimentRun` per dataset item. An experiment cannot silently move to a
newer dataset or evaluator version.

## HTTP agent contract

The experiment worker sends `POST` requests with this shape:

```json
{
  "input": {"message": "Where is order A-42?"},
  "context": {"customer_tier": "gold"},
  "configuration": {
    "provider": "openai",
    "model": "configured-model",
    "prompt_version": "support-v3",
    "temperature": 0,
    "parameters": {}
  },
  "metadata": {
    "experiment_id": "...",
    "experiment_run_id": "...",
    "dataset_item_id": "...",
    "dataset_item_metadata": {}
  }
}
```

The response must contain `output`. It may also contain `metadata`, up to 1,000 trace `spans`, and
`usage` with input/output/total tokens and total cost. Requests include an
`X-AgentScope-Run-ID` idempotency key. Agent implementations should return the same logical result
when that key is retried.

Credentials are never stored in experiment JSON. `headers_from_env` maps an HTTP header name to an
environment variable available only in the experiment worker, for example
`{"Authorization":"SUPPORT_AGENT_AUTH_HEADER"}`. Production defaults reject plain HTTP,
private/reserved destination addresses, redirects, and hosts outside the optional allowlist.

## Execution and concurrency

Starting an experiment claims at most `max_concurrency` pending runs. Each completed invocation
releases one slot and atomically claims one next case. Celery uses late acknowledgements, bounded
retry/backoff, and a prefetch multiplier of one. Invocation responses become normal AgentScope
traces, after which the existing evaluation queue processes the pinned evaluator versions.

States are `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`. Per-case runs additionally
use `EVALUATING`. Cancelling stops new case claims and marks unstarted cases cancelled; an already
in-flight HTTP request is allowed to finish safely.

## Metrics

Every experiment reports total/completed/passed/failed cases, pass rate, latency average and
P50/P95/P99, cost average and total, and token usage. Average correctness, hallucination rate, and
tool accuracy appear only when evaluator types capable of producing those metrics were selected.

## Local verification

Start the deterministic example agent on the host:

```bash
apps/api/.venv/bin/uvicorn app:app \
  --app-dir examples/http-agent --host 0.0.0.0 --port 8090
```

With Docker Compose, use `http://host.docker.internal:8090/invoke` as the agent endpoint. Compose
explicitly enables local HTTP/private endpoints; deployed workers retain the secure defaults.
Open `/experiments`, choose a dataset version and one or more evaluator versions, create the
experiment, then start it and watch progress on its detail page.
