output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.endpoint
}

output "backend_repository_url" {
  description = "ECR repository URL for backend"
  value       = module.compute.backend_repository_url
}

output "frontend_repository_url" {
  description = "ECR repository URL for frontend"
  value       = module.compute.frontend_repository_url
}