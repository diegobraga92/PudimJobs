# Runbook: Database Failover / Unavailability

**Symptoms:** `GET /health` returns `degraded` (db `disconnected`); API returns
500s on DB-backed endpoints; worker tasks fail with connection errors.

## Investigation

1. Confirm Postgres state:
   ```bash
   docker compose ps postgres
   docker compose logs postgres --tail=20
   docker exec <postgres-container> pg_isready -U pudimjobs
   ```
2. Check disk and load:
   ```bash
   docker exec <postgres-container> df -h /var/lib/postgresql/data
   docker exec <postgres-container> psql -U pudimjobs -c "SELECT pg_size_pretty(pg_database_size('pudimjobs'));"
   ```

## Resolution

1. **Container stopped** → restart and verify:
   ```bash
   docker compose up -d postgres
   ```
2. **Disk full** → archive/delete old raw HTML (keep `jobs` rows):
   ```sql
   UPDATE jobs SET raw_html = NULL WHERE created_at < now() - interval '90 days';
   ```
   then `VACUUM FULL jobs;`
3. **Index bloat** → `REINDEX CONCURRENTLY` on the hot indexes
   (`ix_jobs_search_vector`, `ix_jobs_user_id`).
4. **Production RDS failover** → Terraform provisions `multi_az`; the API and
   workers connect via a single `DATABASE_URL` endpoint (the DNS name tracks
   the active instance). Multi-host connection strings are a Phase 8
   refinement — until then a failover briefly interrupts in-flight tasks
   (Celery retries absorb it).

## Verification

- [ ] `GET /health` returns `ok` / db `connected`.
- [ ] A scrape completes and a job is stored.
- [ ] Alert matching delivers (Mailpit / Notifications).
- [ ] Grafana shows DB-related error rate back to zero.
