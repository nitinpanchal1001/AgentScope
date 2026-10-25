# Reverse proxy

AWS deployments use the Terraform ALB. `agentscope.conf` is the equivalent hardened routing example
for self-hosted Docker/Kubernetes ingress: web is the default, while API, ingestion, health, internal,
and metrics paths route to FastAPI. Replace certificate paths and restrict `/internal` and `/metrics`
to trusted networks before use.
