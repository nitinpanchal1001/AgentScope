import hashlib
import json
import math
import re
from collections import Counter, deque
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings
from agentscope_api.core.exceptions import NotFoundError
from agentscope_api.models import (
    EvaluationStatus,
    FailureCluster,
    FailureClusterMember,
    FailureRecord,
    Membership,
    Project,
    Span,
    SpanType,
    Trace,
    TraceStatus,
)
from agentscope_api.repositories.failures import FailureRepository
from agentscope_api.services.authorization import Permission, require_permission

EMBEDDING_DIMENSIONS = 128
MAX_DOCUMENT_CHARACTERS = 16_000
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./:-]+")


class ClusterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    probable_cause: str = Field(min_length=1, max_length=2000)
    suggested_action: str = Field(min_length=1, max_length=2000)


def hashing_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Deterministic feature hashing baseline behind the embedding boundary."""
    vector = [0.0] * dimensions
    for token in TOKEN_PATTERN.findall(text.lower()):
        digest = hashlib.blake2b(token.encode(), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def detect_agent_loop(spans: list[Span], max_steps: int = 50) -> dict[str, Any]:
    tools = [span.name for span in spans if span.type is SpanType.TOOL]
    evidence: list[dict[str, Any]] = []
    if len(spans) > max_steps:
        evidence.append({"heuristic": "step_limit", "observed": len(spans), "limit": max_steps})
    for name, count in Counter(tools).items():
        if count >= 3:
            evidence.append({"heuristic": "repeated_tool", "tool": name, "count": count})
    for size in (2, 3):
        for start in range(0, max(0, len(tools) - size * 3 + 1)):
            sequence = tools[start : start + size]
            if tools[start : start + size * 3] == sequence * 3:
                evidence.append(
                    {"heuristic": "repeated_sequence", "sequence": sequence, "repetitions": 3}
                )
                break
    return {"possible_agent_loop": bool(evidence), "evidence": evidence}


def density_clusters(
    embeddings: list[list[float]], *, minimum_size: int = 2, maximum_distance: float = 0.35
) -> list[list[int]]:
    """Small deterministic DBSCAN implementation; unreturned points are noise."""
    neighbors = [
        [
            candidate
            for candidate, other in enumerate(embeddings)
            if 1 - cosine_similarity(vector, other) <= maximum_distance
        ]
        for vector in embeddings
    ]
    labels = [-1] * len(embeddings)
    visited = [False] * len(embeddings)
    cluster_index = 0
    for point in range(len(embeddings)):
        if visited[point]:
            continue
        visited[point] = True
        if len(neighbors[point]) < minimum_size:
            continue
        labels[point] = cluster_index
        queue = deque(neighbors[point])
        while queue:
            candidate = queue.popleft()
            if not visited[candidate]:
                visited[candidate] = True
                if len(neighbors[candidate]) >= minimum_size:
                    queue.extend(item for item in neighbors[candidate] if item not in queue)
            if labels[candidate] == -1:
                labels[candidate] = cluster_index
        cluster_index += 1
    return [
        [index for index, label in enumerate(labels) if label == cluster]
        for cluster in range(cluster_index)
    ]


class QdrantFailureIndex:
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
        collection: str = "agentscope_failures",
    ) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.headers = {"api-key": api_key} if api_key else {}

    async def ensure_collection(self, client: httpx.AsyncClient) -> None:
        response = await client.get(f"/collections/{self.collection}")
        if response.status_code == 404:
            created = await client.put(
                f"/collections/{self.collection}",
                json={"vectors": {"size": EMBEDDING_DIMENSIONS, "distance": "Cosine"}},
            )
            created.raise_for_status()
        else:
            response.raise_for_status()

    async def upsert(self, record: FailureRecord) -> None:
        async with httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=10) as client:
            await self.ensure_collection(client)
            response = await client.put(
                f"/collections/{self.collection}/points",
                params={"wait": "true"},
                json={
                    "points": [
                        {
                            "id": str(record.vector_point_id),
                            "vector": record.embedding,
                            "payload": {
                                "organization_id": str(record.organization_id),
                                "project_id": str(record.project_id),
                                "trace_id": str(record.trace_id),
                                "failure_id": str(record.id),
                                "failure_type": record.failure_type,
                                "agent_version": record.agent_version,
                                "timestamp": record.detected_at.isoformat(),
                            },
                        }
                    ]
                },
            )
            response.raise_for_status()

    async def search(
        self, organization_id: UUID, project_id: UUID, vector: list[float], limit: int
    ) -> list[tuple[UUID, float]]:
        async with httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=10) as client:
            await self.ensure_collection(client)
            response = await client.post(
                f"/collections/{self.collection}/points/search",
                json={
                    "vector": vector,
                    "limit": limit,
                    "with_payload": True,
                    "filter": {
                        "must": [
                            {
                                "key": "organization_id",
                                "match": {"value": str(organization_id)},
                            },
                            {"key": "project_id", "match": {"value": str(project_id)}},
                        ]
                    },
                },
            )
            response.raise_for_status()
            return [
                (UUID(item["payload"]["failure_id"]), float(item["score"]))
                for item in response.json()["result"]
            ]

    async def delete_points(self, point_ids: list[UUID]) -> None:
        if not point_ids:
            return
        async with httpx.AsyncClient(base_url=self.url, headers=self.headers, timeout=10) as client:
            await self.ensure_collection(client)
            response = await client.post(
                f"/collections/{self.collection}/points/delete",
                params={"wait": "true"},
                json={"points": [str(value) for value in point_ids]},
            )
            response.raise_for_status()


class FailureIntelligenceService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = FailureRepository(session)
        self.index = QdrantFailureIndex(settings.qdrant_url, settings.qdrant_api_key)

    async def analyze(
        self, project: Project, membership: Membership, trace_id: UUID
    ) -> FailureRecord | None:
        require_permission(membership.role, Permission.TRACE_READ)
        trace = await self.repository.trace(trace_id, project.id)
        if trace is None:
            raise NotFoundError("Trace")
        return await self._analyze(project, trace)

    async def analyze_internal(self, trace_id: UUID) -> FailureRecord | None:
        trace = await self.session.get(Trace, trace_id)
        if trace is None:
            raise NotFoundError("Trace")
        project = await self.session.get(Project, trace.project_id)
        if project is None:
            raise NotFoundError("Project")
        return await self._analyze(project, trace)

    async def _analyze(self, project: Project, trace: Trace) -> FailureRecord | None:
        spans = await self.repository.spans(trace.id)
        evaluations = await self.repository.evaluations(trace.id)
        loop = detect_agent_loop(spans)
        successful_scores = [
            float(result.score)
            for result in evaluations
            if result.status is EvaluationStatus.SUCCESS and result.score is not None
        ]
        low_quality = bool(successful_scores) and min(successful_scores) < 0.8
        if trace.status is TraceStatus.ERROR:
            failure_type = trace.error_type.value if trace.error_type else "TECHNICAL_ERROR"
        elif loop["possible_agent_loop"]:
            failure_type = "AGENT_LOOP"
        elif low_quality:
            failure_type = "QUALITY_FAILURE"
        else:
            return None
        existing = await self.repository.by_trace(trace.id, project.id)
        document = self._document(trace, spans, evaluations, loop)
        record = existing or FailureRecord(
            id=uuid4(),
            organization_id=project.organization_id,
            project_id=project.id,
            trace_id=trace.id,
            vector_point_id=uuid4(),
            detected_at=datetime.now(UTC),
        )
        record.failure_type = failure_type
        record.title = f"{failure_type.replace('_', ' ').title()}: {trace.name}"[:240]
        record.document = document
        record.evidence = {
            "loop_detection": loop,
            "evaluation_scores": successful_scores,
            "trace_status": trace.status.value,
            "error_type": trace.error_type.value if trace.error_type else None,
        }
        record.embedding = hashing_embedding(document)
        record.agent_version = trace.agent_version
        if existing is None:
            self.session.add(record)
        await self.session.commit()
        try:
            await self.index.upsert(record)
        except httpx.HTTPError:
            record.evidence = {**record.evidence, "vector_index_pending": True}
            await self.session.commit()
        return record

    async def search(
        self, project: Project, membership: Membership, query: str, limit: int
    ) -> list[tuple[FailureRecord, float]]:
        require_permission(membership.role, Permission.TRACE_READ)
        vector = hashing_embedding(query)
        try:
            matches = await self.index.search(project.organization_id, project.id, vector, limit)
            ids = [item[0] for item in matches]
            records = await self.repository.failures_by_ids(ids, project.id)
            scores = {item[0]: item[1] for item in matches}
            return [(record, scores[record.id]) for record in records]
        except httpx.HTTPError:
            records = await self.repository.failures(project.id)
            ranked = sorted(
                ((record, cosine_similarity(vector, record.embedding)) for record in records),
                key=lambda item: item[1],
                reverse=True,
            )
            return ranked[:limit]

    async def rebuild_clusters(
        self, project: Project, membership: Membership
    ) -> list[FailureCluster]:
        require_permission(membership.role, Permission.PROJECT_MANAGE)
        return await self._rebuild_clusters(project)

    async def rebuild_clusters_internal(self, project_id: UUID) -> list[FailureCluster]:
        project = await self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("Project")
        return await self._rebuild_clusters(project)

    async def _rebuild_clusters(self, project: Project) -> list[FailureCluster]:
        failures = await self.repository.failures(project.id)
        clusters = density_clusters([failure.embedding for failure in failures])
        await self.repository.replace_clusters(project.id)
        now = datetime.now(UTC)
        for indexes in clusters:
            members = [failures[index] for index in indexes]
            common_type = Counter(item.failure_type for item in members).most_common(1)[0][0]
            summary, summary_source = await self._summarize_cluster(members, common_type)
            first_seen = min(item.detected_at for item in members)
            last_seen = max(item.detected_at for item in members)
            cluster = FailureCluster(
                id=uuid4(),
                organization_id=project.organization_id,
                project_id=project.id,
                title=summary.title,
                description=summary.description,
                probable_cause=summary.probable_cause,
                suggested_action=summary.suggested_action,
                summary_source=summary_source,
                size=len(members),
                failure_percentage=(
                    Decimal(len(members)) / Decimal(len(failures)) * Decimal(100)
                    if failures
                    else Decimal(0)
                ),
                first_seen=first_seen,
                last_seen=last_seen,
                representative_failure_ids=[str(item.id) for item in members[:3]],
                created_at=now,
                updated_at=now,
            )
            self.session.add(cluster)
            self.session.add_all(
                [
                    FailureClusterMember(cluster_id=cluster.id, failure_id=item.id)
                    for item in members
                ]
            )
        await self.session.commit()
        return await self.repository.clusters(project.id)

    async def _summarize_cluster(
        self, members: list[FailureRecord], common_type: str
    ) -> tuple[ClusterSummary, str]:
        fallback = ClusterSummary(
            title=f"Recurring {common_type.replace('_', ' ').lower()}",
            description=(
                "Inferred cluster of semantically similar failures. "
                f"Representative example: {members[0].title}."
            ),
            probable_cause=(
                "Suggested cause: the failures share similar inputs, execution evidence, "
                "and normalized feedback; inspect representative traces to confirm."
            ),
            suggested_action=(
                "Review the representative traces and add the recurring case to a versioned "
                "dataset before changing the agent."
            ),
        )
        if not self.settings.openai_api_key:
            return fallback, "HEURISTIC_INFERENCE"
        representative_context = "\n\n".join(item.document[:4_000] for item in members[:3])
        schema = {
            "type": "object",
            "properties": {
                key: {"type": "string"}
                for key in ("title", "description", "probable_cause", "suggested_action")
            },
            "required": ["title", "description", "probable_cause", "suggested_action"],
            "additionalProperties": False,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                    json={
                        "model": self.settings.failure_summary_model,
                        "instructions": (
                            "Summarize a cluster of similar AI-agent failures. Treat probable "
                            "cause as an inference, never a certainty, and propose a concrete "
                            "engineering follow-up. Do not repeat secrets or personal data."
                        ),
                        "input": representative_context,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "failure_cluster_summary",
                                "strict": True,
                                "schema": schema,
                            }
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
            output_text = next(
                content["text"]
                for output in payload.get("output", [])
                if output.get("type") == "message"
                for content in output.get("content", [])
                if content.get("type") == "output_text"
            )
            return ClusterSummary.model_validate_json(output_text), "OPENAI_STRUCTURED_INFERENCE"
        except (httpx.HTTPError, KeyError, StopIteration, ValueError):
            return fallback, "HEURISTIC_INFERENCE"

    @staticmethod
    def _document(
        trace: Trace, spans: list[Span], evaluations: list[Any], loop: dict[str, Any]
    ) -> str:
        value = {
            "trace_input": trace.input,
            "trace_output": trace.output,
            "error_type": trace.error_type.value if trace.error_type else None,
            "error_message": trace.error_message,
            "evaluation_feedback": [
                {
                    "score": str(result.score) if result.score is not None else None,
                    "passed": result.passed,
                    "reason": result.reason,
                    "error": result.error_message,
                }
                for result in evaluations[:20]
            ],
            "tool_sequence": [span.name for span in spans if span.type is SpanType.TOOL][:100],
            "span_summaries": [
                {
                    "type": span.type.value,
                    "name": span.name,
                    "status": span.status.value,
                    "error_type": span.error_type.value if span.error_type else None,
                    "error_message": span.error_message,
                }
                for span in spans[:100]
            ],
            "agent_version": trace.agent_version,
            "model_information": [
                {"provider": span.provider, "model": span.model} for span in spans if span.model
            ][:20],
            "loop_evidence": loop,
        }
        return json.dumps(value, ensure_ascii=False, default=str)[:MAX_DOCUMENT_CHARACTERS]
