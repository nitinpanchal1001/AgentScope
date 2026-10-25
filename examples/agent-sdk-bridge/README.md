# Test Agent SDK agents with AgentScope

This bridge adapts a locally running `@grok/agent-sdk` project to AgentScope's
`POST /invoke` experiment contract. It preserves the final reply, tool spans,
token usage, and Agent SDK session ID. Every experiment request uses
`purpose: "eval"` and `dryRun: true`, so write tools are stubbed during tests.

## 1. Start one agent

Model turns require your Cursor credential. From the agent project:

```bash
cd "/Users/nitinpanchal/Documents/ChatGPT/Ai Agents/faq-agent"
npx --yes "@grok/agent-sdk@0.2.29" login
npx --yes "@grok/agent-sdk@0.2.29" serve --dir . --mode single --dev
```

The agent is served at `http://127.0.0.1:3000`. Keep this terminal open.

## 2. Start the bridge

In another terminal, from the AgentScope repository:

```bash
cd /Users/nitinpanchal/Projects/agentScope
AGENT_SDK_URL=http://127.0.0.1:3000 \
  apps/api/.venv/bin/uvicorn app:app \
  --app-dir examples/agent-sdk-bridge --host 0.0.0.0 --port 8091
```

Check it with `curl http://127.0.0.1:8091/health`.

## 3. Create the AgentScope test

1. Open **Datasets** and create an FAQ dataset. Use objects such as
   `{"message":"What is your return policy?"}` as inputs and add expected outputs.
2. Create deterministic evaluators such as correctness, hallucination, tool
   accuracy, latency, and cost.
3. Open **Experiments**, choose the dataset and evaluators, and use this endpoint:
   `http://host.docker.internal:8091/invoke`.
4. Start the experiment. Open its runs and traces to inspect the answer, tool
   calls, tokens, evaluator scores, and failures.

To test another agent, stop only the Agent SDK server, `cd` into
`research-agent`, `travel-agent`, `support-agent`, or `data-analyst-agent`, and
run the same `serve` command. The bridge and AgentScope can stay running.
