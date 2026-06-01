variable "environment" {
  description = "Environment name (e.g. dev, staging, prod)"
  type        = string
}

variable "rds_endpoint" {
  description = "RDS endpoint for backend to connect to"
  type        = string
  default     = ""
}