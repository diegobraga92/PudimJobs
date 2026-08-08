# ADR 004: Reprocessing Strategy

## Status

Accepted (2026-08-08)

## Context

Scraping is inherently unreliable: sites change their HTML, feeds go stale,
and network errors happen. The product requires an operational story for:

- Inspecting failed scrapes ("the DLQ"),
- Replaying them after a fix,
- Re-parsing stored raw HTML after a parser improvement.

## Decision

### Store raw HTML with every job

`jobs.raw_html` holds the exact markup from which a job was parsed. This makes
reparsing possible without re-fetching — the HTML a site served weeks ago may
no longer exist.

### Durable failed-run log as the reprocessing queue

Every scrape attempt records a `scrape_runs` row (source_id, status,
new_jobs, error, started_at, finished_at). Failed runs are the reprocessing
queue:

- `GET /api/admin/dlq` lists failed runs (with the error message).
- `POST /api/admin/dlq/{run_id}/replay` re-enqueues the source's scrape.
- `POST /api/admin/sources/{id}/reparse` re-runs the parser over stored
  `raw_html` and updates jobs in place.

A DB-backed log is chosen over consuming RabbitMQ's DLQ directly because it
is queryable, auditable, and survives broker restarts; the broker's DLX is
still configured as a safety net for crashed/lost tasks.

### Audit trail

Replay, reparse, and manual-scrape actions write to `audit_logs` with
`entity_type = "reprocessing"`, recording who performed them (Phase 6 will
surface this in an admin dashboard).

## Consequences

### Positive

- Failed work is never lost; the pipeline is recoverable.
- Reparsing improves data quality retroactively after parser changes.
- Everything is auditable and testable.

### Negative / Risks

- `raw_html` grows storage; retention/capacity planning is deferred to
  Phase 8 but the column is already optional (NULL for manually-added jobs).
- Replay re-runs the whole source (not a single job); per-job replay is a
  future refinement.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Consume RabbitMQ DLQ directly in the admin API | Not queryable/auditable; messages are transient |
| Re-fetch HTML instead of storing it | Source may have changed or removed the page |
| Per-job granularity from the start | Extra complexity with no Phase 2 consumer demand |
