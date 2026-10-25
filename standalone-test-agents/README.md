# Real test agents for AgentScope

This directory contains ten independently callable specialist agents and one coordinated product
delivery team. Every invocation calls the OpenAI Responses API; none of the model answers, token
counts, latency, or costs are simulated. Local tools provide grounding or computed context, and the
research/travel agents use OpenAI web search.

| Agent | Port | AgentScope endpoint | Model behavior |
|---|---:|---|---|
| Grounded FAQ | 8101 | `http://host.docker.internal:8101/invoke` | Retrieves local policy text, then asks the model for a cited answer |
| Web research | 8102 | `http://host.docker.internal:8102/invoke` | Uses built-in web search and synthesizes sourced findings |
| Data analyst | 8103 | `http://host.docker.internal:8103/invoke` | Profiles supplied records, then produces an evidence-based analysis |
| Travel planner | 8104 | `http://host.docker.internal:8104/invoke` | Searches current travel information and creates a constrained itinerary |
| Incident triage | 8105 | `http://host.docker.internal:8105/invoke` | Retrieves service signals and a runbook, then proposes safe triage steps |
| UI/UX designer | 8111 | `http://host.docker.internal:8111/invoke` | Turns a product brief into an accessible experience specification and engineering handoff |
| Frontend developer | 8112 | `http://host.docker.internal:8112/invoke` | Produces typed component, state, validation, styling, and frontend test plans |
| Backend developer | 8113 | `http://host.docker.internal:8113/invoke` | Designs tenant-safe APIs, persistence, authorization, migrations, and operations |
| QA engineer | 8114 | `http://host.docker.internal:8114/invoke` | Creates risk-based unit, integration, E2E, negative, and concurrency test coverage |
| Accessibility/performance | 8115 | `http://host.docker.internal:8115/invoke` | Defines WCAG 2.2 AA checks, performance budgets, load tests, and release thresholds |
| Coordinated product team | 8116 | `http://host.docker.internal:8116/invoke` | Runs design, parallel frontend/backend, then parallel QA/accessibility-performance handoffs |

The implementation follows the official OpenAI guidance to use the
[Responses API](https://developers.openai.com/api/docs/guides/text) for new text-generation
applications and its documented
[tool-calling flow](https://developers.openai.com/api/docs/guides/function-calling).

## 1. Configure a real model

Python 3.12 or later is required.

```bash
cd standalone-test-agents
uv sync
source .venv/bin/activate
```

Create an OpenAI API key in your OpenAI account. Do not paste it into source files, datasets, or
AgentScope experiment configuration. Load it into the terminal that will run the agents:

```bash
read -s "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
export OPENAI_MODEL="gpt-6-luna"
echo
```

`gpt-6-luna` is the cost-sensitive default. Set `OPENAI_MODEL` to another model available to your
API project when you want to compare models. Optional price overrides are
`OPENAI_INPUT_PRICE_PER_MILLION` and `OPENAI_OUTPUT_PRICE_PER_MILLION`.

## 2. Start all agents

```bash
chmod +x run_agents.sh
./run_agents.sh
```

Keep that terminal open. A health endpoint checks configuration without making a paid model call:

```bash
for port in 8101 8102 8103 8104 8105 8111 8112 8113 8114 8115 8116; do
  curl -s "http://127.0.0.1:$port/health"
  echo
done
```

Manual FAQ invocation (this makes a real paid API request):

```bash
curl -s http://127.0.0.1:8101/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {"question": "How long does standard shipping take?"},
    "configuration": {"model": "gpt-6-luna", "max_output_tokens": 300}
  }'
```

The response follows AgentScope's HTTP-agent contract and contains the answer, real usage,
provider metadata, tool spans, and an LLM span.

Manual coordinated-team invocation (this makes five real paid API requests):

```bash
curl -s http://127.0.0.1:8116/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "input": {
      "brief": "Build a customer feedback portal",
      "users": ["Customer", "Support agent"],
      "stack": "Next.js, FastAPI, PostgreSQL",
      "requirements": ["Submit feedback", "Status tracking", "Internal triage"],
      "constraints": ["Multi-tenant", "WCAG 2.2 AA"]
    },
    "configuration": {"model": "gpt-6-luna", "max_output_tokens": 700}
  }'
```

The team uses a fixed workflow so its trace is easy to audit:

1. The UI/UX designer creates the product and interaction specification.
2. The frontend and backend developers work in parallel from that specification.
3. The QA and accessibility/performance specialists work in parallel from all three upstream
   artifacts.
4. The response returns all five artifacts, five LLM spans, and two explicit handoff tool spans.

The team endpoint deliberately uses application-managed orchestration rather than provider-managed
beta orchestration. This keeps the execution graph, number of model calls, handoffs, and AgentScope
spans stable between runs.

## 3. Run an AgentScope experiment

1. Start AgentScope with `docker compose up -d` from the repository root.
2. In **Datasets**, create one dataset per agent and import the corresponding file under
   `datasets/` as JSONL. Use `product_team.jsonl` for the coordinated workflow.
3. In **Evaluators**, create and bind evaluators to the experiment environment.
4. In **Experiments**, choose the dataset version, evaluators, and the endpoint from the table.
   Set the coordinated product team's HTTP timeout to `300` seconds because it runs three workflow
   stages; `90` seconds is normally sufficient for an individual specialist.
5. Use a small concurrency such as `1` or `2` to control API spend, then start the experiment.
6. Open the experiment detail page to inspect each run, trace, tool span, tokens, cost, latency, and
   evaluation result.

Recommended deterministic evaluators:

- FAQ: `REQUIRED_TOOL` with `{"tool":"search_knowledge_base"}`
- Research: `REQUIRED_TOOL` with `{"tool":"openai_web_search"}`
- Data analyst: `REQUIRED_TOOL` with `{"tool":"profile_records"}`
- Travel: `REQUIRED_TOOL` with `{"tool":"search_travel_information"}`
- Incident triage: `REQUIRED_TOOL` with
  `{"tools":["fetch_service_health","lookup_runbook"]}`
- Coordinated product team: `REQUIRED_TOOL` with
  `{"tools":["handoff_to_development","handoff_to_testing"]}`
- Every agent: `LATENCY_THRESHOLD` and `COST_THRESHOLD` using limits appropriate to your account

For answer quality, create a `CORRECTNESS`, `RELEVANCE`, or `CUSTOM_RUBRIC` LLM evaluator with an
explicit external-field allowlist such as:

```json
{"external_fields":["input","output","expected_output"]}
```

The evaluation worker also needs its own `OPENAI_API_KEY` in the repository `.env` when using an
LLM judge. Restart `worker-evaluation` after changing that environment.

## 4. Compare versions or models

Create two experiments from the same immutable dataset version and evaluator versions. Change only
the experiment's model configuration, for example `gpt-6-luna` versus `gpt-6.1-sol`. Set the first
completed experiment as the baseline, compare the second, and apply a quality gate to pass rate,
cost, tokens, or latency.

## Security and cost

- These agents make billable external API calls. Each specialist invocation makes one model call;
  each coordinated-team invocation makes five. Start with the two-case datasets and concurrency `1`.
- API credentials stay in environment variables and are never returned in spans.
- OpenAI requests set `store=false`; review your provider account's data controls separately.
- Web results and model answers are untrusted. The agents do not execute model-generated shell,
  SQL, booking, refund, or infrastructure actions.
- The travel agent provides research, not booking or legal/visa advice. The incident agent proposes
  actions but does not execute them.

