from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml


class ConfigurationError(ValueError):
    """Raised when an agentscope.yaml document is invalid."""


@dataclass(frozen=True)
class GateRule:
    metric: str
    constraint: Literal["max_regression", "max_increase"]
    threshold: float
    comparison: Literal["absolute", "relative"]
    severity: Literal["FAIL", "WARN"]


@dataclass(frozen=True)
class RunConfig:
    api_url: str
    token_env: str
    organization: str | None
    project: str
    dataset: str
    dataset_version: str | int
    environment: str
    evaluators: tuple[str, ...]
    agent: dict[str, Any]
    experiment_name: str
    max_concurrency: int
    poll_interval_seconds: float
    timeout_seconds: float
    quality_gate_id: str | None
    quality_gate_name: str
    quality_gate_rules: tuple[GateRule, ...]


METRIC_ALIASES = {
    "correctness": "average_correctness",
    "hallucination": "hallucination_rate",
    "latency_p95": "p95_latency_ms",
    "cost": "average_cost",
}
LOWER_IS_BETTER = {
    "hallucination_rate",
    "average_latency_ms",
    "p50_latency_ms",
    "p95_latency_ms",
    "p99_latency_ms",
    "average_cost",
    "total_cost",
    "token_usage",
}


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ConfigurationError(f"{field} must be a mapping")
    return cast(dict[str, Any], value)


def _required_string(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field} must be a non-empty string")
    return value.strip()


def _rules(value: object) -> tuple[str | None, str, tuple[GateRule, ...]]:
    if value is None:
        return None, "CI quality gate", ()
    gate = _mapping(value, "quality_gate")
    gate_id = gate.get("id")
    if gate_id is not None and not isinstance(gate_id, str):
        raise ConfigurationError("quality_gate.id must be a string")
    name = gate.get("name", "CI quality gate")
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("quality_gate.name must be a non-empty string")
    rules: list[GateRule] = []
    explicit = gate.get("rules")
    values = (
        explicit
        if explicit is not None
        else {key: item for key, item in gate.items() if key not in {"id", "name"}}
    )
    if isinstance(values, list):
        entries = []
        for index, item in enumerate(values):
            parsed = _mapping(item, f"quality_gate.rules[{index}]")
            metric = _required_string(parsed, "metric")
            entries.append((metric, parsed))
    elif isinstance(values, dict):
        entries = [
            (str(metric), _mapping(rule, f"quality_gate.{metric}"))
            for metric, rule in values.items()
        ]
    else:
        raise ConfigurationError("quality_gate.rules must be a list or mapping")
    for source_metric, rule in entries:
        metric = METRIC_ALIASES.get(source_metric, source_metric)
        constraints = [key for key in ("max_regression", "max_increase") if key in rule]
        if len(constraints) != 1:
            raise ConfigurationError(f"quality gate rule {source_metric} needs one constraint")
        constraint = cast(Literal["max_regression", "max_increase"], constraints[0])
        try:
            threshold = float(rule[constraint])
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"quality gate threshold for {source_metric} is invalid"
            ) from error
        if threshold < 0:
            raise ConfigurationError("quality gate thresholds cannot be negative")
        comparison_value = rule.get("comparison")
        comparison = comparison_value or (
            "absolute"
            if metric in {"pass_rate", "average_correctness", "hallucination_rate", "tool_accuracy"}
            else "relative"
        )
        if comparison not in {"absolute", "relative"}:
            raise ConfigurationError(f"invalid comparison for {source_metric}")
        severity = rule.get("severity", "WARN" if metric in LOWER_IS_BETTER else "FAIL")
        if severity not in {"FAIL", "WARN"}:
            raise ConfigurationError(f"invalid severity for {source_metric}")
        rules.append(
            GateRule(
                metric=metric,
                constraint=constraint,
                threshold=threshold,
                comparison=cast(Literal["absolute", "relative"], comparison),
                severity=cast(Literal["FAIL", "WARN"], severity),
            )
        )
    return gate_id, name.strip(), tuple(rules)


def load_config(path: Path) -> RunConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(f"Could not read {path}: {error}") from error
    document = _mapping(raw, "configuration")
    agent = _mapping(document.get("agent"), "agent")
    endpoint = agent.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://")):
        raise ConfigurationError("agent.endpoint must be an HTTP(S) URL")
    evaluators = document.get("evaluators")
    if (
        not isinstance(evaluators, list)
        or not evaluators
        or not all(isinstance(value, str) and value.strip() for value in evaluators)
    ):
        raise ConfigurationError("evaluators must contain at least one evaluator name or ID")
    experiment = _mapping(document.get("experiment", {}), "experiment")
    gate_id, gate_name, gate_rules = _rules(document.get("quality_gate"))
    max_concurrency = int(experiment.get("max_concurrency", 5))
    if not 1 <= max_concurrency <= 100:
        raise ConfigurationError("experiment.max_concurrency must be between 1 and 100")
    return RunConfig(
        api_url=str(document.get("api_url", "http://localhost:8000")).rstrip("/"),
        token_env=str(document.get("token_env", "AGENTSCOPE_TOKEN")),
        organization=cast(str | None, document.get("organization")),
        project=_required_string(document, "project"),
        dataset=_required_string(document, "dataset"),
        dataset_version=cast(str | int, document.get("dataset_version", "latest")),
        environment=str(document.get("environment", "development")),
        evaluators=tuple(cast(list[str], evaluators)),
        agent=agent,
        experiment_name=str(experiment.get("name", "CI candidate")),
        max_concurrency=max_concurrency,
        poll_interval_seconds=float(experiment.get("poll_interval_seconds", 2)),
        timeout_seconds=float(experiment.get("timeout_seconds", 1800)),
        quality_gate_id=gate_id,
        quality_gate_name=gate_name,
        quality_gate_rules=gate_rules,
    )
