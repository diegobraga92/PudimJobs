# Runbook: Scraper Failure / Circuit Breaker Open

**Symptoms:** Source health shows `failing` in the Admin UI; DLQ has `failed`
scrape runs; no new jobs from a source; alert notifications for that source stop.

## Investigation

1. Open **Admin → Dead-Letter Queue** (or `GET /api/admin/dlq`) and read the
   `error` of the latest failed run.
   ```bash
   curl -s http://localhost:8000/api/admin/dlq -H "Authorization: Bearer $TOKEN" | jq
   ```
2. Open the source URL in a browser. If the page structure changed, the error
   will usually be `'title' key missing` or a selector returned nothing.
3. Check the circuit breaker state (Redis):
   ```bash
   docker exec <redis-container> redis-cli GET "cb:<source_id>"
   ```

## Resolution

### Case A — target site HTML/format changed

1. Update the scraper selectors/parser in `scrapers/career_page.py` (or the
   source-specific adapter).
2. Trigger a manual scrape to verify the fix:
   ```bash
   curl -X POST http://localhost:8000/api/admin/sources/<source_id>/scrape \
     -H "Authorization: Bearer $TOKEN"
   ```
3. Reset the circuit breaker so the source isn't skipped:
   ```bash
   docker exec <redis-container> redis-cli DEL "cb:<source_id>"
   ```
4. Recover historical jobs from stored `raw_html` without re-scraping:
   ```bash
   curl -X POST http://localhost:8000/api/admin/sources/<source_id>/reparse \
     -H "Authorization: Bearer $TOKEN"
   ```

### Case B — rate limit / robots.txt

1. Lower `sources.rate_limit_seconds` (or the per-domain cooldown).
2. Confirm `robots.txt` allows the path (the scraper caches it for 1h).
3. Reset the circuit breaker as above.

### Case C — transient network failure

The built-in Celery retry (1m → 2m → 4m, 3 attempts) usually self-heals. If
runs are still failing, follow Case A.

## Verification

- [ ] `GET /api/admin/sources/health` shows `healthy` again.
- [ ] `GET /api/admin/dlq` no longer grows.
- [ ] New jobs appear for the source (search or admin stats).
- [ ] Data quality dashboard shows the source's completeness recovering.
