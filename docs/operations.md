# Operations

SLOs, capacity, cost, security and on-call runbooks for the dev / production
stack. Everything here assumes `docker compose up` unless stated otherwise.

## SLOs

| Service | SLI / target | Notes |
|---------|--------------|-------|
| API availability | `successful_health_checks / total_health_checks` over 7d → **99.5%** | Prometheus `up`, scraped every 30s; error budget 0.5% (~5h/yr) |
| Scraping freshness | 95% of sources scraped within 1h | per-source; Beat sweep every 15 min |
| Search latency | p99 < 500ms | PostgreSQL FTS |
| Notification delivery | 99% delivered within 5min | email + in-app; sourced from `notifications.status` |

Error-budget policy: >2% of the budget burned in 1h pages on-call; exhausting the
budget freezes feature deploys until it is restored; downtime is root-caused in a
postmortem.

## Capacity

A scrape task (fetch + parse + insert) takes ≈0.5s → ≈8 scrapes/s per worker at
concurrency 4.

| Metric | 50 sources hourly | 500 sources hourly |
|--------|-------------------|--------------------|
| Scrape tasks/hour | 50 | 500 |
| Wall time, 2 workers | ~25s | ~5min |
| Workers needed (<1min window) | 2 | 10 |

| Search dataset | Latency |
|----------------|---------|
| 2k jobs (MVP) | 0.7ms (measured) |
| 10⁵ jobs | ~2–5ms (GIN index) |
| 10⁶ jobs | ~10ms — read replica / OpenSearch decision point |

Storage ≈1KB per job row (~15MB/mo at 500 sources), ~10KB per generated CV PDF.
Raw HTML is intentionally not retained, so reprocessing is a re-scrape.

Scaling signals: `celery` queue depth > 100 → `docker compose up -d --scale
worker=4`; scrape p95 > 2s → check target rate limits; rising
`pudimjobs_scrapes_total{status="failed"}` → `scraper-failure` runbook.

## Cost (monthly, AWS us-east-1, indicative)

| Scenario | Configuration | Total |
|----------|---------------|-------|
| MVP (50 sources) | RDS `db.t4g.small` + 2×`t4g.small` compute + `cache.t4g.micro` + S3 + ALB | **~$88** |
| Projection (500 sources, 10k users) | RDS `db.t4g.medium` + 2×`t4g.medium` API + 3×`t4g.medium` spot workers + `cache.t4g.small` + S3 + ALB | **~$240** (+$75 with OpenSearch) |

Cost levers: spot instances for workers (largest single saving, 60–70%), S3
lifecycle to Glacier for old CV PDFs, single-AZ RDS, reserved capacity at steady
state. `infra/main.tf` provisions RDS + ECR today; ECS/ALB/VPC/S3/ElastiCache are
documented provisioning gaps.

## Database performance

Measured on local PostgreSQL 16 with 2,000 jobs (one user).

| Query | Time | Plan |
|-------|------|------|
| FTS (`search_vector @@ plainto_tsquery('english','python')`, ranked, user-filtered) | 0.70ms | Bitmap Heap Scan on `ix_jobs_user_id` + `search_vector` filter |
| FTS, no user filter | 0.75ms | Seq Scan (planner prefers it at 2k rows) |
| Legacy ILIKE (3 columns) | 2.08ms | Seq Scan + 3 pattern filters |

`search_vector` is a generated stored column (`setweight` title A > company B >
description C) with a GIN index (`ix_jobs_search_vector`); the planner prefers the
GIN index past ~10⁴–10⁵ rows. Alert matching (`ix_alert_rules_user_id`) and the
pipeline query (`ix_applications_user_id`) are <0.1ms at current scale; add
composite `(user_id, active)` / `(user_id, status)` indexes past ~1k rows/user.
`scripts/load_test.py` (asyncio + httpx, concurrency 20) reports p50 <5ms,
p95 <15ms, ≈200 req/s single-process uvicorn.

## Search evaluation (PG FTS vs Elasticsearch/OpenSearch)

| Capability | PG FTS | ES |
|-----------|--------|----|
| Relevance | `ts_rank` (lexical) | BM25 (tunable) |
| Prefix / typo | manual (`prefix` tsquery) | `edge_ngram` + fuzzy |
| Faceted aggregation | SQL `GROUP BY` | native aggregations |
| Scale-out | manual sharding | native cluster |
| Operational cost | $0 extra containers | +1GB cluster, +$100–180/mo |

The corpus (≈2.5k live jobs, ~10⁵ historical) is far below the scale where ES
pays off, and there is no faceted/typo/search-as-you-type requirement. Switch to
ES when the corpus exceeds ~10⁶ rows, multi-tenant search needs isolation, or
BM25-tuning is required — the `job.new` event bus already feeds an ES index as an
extra consumer without an API change (ADR 009).

## Security

### STRIDE threat model

**API**

| Threat | Mitigation | Status |
|--------|-----------|--------|
| Spoofing | HS256 JWT with server secret, 24h expiry, bcrypt passwords | Implemented |
| Tampering | TLS in production; Pydantic request validation | Implemented |
| Repudiation | `audit_logs` records CV/app/reprocessing mutations + admin search UI | Implemented |
| Information disclosure | every query scoped by `user_id`; admin routes behind `require_admin` | Implemented |
| Denial of service | slowapi: login 5/min, authenticated API 120/min | Implemented |
| Elevation of privilege | role checked in `require_admin` on every admin route | Implemented |

**Scraping engine**

| Threat | Mitigation | Status |
|--------|-----------|--------|
| Spoofing | scraped data validated by Pydantic/ORM; normalized extract only | Implemented |
| Tampering | HTTPS fetches; user-agent rotation (read-only, no signed payloads) | Implemented |
| Information disclosure | workers read only the env vars they need; no cloud credentials mounted | Implemented |
| Denial of service | per-domain rate limiting + circuit breakers + robots.txt | Implemented |
| Elevation of privilege | workers use the application DB user (least privilege) | Implemented |

Supply chain: `pip-audit` (Python) + Trivy (container) in CI; pinned
requirements with upgrade review.

Accepted residual risks: no refresh-token rotation yet (access-token expiry is
the only bound); rate limits are per-IP/per-token, not per-account; TLS
terminates at the load balancer in production, not in the dev compose stack.

### Secrets rotation

| Secret | Env var / location | Used by |
|--------|--------------------|---------|
| JWT signing key | `SECRET_KEY` | API (token signing/verification) |
| Database password | `DATABASE_URL` (embedded) | API, workers, Alembic |
| RabbitMQ password | `RABBITMQ_URL` / `CELERY_BROKER_URL` | workers, consumer, API broker |
| Redis | `REDIS_URL` | API, workers (no auth in dev) |
| SMTP password | `SMTP_PASSWORD` | email service |
| OpenAI API key (optional) | `OPENAI_API_KEY` / `llm_config` row | LLM tailoring (feature-flagged) |

Generic procedure: generate a new value → update the env var (`.env`, secret
manager, or Terraform) → restart API/workers/consumer → verify (login, trigger a
scrape, check traces/metrics). `SECRET_KEY` rotation invalidates all live
sessions immediately — schedule it for a low-traffic window. Postgres rotates
with `ALTER ROLE … WITH PASSWORD`, RabbitMQ by adding a new user via `rabbitmqctl`
before removing the old one, SMTP by updating `SMTP_PASSWORD` (the mailer
reconnects per message).

Verification checklist: `GET /health` → `ok`; `POST /api/auth/login` works;
a scrape completes; an alert email arrives (Mailpit); Grafana/Jaeger show fresh
data. `.env` is gitignored and the repo history is clean; prefer AWS Secrets
Manager / Vault in production — the app reads everything from env vars, so
swapping the source is config-only.

## Runbooks

### Scraper failure / circuit breaker open

*Symptoms:* source health `failing` in Admin; `failed` DLQ runs; no new jobs.

1. Read the latest error: Admin → Dead-Letter Queue (or `GET /api/admin/dlq`).
2. Open the source URL — a selector error usually reads `'title' key missing`.
3. Check the breaker: `docker exec <redis> redis-cli GET "cb:<source_id>"`.
4. **HTML/format changed** → fix selectors in `scrapers/career_page.py` (or the
   adapter), trigger `POST /api/admin/sources/<id>/scrape`, then
   `redis-cli DEL "cb:<source_id>"` to close the breaker.
5. **Rate limit / robots.txt** → lower `sources.rate_limit_seconds`, confirm
   `robots.txt` allows the path, reset the breaker.
6. **Transient** → the built-in Celery retry (1m→2m→4m, 3 attempts) self-heals;
   if not, treat as case 4.

Verify: health `healthy`, DLQ stops growing, new jobs appear, quality recovers.

### RabbitMQ queue backlog

*Symptoms:* `matching.job.new`/`celery` queues grow (RabbitMQ UI `:9672`);
notifications lag.

1. Inspect depth (`curl -u pudimjobs:pudimjobs_dev .../api/queues/%2F`).
2. Check the consumer: `docker compose ps event-consumer` + logs.
3. **Consumer down** → `docker compose up -d event-consumer` (durable queues
   buffer events; no loss).
4. **Saturated workers** → `docker compose up -d --scale worker=4`.
5. **Poison messages** → purge the `celery` queue only after confirming no
   legitimate work is queued.

Verify: depths return to ~0, notifications arrive, Grafana shows no backlog.

### Data quality degradation

*Symptoms:* Admin → Data Quality shows completeness dropping or duplicates
rising.

1. Pull `GET /api/admin/quality/overview` and `/by-source`; identify the source
   and the dominant issue (low completeness = missing fields; rising duplicates =
   cross-posting; dropping normalization = mapping gaps).
2. **Completeness** → inspect affected jobs, fix the parser (see scraper-failure),
   re-scrape the source to refresh jobs and quality.
3. **Duplicates** → confirm via the job's `issues` (`possible duplicate of
   <canonical_id>`), tune `is_duplicate_of`'s threshold in
   `app/services/quality.py`, or exclude the noisy source; re-assess.
4. **Normalization gaps** → add the mapping to `app/data/company_map.json` or
   `title_map.json` and re-run quality for affected jobs.

Verify: average completeness back to baseline, duplicate count stable.

### Database failover / unavailability

*Symptoms:* `GET /health` returns `degraded` (db `disconnected`); 500s on
DB-backed routes; worker connection errors.

1. Confirm state: `docker compose ps postgres`, logs, `pg_isready -U pudimjobs`.
2. Check disk and size (`df -h`, `pg_database_size('pudimjobs')`).
3. **Container stopped** → `docker compose up -d postgres`.
4. **Disk full** → delete old `generated_cvs`/`scrape_runs` rows (>90 days) and
   `VACUUM FULL jobs;`.
5. **Index bloat** → `REINDEX CONCURRENTLY` on `ix_jobs_search_vector` and
   `ix_jobs_user_id`.
6. **Production RDS failover** → Terraform provisions `multi_az`; API and workers
   use a single `DATABASE_URL` endpoint whose DNS name tracks the active
   instance. Multi-host strings are a future refinement — a failover briefly
   interrupts in-flight tasks (Celery retries absorb it).

Verify: health `ok`/db `connected`, a scrape stores a job, alerts deliver,
DB error rate back to zero.

## Incidents, chaos & monitoring

**Chaos experiments** (`scripts/chaos/`, run against a live stack):
`kill_rabbitmq.py` (durable queues buffer events), `break_scraper_html.py`
(retries → breaker → DLQ → recovery), `exhaust_worker_memory.py` (OOM retried,
idempotent inserts prevent duplicates), `drop_data_quality.py` (normalization
degrades and recovers). Each script prints `[PASS]`/`[FAIL]` and restores state.

**Postmortem 001 — scraper outage & data quality degradation** (simulated,
`break_scraper_html.py`). A job board redesigned its career page; hardcoded CSS
selectors stopped matching, the circuit breaker tripped after 5 failures, and the
source paused (health `failing`, runs recorded with
`error = "'title' key missing in normalized output"`). ~40 postings and alert
coverage for 12 users were affected for ~2h; no data loss (re-scrape recovered
everything). Root cause: selectors with no pre-normalization validation.
Contributing: no automated alert on `source.health == failing`. What worked:
circuit breaker, retry/backoff, DLQ + replay, re-scrape recovery. Corrective
actions: fail a scrape when *every* parsed item is missing `title`/`company`
(done); add a Grafana alert on `failing` health / open breaker; add
changed-markup test fixtures asserting a *failed* scrape; add a per-source
expected-vs-actual jobs drift metric; schedule the chaos script quarterly.

**Dashboards** — Grafana (RED API, scraper throughput, data quality) at `:9300`;
Prometheus `:9409`; Jaeger traces `:9668`.
