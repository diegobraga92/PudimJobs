# ADR 005: Scraping Resilience Patterns

## Status

Accepted (2026-08-08)

## Context

The scraping engine hits third-party websites whose behaviour is outside our
control. Failures must not cascade, targets must not be hammered, and
permanently-broken sources need to be paused and inspected. The plan calls for
circuit breakers, rate limiting, robots.txt compliance, user-agent rotation,
exponential-backoff retries, and a dead-letter queue.

## Decision

### Circuit breaker (Redis, per-source, auto-reset)

- Redis key `cb:{source_id}` holds a consecutive-failure counter.
- Each failure increments it (with a 1h TTL); ≥5 failures = **open**.
- While open, the source's scrape is skipped (`scrape_runs.status = skipped`).
- A successful scrape resets the counter. The TTL provides automatic
  half-open recovery after an hour.
- Rationale: Redis is already the broker/backend, giving shared state across
  worker processes without adding a service.

### Rate limiting (per-domain, Redis TTL)

- `sources.rate_limit_seconds` (default 30) is the per-source cooldown.
- The task marks the domain in Redis (`rate:{domain}`) before fetching and
  sleeps for the remaining TTL if recently fetched.
- This serialises scrape bursts across sources that share a domain.

### robots.txt compliance

- Fetched once per domain, cached in-process for 1h; `Disallow` rules are
  matched against the request path. Best-effort: a failed robots fetch
  defaults to allowed.

### User-agent rotation

- A configured pool of realistic browser UAs (env `user_agents`); each
  request picks one at random. Proxy support is documented as a future
  enhancement (not implemented in Phase 2).

### Retry with exponential backoff

- Celery `autoretry_for=(Exception,)`, `max_retries=3`,
  `retry_backoff=True` (1m → 2m → 4m, capped at 10m).
- `CircuitBreakerOpenError` and `ValueError` (unknown source) are excluded —
  they should not retry.

### Dead-letter safety net

- The `celery` queue is declared with `x-dead-letter-exchange` →
  `pudimjobs.dlx`; rejected/lost tasks land there.
- The durable `scrape_runs` failed rows are the primary reprocessing queue
  (see ADR 004); the broker DLX is the crash safety net.

## Consequences

### Positive

- Failure isolation: one broken source never blocks others.
- Ethical scraping: rate limits + robots.txt respect.
- Ops visibility: health state (`healthy/degraded/failing`) + failed runs
  drive the admin dashboard.

### Negative / Risks

- Redis is a new hard dependency for the workers (acceptable — already
  required as broker/backend).
- In-process robots cache is per-worker (not shared); fine at Phase 2 scale,
  a Redis-backed cache is a future refinement.
- Exponential backoff means recovery latency can reach minutes for
  pathological sources.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Process-local circuit breaker | State lost on restart; not shared across workers |
| Naive fixed-interval scraping | Ignores domain cooldowns; risks bans |
| Playwright/headless for all sites | Overkill for feed/static pages; per-site opt-in later |
