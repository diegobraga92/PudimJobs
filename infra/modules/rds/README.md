# RDS Module (PostgreSQL)

Creates an RDS PostgreSQL instance for PudimJobs.

## Usage

```hcl
module "rds" {
  source = "./modules/rds"

  environment = "dev"
  db_password = var.db_password
}
```

## Inputs

| Name | Description | Type | Default |
|------|-------------|------|---------|
| environment | Environment name (dev, staging, prod) | string | required |
| db_password | Master password for RDS | string (sensitive) | required |
| db_name | Database name | string | "pudimjobs" |
| db_user | Master username | string | "pudimjobs" |
| allocated_storage | Storage in GB | number | 20 |

## Outputs

| Name | Description |
|------|-------------|
| endpoint | RDS instance endpoint |
| port | RDS instance port |
| db_name | Database name |
| db_user | Master username |

## Notes

- Uses PostgreSQL 16 on db.t3.micro
- Encryption at rest enabled (storage_encrypted = true)
- Backup retention: 7 days
- Deletion protection enabled for production