# Decisions

Significant engineering decisions, one row each: what we chose, what we chose it
over, and why. Dates and full context live in git history.

| # | Decision | Chosen over | Why |
|---|----------|-------------|-----|
| 001 | Python 3.12 + FastAPI | Django, Flask, Node.js, Go | Async-native; best data/NLP ecosystem (spaCy, BeautifulSoup, httpx) |
| 002 | UUID PKs, JSONB CV, string enums (`native_enum=False`) | auto-increment IDs, native PG enums, normalized CV tables | No sequence coordination across async workers; safe Alembic migrations; snapshot-able, versionable CV |
| 003 | Versioned JSON events on a topic exchange | Avro/Protobuf + schema registry | Lighter infra; additive-only versioning is enough at this scale |
| 004 | DB-backed DLQ (`scrape_runs`) + normalized extract only | consuming RabbitMQ DLQ directly; storing raw HTML | Queryable, auditable, survives broker restarts; avoids copyright/ToS and storage exposure |
| 005 | Redis circuit breaker + per-domain rate limit | process-local state | Shared across workers, survives restarts, auto-resets by TTL |
| 006 | Rule-based tailoring with an optional LLM layer | LLM-only | Deterministic and free by default; the LLM is a feature-flagged polish layer |
| 007 | Dedicated RabbitMQ consumer for matching | chaining `match_job` inside the scrape task | Broker buffers `job.new`; one event feeds many consumers |
| 008 | Dedicated `scrape_quality` table + multi-pass normalization | quality columns on `jobs` | Independent lifecycle; re-assessment is an upsert |
| 009 | PostgreSQL full-text search | Elasticsearch/OpenSearch, ILIKE | $0 extra infra, sub-ms at 10⁵ rows; ES only pays off beyond 10⁶ |
| 010 | Pluggable discovery providers (ATS feeds + search APIs) | reusing `aggregator` adapters | Discovery is cross-domain and two-stage; search keys are secrets |
| 011 | Server-side CV import (deterministic parse + optional LLM) | LLM-only, browser-side parsing | Zero-config baseline; review-before-save matches every CV path |
| 012 | React Native via Expo (SDK 57) | bare RN CLI, Flutter, PWA | Iteration speed; reuses web TS types and the generated i18n dictionary |
| 013 | Hybrid ATS scoring + `ats`-safe PDF template | LLM-only scoring, third-party ATS API | Deterministic zero-config baseline; the LLM review never blocks the score |
| 014 | `prep_tasks` table + `lessons_learned` column | separate retrospective entity, calendar integration | One table and one column cover the plan/learn loop; nothing new to run |
| 015 | Per-application CV workspace | tailoring from `/cv` or the job page | The CV is sent *with* an application; the artifact and its ATS check belong next to the job, and tailoring happens once so the artifact is always linked |
| 016 | Tailored CVs as self-contained `generated_cvs` artifacts | non-current `master_cv` versions | Master CV history stays clean, each artifact carries its own content, and `rule`/`llm` variants are scored by the same scorer |
| 017 | On-demand DOCX export via `python-docx` | storing a second artifact, HTML→DOCX conversion, new dependencies (pandoc/LibreOffice), ODT | `python-docx` is already a dependency for CV *import*; rendering from the stored `structured_json` at download time means one canonical stored PDF, no migration, an editable copy that tracks the latest edit, and real Word styles (single column, `List Bullet`) that ATS parsers read |
| 018 | `manual` source type (watchlist) + in-app re-check reminders | pretending to scrape login-walled boards, cookie auth, dropping those boards entirely | The engine cannot reach authenticated/anti-bot boards by design (see `scraping.md`); a hand-checked source keeps them tracked with cadence in `config` (no migration) and the sweep only reminds — it never fetches. The cadence contract is published once (`GET /api/sources/manual-metadata`) and validated (1–365 → 422); clients must **merge** `config` on update so engine-managed `next_check_at`/`reminded_at` survive |
| 019 | One shared `AppModalComponent` (fixed-overlay dialog) for transient forms | per-page inline expanding panels; a routed create/edit page per form | Create/edit forms used to render inline above the list (`showForm` + `<form class="panel form">`), pushing content down on Sources, Jobs, Alerts and Prep tasks. The modal reuses the global `.modal-backdrop`/`.modal` styles and the confirm-dialog conventions (backdrop click, Escape, `role="dialog"`), keeps the list in context, and collapses four copies of the pattern into one primitive. Full-page editors (CV editor, application detail) stay routed because they are destinations, not transient edits |
| 020 | Skills-section parsing splits on real separators only, and strips group labels | splitting on single whitespace and `/`; treating the CV's own `Group:` labels as a second grouping source | A label prefix (`Frameworks:`, `Cloud & DevOps:`) and multi-word names (`Apache Thrift`, `Test-Driven Development`, `CI/CD`) are both natural content for this section, so whitespace was never a delimiter: it shredded the names *and* the labels into fragments (`Frameworks`, `Apache`, `CI`, `CD`) that no taxonomy lookup could place, which is what piled into `Additional`. Splitting on commas/semicolons/pipes/bullets/2+ spaces — never a single space or `/` — plus stripping a known label prefix fixes it at the source, keeps the taxonomy the single source of grouping, and restores multi-word entries to `match_skills`. A label left alone on its line inside the block stays in the section instead of being read as the spoken-languages heading. Taxonomy entries shorter than the 3-char matching floor (`qt`) group but never match a JD |

| 021 | CV header renders as one flowing contact line at 8pt | keeping the "details" line + "links" line split; a smaller name; a narrower font family for the header alone; tighter page margins | The two-line header existed only because each field was unbreakable and adjacent fields offered no break, so one line could only overflow the page edge or be pre-split. Making the separator itself the break opportunity removes that trade-off: the block packs greedily onto one line and wraps *between* fields when it has to, never mid-token and never past the margin. 8pt is the measured size at which a real five-field header (email, phone, location, two links — 109 characters) fits DejaVu Sans inside the 17.4cm A4 text block: 472.9pt of the 493.2pt available, where the previous 9.5pt wrapped onto a second line (the ATS template, at its wider 11pt, needed ~639pt of 487.6pt). DejaVu's large x-height keeps 8pt legible, and it needs no font the render host may lack. Both templates, the DOCX (now on the same A4/1.8cm page box, since Letter's 432pt is too narrow) and the editor preview follow the same rule; resetting the UA's 8px `body` margin, which had silently narrowed the content box to 16.98cm, is part of the same fix |

## Notes

- **Datastores** — PostgreSQL is the only database; Redis is the Celery result
  backend, rate-limit store and circuit-breaker store; RabbitMQ is the event
  broker. Every choice above is reversible behind `DATABASE_URL`/`REDIS_URL`/
  `CELERY_BROKER_URL`.
- **Tailoring (006/013/016)** — the deterministic engine always runs and always
  produces an artifact. The LLM rewrite is an opt-in *second* variant (enable the
  LLM in Admin → LLM with a stored API key); both variants are scored by the
  same deterministic ATS scorer so they can be compared, and a failure degrades
  to the rule variant. No tailor run ever creates a `master_cv` version.
- **Connection pooling** — sessions use `NullPool` (a fresh connection per
  session). Correct for short-lived worker tasks; switch to
  `AsyncAdaptedQueuePool` (`pool_size=10`, `max_overflow=20`) above ~1k req/s.
- **ATS scoring weights** — skills 40%, keywords 15%, completeness 20%,
  readability 25%; an LLM review is blended in at 30% when configured and never
  blocks the deterministic score.

## Event schema (ADR 003)

`job.new` events are JSON on the durable topic exchange `pudimjobs.events`, with
version-scoped routing keys (`job.new.v1`, `job.new.v2`, …) and a `version`
integer in every payload. Schemas live in `api/events/` so the API and workers
share them.

**Compatibility contract**

1. Additive only — a new field MUST be optional with a sensible default
   (`None`, `False`, `[]`); older consumers must still deserialize it.
2. Deprecation window — a deprecated field keeps its default for two schema
   versions before removal.
3. Version bump — any non-additive change is a new `version`, never an in-place
   edit. Consumers bind with `job.new.#` and check `version` before parsing.

**Versions**

| Version | Fields |
|---------|--------|
| v1 | `version`, `event_id`, `job_id`, `source_id`, `title`, `company`, `url`, `posted_date`, `tags`, `timestamp` |
| v2 (planned) | adds `salary_range: str \| None = None`, `remote: bool \| None = None` |
