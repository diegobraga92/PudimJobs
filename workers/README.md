# PudimJobs Celery Workers

Celery workers that run the scraping engine. The broker is RabbitMQ (with a
dead-letter exchange) and Redis is the result backend + circuit-breaker store.

## Local development

The worker imports the backend's `app` package (models, config, database), so
install the backend requirements first:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd ../workers && pip install -r requirements.txt
```

With RabbitMQ and Redis running (docker-compose or local), run:

```bash
# Worker process
celery -A workers.celery_app worker --loglevel=info

# Beat scheduler (periodic sweep)
celery -A workers.celery_app beat --loglevel=info
```

The Beat scheduler is configured in `workers/beat_schedule.py` (and mirrored
in `workers/celery_app.py`). It runs `sweep_sources` every
`scrape_sweep_interval_minutes`, which enqueues a `scrape_source` task per
source due for scraping.

## Resilience overview

| Mechanism | Implementation |
|-----------|----------------|
| Circuit breaker | Redis `cb:{source_id}` counter; ≥5 consecutive failures pauses the source for 1h |
| Rate limiting | Redis `rate:{domain}` TTL per source (`sources.rate_limit_seconds`) |
| User-agent rotation | Configured pool in `app.config` |
| robots.txt | Checked per domain, cached in-process for 1h |
| Retry | Celery `autoretry_for` with exponential backoff (1m→2m→4m) |
| Dead letters | RabbitMQ DLX (`pudimjobs.dlx`) + durable `scrape_runs` failed records |
