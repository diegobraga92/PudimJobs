resource "aws_db_instance" "pudimjobs" {
  identifier     = "pudimjobs-${var.environment}"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t3.micro"

  db_name  = var.db_name
  username = var.db_user
  password = var.db_password

  allocated_storage     = var.allocated_storage
  storage_encrypted     = true
  storage_type          = "gp3"
  backup_retention_period = 7
  backup_window         = "03:00-04:00"
  maintenance_window    = "sun:04:00-sun:05:00"

  publicly_accessible   = false
  skip_final_snapshot   = var.environment != "prod"
  deletion_protection   = var.environment == "prod"

  vpc_security_group_ids = [aws_security_group.rds.id]

  tags = {
    Name        = "pudimjobs-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "pudimjobs-rds-${var.environment}-"
  description = "Security group for PudimJobs RDS instance"

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    cidr_blocks     = ["10.0.0.0/8"]  # VPC-only access
    description     = "PostgreSQL access from VPC"
  }

  tags = {
    Name        = "pudimjobs-rds-sg-${var.environment}"
    Environment = var.environment
  }
}