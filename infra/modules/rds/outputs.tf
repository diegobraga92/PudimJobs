output "endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.pudimjobs.endpoint
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.pudimjobs.port
}

output "db_name" {
  description = "Database name"
  value       = aws_db_instance.pudimjobs.db_name
}

output "db_user" {
  description = "Master username"
  value       = aws_db_instance.pudimjobs.username
}