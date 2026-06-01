# Compute Module - Placeholder for production deployment
#
# This module is a skeleton that will be expanded in a later phase
# when cloud deployment is implemented. Currently, development runs
# via Docker Compose locally.
#
# Planned resources:
# - ECS Fargate cluster for backend and workers
# - ECR repositories for Docker images
# - Application Load Balancer
# - Auto-scaling policies
# - S3 bucket for static frontend hosting (or CloudFront CDN)

# ECR repositories (placeholder)
resource "aws_ecr_repository" "backend" {
  name                 = "pudimjobs-backend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  tags = {
    Name        = "pudimjobs-backend-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "pudimjobs-frontend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  tags = {
    Name        = "pudimjobs-frontend-${var.environment}"
    Environment = var.environment
  }
}