# Ingestion load testing

The checked-in k6 profile models concurrent SDK clients calling the idempotent batch ingestion
endpoint. Defaults are 100 virtual users, one request per user, and 50 telemetry events per batch
(25 complete traces). It records request failure rate, rejected batches, and request latency. The
default P95 threshold is a 10-second smoke-test ceiling, not a production SLO; set
`P95_THRESHOLD='p(95)<...'` to the approved SLO for the tested deployment.

```bash
export AGENTSCOPE_API_KEY=as_test_your_one_time_key
make load-test
```

All controls can be overridden without editing the profile:

```bash
VUS=20 ITERATIONS_PER_VU=5 BATCH_SIZE=50 \
P95_THRESHOLD='p(95)<1500' ERROR_RATE_THRESHOLD='rate<0.005' \
AGENTSCOPE_API_KEY=as_test_... make load-test
```

Run against an isolated environment with representative PostgreSQL, Redis, API replica, and network
settings. Capture the k6 summary, API `/metrics`, PostgreSQL saturation, and worker queue depth. This
repository intentionally publishes the method and thresholds but no performance number: a result is
valid only with the tested commit, infrastructure shape, data volume, and raw k6 output attached.
