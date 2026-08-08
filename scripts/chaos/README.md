# Chaos Experiments

Reproducible failure-injection scripts that prove the resilience story.
Each script assumes the full stack is running (`docker compose up`), injects a
failure, verifies the system's response, then restores.

| Script | Chaos injected | What it verifies |
|--------|---------------|------------------|
| `kill_rabbitmq.py` | Stop RabbitMQ while a scrape is triggered | Durable queues buffer events; worker recovers after restart |
| `break_scraper_html.py` | Serve malformed feed HTML | Celery retries, circuit breaker trips, DLQ captures failures, recovery after fix |
| `exhaust_worker_memory.py` | Cap worker container at 64MB during a scrape burst | OOM tasks are retried; no duplicate jobs (idempotent inserts) |
| `drop_data_quality.py` | Empty the company-name mapping | Normalization degrades visibly in the quality dashboard; recovers when restored |

Run a single experiment:

```bash
cd scripts/chaos
python break_scraper_html.py
```

The scripts print `[PASS]`/`[FAIL]` lines suitable for a demo. See the
postmortem (`docs/postmortems/001-scraper-outage-data-quality.md`) for the
narrative behind `break_scraper_html.py`, and the runbooks
(`docs/runbooks/`) for how an operator responds to each scenario.
