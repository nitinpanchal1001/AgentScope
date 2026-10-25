# AWS deployment

This Terraform stack provisions the stable AgentScope runtime topology:

- a two-AZ VPC with public ALB subnets and private application/data subnets;
- ECS/Fargate services for web, API, evaluation/experiment/general workers, and one Celery beat;
- encrypted RDS PostgreSQL and ElastiCache Redis with backups and deletion protection controls;
- ECR repositories, CloudWatch log groups, Secrets Manager, least-privilege task roles, and scaling;
- an HTTPS ALB that routes API/ingestion/health/metrics paths to FastAPI and all other paths to web.

Qdrant Cloud remains managed by Qdrant. Supply its HTTPS cluster URL and API key; both are injected
from Secrets Manager. Terraform state contains generated/runtime secrets, so use an encrypted remote
backend with tightly restricted access. The local backend is only suitable for evaluation.

## Deploy

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

Build and push `api`, `web`, and `worker` images to the ECR outputs before creating services (or run
the first apply with desired counts set to zero). Build the web image with
`NEXT_PUBLIC_API_URL=https://your-domain.example`; the supplied ALB routes that same host.

Run migrations as a one-off API task before updating the API service:

```bash
aws ecs run-task --cluster <cluster> --launch-type FARGATE \
  --task-definition <api-task-family> --network-configuration '<private-network-json>' \
  --overrides '{"containerOverrides":[{"name":"api","command":["alembic","upgrade","head"]}]}'
```

Keep exactly one `worker-beat` replica. Application services use deployment circuit breakers;
migrations are intentionally not coupled to API container startup. Configure DNS to the ALB, keep
RDS deletion protection enabled, and put AWS WAF/rate controls in front of authentication and
ingestion for internet-facing deployments.
