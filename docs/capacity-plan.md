# Capacity Plan

Scaling analysis for PudimJobs. Two snapshots: the MVP (50 sources) and the
projection (500 sources, 10k users). Figures derive from the Phase 5
`EXPLAIN ANALYZE` measurements and the Phase 2/4 worker design.

## Throughput model

A scrape task takes ≈ 0.5 s (fetch + parse + insert, measured in Phase 2).
Per worker (concurrency 4) that is ≈ 8 scrapes/s per worker.

| Metric | 50 sources hourly | 500 sources hourly |
|--------|-------------------|--------------------|
| Scrape tasks/hour | 50 | 500 |
| Wall time with 2 workers | ~25 s | ~5 min |
| Workers required (< 1 min window) | 2 | 10 |

**Bottleneck:** worker pool size. Celery + Redis broker comfortably handles
> 500 msg/s, so the worker count is the constraint. Beat's uniform 15-minute
sweep staggers tasks naturally; `--scale worker=N` covers spikes.

## Search (PostgreSQL FTS)

| Dataset | Latency (measured/estimated) |
|---------|------------------------------|
| 2k jobs (MVP) | 0.7 ms (measured, Phase 5) |
| 10⁵ jobs (projection) | ~2–5 ms (GIN index) |
| 10⁶ jobs | ~10 ms — read-replica or OpenSearch evaluation point |

**Bottleneck:** single-node PostgreSQL CPU on FTS + `ts_rank` sorting. At
> 10⁶ rows, split reads onto a read replica (see ADR 009 migration path).

## Alert matching

Per `job.new` event, the `match_job` task evaluates the job against the
owner's active rules. Cost per job ≈ O(rules) — sub-millisecond at
5–50 rules/user.

| Metric | MVP | 10k users (500 sources) |
|--------|-----|------------------------|
| New jobs/hour | ~50 | ~500 |
| Match tasks/hour | ~50 | ~500 |
| Notification writes | ~50/hour | ~500/hour (batch inserts recommended) |

**Bottleneck:** write contention on `notifications` under burst; batch inserts
or a dedicated table partition at > 10³ notifications/hour.

## Storage growth

| What | Size/job | 50 sources (≈1.5k jobs/mo) | 500 sources (≈15k jobs/mo) |
|------|----------|---------------------------|----------------------------|
| Jobs row + JSONB | ~1 KB | ~1.5 MB/mo | ~15 MB/mo |
| `raw_html` | ~3 KB | ~4.5 MB/mo → **54 MB/yr** | ~45 MB/mo → **540 MB/yr** |
| Generated CV PDFs | ~10 KB | negligible | ~150 MB/yr |
| GIN tsvector index | ~20% of text | negligible | ~100 MB/yr |

**Recommendation:** move `raw_html` > 90 days old to S3/Glacier (migration is
a column update + archive job). Retains the reprocessing guarantee (ADR 004)
while keeping the RDS volume lean.

## Worker scaling guidance

| Signal | Action |
|--------|--------|
| `celery` queue depth > 100 | `docker compose up -d --scale worker=4` |
| Scrape p95 > 2 s | Check target rate limits / add circuit-breaker tuning |
| `pudimjobs_scrapes_total{status="failed"}` rising | Scraper/HTML incident → runbook `scraper-failure` |
| Notifications write latency > 50 ms | Batch inserts (Phase 5 queue) |

## Summary of bottlenecks

1. **Worker pool size** — first constraint (scale horizontally, spot instances).
2. **PostgreSQL single-node** — FTS CPU + storage at > 10⁶ rows (read replica).
3. **Notification write path** — batch inserts at high job ingestion rates.
