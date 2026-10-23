# Security architecture

The organization is the primary tenant boundary. A request authenticates a user, resolves a membership through the requested resource's organization, and only then applies a centralized permission. Scoped repositories return not-found for foreign UUIDs to avoid confirming another tenant's resource existence.

Dashboard credentials and SDK credentials are deliberately separate. Dashboard access uses access JWTs plus opaque rotating refresh tokens. SDK keys are project/environment credentials with visible prefixes; the secret appears only in the creation response and is stored as an HMAC-SHA-256 digest keyed by a dedicated server secret.

## Operational requirements

- Terminate TLS before the API and enable secure cookies in production.
- Store JWT and hashing secrets in a secrets manager and rotate them using a documented incident process.
- Restrict CORS to the deployed dashboard origin.
- Limit database roles, network paths, and backup access.
- Forward structured logs to a protected sink; do not add raw authorization headers or payload secrets.
- The ingestion boundary enforces configurable batch/event/content limits and a per-project-key Redis request limit. Authentication-edge rate limiting should also be enforced at the load balancer/WAF.
- Enable SDK redaction processors for every deployment that may handle sensitive prompts. Server-side truncation is a size control, not a substitute for pre-transport redaction.

Password-reset delivery is not exposed yet. The table reserves single-use, expiring token storage without asserting an incomplete email workflow.

