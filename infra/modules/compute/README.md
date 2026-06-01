# Compute Module (Placeholder)

Skeleton for production compute resources. Currently a placeholder — Phase 0 development runs locally via Docker Compose.

## Planned Resources

- ECS Fargate cluster for backend API and Celery workers
- ECR repositories for Docker images (created now)
- Application Load Balancer
- Auto-scaling policies
- S3 bucket or CloudFront for frontend hosting

## Current Resources

| Resource | Purpose |
|----------|---------|
| aws_ecr_repository.backend | Stores backend Docker images |
| aws_ecr_repository.frontend | Stores frontend Docker images |

## Usage

```hcl
module "compute" {
  source = "./modules/compute"

  environment  = "dev"
  rds_endpoint = module.rds.endpoint
}