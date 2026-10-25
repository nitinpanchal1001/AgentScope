import json
import math
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from agentscope_evaluation.models import JudgeOutput


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        endpoint: str = "https://api.openai.com/v1",
        timeout: float = 30,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.endpoint}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda item: item["index"])]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding vectors must be non-empty and equal length")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


class LiteLLMJudgeProvider:
    async def judge(
        self,
        *,
        provider: str,
        model: str,
        rubric: str,
        payload: dict[str, Any],
        parameters: dict[str, Any] | None = None,
    ) -> JudgeOutput:
        from litellm import acompletion

        model_name = model if "/" in model else f"{provider}/{model}"
        prompt = (
            "Evaluate the supplied AI-agent execution against the rubric. "
            "Return only a JSON object matching the requested schema.\n\n"
            f"Rubric:\n{rubric}\n\nExecution:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        messages = [{"role": "user", "content": prompt}]
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The prior output was invalid. Return strict JSON only, "
                            "with no markdown."
                        ),
                    }
                )
            try:
                response = await acompletion(
                    model=model_name,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "evaluation_result",
                            "strict": True,
                            "schema": JudgeOutput.model_json_schema(),
                        },
                    },
                    timeout=30,
                    num_retries=0,
                    **(parameters or {}),
                )
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise ValueError("judge returned no text content")
                return JudgeOutput.model_validate_json(content)
            except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
                last_error = error
        raise ValueError(
            "LLM judge returned invalid structured output after repair"
        ) from last_error
