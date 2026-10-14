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
