# Baselines, quality gates, and CI

AgentScope compares a completed candidate experiment with one completed baseline from the same
dataset lineage. A comparison records the baseline value, candidate value, absolute delta,
percentage delta (when the baseline is non-zero), direction, and regression/improvement label.
The original experiments remain immutable.

## Configure a baseline and gate

Open a completed experiment and select **Set as baseline**, or call:

```bash
curl -X POST \
  -H "Authorization: Bearer $AGENTSCOPE_TOKEN" \
  "$AGENTSCOPE_URL/api/v1/projects/$PROJECT_ID/experiments/$EXPERIMENT_ID/baseline"
```

Rules are stored as structured data rather than UI expressions. Higher values are considered
better for pass rate, correctness, and tool accuracy. Lower values are better for hallucination,
latency, cost, and token usage. `max_regression` follows that direction automatically;
`max_increase` always constrains a numeric increase. Absolute thresholds are measured in metric
units, while relative thresholds are fractions (`0.25` means 25%). Relative rules cannot use a
zero baseline.

```json
{
  "name": "Production release",
  "rules": [
    {"metric":"average_correctness","constraint":"max_regression","threshold":0.03,"comparison":"absolute","severity":"FAIL"},
    {"metric":"hallucination_rate","constraint":"max_increase","threshold":0.02,"comparison":"absolute","severity":"FAIL"},
    {"metric":"p95_latency_ms","constraint":"max_increase","threshold":0.25,"comparison":"relative","severity":"WARN"},
    {"metric":"average_cost","constraint":"max_increase","threshold":0.15,"comparison":"relative","severity":"WARN"}
  ]
}
```

The result is `PASSED`, `PASSED_WITH_WARNINGS`, or `FAILED`, and includes persisted violations,
warnings, comparisons, the rule snapshot, both experiment IDs, and the evaluation time.

## Run from the CLI

Copy [`../agentscope.example.yaml`](../agentscope.example.yaml) to `agentscope.yaml`, select the
project, dataset, evaluator versions, and candidate HTTP endpoint, then run:

```bash
uv tool install ./packages/cli
export AGENTSCOPE_TOKEN="your short-lived access token"
export CANDIDATE_AGENT_AUTHORIZATION="Bearer ..."
agentscope auth
agentscope eval run --config agentscope.yaml
```

The CLI resolves IDs, slugs, or unambiguous names, creates and executes an experiment, waits for
terminal aggregation, creates or reuses the configured gate, and evaluates the candidate. Agent
credential values are resolved only by the experiment worker from environment variables named in
`headers_from_env`; YAML contains names, not secrets.

Exit codes are stable for CI:

- `0`: passed, including `PASSED_WITH_WARNINGS`
- `1`: quality gate failed
- `2`: invalid configuration, API failure, experiment failure, or timeout

Add `--json` for a single machine-readable JSON document. `agentscope experiment status` and
`agentscope quality-gate` can inspect an existing run or evaluate an existing candidate directly.

The opt-in workflow at
[`../.github/workflows/agentscope-quality-gate.example.yml`](../.github/workflows/agentscope-quality-gate.example.yml)
shows the complete GitHub Actions flow. Copy the example configuration to `agentscope.yaml`, set
the repository secrets, and adapt the URLs before enabling it in a deployment repository.
