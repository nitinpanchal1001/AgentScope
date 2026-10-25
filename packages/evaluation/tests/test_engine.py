from typing import Any

import pytest

from agentscope_evaluation import EvaluationEngine, EvaluationRequest, EvaluationType
from agentscope_evaluation.models import JudgeOutput
from agentscope_evaluation.providers import LiteLLMJudgeProvider


def test_litellm_imports_with_security_patched_filelock() -> None:
    import filelock
    import litellm

    assert filelock.__version__.split(".", maxsplit=1)[0] == "4"
    assert callable(litellm.acompletion)


class FakeEmbeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        assert len(texts) == 2
        return [[1.0, 0.0], [0.8, 0.2]]


class FakeJudge(LiteLLMJudgeProvider):
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}

    async def judge(
        self,
        *,
        provider: str,
        model: str,
        rubric: str,
        payload: dict[str, Any],
        parameters: dict[str, Any] | None = None,
    ) -> JudgeOutput:
        self.payload = payload
        return JudgeOutput(
            score=0.9,
            passed=True,
            label="GOOD",
            reason="The response follows the rubric",
            evidence=["relevant"],
        )


@pytest.mark.parametrize(
    ("evaluator_type", "configuration", "output", "trace"),
    [
        (EvaluationType.EXACT_MATCH, {"expected": "ok"}, "ok", {}),
        (EvaluationType.CONTAINS, {"values": ["shipped", "tomorrow"]}, "Shipped tomorrow", {}),
        (EvaluationType.REGEX, {"pattern": r"ORD-\d+"}, "Order ORD-42", {}),
        (
            EvaluationType.JSON_SCHEMA,
            {"schema": {"type": "object", "required": ["answer"]}},
            {"answer": "ok"},
            {},
        ),
        (EvaluationType.LATENCY_THRESHOLD, {"max_latency_ms": 100}, None, {"latency_ms": 90}),
        (EvaluationType.COST_THRESHOLD, {"max_cost": "0.01"}, None, {"total_cost": "0.001"}),
        (
            EvaluationType.REQUIRED_TOOL,
            {"tool": "lookup_order"},
            None,
            {"spans": [{"type": "TOOL", "name": "lookup_order"}]},
        ),
        (
            EvaluationType.FORBIDDEN_TOOL,
            {"tool": "refund_order"},
            None,
            {"spans": [{"type": "TOOL", "name": "lookup_order"}]},
        ),
        (
            EvaluationType.TOOL_ARGUMENTS,
            {"tool": "lookup_order", "arguments": {"order_id": "ORD-42"}},
            None,
            {
                "spans": [
                    {
                        "type": "TOOL",
                        "name": "lookup_order",
                        "input": {"order_id": "ORD-42"},
                    }
                ]
            },
        ),
        (EvaluationType.CITATION_PRESENCE, {"minimum": 1}, {"citations": ["KB-1"]}, {}),
    ],
)
async def test_deterministic_evaluators_pass(
    evaluator_type: EvaluationType,
    configuration: dict[str, Any],
    output: Any,
    trace: dict[str, Any],
) -> None:
    result = await EvaluationEngine().evaluate(
        EvaluationRequest(
            evaluator_type=evaluator_type,
            configuration=configuration,
            output=output,
            trace=trace,
        )
    )
    assert result.passed is True
    assert result.score == 1.0


async def test_semantic_similarity_uses_provider_and_threshold() -> None:
    result = await EvaluationEngine(embedding_provider=FakeEmbeddings()).evaluate(
        EvaluationRequest(
            evaluator_type=EvaluationType.SEMANTIC_SIMILARITY,
            output="candidate",
            expected_output="reference",
            threshold=0.9,
        )
    )
    assert result.passed is True
    assert result.score is not None and 0.9 < result.score <= 1


async def test_llm_judge_only_receives_explicitly_allowed_fields() -> None:
    judge = FakeJudge()
    result = await EvaluationEngine(judge_provider=judge).evaluate(
        EvaluationRequest(
            evaluator_type=EvaluationType.CORRECTNESS,
            input="private input",
            output="public output",
            trace={"metadata": {"secret": "never send"}},
            configuration={"external_fields": ["output"]},
            provider="test",
            model="judge",
            rubric="Score correctness",
        )
    )
    assert result.score == 0.9
    assert judge.payload == {"output": "public output"}


async def test_llm_judge_rejects_implicit_external_data_sharing() -> None:
    with pytest.raises(ValueError, match="explicit external_fields"):
        await EvaluationEngine(judge_provider=FakeJudge()).evaluate(
            EvaluationRequest(
                evaluator_type=EvaluationType.CORRECTNESS,
                output="candidate",
                provider="test",
                model="judge",
                rubric="Score correctness",
            )
        )
