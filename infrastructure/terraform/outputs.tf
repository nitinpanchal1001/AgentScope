output "load_balancer_dns_name" {
  value = aws_lb.main.dns_name
}

output "ecr_repositories" {
  value = { for name, repository in aws_ecr_repository.images : name => repository.repository_url }
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "task_definition_families" {
  value = { for name, definition in aws_ecs_task_definition.service : name => definition.family }
}

output "runtime_secret_arn" {
  value     = aws_secretsmanager_secret.runtime.arn
  sensitive = true
}
