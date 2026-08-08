# ADR 007: Matching and Alerting

## Status

Accepted (2026-08-08)

## Context

Users want to be notified when new jobs matching their saved criteria arrive.
The scraping engine already publishes versioned `job.new` events to RabbitMQ
(Phase 2, ADR 003). We need an event-driven matching engine plus notification
delivery (in-app and email) with observable delivery status.

## Decision

### Event-driven matching via a dedicated RabbitMQ consumer

- A durable queue `matching.job.new` is bound to the `pudimjobs.events` topic
  exchange with routing key `job.new.#` — the broker buffers events until a
  consumer is up (no events are lost while the consumer restarts).
- `workers/consume_events.py` is a long-running process (separate service in
  docker-compose) that reads events and enqueues the `match_job` Celery task
  per event. The task does the heavy lifting (DB queries, email) so the
  consumer stays cheap and Celery provides retries/backpressure.

### Saved-search model (`alert_rules`)

Each rule is owned by a user and holds: keywords, companies, tags,
`remote_only`, `min_years_experience`, delivery `channels`, and an `active`
toggle. The matching engine evaluates every active rule for the job's owner.

### Delivery + observability

- In-app notifications are stored in the `notifications` table (channel
  `in_app`) and exposed via the API (list, mark-read).
- Email is sent via SMTP (`app/services/email.py`); Mailpit is used as the
  local dev SMTP server. Every notification row records `status`
  (created/sent/failed) and an error message — this is the delivery
  observability SLO input (99% delivered within 5 min, Phase 5 dashboards).
- Email failures are non-fatal: the matching task marks the notification
  `failed` and continues; in-app delivery is unaffected.

### Why a separate consumer vs direct chaining

Chaining `match_job` directly inside the scrape task couples the pipeline and
loses the broker buffer. The consumer approach:
- survives worker/scrape downtime (queued events),
- keeps the scrape task focused on ingestion,
- demonstrates the intended event-driven architecture for future consumers
  (data-quality workers in Phase 5).

## Consequences

### Positive

- Reliable, observable delivery with a durable event queue.
- Matching logic is a pure, unit-testable function (`job_matches_rule`).
- In-app + email channels with graceful degradation.

### Negative / Risks

- One more long-running process to operate (the consumer).
- Keyword matching is substring-based (case-insensitive); a semantic matcher
  is a future enhancement.
- No digest batching yet — every match sends immediately (user preference
  frequency is a Phase-5/6 refinement).

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Chain matching inside the scrape task | Loses broker buffering; couples ingestion to alerting |
| Poll the jobs table periodically | Duplicates the event bus we already have |
| Firebase push as primary channel | Deferred (optional per plan); SMTP + in-app cover the MVP |
