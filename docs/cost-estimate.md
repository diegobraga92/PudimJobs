# Cost Estimation

Monthly cloud costs for running PudimJobs. Two scenarios: the **MVP** (50
sources, single user, hourly scraping) and the **projection** (500 sources,
10k users). Prices are indicative (AWS us-east-1, on-demand; spot noted).

## Scenario A — MVP (50 sources, hourly)

| Component | Configuration | Monthly |
|-----------|---------------|---------|
| RDS PostgreSQL 16 | `db.t4g.small`, 20 GB gp3, single-AZ | $25 |
| Compute (API) | 1 × `t4g.small` (ECS Fargate) | $15 |
| Compute (worker + beat + consumer) | 1 × `t4g.small` | $15 |
| ElastiCache Redis 7 | `cache.t4g.micro` (broker/backend/CB) | $12 |
| S3 | 10 GB (raw HTML + PDFs), infrequent access | $1 |
| Application Load Balancer | 1 ALB | $20 |
| **Total** | | **~$88/mo** |

Notes:
- ELK/Jaeger/Grafana run **locally** in dev (docker-compose); not billed.
- Using spot instances for workers drops compute ~60–70% (→ ~$10/mo).

## Scenario B — Projection (500 sources, 10k users)

| Component | Configuration | Monthly |
|-----------|---------------|---------|
| RDS PostgreSQL 16 | `db.t4g.medium`, 100 GB gp3 | $70 |
| Compute (API) | 2 × `t4g.medium` (Fargate) | $60 |
| Compute (workers) | 3 × `t4g.medium` (spot) | $45 |
| ElastiCache Redis 7 | `cache.t4g.small` | $25 |
| S3 | 500 GB (lifecycle to Glacier after 90d) | $10 |
| ALB | 1 ALB + target groups | $30 |
| Elasticsearch (optional, Phase 5 eval) | 3 × `t4g.small` | $75 |
| **Total (without ES)** | | **~$240/mo** |
| **Total (with ES)** | | **~$315/mo** |

## What the existing IaC already provisions

`infra/main.tf` + modules:
- `infra/modules/rds` — RDS PostgreSQL 16, `db.t3.micro`, encrypted storage,
  backup retention 7 days, deletion protection in prod.
- `infra/modules/compute` — ECR repositories for backend + frontend (skeleton).

**Not yet provisioned** (documented as Phase-8 gaps):
- ECS Fargate task definitions / EKS workloads
- ALB + target groups
- VPC networking (the RDS security group currently assumes `10.0.0.0/8`)
- S3 bucket for raw-HTML/PDF archive + lifecycle rules
- ElastiCache Redis

## Cost levers

1. **Spot instances** for workers — largest single saving (60–70%).
2. **Storage lifecycle** — move `raw_html` > 90 days to Glacier (S3) instead of
   the RDS volume.
3. **Single-AZ vs Multi-AZ** — Multi-AZ doubles RDS cost; Phase 7's failover
   runbook assumes the simpler single-AZ dev setup.
4. **Reserved capacity** at steady state (1–3 yr commits cut ~40%).
