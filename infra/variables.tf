variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Project name used for resource naming"
  type        = string
  default     = "kbaas"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ---------- Database ----------
variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t4g.micro" # Cheapest — 2 vCPU, 1GB RAM, ~$12/mo
}

variable "db_allocated_storage" {
  description = "RDS storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "kbaas"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "kbaas"
}

# ---------- ECS ----------
variable "backend_cpu" {
  description = "Fargate task CPU units (256 = 0.25 vCPU)"
  type        = number
  default     = 256
}

variable "backend_memory" {
  description = "Fargate task memory in MB"
  type        = number
  default     = 512
}

variable "backend_desired_count" {
  description = "Number of ECS tasks"
  type        = number
  default     = 1
}

# ---------- Budget ----------
variable "monthly_budget_limit" {
  description = "Monthly AWS spend alert threshold in USD"
  type        = number
  default     = 50
}

variable "budget_alert_email" {
  description = "Email for budget alerts"
  type        = string
  default     = ""
}
