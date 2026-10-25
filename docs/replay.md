# Production trace replay

Replay executes the input from a terminal production trace against a specified HTTP agent while
leaving the original trace and spans unchanged. Each replay has a durable record with explicit
`original_trace_id` and `replay_trace_id` fields. The generated execution is a normal trace tagged
with its replay relationship, so existing trace inspection and evaluation tools continue to work.

## HTTP contract and overrides

Start a replay from trace detail or call:

```bash
curl -X POST \
  -H "Authorization: Bearer $AGENTSCOPE_TOKEN" \
  -H "Content-Type: application/json" \
  "$AGENTSCOPE_URL/api/v1/projects/$PROJECT_ID/traces/$TRACE_ID/replays" \
  -d '{
    "agent": {
      "endpoint": "https://candidate-agent.example.com/invoke",
      "headers_from_env": {"Authorization": "CANDIDATE_AGENT_AUTHORIZATION"}
    },
    "overrides": {
      "model": "candidate-model",
      "prompt_version": "support-v2",
      "temperature": 0.1,
      "agent_version": "agent-v2",
      "parameters": {"max_steps": 6}
    }
  }'
```

The worker sends the same strict request/response contract used by experiments. Configuration is
derived from recorded trace metadata and model spans, then merged with explicit overrides. Secret
values are never accepted in replay configuration: `headers_from_env` maps header names to worker
environment-variable names. Replay endpoints use the outbound destination policy, timeouts,
response-size limit, strict response validation, bounded retries, and disabled redirects.

## Evaluation and comparison

When the original has evaluation results, replay creates new results using those exact immutable
evaluator versions and thresholds. A replay stays `EVALUATING` until the cloned evaluations reach
a terminal state. If there are no original evaluations, it completes immediately after invocation.

`GET /api/v1/projects/{project_id}/replays/{replay_id}/comparison` returns side-by-side snapshots
for:

- output and output-changed status
- aggregate evaluation score and delta
- latency, cost, and token deltas
- ordered tool calls
- ordered span structure with parent ordinals

Comparison is available as soon as the replay trace exists; scores may remain null while evaluation
is running. The trace-detail UI polls replay status and renders the comparison, with a link to inspect
the generated trace independently.

## Failure and retry behavior

Dispatch failures and final invocation failures are persisted on the replay record. Completion is
idempotent, so a retry cannot create a second replay trace or overwrite the original. If evaluation
dispatch is interrupted after invocation, retrying the replay task rediscovers outstanding result
IDs and safely dispatches them again.
