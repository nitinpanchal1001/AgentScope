# Scaling strategy

The control plane begins with stateless FastAPI services and PostgreSQL. This keeps transactional tenant configuration, credentials, datasets, and experiments understandable and recoverable. Redis coordinates bounded background work; separate Celery queues prevent expensive evaluation jobs from starving maintenance or alert work.

At sustained ingestion volumes that PostgreSQL cannot serve economically, only the trace-storage boundary evolves:

```text
SDK → load balancer → stateless ingestion → Kafka → trace processors → ClickHouse
                                                        └──────────────→ S3 (oversized payloads)
PostgreSQL → identity, projects, configuration, datasets, experiments
Qdrant     → tenant-filtered failure embeddings
Redis      → task coordination, rate limits, intentional short-lived caches
```

Repositories keep trace storage behind a boundary beginning in Phase 2. Kafka and ClickHouse should not be introduced until measured load and query profiles justify their operational cost. Metrics must avoid unbounded labels such as trace IDs or tenant IDs.

