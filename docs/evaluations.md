# Evaluations

AgentScope stores evaluator definitions separately from immutable evaluator versions. Every result
references the exact version used, so later configuration, model, threshold, or rubric changes do
not rewrite history.

## Evaluator types

Deterministic evaluators run locally and never call a model: exact match, contains, regex, JSON
Schema, latency threshold, cost threshold, required tool, forbidden tool, tool arguments, and
citation presence. Semantic similarity uses the `EmbeddingProvider` abstraction. LLM judges cover
correctness, relevance, faithfulness, completeness, hallucination, instruction following, tool
selection, and custom rubrics.

LLM judges require `provider`, `model`, `rubric`, and an explicit `configuration.external_fields`
allowlist. Supported fields are `input`, `output`, `expected_output`, `context`, and `trace`.
AgentScope sends only fields on that list. Judge output is parsed into the strict result schema and
gets one repair attempt; malformed output after that records a failed evaluation without inventing
a score.

## Production execution

A production binding selects an immutable evaluator version, environment, deterministic sample
rate, optional status/tag/agent-version filters, and enabled state. At trace completion, AgentScope
creates an idempotent pending result in the ingestion transaction. Dispatch happens as an HTTP
background action after the response, so Redis or model-provider failures cannot roll back trace
ingestion.

The `evaluation` Celery queue receives only result IDs. Workers obtain a scoped payload from the
internal API using `AGENTSCOPE_WORKER_API_KEY`, run the shared evaluation package, and post a
terminal success or failure. Retryable network, rate-limit, and provider 5xx failures use bounded
exponential backoff. Terminal results are idempotent.

## Local workflow

1. Start the stack with `docker compose up --build`.
2. Open `/evaluators`, choose a project, and create an evaluator.
3. Bind its latest version to an environment.
4. Run an instrumented agent using a key for that environment.
5. Open the completed trace. Its evaluation result moves from pending/running to success or failed,
   with score, reason, and evidence in the trace view.

For semantic or LLM evaluation, put provider credentials such as `OPENAI_API_KEY` in `.env`. Never
store provider keys in evaluator configuration.
