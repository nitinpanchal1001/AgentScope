from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentscope_evaluation.deterministic import evaluate_deterministic
from agentscope_evaluation.models import EvaluationOutcome, EvaluationType
from agentscope_evaluation.providers import (
    EmbeddingProvider,
    LiteLLMJudgeProvider,
    cosine_similarity,
)

DETERMINISTIC_TYPES = {
    EvaluationType.EXACT_MATCH,
    EvaluationType.CONTAINS,
    EvaluationType.REGEX,
    EvaluationType.JSON_SCHEMA,
    EvaluationType.LATENCY_THRESHOLD,
    EvaluationType.COST_THRESHOLD,
    EvaluationType.REQUIRED_TOOL,
    EvaluationType.FORBIDDEN_TOOL,
    EvaluationType.TOOL_ARGUMENTS,
    EvaluationType.CITATION_PRESENCE,
}


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator_type: EvaluationType
    input: Any = None
    output: Any = None
    expected_output: Any = None
    context: Any = None
    trace: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    threshold: float = Field(default=0.8, ge=0, le=1)
    provider: str | None = None
    model: str | None = None
    rubric: str | None = None


class EvaluationEngine:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        judge_provider: LiteLLMJudgeProvider | None = None,
    ) -> None:
        self.embedding_provider = embedding_provider
        self.judge_provider = judge_provider or LiteLLMJudgeProvider()

    async def evaluate(self, request: EvaluationRequest) -> EvaluationOutcome:
        if request.evaluator_type in DETERMINISTIC_TYPES:
            return evaluate_deterministic(
                request.evaluator_type,
                candidate=request.output,
                expected_output=request.expected_output,
                trace=request.trace,
                configuration=request.configuration,
            )
        if request.evaluator_type is EvaluationType.SEMANTIC_SIMILARITY:
            if self.embedding_provider is None:
                raise ValueError("semantic evaluation requires an embedding provider")
            candidate = str(request.output or "")
            reference = str(
                request.expected_output or request.configuration.get("reference_output") or ""
            )
            vectors = await self.embedding_provider.embed([candidate, reference])
            score = cosine_similarity(vectors[0], vectors[1])
            return EvaluationOutcome(
                score=score,
                passed=score >= request.threshold,
                label="PASS" if score >= request.threshold else "FAIL",
                reason="Cosine similarity between candidate and reference embeddings",
                evidence=[{"similarity": score}],
            )
        if request.provider is None or request.model is None or request.rubric is None:
            raise ValueError("LLM evaluation requires provider, model, and rubric")
        external_fields = request.configuration.get("external_fields")
        allowed_fields = {"input", "output", "expected_output", "context", "trace"}
        if not isinstance(external_fields, list) or not external_fields:
            raise ValueError("LLM evaluation requires explicit external_fields configuration")
        if any(field not in allowed_fields for field in external_fields):
            raise ValueError("LLM evaluation external_fields contains an unsupported field")
        available_payload = {
            "input": request.input,
            "output": request.output,
            "expected_output": request.expected_output,
            "context": request.context,
            "trace": request.trace,
        }
        judged = await self.judge_provider.judge(
            provider=request.provider,
            model=request.model,
            rubric=request.rubric,
            payload={field: available_payload[field] for field in external_fields},
            parameters=request.configuration.get("parameters"),
        )
        return EvaluationOutcome(**judged.model_dump())
