# Monitoring, alerts, and retention

The `/monitoring` screen presents project and environment-scoped production analytics. Trace detail
uses authenticated server-sent events while a trace is running and closes the stream when the trace
reaches a terminal state.

Alert rules support error rate, hallucination rate, P95 latency, average trace cost, average
evaluation score, and tool failure rate. Rules select an operator, threshold, lookback window,
severity, optional environment, delivery channel, and cooldown. Celery beat evaluates enabled rules
every minute. A window-derived unique key plus the per-rule cooldown prevents duplicate events and
notification storms. Every attempt is stored in alert history.

Webhook notifications reject plain HTTP and private/reserved destinations by default, do not follow
redirects, omit the target URL from the body, and include `X-AgentScope-Signature-256`, an HMAC-SHA256
signature over the exact request body. Set `AGENTSCOPE_NOTIFICATION_SIGNING_SECRET` to a random
secret and verify the signature at the receiver. Development-only HTTP/private delivery must be
enabled explicitly. Email uses SMTP with optional STARTTLS and authentication; passwords remain in
worker environment variables and never enter alert history or audit metadata.

Each project has a 1–365 day retention period. The daily maintenance task deletes expired Qdrant
points before hard-deleting traces and their cascading spans, evaluations, and failure records. It
also intentionally removes replay relationships that would otherwise retain a trace. If Qdrant is
unavailable for a project containing indexed failures, deletion is skipped for that project so
vectors cannot outlive their authoritative records; the next scheduled run retries it.
