variable "environment" {
  description = "Environment name (e.g. dev, staging, prod)"
  type        = string
}

variable "db_password" {
  description = "Master password for the RDS instance"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "pudimjobs"
}

variable "db_user" {
  description = "Master username for the RDS instance"
  type        = string
  default     = "pudimjobs"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}