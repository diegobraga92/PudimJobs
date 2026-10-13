# PudimJobs — Development Plan

Companion to the [README](../README.md): what was built, in what order, and
where to find it. Every checkbox below maps to code, a migration, or a doc in
this repository — clone it and grep for the named file to verify.

**Status: Phases 0–8 complete.** 294 backend tests + 24 Angular specs pass;
`ruff check`, `ruff format --check`, `ng build` and `ng test` are clean.

How this plan is organised:

| Phase | Theme | Proof |
|-------|-------|-------|
| [0](#phase-0--project-skeleton-infra--cicd) | Skeleton, infra, CI/CD | `docker-compose.yml`, `.github/workflows/` |
| [1](#phase-1--core-data-models--crud) | Data models & CRUD | `backend/app/models/`, `backend/app/routers/` |
| [2](#phase-2--scraping-engine--reprocessing) | Scraping engine & reprocessing | `scrapers/`, `workers/tasks/` |
| [3](#phase-3--jd-parsing--cv-tailoring) | JD parsing & CV tailoring | `app/services/jd_parser.py`, `cv_tailor.py` |
| [4](#phase-4--matching-alerts--notifications) | Matching, alerts, notifications | `app/services/matcher.py`, `workers/consume_events.py` |
| [5](#phase-5--observability-data-quality--search) | Observability, quality, search | `app/services/quality.py`, `infra/` |
| [6](#phase-6--security-hardening) | Security hardening | `docs/stride-threat-model.md`, slowapi limits |
| [7](#phase-7--chaos-engineering--postmortem) | Chaos & incident response | `scripts/chaos/`, `docs/runbooks/` |
| [8](#phase-8--cost-analysis--portfolio-polish) | Cost analysis & portfolio polish | `docs/cost-estimate.md`, ADRs 011–015 |

---

## Phase 0 — Project skeleton, infra & CI/CD

- [x] Repository layout: `backend/`, `frontend/`, `mobile/`, `scrapers/`,
      `workers/`, `api/`, `infra/`, `scripts/`, `docs/`
- [x] `docker-compose.yml` with PostgreSQL 16, RabbitMQ (management UI), Redis,
      Mailpit, Prometheus, Grafana, Jaeger, backend and frontend
- [x] Host ports centralised in `.env` (`PJ_*_PORT`) — see [`.env.example`](../.env.example)
- [x] `Makefile` shortcuts (`make up|down|logs|test|lint`)
- [x] Three CI pipelines: `.github/workflows/backend-ci.yml` (ruff, pip-audit,
      pytest, Docker build, Trivy), `frontend-ci.yml` (`ng test`, `ng build`),
      `mobile-ci.yml` (typecheck, lint, jest, `expo export`)
- [x] Terraform skeleton for production (`infra/main.tf`, `infra/modules/`)

## Phase 1 — Core data models & CRUD

- [x] Async SQLAlchemy 2.0 + Alembic; **18 migrations**, single linear head
      (`alembic upgrade head` is the only setup step)
- [x] Models: `users`, `sources`, `jobs`, `master_cv`, `generated_cvs`,
      `applications`, `alert_rules`, `notifications`, `scrape_runs`,
      `scrape_quality`, `audit_log`, `prep_tasks`
- [x] UUID primary keys, JSONB for CV content, string enums
      (`native_enum=False`) — ADR 002
- [x] JWT auth (`POST /api/auth/login`, `GET /api/auth/me`) with bcrypt; every
      resource query is scoped to `user_id`
- [x] CRUD routers: `sources`, `jobs` (manual add + search/filter/hide),
      `cv` (versioned master CV), `applications` (pipeline), `prep_tasks`
- [x] Idempotent seed (`python -m app.seed`) for the dev admin user
- [x] Audit logging for CV, application, prep-task and admin mutations

## Phase 2 — Scraping engine & reprocessing

- [x] Celery app + worker + Beat (`workers/celery_app.py`, `workers/beat_schedule.py`)
- [x] Pluggable scrapers (`scrapers/`): career page (schema.org/JSON-LD),
      RSS, aggregator base, discovery providers (Ashby, Greenhouse, Lever,
      Workable + Google CSE, Bing, Brave, SerpApi, Bright Data) — ADR 010
- [x] `scrape_source` task: circuit breaker → rate limit → fetch → parse →
      normalize → dedup → publish `job.new` → update source health
- [x] Resilience: Redis circuit breaker (5 failures → 1 h pause), per-domain
      rate limiting, robots.txt checks, UA rotation, DLX + retries — ADR 005
- [x] Durable failed-run log (`scrape_runs`) with admin list/replay — ADR 004
- [x] Versioned `job.new.v1` events published to RabbitMQ (`api/events/`)

## Phase 3 — JD parsing & CV tailoring

- [x] spaCy JD parser → `jobs.parsed_jd` (skills, years, education, keywords)
- [x] Curated skills taxonomy + `match_skills` relevance scoring
      (`app/data/skills_taxonomy.json`, `app/services/skill_matcher.py`)
- [x] Deterministic tailoring (`cv_tailor.tailor_cv`) with a summary that leads
      with the JD-matched strengths and an explicit `used_fallback` signal —
      ADR 006
- [x] Optional full-LLM rewrite kept as a *second* variant
      (`TAILORING_LLM_VARIANT_ENABLED`), schema-validated and degradation-safe —
      ADR 016
- [x] PDF generation via Jinja2 + weasyprint; tailored CVs persisted as
      self-contained `generated_cvs` artifacts (migration `0019`) — ADR 016
- [x] CV import (`POST /api/cv/parse`): PDF, DOCX and ODT → structured
      `CVStructure` (rule-based parser, optional LLM upgrade) — ADR 011
- [x] Rich CV structure: contact block (`full_name`, `email`, `phone`,
      `location`, `links`), `certifications`, `languages`
- [x] ATS scoring (`POST /api/cv/ats-score`): weighted heuristic baseline +
      optional 30 % LLM blend, cached on `generated_cvs.ats_score/.ats_report`
      (migration `0018`) — ADR 013
- [x] ATS-safe PDF template (`template=ats`) alongside `classic` — ADR 013


## Phase 4 — Matching, alerts & notifications

- [x] Alert rules (saved searches): keywords, companies, tags, remote-only,
      min years, channels, active toggle — `/api/alert-rules` + web/Alerts UI
- [x] Dedicated RabbitMQ consumer (`workers/consume_events.py`) turning
      `job.new` into `match_job` — ADR 007
- [x] `match_job` evaluates a job against every active rule of its owner
      (`app/services/matcher.py`)
- [x] Delivery: in-app notifications + SMTP email (Mailpit locally, Jinja2
      template) with per-notification delivery status
- [x] API: `/api/notifications` (list, mark-read, read-all)
- [x] Frontend: Alerts page (CRUD + pause/resume) and Notifications page with
      an unread badge in the sidebar

## Phase 5 — Observability, data quality & search

- [x] PostgreSQL Full-Text Search: generated `search_vector` + GIN index,
      `plainto_tsquery`/`ts_rank` with per-result `score` (migration `0006`) —
      ADR 009; Elasticsearch comparison in `docs/elasticsearch-comparison.md`
- [x] Data quality pipeline (`app/services/quality.py`): normalization mappings,
      completeness scoring, cross-source fuzzy duplicate detection → dedicated
      `scrape_quality` table (migration `0007`) — ADR 008
- [x] OpenTelemetry instrumentation (FastAPI + Celery) → Jaeger; trace IDs in
      structured logs (`app/logging_config.py`, `workers/metrics.py`)
- [x] Prometheus metrics (RED + scraper) and provisioned Grafana dashboards
      (`infra/prometheus/`, `infra/grafana/`)
- [x] Admin dashboard: stats, source health, DLQ with replay, quality overview,
      audit log with expandable diffs
- [x] Load test script + real `EXPLAIN ANALYZE` numbers
      (`scripts/load_test.py`, `docs/database-performance.md`)

## Phase 6 — Security hardening

- [x] STRIDE threat model for the API and scrapers (`docs/stride-threat-model.md`)
- [x] Rate limiting with slowapi (Redis-backed): login 5/min, authenticated API
      120/min, ATS scoring and PDF export included
- [x] Strict per-user ownership checks on every resource (404, never 403 leaks)
- [x] Audit investigation API (`GET /api/admin/audit` + `/audit/actions`) and
      the admin Audit Log tab
- [x] CI security gates: `pip-audit` + Trivy image scan
- [x] Secrets rotation guide (`docs/secrets-rotation.md`)

## Phase 7 — Chaos engineering & postmortem

- [x] Chaos scripts (`scripts/chaos/`): kill RabbitMQ, break scraper HTML,
      exhaust worker memory, break a normalization rule
- [x] Blameless postmortem with corrective actions
      (`docs/postmortems/001-scraper-outage-data-quality.md`)
- [x] Runbooks: scraper failure, RabbitMQ backlog, data-quality degradation,
      database failover (`docs/runbooks/`)
- [x] SLOs and error budgets (`docs/slo.md`)

## Phase 8 — Cost analysis & portfolio polish

- [x] Cost estimate and capacity plan (`docs/cost-estimate.md`,
      `docs/capacity-plan.md`)
- [x] C4 architecture diagram (`docs/architecture-c4.puml`)
- [x] Tradeoff index for every ADR (`docs/tradeoffs.md`)
- [x] React Native (Expo) mobile client mirroring the web app (ADR 012)
- [x] CV import/parsing (ADR 011), ATS scoring + ATS-safe template (ADR 013)
- [x] Application retrospectives and interview prep tasks (ADR 014)
- [x] Per-application workspace: tailored CV + ATS move to `/applications/:id`,
      `/cv` is master-only and the job page links to the workspace instead of
      offering a second, unlinked tailor action (ADR 015)
- [x] Tailored CVs as first-class artifacts: dual `rule`/`llm` variants scored
      by the same deterministic scorer, an artifact-level editor
      (`PUT /api/cv/generated/{id}`), `Application.generated_cv_id` and no
      master-CV version leak (migration `0019`) — ADR 016
- [x] This development plan, kept in sync with the README status table

### Demo walkthrough (recorded script)

The demo follows one job through the whole system, in this order:

1. **Scrape** — `make up`, open `http://SERVER_IP:9400`, add a source
   (career page or discovery provider) and trigger a scrape from the admin
   overview; watch new jobs appear with source health and scrape stats.
2. **Data quality** — admin → Quality: normalization fixes, completeness
   scores, cross-source duplicates for the freshly scraped jobs.
3. **Search** — Jobs page: keyword search, filters, tag chips (PostgreSQL FTS).
4. **Tailor + ATS** — open a job → *Parse now* → *Add to applications* → the job
   page now shows *Open workspace* (it has no tailor button of its own) → in the
   workspace press *Tailor CV for this job*, refresh the panel once the worker
   lands it, inspect the PDF preview and run the **ATS check** for that job
   (score, missing skills, recommendations). The master CV page is master-only:
   import an existing `PDF`/`DOCX`/`ODT` CV there to show the parser pre-filling
   the editor, and use *Edit in CV editor* from the panel to hand-edit a tailored
   version (saved as a new master version).
5. **Alert + notification** — create an alert rule matching the job, add a
   matching job, show the in-app notification (and the Mailpit email).
6. **Pipeline + prep** — *Add to applications*, drag the card
   saved → applied → interview, add prep tasks against that job/application,
   then write a retrospective: it shows up in *Lessons learned*.
7. **Resilience** — `python scripts/chaos/break_scraper_html.py`: the source's
   circuit breaker trips, the run lands in the dead-letter queue and can be
   replayed from the admin DLQ tab (`scripts/chaos/README.md` has the rest).

## Test & quality gates

| Gate | Command | Current result |
|------|---------|----------------|
| Backend lint | `cd backend && ruff check .` | clean |
| Backend format | `cd backend && ruff format --check .` | clean (107 files) |
| Backend tests | `cd backend && pytest` | 311 passed |
| Migration graph | `alembic heads` | single head `0018` |
| Frontend tests | `cd frontend && ng test --watch=false --browsers=ChromeHeadless` | 43 passed |
| Frontend build | `cd frontend && ng build` | clean (no budget warnings) |
| Mobile | `cd mobile && npm run typecheck && npm run lint && npm test` | see `mobile-ci.yml` |

Integration tests need PostgreSQL (`TEST_DATABASE_URL`, default port 5433) and
Redis (`REDIS_URL`, default 6380) test services; they skip automatically when
neither is reachable.

## Known gaps & follow-ups

Deliberately out of scope so far — kept here instead of hidden:

- **Mobile parity for the newest features**: the Expo client has no ATS-safe
  template selector, no `.odt` document-picker filter, and no prep-tasks/lessons
  screens yet (the API is ready for all three). The application workspace and
  the tailored-CV/ATS panel *are* implemented (ADR 015, ADR 016).
- **ATS `job_title`** is folded into the keyword pool and recommendations; it
  does not feed the LLM prompt (the description does).
- **Prep tasks have no reminders**: `due_date` is a planning hint, not a
  scheduler — notifications remain reserved for job alerts (ADR 007).
- **`lessons_learned` is free text**, so it cannot be aggregated automatically.
- **Angular component-style budget** was raised from 4 kB to 6 kB (warning
  only; the error ceiling stays at 8 kB) because the CV editor and the
  application workspace (CV + ATS panels) are the largest component stylesheets
  in the app.

