# AgentScope CLI

The CLI runs reproducible AgentScope experiments and returns CI-safe exit codes: `0` for a
passing gate (warnings included), `1` for a failed gate, and `2` for configuration or execution
errors.

```bash
uv tool install ./packages/cli
export AGENTSCOPE_TOKEN="..."
agentscope auth
agentscope eval run --config agentscope.yaml
agentscope eval run --config agentscope.yaml --json
```

Projects, datasets, environments, and evaluator versions may be referenced by ID, slug (where
available), or an unambiguous name. Access tokens are read from an environment variable and are
never stored in configuration.

See [`../../docs/quality-gates.md`](../../docs/quality-gates.md) for the complete configuration
and CI guide.

