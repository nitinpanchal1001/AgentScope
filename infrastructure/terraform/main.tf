data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "${var.name_prefix}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 2)
  public_subnets = {
    for index, az in local.azs : az => cidrsubnet(var.vpc_cidr, 8, index)
  }
  private_subnets = {
    for index, az in local.azs : az => cidrsubnet(var.vpc_cidr, 8, index + 10)
  }
  services = {
    api = {
      repository = "api", desired = var.api_desired_count, cpu = 1024, memory = 2048, port = 8000
      command    = ["uvicorn", "agentscope_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    }
    web = {
      repository = "web", desired = var.web_desired_count, cpu = 512, memory = 1024, port = 3000
      command    = null
    }
    worker-evaluation = {
      repository = "worker", desired = var.worker_desired_count, cpu = 1024, memory = 2048, port = null
      command    = ["celery", "-A", "agentscope_worker.celery_app", "worker", "-Q", "evaluation", "-l", "INFO"]
    }
    worker-experiment = {
      repository = "worker", desired = var.worker_desired_count, cpu = 1024, memory = 2048, port = null
      command    = ["celery", "-A", "agentscope_worker.celery_app", "worker", "-Q", "experiment,replay", "-l", "INFO"]
    }
    worker-general = {
      repository = "worker", desired = var.worker_desired_count, cpu = 1024, memory = 2048, port = null
      command    = ["celery", "-A", "agentscope_worker.celery_app", "worker", "-Q", "failure_analysis,analytics,alerts,maintenance", "-l", "INFO"]
    }
    worker-beat = {
      repository = "worker", desired = 1, cpu = 256, memory = 512, port = null
      command    = ["celery", "-A", "agentscope_worker.celery_app", "beat", "-l", "INFO"]
    }
  }
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = local.name }
}

resource "aws_subnet" "public" {
  for_each                = local.public_subnets
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = each.value
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${each.key}" }
}

resource "aws_subnet" "private" {
  for_each          = local.private_subnets
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = each.value
  tags              = { Name = "${local.name}-private-${each.key}" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name}-nat" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = values(aws_subnet.public)[0].id
  depends_on    = [aws_internet_gateway.main]
  tags          = { Name = local.name }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "alb" {
  name   = "${local.name}-alb"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "app" {
  name   = "${local.name}-app"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    from_port = 8000
    to_port   = 8000
    protocol  = "tcp"
    self      = true
  }
  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "data" {
  name   = "${local.name}-data"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

resource "random_password" "database" {
  length  = 40
  special = false
}
resource "random_password" "redis" {
  length  = 40
  special = false
}
resource "random_password" "jwt" {
  length  = 64
  special = false
}
resource "random_password" "hash" {
  length  = 64
  special = false
}
resource "random_password" "worker" {
  length  = 64
  special = false
}
resource "random_password" "notification" {
  length  = 64
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = values(aws_subnet.private)[*].id
}

resource "aws_db_instance" "postgres" {
  identifier                   = "${local.name}-postgres"
  engine                       = "postgres"
  engine_version               = "17"
  instance_class               = var.db_instance_class
  allocated_storage            = 50
  max_allocated_storage        = 500
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "agentscope"
  username                     = "agentscope"
  password                     = random_password.database.result
  db_subnet_group_name         = aws_db_subnet_group.main.name
  vpc_security_group_ids       = [aws_security_group.data.id]
  multi_az                     = var.environment == "production"
  backup_retention_period      = 14
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = !var.deletion_protection
  final_snapshot_identifier    = var.deletion_protection ? "${local.name}-final" : null
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
}

resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = values(aws_subnet.private)[*].id
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${local.name}-redis"
  description                = "AgentScope coordination and rate limits"
  node_type                  = var.redis_node_type
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.data.id]
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token                 = random_password.redis.result
  automatic_failover_enabled = var.environment == "production"
  multi_az_enabled           = var.environment == "production"
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  snapshot_retention_limit   = 7
}

resource "aws_secretsmanager_secret" "runtime" {
  name                    = "${local.name}/runtime"
  recovery_window_in_days = 30
}

resource "aws_secretsmanager_secret_version" "runtime" {
  secret_id = aws_secretsmanager_secret.runtime.id
  secret_string = jsonencode({
    DATABASE_URL                = "postgresql+asyncpg://agentscope:${urlencode(random_password.database.result)}@${aws_db_instance.postgres.address}:5432/agentscope"
    REDIS_URL                   = "rediss://:${urlencode(random_password.redis.result)}@${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
    JWT_SECRET                  = random_password.jwt.result
    TOKEN_HASH_SECRET           = random_password.hash.result
    WORKER_API_KEY              = random_password.worker.result
    NOTIFICATION_SIGNING_SECRET = random_password.notification.result
    QDRANT_URL                  = var.qdrant_url
    QDRANT_API_KEY              = var.qdrant_api_key
    OPENAI_API_KEY              = var.openai_api_key
  })
}

resource "aws_ecr_repository" "images" {
  for_each             = toset(["api", "web", "worker"])
  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_cloudwatch_log_group" "service" {
  for_each          = local.services
  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = 30
}

resource "aws_iam_role" "execution" {
  name = "${local.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets" {
  name = "runtime-secrets"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.runtime.arn }]
  })
}

resource "aws_iam_role" "task" {
  name = "${local.name}-ecs-task"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${local.name}.internal"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "api" {
  name = "api"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }
  health_check_custom_config { failure_threshold = 1 }
}

resource "aws_lb" "main" {
  name                       = substr(local.name, 0, 32)
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = values(aws_subnet.public)[*].id
  enable_deletion_protection = var.deletion_protection
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "api" {
  name        = substr("${local.name}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path    = "/health/ready"
    matcher = "200"
  }
}

resource "aws_lb_target_group" "web" {
  name        = substr("${local.name}-web", 0, 32)
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"
  health_check {
    path    = "/"
    matcher = "200-399"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern { values = ["/api/*", "/v1/*", "/health/*"] }
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = local.services
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([merge({
    name = each.key, image = "${aws_ecr_repository.images[each.value.repository].repository_url}:${var.image_tag}", essential = true
    environment = each.key == "web" ? [] : [
      { name = "AGENTSCOPE_ENVIRONMENT", value = var.environment },
      { name = "AGENTSCOPE_ALLOWED_ORIGINS", value = jsonencode([var.public_origin]) },
      { name = "AGENTSCOPE_REFRESH_COOKIE_SECURE", value = "true" },
      { name = "AGENTSCOPE_WORKER_API_URL", value = "http://api.${aws_service_discovery_private_dns_namespace.main.name}:8000" },
      { name = "AGENTSCOPE_EXPERIMENT_ALLOW_HTTP", value = "false" },
      { name = "AGENTSCOPE_EXPERIMENT_ALLOW_PRIVATE_ENDPOINTS", value = "false" },
      { name = "AGENTSCOPE_NOTIFICATION_ALLOW_HTTP", value = "false" },
      { name = "AGENTSCOPE_NOTIFICATION_ALLOW_PRIVATE_ENDPOINTS", value = "false" }
    ]
    secrets = each.key == "web" ? [] : [
      for key in ["DATABASE_URL", "REDIS_URL", "JWT_SECRET", "TOKEN_HASH_SECRET", "WORKER_API_KEY", "NOTIFICATION_SIGNING_SECRET", "QDRANT_URL", "QDRANT_API_KEY", "OPENAI_API_KEY"] :
      { name = key == "OPENAI_API_KEY" ? key : "AGENTSCOPE_${key}", valueFrom = "${aws_secretsmanager_secret.runtime.arn}:${key}::" }
    ]
    portMappings = each.value.port == null ? [] : [{ containerPort = each.value.port, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options   = { awslogs-group = aws_cloudwatch_log_group.service[each.key].name, awslogs-region = var.aws_region, awslogs-stream-prefix = each.key }
    }
  }, each.value.command == null ? {} : { command = each.value.command })])
}

resource "aws_ecs_service" "service" {
  for_each        = local.services
  name            = each.key
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = each.value.desired
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = values(aws_subnet.private)[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }
  dynamic "load_balancer" {
    for_each = contains(["api", "web"], each.key) ? [each.key] : []
    content {
      target_group_arn = each.key == "api" ? aws_lb_target_group.api.arn : aws_lb_target_group.web.arn
      container_name   = each.key
      container_port   = each.key == "api" ? 8000 : 3000
    }
  }
  dynamic "service_registries" {
    for_each = each.key == "api" ? [1] : []
    content {
      registry_arn = aws_service_discovery_service.api.arn
    }
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  health_check_grace_period_seconds = contains(["api", "web"], each.key) ? 60 : null
  depends_on                        = [aws_lb_listener.https, aws_secretsmanager_secret_version.runtime]
  lifecycle { ignore_changes = [desired_count] }
}

resource "aws_appautoscaling_target" "service" {
  for_each           = { for key, value in local.services : key => value if key != "worker-beat" }
  max_capacity       = contains(["api", "web"], each.key) ? 10 : 20
  min_capacity       = each.value.desired
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  for_each           = aws_appautoscaling_target.service
  name               = "${local.name}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = each.value.resource_id
  scalable_dimension = each.value.scalable_dimension
  service_namespace  = each.value.service_namespace
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}
