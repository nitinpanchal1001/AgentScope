# Customer support agent

This deterministic example exercises the real Phase 2 SDK and ingestion path without requiring an
LLM provider key. It emits nested retrieval, LLM, and tool spans to the development environment.

```bash
pip install -e packages/python-sdk
export AGENTSCOPE_API_KEY=as_test_your_one_time_key
python examples/customer-support-agent/demo.py
```

Open `http://localhost:3000/traces` and select the matching project. The demo intentionally reports
simulated provider/model metadata; it does not claim real model output, token usage, or benchmark data.
