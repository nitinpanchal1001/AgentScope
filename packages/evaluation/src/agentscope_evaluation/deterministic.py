import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from jsonschema import ValidationError, validate

from agentscope_evaluation.models import EvaluationOutcome, EvaluationType


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _result(passed: bool, *, reason: str, evidence: list[Any] | None = None) -> EvaluationOutcome:
    return EvaluationOutcome(
        score=1.0 if passed else 0.0,
        passed=passed,
        label="PASS" if passed else "FAIL",
        reason=reason,
        evidence=evidence or [],
    )


def _tool_spans(trace: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    spans = trace.get("spans", [])
    if not isinstance(spans, list):
        return []
    return [item for item in spans if isinstance(item, Mapping) and item.get("type") == "TOOL"]


def evaluate_deterministic(
    evaluator_type: EvaluationType,
    *,
    candidate: Any,
    expected_output: Any,
    trace: Mapping[str, Any],
    configuration: Mapping[str, Any],
) -> EvaluationOutcome:
    if evaluator_type is EvaluationType.EXACT_MATCH:
        actual = _text(candidate)
        expected = _text(configuration.get("expected", expected_output))
        if not configuration.get("case_sensitive", True):
            actual, expected = actual.casefold(), expected.casefold()
        return _result(actual == expected, reason="Candidate exactly matches the expected output")

    if evaluator_type is EvaluationType.CONTAINS:
        values = configuration.get("values", [configuration.get("value", expected_output)])
        values = values if isinstance(values, list) else [values]
        actual = _text(candidate)
        if not configuration.get("case_sensitive", False):
            actual = actual.casefold()
            values = [_text(value).casefold() for value in values]
        else:
            values = [_text(value) for value in values]
        missing = [value for value in values if value not in actual]
        return _result(
            not missing,
            reason="Candidate contains every required value",
            evidence=missing,
        )

    if evaluator_type is EvaluationType.REGEX:
        pattern = str(configuration["pattern"])
        flags = re.IGNORECASE if configuration.get("ignore_case", False) else 0
        matched = re.search(pattern, _text(candidate), flags) is not None
        return _result(
            matched,
            reason=f"Candidate {'matches' if matched else 'does not match'} regex",
        )

    if evaluator_type is EvaluationType.JSON_SCHEMA:
        try:
            instance = json.loads(candidate) if isinstance(candidate, str) else candidate
            validate(instance=instance, schema=configuration["schema"])
        except (json.JSONDecodeError, ValidationError) as error:
            return _result(
                False,
                reason="Candidate failed JSON Schema validation",
                evidence=[str(error)],
            )
        return _result(True, reason="Candidate satisfies the configured JSON Schema")

    if evaluator_type is EvaluationType.LATENCY_THRESHOLD:
        actual_latency = int(trace.get("latency_ms") or 0)
        maximum_latency = int(configuration["max_latency_ms"])
        return _result(
            actual_latency <= maximum_latency,
            reason=f"Trace latency {actual_latency} ms; threshold {maximum_latency} ms",
            evidence=[{"actual_ms": actual_latency, "maximum_ms": maximum_latency}],
        )

    if evaluator_type is EvaluationType.COST_THRESHOLD:
        actual_cost = Decimal(str(trace.get("total_cost") or 0))
        maximum_cost = Decimal(str(configuration["max_cost"]))
        return _result(
            actual_cost <= maximum_cost,
            reason=f"Trace cost {actual_cost}; threshold {maximum_cost}",
            evidence=[{"actual": str(actual_cost), "maximum": str(maximum_cost)}],
        )

    if evaluator_type in {EvaluationType.REQUIRED_TOOL, EvaluationType.FORBIDDEN_TOOL}:
        tools = [str(span.get("name")) for span in _tool_spans(trace)]
        configured = configuration.get("tools", [configuration.get("tool")])
        configured = [str(item) for item in configured if item]
        present = [name for name in configured if name in tools]
        passed = (
            len(present) == len(configured)
            if evaluator_type is EvaluationType.REQUIRED_TOOL
            else not present
        )
        return _result(passed, reason="Tool policy evaluated", evidence=[{"observed": tools}])

    if evaluator_type is EvaluationType.TOOL_ARGUMENTS:
        tool_name = str(configuration["tool"])
        expected = configuration.get("arguments", {})
        matching = [span for span in _tool_spans(trace) if span.get("name") == tool_name]
        passed = any(
            isinstance(span.get("input"), Mapping)
            and all(span["input"].get(key) == value for key, value in expected.items())
            for span in matching
        )
        return _result(passed, reason="Tool arguments evaluated", evidence=matching)

    if evaluator_type is EvaluationType.CITATION_PRESENCE:
        if isinstance(candidate, Mapping):
            citations = candidate.get("citations", [])
        else:
            pattern = str(configuration.get("pattern", r"\[[^\]]+\]"))
            citations = re.findall(pattern, _text(candidate))
        minimum = int(configuration.get("minimum", 1))
        count = len(citations) if isinstance(citations, list) else 0
        return _result(
            count >= minimum,
            reason=f"Found {count} citations; required {minimum}",
            evidence=list(citations) if isinstance(citations, list) else [],
        )

    raise ValueError(f"{evaluator_type} is not a deterministic evaluator")
