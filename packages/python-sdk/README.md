# AgentScope Python SDK

The SDK records trace and span events without putting telemetry on the host application's
critical path. It includes async-safe context propagation, bounded background batching,
retry/backoff, deterministic sampling, and pre-transport redaction.

```python
import os
from agentscope import AgentScope, default_redaction

client = AgentScope(
    api_key=os.environ["AGENTSCOPE_API_KEY"],
    endpoint=os.getenv("AGENTSCOPE_ENDPOINT", "http://localhost:8000"),
    processors=default_redaction(),
)


@client.trace(name="support-agent", agent_version="v1")
async def support_agent(message: str) -> str:
    async with client.span(
        name="lookup-order", span_type="tool", input={"message": message}
    ) as span:
        result = {"status": "shipped"}
        span.set_output(result)
    return "Your order has shipped."
```

Install locally with `pip install -e packages/python-sdk`. Call `client.close()` during graceful
application shutdown (or use `AgentScope` as a context manager) to make a bounded final flush.

