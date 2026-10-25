# Customer support agent

This deterministic HTTP agent is the production-demo fixture for AgentScope. It exposes two
versioned behaviours against the same four tools:

- `support-v1` deliberately has weak cancellation, refund-window, and policy handling.
- `support-v2` enforces order state and policy rules and is the expected baseline.

No LLM key is needed and no benchmark result is fabricated. Every result shown in AgentScope is
produced by running the checked-in golden cases against the live endpoint.

```bash
apps/api/.venv/bin/uvicorn app:app \
  --app-dir examples/customer-support-agent --host 0.0.0.0 --port 8090
curl -s http://localhost:8090/health
```

Run `make seed` after `docker compose up -d`; Compose exposes this agent to the experiment worker as
`http://demo-agent:8090/invoke`. The seed command creates the organization, project, immutable
dataset, deterministic evaluators, and V1/V2 experiments, then starts each pending experiment.

`demo.py` remains a small SDK tracing example. It is independent from the HTTP experiment fixture.
