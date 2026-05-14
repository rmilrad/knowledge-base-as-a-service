output "app_url" {
  description = "CloudFront URL (main entry point)"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "alb_url" {
  description = "ALB URL (direct, HTTP only)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_backend_url" {
  description = "ECR repository URL for backend Docker pushes"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_url" {
  description = "ECR repository URL for frontend Docker pushes"
  value       = aws_ecr_repository.frontend.repository_url
}

output "s3_docs_bucket" {
  description = "S3 bucket for document storage"
  value       = aws_s3_bucket.docs.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.main.id
}

output "rds_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.address
  sensitive   = true
}

output "db_secret_arn" {
  description = "ARN of the DB credentials secret"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "app_secret_arn" {
  description = "ARN of the app secrets (JWT + Anthropic key)"
  value       = aws_secretsmanager_secret.app_secrets.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}
