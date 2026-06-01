terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend: local state for Phase 0
  # Will migrate to S3 + DynamoDB in a later phase
}

provider "aws" {
  region = var.aws_region
}

module "rds" {
  source = "./modules/rds"

  environment = var.environment
  db_password = var.db_password
}

module "compute" {
  source = "./modules/compute"

  environment  = var.environment
  rds_endpoint = module.rds.endpoint
}