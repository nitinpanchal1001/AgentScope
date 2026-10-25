# Failure intelligence

AgentScope normalizes technical errors, low evaluation scores, and heuristic agent-loop evidence
into bounded failure documents. Documents contain input/output, errors, evaluation feedback, tool
order, bounded span summaries, agent version, model information, and loop evidence; they are capped
at 16,000 characters rather than embedding unbounded raw telemetry.

The built-in embedding boundary uses deterministic 128-dimensional feature hashing, which is
private, reproducible, and works without sending trace content to a third party. A provider-backed
semantic model can replace this implementation without changing persistence or search APIs.
PostgreSQL is authoritative; Qdrant is a rebuildable similarity index.

Every Qdrant point carries `organization_id`, `project_id`, `trace_id`, `failure_id`, failure type,
agent version, and timestamp. Search always includes exact organization and project filters. The API
also re-scopes returned IDs through PostgreSQL, and falls back to tenant-scoped PostgreSQL cosine
search if Qdrant is temporarily unavailable.

## Detection and search

Terminal ingestion and completed evaluations enqueue idempotent failure analysis on the dedicated
Celery queue. The worker-authenticated internal endpoint also refreshes project clusters when a
failure is found. Operators can retry manually from a terminal trace with **Analyze failure** (or `POST
/api/v1/projects/{project_id}/traces/{trace_id}/failure-analysis`). Successful traces without a low
score or loop signal do not create a failure. Analysis is idempotent per trace.

Loop evidence is explicitly heuristic and labeled `possible_agent_loop`. V1 detects repeated tools,
repeated two/three-step tool sequences, and excessive total steps. It does not claim certainty.

Semantic search is available through `POST /api/v1/projects/{project_id}/failures/search` with a
query and limit. The failure-intelligence screen links every result back to its source trace.

## Clustering

Cluster rebuild uses DBSCAN-style density clustering over normalized vectors. It never assumes a
cluster count and leaves sparse points as noise. Stored clusters include size, share of failures,
first/last seen timestamps, representative records, and suggested follow-up.

When `OPENAI_API_KEY` is configured, AgentScope sends at most three bounded representative
documents to the Responses API and requests strict JSON-schema output. The response is validated
again before storage and labeled `OPENAI_STRUCTURED_INFERENCE`. Provider failures fall back to
`HEURISTIC_INFERENCE`. Both are suggestions, not established root causes; engineers should confirm
them by inspecting representative traces. The implementation follows the official OpenAI
[Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
