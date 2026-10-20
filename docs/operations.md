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

### Source `degraded` but nothing failed (`skipped` runs)

*Symptoms:* the Sources page shows a `degraded` badge, its last run says
`skipped`, and Admin → DLQ (which defaults to `failed`) has nothing — so the
source looks broken with no explanation.

Every source row now carries its **last run** (any status) and the reason
behind its health. Click the health badge to open the panel: health, reason,
last run/success, stored job count and the last 10 attempts. The same data is
served by `GET /api/sources/<id>/diagnostics` and
`GET /api/sources/<id>/runs?limit=10`.

1. `robots.txt disallows this source (<url>)` is a **rule**, not a failure:
   do not bypass it. Use a provider for that board or drop the source.
2. `robots.txt unreachable at <url> (...)` is a **transient** failure (timeout,
   DNS/TLS error, 5xx): the run is denied conservatively but retried on the next
   sweeps. The backoff is `SCRAPE_SKIP_RETRY_MINUTES` (15 min), not the 24 h
   used for a real skip. A failed robots fetch is cached for only 60 s (a
   successful parse is cached for 1 h), so recovery is picked up quickly.
3. `robots.txt` returning **4xx** means "no restrictions published" (RFC 9309)
   and never skips a run.
4. `API key`/`manual source`/`source is avoided` in the reason are
   configuration states: store the key, check a watchlist by hand, or restore
   the avoided source.
5. **Retry now** → the panel's *Re-check now*
   (`POST /api/sources/<id>/scrape`, owner-scoped) or
   `POST /api/admin/sources/<id>/scrape`. Both clear the skip backoff first,
   so the retry does not wait for the sweep/backoff to expire.
6. If `unreachable` keeps coming back, check worker egress:
   `docker compose exec worker python -c "import httpx; print(httpx.get('https://<host>/robots.txt', timeout=5).status_code)"`.

Verify: a fresh `success` row appears in the health panel, the badge returns to
`healthy`, and the reason line disappears.

### RabbitMQ queue backlog

*Symptoms:* `matching.job.new`/`celery` queues grow (RabbitMQ UI `:9672`);
notifications lag; the worker is "Up" but a scrape never starts.

1. Inspect depth and consumers:
   `docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers`.
   A `celery` queue with `messages > 0` and `consumers = 0` means the worker
   lost its broker consumer; restarting it while stale tasks still occupy its
   slots does not help.
2. Check the consumer: `docker compose ps event-consumer` + logs.
3. **Consumer down** → `docker compose up -d event-consumer` (durable queues
   buffer events; no loss).
4. **Saturated workers** → `docker compose up -d --scale worker=4`.
5. **Worker lost its consumer** (logs mention a delivery acknowledgement
   timeout) → `docker compose kill worker` (do not wait for a warm shutdown on
   a long run), purge the stale `celery` queue, then start the worker again.
   The sweep rebuilds the due list; purge only after confirming the queued work
   is stale. Scrapes now fail at `SCRAPE_TASK_SOFT_TIME_LIMIT_SECONDS` (20 min)
   / hard limit 25 min, below RabbitMQ's `consumer_timeout` (2h in
   `infra/rabbitmq/rabbitmq.conf`), so the broker only kills the consumer if the
   worker itself is wedged.
6. **Poison messages** → purge the `celery` queue only after confirming no
   legitimate work is queued.

The sweep also fails `running` rows older than `SCRAPE_RUN_STALE_MINUTES` (30),
skips sources with a live run, and backs off permanently skipped sources for
`SCRAPE_SKIP_BACKOFF_MINUTES` (24h) — transient skips (robots.txt unreachable)
only `SCRAPE_SKIP_RETRY_MINUTES` (15 min). If the Sources page still shows "Due
now" after a restart, check `scrape_runs` for orphaned rows and the worker logs.

Verify: depths return to ~0, notifications arrive, Grafana shows no backlog.

#### Celery consumer stall — copy-paste triage

Run these on the Docker host (`ssh 192.168.3.99`, then `cd ~/PudimJobs`).
Define the helpers once in the shell. The `WORKER_METRICS_PORT=0` /
`OTLP_ENDPOINT=` overrides are required for any extra process that imports
`workers.celery_app`; otherwise it tries to bind the worker's metrics port 9100
and exits with `Address already in use`.

```bash
cd ~/PudimJobs
celeryw() { docker compose exec -T -e WORKER_METRICS_PORT=0 -e OTLP_ENDPOINT= worker celery -A workers.celery_app "$@"; }
pyw()     { docker compose exec -T -e WORKER_METRICS_PORT=0 -e OTLP_ENDPOINT= worker python "$@"; }
psqlw()   { docker compose exec -T postgres psql -U pudimjobs -d pudimjobs "$@"; }
redisw()  { docker compose exec -T redis redis-cli "$@"; }
rabbitw() { docker compose exec -T rabbitmq rabbitmqctl "$@"; }
```

If you put these in a non-interactive script or heredoc, append `</dev/null` to
each `docker compose exec` call; otherwise `-T` can consume the rest of the
script as stdin.

**1. Triage (read-only).**

```bash
docker compose ps worker beat event-consumer backend
docker inspect -f 'worker status={{.State.Status}} exit={{.State.ExitCode}} restarts={{.RestartCount}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' pudimjobs-worker-1
rabbitw list_queues name messages messages_ready messages_unacknowledged consumers
celeryw inspect ping --timeout 10
celeryw inspect active --timeout 10
celeryw inspect reserved --timeout 10
psqlw -c "SELECT s.name, r.id, r.started_at, now()-r.started_at AS age
          FROM scrape_runs r JOIN sources s ON s.id=r.source_id
          WHERE r.status='running' ORDER BY r.started_at;"
```

The stall signature is the **`celery`** queue with `messages > 0` and
`consumers = 0`. `messages_unacknowledged` counts active/reserved work; up to
`worker_concurrency` (4) is normal. `matching.job.new` belongs to the event
consumer, not the worker. `restart: unless-stopped` restarts an exited worker,
but **does not** restart a container that is merely unhealthy; the queue's
consumer count is the definitive check. `inspect ping` can still answer through
the separate pidbox consumer, so do not rely on it alone.

**2. Confirm the timeout and the worker's limits.**

```bash
rabbitw eval 'application:get_env(rabbit, consumer_timeout).'   # expect {ok,7200000}
docker compose exec -T rabbitmq cat /etc/rabbitmq/rabbitmq.conf
pyw -c "from workers.tasks.scrape import scrape_source as t; print('soft', t.soft_time_limit, 'hard', t.time_limit, 'expires', t.expires, 'no-retry', t.dont_autoretry_for)"
docker compose logs --since 2h worker | grep -Ei \
  'PRECONDITION_FAILED|delivery acknowledgement|consumer_timeout|timed out|StreamLostError|WorkerLostError|SoftTimeLimitExceeded|ready'
docker compose logs --since 2h rabbitmq | grep -Ei 'consumer_timeout|timed out|closing AMQP connection'
```

`delivery acknowledgement ... timed out. Timeout value used: 1800000 ms` means
a task outlived the broker's `consumer_timeout`. `SoftTimeLimitExceeded` means
the worker's own 20-minute guard fired first (expected for a slow source). If
`consumer_timeout` is missing or still 1800000, the config mount is wrong;
recreating the broker re-reads it (the `rabbitmq_data` volume is preserved):

```bash
docker compose up -d --force-recreate rabbitmq
docker compose up -d worker beat event-consumer backend
rabbitw eval 'application:get_env(rabbit, consumer_timeout).'
```

**3. Inspect queued task names before deleting anything.** The management API
is on `http://127.0.0.1:9672` (default credentials `pudimjobs` /
`pudimjobs_dev`; use the remote host/IP if not running locally).
`ack_requeue_true` peeks without removing messages:

```bash
curl -fsS -u pudimjobs:pudimjobs_dev -H 'content-type: application/json' \
  -X POST 'http://127.0.0.1:9672/api/queues/%2F/celery/get' \
  -d '{"count":5,"ackmode":"ack_requeue_true","encoding":"auto","truncate":50000}' \
  | python3 -c 'import json,sys
for m in json.load(sys.stdin):
    h = (m.get("properties") or {}).get("headers") or {}
    print(h.get("task"), (m.get("payload") or "")[:160])'
```

If the queue contains only stale `workers.tasks.scrape.scrape_source` /
`sweep_sources` messages, purging is safe because the sweep rebuilds the due
list. If it also contains `jd_parse`, `match_job`, `quality` or `tailor` tasks,
do not purge blindly — start the worker and let those drain first.

**4. Recover a lost consumer.** Stop the worker with `stop` (not `kill`) so
`unless-stopped` does not immediately restart it; update **all** `running` rows
only after the worker is down, and clear the per-source locks while nothing can
be running:

```bash
docker compose stop beat
docker compose stop -t 5 worker
docker compose ps worker                         # must show Exited before continuing
rabbitw purge_queue celery                       # only after step 3
psqlw -c "UPDATE scrape_runs SET status='failed', finished_at=now(),
          error='orphaned: worker stopped for consumer recovery'
          WHERE status='running';"
docker compose exec -T redis sh -c \
  'redis-cli --scan --pattern "scrape:lock:*" | while read k; do redis-cli DEL "$k"; done'
docker compose up -d worker
for _ in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' pudimjobs-worker-1)" = healthy ] && break
  sleep 2
done
docker inspect -f '{{.State.Health.Status}}' pudimjobs-worker-1
rabbitw list_queues name messages messages_ready messages_unacknowledged consumers
celeryw inspect ping --timeout 10
docker compose up -d beat
pyw -c "from workers.tasks.sweep import sweep_sources; print(sweep_sources.delay().id)"
docker compose logs --tail=100 worker | grep -E 'sweep_complete|scrape_'
```

The sweep itself reaps rows older than `SCRAPE_RUN_STALE_MINUTES` (30). If you
did not stop the worker, use the 30-minute guard instead of updating all
`running` rows. Beat's first automatic sweep can be up to one interval (15 min)
after a restart, hence the manual `.delay()` above. If beat starts but never
logs `Sending due task sweep-sources`, reset its ephemeral schedule:

```bash
docker compose up -d --force-recreate beat
```

**5. Unstick one source** (open breaker / 24h skip backoff / stale lock).
These keys live in Redis **DB 0** (the app's `REDIS_URL`), not the Celery result
backend DB 1:

```bash
SRC=<source-uuid>
psqlw -c "SELECT id, name, health, last_scraped, rate_limit_seconds FROM sources ORDER BY name;"
psqlw -c "SELECT status, started_at, finished_at, left(error,160)
          FROM scrape_runs WHERE source_id='$SRC' ORDER BY started_at DESC LIMIT 5;"
redisw GET "cb:$SRC";            redisw TTL "cb:$SRC"
redisw GET "skip:$SRC";          redisw TTL "skip:$SRC"
redisw GET "scrape:lock:$SRC";   redisw TTL "scrape:lock:$SRC"
```

`TTL` `-2` means the key is absent. The breaker opens after 5 failures and
expires after 1h; the skip backoff lasts 24h. Clear them only after fixing the
cause. Clear the lock only when no run for that source is active:

```bash
redisw DEL "cb:$SRC" "skip:$SRC"
redisw DEL "scrape:lock:$SRC"    # only with no running row / active task
pyw -c "from workers.tasks.scrape import scrape_source; print(scrape_source.delay('$SRC').id)"
```

Or use Admin → “Scrape now”. A failed scrape can also be replayed with
`POST /api/admin/dlq/<run_id>/replay`. Lower a slow source's pacing (takes
effect on the next run, no restart):

```bash
psqlw -c "UPDATE sources SET rate_limit_seconds=12 WHERE id='$SRC';"
```

**6. Find sources that can exceed the 10-minute budget.**

```bash
psqlw -c "SELECT name, rate_limit_seconds,
                 COALESCE((config->>'max_results')::int, 20) AS max_results,
                 rate_limit_seconds * COALESCE((config->>'max_results')::int, 20) AS worst_case_seconds
          FROM sources WHERE type <> 'manual'
          ORDER BY worst_case_seconds DESC LIMIT 15;"
```

Keep `worst_case_seconds` ≤600. That leaves 10 minutes before the 20-minute
soft limit and 15 before the 25-minute hard limit. Lower `rate_limit_seconds`
or `max_results` for the top offenders; `rate_limit_seconds=0` means no
cooldown (and is valid). `max_results` defaults to 20 here, but some adapters
default higher, so treat the query as a lower bound.

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
