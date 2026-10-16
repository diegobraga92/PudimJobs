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
| 020 | Skills-section parsing splits on real separators only, and strips group labels | splitting on single whitespace and `/`; treating the CV's own `Group:` labels as a second grouping source | A label prefix (`Frameworks:`, `Cloud & DevOps:`) and multi-word names (`Apache Thrift`, `Test-Driven Development`, `CI/CD`) are both natural content for this section, so whitespace was never a delimiter: it shredded the names *and* the labels into fragments (`Frameworks`, `Apache`, `CI`, `CD`) that no taxonomy lookup could place, which is what piled into `Additional`. Splitting on commas/semicolons/pipes/bullets/2+ spaces — never a single space or `/` — plus stripping a known label prefix fixes it at the source, keeps the taxonomy the single source of grouping, and restores multi-word entries to `match_skills`. A label left alone on its line inside the block stays in the section instead of being read as the spoken-languages heading. Taxonomy entries shorter than the 3-char matching floor (`qt`) group but never match a JD. The label list is a fast path only, and a label glued to its values is fixed at the resolution step rather than by growing the list — see 022 |

| 021 | CV header renders as one flowing contact line at 8pt | keeping the "details" line + "links" line split; a smaller name; a narrower font family for the header alone; tighter page margins | The two-line header existed only because each field was unbreakable and adjacent fields offered no break, so one line could only overflow the page edge or be pre-split. Making the separator itself the break opportunity removes that trade-off: the block packs greedily onto one line and wraps *between* fields when it has to, never mid-token and never past the margin. 8pt is the measured size at which a real five-field header (email, phone, location, two links — 109 characters) fits DejaVu Sans inside the 17.4cm A4 text block: 472.9pt of the 493.2pt available, where the previous 9.5pt wrapped onto a second line (the ATS template, at its wider 11pt, needed ~639pt of 487.6pt). DejaVu's large x-height keeps 8pt legible, and it needs no font the render host may lack. Both templates, the DOCX (now on the same A4/1.8cm page box, since Letter's 432pt is too narrow) and the editor preview follow the same rule; resetting the UA's 8px `body` margin, which had silently narrowed the content box to 16.98cm, is part of the same fix |

| 022 | Skill labels are recognised by *shape*, and every entry resolves to its canonical skill(s) | extending the closed label word list; splitting entries on `/`; one skill per entry | The word list from 020 only knows the labels we anticipated, so a CV writing `Frameworks & Tools:`, `Databases & Analytics:` or `Systems & Tools:` kept its label glued to the first value on the line (`Frameworks & Tools: Qt`), which no taxonomy lookup can resolve; the label words that never got glued (`Additional`, `Methodologies`) then became skills, and the whole tail of the section rendered as one `Additional` line. A label is now recognised by shape — at most four words, no digits, and no word the taxonomy knows as a skill (that last rule is what keeps `AWS: EC2` and `CKA: Certified Kubernetes Administrator` intact) — with the word list kept as the fast path; *every* label on a line is stripped, because PDF extraction merges two labelled columns onto one line, and brackets are unwrapped only when balanced, so `Test-Driven Development (TDD)` keeps the acronym an ATS searches for. Entries then resolve through a ladder: exact/alias → all parts of a `/`-or-`&`-compound (`JavaScript/TypeScript`, `Protobuf/gRPC`) → the longest known name inside the entry (`Google BigQuery`, `Test-Driven Development (TDD)`), the entry itself when nothing matches. That puts compounds in their real groups instead of `Additional`, and lets `match_skills` credit a CV that spells the JD's skill as half of a compound. Two rules keep it honest: a compound whose parts disagree (`AWS/PostgreSQL`) still falls to `Additional` rather than being placed on a coin flip, and the CV's own spelling is never rewritten — the tailorer reorders its own entries instead of injecting a second copy of a matched skill |
| 023 | Bulk job cleanup by `created_at` age and/or source, preview-first, applications protected by default | deleting per job in the UI; filtering by `posted_date`; deleting every match without a preview; excluding tracked jobs server-side with no opt-in | The list is where the clutter shows up (a boarded source can add hundreds of rows), and the DB makes the stakes asymmetric: `applications.job_id` is `ON DELETE CASCADE`, so a careless cleanup silently destroys the pipeline history, while `generated_cvs.job_id` merely `SET NULL`. Age is matched on `created_at`, never the nullable `posted_date` that scraped rows often lack — an age filter there would silently spare whole sources. `POST /api/jobs/cleanup` therefore defaults to `dry_run`, returns `{matched, deleted, protected}` so the dialog can show exactly what will go before anything is removed, requires at least one criterion (an empty body would mean "delete everything"), and is audit-logged (`bulk_deleted`). Opting into `include_with_applications` is the one way a tracked job is deleted, because that is the one way an application disappears |
| 024 | PT-BR CV export translated on demand by the LLM, with section headings from a fixed catalog | storing a translated `pt-BR` artifact per CV; a second `language` column/migration; asking the LLM for the whole document including headings | Nothing is persisted: like DOCX (017), the translated copy is rendered at download time from the same `structured_json`, so no migration is needed and the copy can never go stale after an edit. Headings are *chrome*, not content — the same words on every CV in a language — so they come from `cv_labels` (deterministic, and the reason a translated CV never mixes "Experiência" with "Summary"); only free text goes through `cv_translator`, whose prompt pins the non-negotiables (employers, dates, degrees, numbers, tech names, links) and whose reply is re-validated through `CVStructure` and rejected when it empties a section the input had filled. English is the stored language and stays LLM-free; a non-default language with the LLM off is a 409 (never a silent English download) and a failed translation is a 502. The client cannot read admin settings, so `GET /api/cv/capabilities` publishes `{llm_enabled, export_languages}` and the UI greys PT-BR out before the user picks it |

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
- **Cleanup (023) & PT-BR export (024)** — bulk cleanup is *always* preview-first
  (`dry_run` defaults to `true`) and never removes a job that has an application
  unless the caller opts in, because the cascade would take the application with
  it. Translated exports are computed per request and never stored: the English
  PDF stays the one canonical artifact, the translated copy is rendered from the
  same structure, and a non-default language is refused with 409 rather than
  silently served in English.
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
