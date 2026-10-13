# ADR 015: A Per-Application Workspace for the Tailored CV and its ATS Check

## Status

Accepted (2026-10-13)

## Context

Two features that were built independently ended up fighting for the same page.

`/cv` started as the master CV editor (ADR 011) and grew a "Version history"
rail, then a tailored-CV list (ADR 006) and finally the ATS check (ADR 013).
By then the page was labelled *Master CV* but hosted three different ideas:

1. the master document itself (the only thing that is genuinely global),
2. `n` tailored CVs, each belonging to a specific **job**, and
3. an ATS score, whose whole point is being computed **against a job**.

The result was a page where the user had to re-select "which job am I checking
against?" every time, where loading a tailored CV and pressing *Save* silently
created a new *master* version, and where the tailored list was a flat
cross-application dump with no link back to the application it was generated for.

Meanwhile the per-application side was already half-built and unused:
`Application.cv_version` (FK → `master_cv`, present since migration `0001`) was
never written nor displayed, and `ApplicationDetail` (an `ApplicationResponse`
plus `job_description`) was defined in `app/schemas/application.py` but imported
nowhere. So the data model already said "an application knows which CV version it
was sent with"; only the wiring and the UI were missing.

Constraints: no new infrastructure, no schema migration (the FK exists), additive
API changes, and parity between the Angular web client and the React Native
client.

## Decision

**1. The tailored CV and its ATS check move to the application.**
`GET /api/applications/{id}` returns `ApplicationDetail` (ownership-checked,
joining `Job` for `job_description`), which resurrects the dead schema. The web
client gets a new workspace at `/applications/:id` holding:

- the pipeline fields that used to live in the kanban modal (status, applied
  date, notes, retrospective),
- the job description (so the ATS verdict has visible context), and
- a `CvPanel` — the tailored CV for that job, its preview, its ATS score, and
  the tailor / re-tailor / download / delete actions.

`/cv` slims back to the single source of truth: edit, import, preview, export,
version history. The kanban board becomes a navigation surface (cards open the
workspace) instead of a detail modal.

**2. `Application.cv_version` is wired end-to-end.** `POST /api/jobs/{id}/tailor`
accepts an optional `application_id`, which is threaded through
`enqueue_tailor` → `tailor_cv_task` → `_run_tailor`, and the task points the
application at the produced version on **both** the fresh-artifact and the
idempotent-reuse branches. The write is deliberately best-effort and guarded: a
missing, foreign, or job-mismatched id is skipped with a warning log, so a stale
Celery message can never cross-link another user's pipeline. No migration: the
column is already in the initial schema.

**3. `GET /api/cv/generated` takes an optional `job_id`** so the panel can load
exactly the versions relevant to one application instead of filtering a global
list client-side.

**4. Async is acknowledged in the UI.** Tailoring is 202 + Celery by design
(ADR 004/006), so enqueueing flips the panel into an explicit *pending* state
with a *Refresh* action rather than pretending the artifact exists. No
websocket/SSE polling: the request volumes do not justify it, and the existing
job-detail screen already teaches the "queued, refresh in a moment" pattern.

**5. Editing a tailored CV still happens in one place.** The panel's *Edit in CV
editor* action navigates to `/cv?generated=<id>`, which loads that version into
the master editor with a message stating that saving produces a **new master
version**. That removes the old ambiguity (a tailored CV load followed by a
silent master-version save) without duplicating a 500-line form.

**6. Mobile parity** (`src/navigation/ApplicationsStack.tsx`,
`src/screens/ApplicationDetailScreen.tsx`, `src/components/cv/CvPanel.tsx`): an
Applications stack with a workspace screen, the same `cv_version` badge, the
tailored-CV list scoped by job, and the ATS report — mirroring the web.

## Consequences

### Positive

- **One home per concept.** Master document on `/cv`; "the CV I sent, and how it
  scores" attached to the application it belongs to. The ATS check no longer
  needs a job picker because the job is implicit.
- **"What did I send?" is answerable** — `cv_version` is written by the tailor
  task and surfaced as a `sent` badge next to the version it points at.
- **No migration and an additive API surface** — the FK pre-existed; the new
  endpoint and the optional query parameter are backwards compatible (the tailor
  payload field is optional, `GET /api/cv/generated` without `job_id` is
  unchanged).
- **Fewer ways to be confused.** The kanban modal is gone, so notes/retrospective
  are edited in one place, and a tailored CV can no longer be mistaken for the
  master document.

### Negative / accepted trade-offs

- **Cross-application browsing is gone.** There is no longer one list of every
  tailored CV; you get there through the application (or by job). Judged
  acceptable — the per-job list is what the user actually needs, and
  `GET /api/cv/generated` still returns everything when unscoped.
- **A manual refresh step.** Because tailoring stays fire-and-forget, the panel
  can show "pending" until the user refreshes. A poll was rejected as noise; the
  state is explicit rather than silently empty.
- **`Application.job_id` is not unique**, so an application workspace assumes one
  application per job when it lists tailored CVs for that `job_id`. This is a
  pre-existing data-model assumption, now made visible; the API filters by
  `job_id` because that is what `GeneratedCV` records.
- **The panel re-scores on demand.** The report is cached on the generated CV
  (ADR 013) and shown from that cache, but a user who edits and re-tailors sees
  the stale score until they ask again.
- **Two clients to keep aligned.** As with every UI-facing decision since
  ADR 012, the workspace has to be mirrored in the Angular and React Native
  clients.

## Alternatives Not Selected

| Option | Reason for Rejection |
| ------ | -------------------- |
| Keep everything on `/cv`, split into tabs | The broken mental model (master vs per-job) survives; the ATS check still needs a job picker |
| A separate top-level `/tailored-cvs` page | Splits per-job data (JD, notes, pipeline state) from the CV again — the problem this ADR fixes |
| A dedicated `/jobs/:id/cv` page instead of the application workspace | The CV was sent *with an application*; the application is the unit the user reasons about, and it already owns `cv_version` |
| Tailor synchronously and return the artifact | Turns a slow render plus an optional LLM call into an HTTP request and discards the worker's retry/idempotency behaviour |
| Poll or stream the panel after enqueueing | Extra load and flaky UX for a task that typically takes seconds; an explicit Refresh matches the existing pattern |
| Show the linked CV on the kanban card | The card is a triage/navigation surface; the workspace is where the CV and ATS detail live |

## References

- `app/routers/applications.py` (`GET /api/applications/{id}`),
  `app/schemas/application.py` (`ApplicationDetail`),
  `app/routers/cv.py` (`?job_id=`), `app/routers/jobs.py` (tailor payload),
  `workers/tasks/tailor.py` (`_link_application`)
- `app/broker.py` (`enqueue_tailor`), `app/models/application.py`
  (`cv_version`, migration `0001`)
- `frontend/src/app/components/application-detail/`,
  `frontend/src/app/shared/cv-panel/`, `frontend/src/app/shared/ats-report/`
- `mobile/src/navigation/ApplicationsStack.tsx`,
  `mobile/src/screens/ApplicationDetailScreen.tsx`,
  `mobile/src/components/cv/CvPanel.tsx`
- ADR 002 (data model), ADR 006 (rule-based tailoring), ADR 013 (ATS scoring),
  ADR 014 (prep tasks and retrospectives)
