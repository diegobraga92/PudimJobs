# ADR 004: Reprocessing Strategy

## Status

Accepted (2026-08-08)

## Context

Scraping is inherently unreliable: sites change their HTML, feeds go stale,
and network errors happen. The product requires an operational story for:

- Inspecting failed scrapes ("the DLQ"),
- Replaying them after a fix,
- Re-scraping a source after a parser improvement.

## Decision

### Normalized extract only — raw HTML is not retained

Only the normalized job fields (title, company, description, url, tags,
`external_id`) are stored. Full page markup is deliberately not retained:
storing third-party content raises copyright/ToS and storage concerns, and the
normalized extract is enough for reprocessing. Recovery after a parser fix is
therefore a re-scrape (the live page may have changed — an accepted tradeoff).

### Durable failed-run log as the reprocessing queue

Every scrape attempt records a `scrape_runs` row (source_id, status,
new_jobs, error, started_at, finished_at). Failed runs are the reprocessing
queue:

- `GET /api/admin/dlq` lists failed runs (with the error message).
- `POST /api/admin/dlq/{run_id}/replay` re-enqueues the source's scrape.

A DB-backed log is chosen over consuming RabbitMQ's DLQ directly because it
is queryable, auditable, and survives broker restarts; the broker's DLX is
still configured as a safety net for crashed/lost tasks.

### Audit trail

Replay and manual-scrape actions write to `audit_logs` with
`entity_type = "reprocessing"`, recording who performed them (Phase 6 will
surface this in an admin dashboard).

## Consequences

### Positive

- Failed work is never lost; the pipeline is recoverable.
- Reparsing improves data quality retroactively after parser changes.
- Everything is auditable and testable.

### Negative / Risks

- Re-scrape recovery only reflects the *current* state of a page: postings
  that were removed or rewritten after the failure cannot be recovered.
- Replay re-runs the whole source (not a single job); per-job replay is a
  future refinement.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Consume RabbitMQ DLQ directly in the admin API | Not queryable/auditable; messages are transient |
| Store raw HTML with every job | Copyright/ToS + storage; recovery is a re-scrape instead |
| Per-job granularity from the start | Extra complexity with no Phase 2 consumer demand |
