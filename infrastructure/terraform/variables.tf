variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "name_prefix" {
  type    = string
  default = "agentscope"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the public AgentScope hostname."
}

variable "public_origin" {
  type        = string
  description = "HTTPS browser origin, for example https://agentscope.example.com."
  validation {
    condition     = startswith(var.public_origin, "https://")
    error_message = "public_origin must use HTTPS"
  }
}

variable "image_tag" {
  type        = string
  description = "Immutable image tag, normally a Git SHA."
  validation {
    condition     = var.image_tag != "latest" && length(var.image_tag) > 0
    error_message = "Use an immutable image tag, not latest."
  }
}

variable "qdrant_url" {
  type        = string
  description = "Managed Qdrant HTTPS cluster URL."
  validation {
    condition     = startswith(var.qdrant_url, "https://")
    error_message = "qdrant_url must use HTTPS"
  }
}

variable "qdrant_api_key" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "api_desired_count" {
  type    = number
  default = 2
}

variable "web_desired_count" {
  type    = number
  default = 2
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "deletion_protection" {
  type    = bool
  default = true
}
