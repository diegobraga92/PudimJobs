# ADR 014: Interview Prep Tasks and Application Retrospectives

## Status

Accepted (2026-10-13)

## Context

The pipeline (ADR 007) tracks where an application *is*, and alerting tells the
user what to apply to next. Two gaps remained on the "what do I actually do"
side of a job hunt:

1. **No planning surface.** Between "applied" and "offer" there is real work —
   research the company, rehearse a system-design round, prepare a story bank,
   confirm logistics. Those steps lived outside the product (notes apps,
   calendars) with no link back to the job or the application they belong to.
2. **No learning loop.** When an application ends — rejected, withdrawn, or an
   offer declined — the useful output is *why*. The user needed a place to
   record that briefly, and a way to read those notes back across applications
   instead of opening each one.

Constraints carried over from the rest of the project: user-scoped data with
ownership checks, no new infrastructure, no LLM dependency, migrations that are
additive and reversible, and full parity in the Angular web client (the
mobile client follows the same API).

## Decision

**1. A `prep_tasks` table (migration `0017`) with full CRUD** under
`/api/prep-tasks` (`app/routers/prep_tasks.py`, `app/models/prep_task.py`,
`app/schemas/prep_task.py`). Deliberately *no* service layer: the logic is a
thin query + ownership validation, so the router stays readable.

- Fields: `title` (required, ≤ 255), `category` (`technical`, `behavioral`,
  `research`, `logistics`, `other` — string enums persisted with
  `native_enum=False`), `status` (`pending`, `in_progress`, `done`),
  `due_date`, `notes`, and optional `job_id` / `application_id` links.
- A task with neither link is a general to-do; both links are ownership-checked
  before write (404 on someone else's row) and `job_id` cascades on job delete
  while `application_id` is set to `NULL` when an application is removed.
- List ordering is deliberate: unfinished work first (`pending` → `in_progress`
  → `done`), then nearest due date with undated tasks last, then newest first —
  expressed as SQL (`case` + `due_date IS NULL`) rather than sorted in Python.
- Every write that changes something is audit-logged (`entity_type="prep_task"`)
  with a before/after diff, matching the CV and application audit trail.

**2. Retrospectives live on the application, not in a new table.** An
`applications.lessons_learned` text column (migration `0016`) is written through
the existing `PUT /api/applications/{id}` handler, and read back across the
pipeline by `GET /api/applications/lessons`
(`app/schemas/application.py::LessonEntry`).

- The feed returns only applications whose `lessons_learned` is non-empty, joined
  with the job for display, ordered by `updated_at` descending.
- Keeping the note on the application avoids a second entity that would need its
  own lifecycle, and means the kanban detail modal is the single place to write
  it (no separate "add a lesson" flow).

**3. Both surfaces are first-class in the web client**: an "Interview prep"
workspace (`/prep-tasks`) with status chips, job filter, inline status cycling
and a create/edit form, and a "Lessons learned" workspace (`/lessons`) with
status/text filtering. The application detail modal edits notes *and*
`lessons_learned`.

## Consequences

### Positive

- **Actionable pipeline** — a job, its applications and its preparation steps
  are one graph; deleting a job cleans up its tasks automatically.
- **Zero new infrastructure** — one table, one JSON-free column, two endpoints;
  no worker, queue or LLM involvement.
- **Auditable** — prep-task mutations land in the same audit log the admin UI
  already exposes, alongside CV and application changes.
- **Cheap to read back** — the lessons feed is a single indexed query
  (`applications.user_id` + `updated_at`) instead of N per-application fetches.

### Negative / accepted trade-offs

- **`lessons_learned` is free text** — no structure means it cannot be
  aggregated automatically (e.g. "most common rejection reason"). Structured
  reasons were rejected as too heavy for a note the user writes in 30 seconds.
- **A prep task belongs to one user only** — no sharing or team boards; out of
  scope for a personal job tracker.
- **List ordering is server-side** — the UI cannot re-sort arbitrarily without a
  refetch; acceptable for the volumes involved (tens of tasks per user).
- **`due_date` has no time component or reminders** — due dates are planning
  hints, not a scheduling system; notifications remain reserved for job alerts
  (ADR 007).

## References

- Migration `0016` (`lessons_learned`), migration `0017` (`prep_tasks`)
- `app/routers/prep_tasks.py`, `app/routers/applications.py`
- `frontend/src/app/components/prep-tasks/`,
  `frontend/src/app/components/lessons/`
- ADR 002 (data model), ADR 007 (matching and alerting)
