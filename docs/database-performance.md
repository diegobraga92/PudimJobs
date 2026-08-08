# Database Performance Report

Measured against a local PostgreSQL 16 with **2,000 sample jobs** (all owned by
one user). Commands: `EXPLAIN ANALYZE` via `psql`.

## Search: Full-Text Search vs ILIKE

| Query | Execution time | Plan |
|-------|---------------|------|
| FTS (`search_vector @@ plainto_tsquery('english','python')`, ranked, user-filtered) | **0.70 ms** | Bitmap Heap Scan on `ix_jobs_user_id`, then `search_vector @@` filter; top-N heapsort |
| FTS (same, **no** user filter) | **0.75 ms** | Seq Scan (planner prefers it at 2k rows; GIN index engages at scale) |
| Legacy ILIKE (`title OR company OR description ILIKE '%python%'`) | **2.08 ms** | Seq Scan + 3 pattern filters |

**Key findings**

- FTS is ~3× faster than the 3-column ILIKE for the same intent, and it
  returns *relevance-ranked* results with a per-row `score`.
- The `search_vector` is a **generated stored column** — maintained by the
  database on every INSERT/UPDATE, no application code required.
- At 2,000 rows the planner favours sequential scans (correctly); the GIN
  index (`ix_jobs_search_vector`) becomes the preferred path once a user (or
  the whole corpus) exceeds roughly 10⁴–10⁵ rows — the typical workload for
  this product (50 sources × ~50 jobs each ≈ 2.5k jobs, growing linearly).

## Alert matching query

`SELECT * FROM alert_rules WHERE user_id = $1 AND active = TRUE` uses the
`ix_alert_rules_user_id` index. With per-user rule counts in the tens, cost is
negligible (< 0.1 ms). If rule counts grow, add a composite index
`(user_id, active)`.

## Application pipeline query

`applications JOIN jobs WHERE user_id = $1 [AND status = $2]` is served by
`ix_applications_user_id`. A composite `(user_id, status)` index is a
recommended addition once per-user application counts exceed ~1k (deferred —
not needed at current scale).

## Index inventory (as of migration 0007)

| Table | Index | Purpose |
|-------|-------|---------|
| `jobs` | `ix_jobs_search_vector` (GIN) | Full-text search |
| `jobs` | `ix_jobs_user_id`, `ix_jobs_company`, `uq_jobs_source_url` | Scoping, filtering, dedup |
| `applications` | `ix_applications_user_id` | Pipeline scoping |
| `master_cv` | `ix_master_cv_user_id`, `uq_master_cv_user_version` | Version scoping |
| `sources` | `ix_sources_user_id` | Scoping |
| `alert_rules` | `ix_alert_rules_user_id` | Matching lookup |
| `notifications` | `ix_notifications_user_id` | Inbox |
| `scrape_quality` | `ix_scrape_quality_job_id` (unique) | One assessment per job |

## Connection pooling

The API and workers use **`NullPool`** (a fresh connection per session). This is
deliberate:

- Workers are short-lived task processes with low connection reuse — a pool
  would hold idle sockets open pointlessly.
- The API benefits from per-request connections under `AsyncSession` with no
  cross-request state.

When sustained throughput exceeds ~1k req/s (Phase 8 capacity planning),
switch to `AsyncAdaptedQueuePool` with `pool_size=10`, `max_overflow=20`, and
measure via `prometheus` `db` gauges. The `DATABASE_URL` knob already supports
this without code changes.

## Load test

See `scripts/load_test.py` (asyncio + httpx). Concurrency of 20 with 200
search requests against FTS: p50 < 5 ms, p95 < 15 ms on a dev workstation;
throughput ≈ 200+ req/s single-process uvicorn. Errors 0.
