# PudimJobs — Job Application Tracker

> **A job hunting assistant** — scrapes job listings from multiple sources,
> enriches and deduplicates them, helps you tailor your CV to each job
> description, and tracks your applications from *saved* to *offer*.
>
> Flagship project for async pipelines, data engineering, search, and resilient
> external integrations.

## Who this is for

**Job seekers** — PudimJobs watches your target companies and feeds for you: new
postings are scraped, deduplicated, and matched against your saved searches
(alerts in-app and by email). Tailoring produces a job-specific CV PDF from your
master CV (from the application workspace), and the kanban pipeline tracks each
application from *saved* through *offer*.

**Engineers / interviewers** — this is a portfolio project showing how a small
team would build a production job board: an event-driven scraping pipeline with
circuit breakers and a dead-letter queue, a data-quality pipeline with
normalization and dashboards, relevance-ranked search, and versioned CV
generation. The reasoning lives in three docs:

- [`docs/decisions.md`](docs/decisions.md) — 16 ADRs + trade-off table + event-schema contract
- [`docs/operations.md`](docs/operations.md) — SLOs, capacity, cost, DB/search numbers, STRIDE, secrets, runbooks, postmortem
- [`docs/scraping.md`](docs/scraping.md) — source capability matrix, onboarding, coverage
- [`docs/architecture-c4.puml`](docs/architecture-c4.puml) — C4 container diagram

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | Python 3.12 + FastAPI | REST API, auth, CRUD, orchestration |
| **Workers** | Celery + RabbitMQ | Async scraping, JD parsing, CV tailoring, matching alerts |
| **Database** | PostgreSQL 16 (asyncpg / SQLAlchemy) | Sources, jobs, master CV, applications, audit log |
| **Cache / broker** | Redis | Celery result backend, rate limiting, circuit breakers |
| **Search** | PostgreSQL Full-Text Search | Keyword search over jobs (Elasticsearch tradeoff documented) |
| **Frontend** | Angular 17 + TypeScript | Source management, job search, CV editor, application pipeline |
| **Mobile** | React Native (Expo SDK 57, Android-first) | Mobile mirror of the web UI |
| **Observability** | OpenTelemetry → Jaeger, Prometheus, Grafana, structlog | Traces, metrics, structured logs, RED + data-quality dashboards |
| **Infrastructure** | Docker Compose (dev), Terraform + AWS (prod) | Local & cloud deployment |

```
┌─────────────┐      ┌──────────────┐      ┌───────────────────┐
│   Angular   │ ───▶ │    FastAPI   │ ───▶ │ PostgreSQL 16     │
│   frontend  │      │    backend   │      │ (sources, jobs…)  │
└─────────────┘      └──────┬───────┘      └───────────────────┘
                            │  /health, /metrics
                     ┌──────▼────────┐      ┌───────────────────┐
                     │ RabbitMQ      │ ◀─── │ Celery workers    │
                     │ (event bus)   │      │ (scrapers, NLP)   │
                     └───────────────┘      └───────────────────┘
```

## Project structure

```
PudimJobs/
├── backend/          # FastAPI application (Python 3.12)
│   └── app/          #   config, database, models, routers, services, data, templates
├── frontend/         # Angular 17 application (standalone components, PWA)
│   └── src/app/      #   components, services, routing, guards, interceptors
├── mobile/           # React Native (Android-first) client — mirrors the web UI
│   └── src/          #   screens, components, api, hooks, theme, i18n, navigation
├── scrapers/         # Scraper implementations & adapters (per-source)
├── workers/          # Celery app, tasks, event consumer, metrics
├── api/              # Event schemas/producer + hand-written OpenAPI specs
├── infra/            # Terraform (RDS, ECR) + Prometheus/Grafana provisioning
├── scripts/          # Load test + chaos experiment scripts
├── docs/             # decisions, operations, scraping, architecture-c4.puml
└── docker-compose.yml
```

## Quick start (local development)

Requirements: Docker + Docker Compose.

```bash
docker compose up          # everything: PostgreSQL, RabbitMQ, Redis, backend, frontend
make up                    # same, via the Makefile

# Frontend:      http://localhost:9400   (proxies /api → backend internally)
# RabbitMQ UI:   http://localhost:9672   (pudimjobs / pudimjobs_dev)
# Mailpit:       http://localhost:9025   (dev email inbox)
# Grafana:       http://localhost:9300   (admin / admin)
# Prometheus:    http://localhost:9409
# Jaeger UI:     http://localhost:9668
```

`docker compose up` runs the backend with hot reload, so Python changes apply
immediately. Only the frontend and the admin dashboards are bound to host ports
(all configurable via `.env` — see [`.env.example`](.env.example)); PostgreSQL,
Redis, RabbitMQ AMQP and the FastAPI backend stay on Docker's internal network,
where the Angular dev server proxies `/api` → `backend:8000`.

Dev seed credentials (created by `python -m app.seed`, dev only):
**`admin@pudimjobs.dev` / `admin123`** — an `admin` role, so the Admin panel is
visible.

**Mobile app (Android)** — the React Native client in [`mobile/`](mobile/)
talks to the backend directly. The backend is bound to an optional host port
(`PJ_BACKEND_PORT`, default `8000`) so the app can reach `/api` from an emulator
(`10.0.2.2`) or a device; override `EXPO_PUBLIC_API_URL` in `mobile/.env`.
Native apps do not need CORS (browser-only), but the backend's allow-list
defaults to `localhost:4200/9400` — add your LAN origin to `PJ_CORS_ORIGINS` if
you open Swagger UI from another host.

```bash
cd mobile && npm install && npm run android   # or: npm start
```

## LAN server deployment

PudimJobs is designed to run on a shared LAN server without colliding with the
webservers already running there. Every host port binding is configurable via
`.env`; the UI and dashboards sit in a `9xxx` range that avoids the usual
suspects (`80`, `3000`, `4200`, `5432`, `6379`, `9090`, …), and the API keeps its
conventional `8000`.

```bash
cp .env.example .env
ss -tlnp | grep -E ':(9400|9300|9409|9668|9672|9025|8000)\b' || echo "all free"
docker ps --format '{{.Names}}\t{{.Ports}}'     # what Docker already bound
docker compose up -d
```

| Variable | Service | Default |
|----------|---------|---------|
| `PJ_FRONTEND_PORT` | Angular UI | `9400` |
| `PJ_BACKEND_PORT` | FastAPI (mobile clients, API tooling, Swagger) | `8000` |
| `PJ_GRAFANA_PORT` | Grafana | `9300` |
| `PJ_PROMETHEUS_PORT` | Prometheus | `9409` |
| `PJ_JAEGER_UI_PORT` | Jaeger UI | `9668` |
| `PJ_RABBITMQ_MGMT_PORT` | RabbitMQ management | `9672` |
| `PJ_MAILPIT_PORT` | Mailpit UI | `9025` |
| `PJ_CORS_ORIGINS` | Allowed browser origins (comma-separated) | `http://localhost:9400,…` |

From the LAN, `http://SERVER_IP:9400` is the app UI; the dashboards move to the
same host with the ports above. PostgreSQL, Redis and RabbitMQ AMQP are **not**
exposed — reach them with `docker compose exec`:

```bash
docker compose exec postgres psql -U pudimjobs -d pudimjobs
docker compose exec backend python -c "import httpx; print(httpx.get('http://localhost:8000/health').json())"
```

The `scripts/` tooling (load test, chaos experiments) talks to
`http://localhost:8000` — set `PJ_BACKEND_PORT` in `.env` if that port is taken.

> **Upgrading an existing checkout?** Delete the `TAILORING_LLM_VARIANT_ENABLED`
> line from your `.env` — the setting was removed (ADR 016 amendment) and
> `Settings` forbids unknown keys, so a native `backend`/`worker` run now fails
> validation at import. The AI rewrite variant is instead turned on by enabling
> the LLM in Admin → LLM with an API key. No data migration is needed for
> tailored CVs: artifacts written before ADR 016 (`structured_json` NULL) are
> repaired in place by the next tailor run for that job, same row id, so the
> application link and PDF keep working.

## Development commands

```bash
make test       # Backend tests (pytest)
make lint       # Backend lint (ruff)
make logs       # Stream all service logs
make up / down  # Start / stop services
```

**Backend (FastAPI + PostgreSQL)**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest                    # tests/ with asyncio mode auto
ruff check .              # lint
alembic upgrade head      # apply migrations
python -m app.seed        # create the admin user (idempotent)
uvicorn app.main:app --reload
```

Integration tests need PostgreSQL and default to
`postgresql+asyncpg://pudimjobs:pudimjobs_test@localhost:5433/pudimjobs_test`
(skipped automatically when unreachable); override with `TEST_DATABASE_URL=…`.

**Frontend (Angular 17)**

```bash
cd frontend
npm ci
npm start                 # dev server on :4200
npm test                  # unit tests (Karma + Jasmine)
npm run build             # production build into dist/
```

The UI is token-driven: design tokens, shared classes (`.btn`, `.panel`, `.card`,
`.input`, `.modal-*`, `.toast`, …) and inline-SVG icons live in
`src/styles.scss` and `src/app/shared/icons/`. Dark mode persists to
`localStorage` (`pudimjobs_theme`) with a `prefers-color-scheme` fallback;
`angular.json` enforces a 6 kB/8 kB `anyComponentStyle` budget. The app is
installable and works offline (`@angular/service-worker`, `ngsw-config.json`,
`manifest.webmanifest`).

**Mobile (React Native / Expo SDK 57)**

```bash
cd mobile
npm run typecheck   # tsc --noEmit
npm run lint        # eslint .
npm test            # jest
npm run format      # prettier --write .   (format:check = verify only)
npx expo export --platform android   # validate the production bundle
```

The i18n dictionary is **generated** from the web frontend
(`node mobile/scripts/extract-dictionary.js`, run from the repo root) so the two
never drift; app icons are generated from the web brand mark by
`mobile/scripts/generate-icons.js`. These checks run in CI via
`.github/workflows/mobile-ci.yml`.

**Workers (Celery + RabbitMQ)**

The worker imports the backend's `app` package, so install the backend
requirements first. With RabbitMQ and Redis up:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ../workers && pip install -r requirements.txt

celery -A workers.celery_app worker --loglevel=info   # worker
celery -A workers.celery_app beat   --loglevel=info   # periodic sweep
```

`workers/beat_schedule.py` runs `sweep_sources` every
`scrape_sweep_interval_minutes`, enqueuing a `scrape_source` task per due source.

| Resilience mechanism | Implementation |
|----------------------|----------------|
| Circuit breaker | Redis `cb:{source_id}` counter; ≥5 consecutive failures pause the source for 1h |
| Rate limiting | Redis `rate:{domain}` TTL per source (`sources.rate_limit_seconds`, default 30s) |
| User-agent rotation | Configured pool in `app.config` |
| robots.txt | Checked per domain, cached in-process 1h (`sources.respect_robots_txt`, default on) |
| Retry | Celery `autoretry_for`, exponential backoff 1m→2m→4m |
| Dead letters | RabbitMQ DLX (`pudimjobs.dlx`) + durable `scrape_runs` failed records |

**Chaos experiments** (`scripts/chaos/`, run against a live stack — each injects
a failure, verifies the response, then restores and prints `[PASS]`/`[FAIL]`):

| Script | Injects | Verifies |
|--------|---------|----------|
| `kill_rabbitmq.py` | stop RabbitMQ mid-scrape | durable queues buffer events; worker recovers |
| `break_scraper_html.py` | malformed feed HTML | retries → circuit breaker → DLQ → recovery |
| `exhaust_worker_memory.py` | cap worker at 64MB during a burst | OOM tasks retried; no duplicate jobs |
| `drop_data_quality.py` | empty the company-name mapping | normalization degrades visibly, then recovers |

```bash
cd scripts/chaos && python break_scraper_html.py
```

**Infrastructure (Terraform)** — `infra/` provisions RDS PostgreSQL 16
(`db.t3.micro`, encrypted at rest, 7-day backups, `multi_az`, deletion protection
in prod; inputs `environment`, `db_password`, optional `db_name`/`db_user`/
`allocated_storage`; outputs `endpoint`/`port`/`db_name`/`db_user`) and the ECR
repositories for backend/frontend images. ECS, ALB, VPC, S3 and ElastiCache are
documented provisioning gaps.

## Status & features

All eight development phases are complete: skeleton/infra/CI → data models →
scraping & reprocessing → JD parsing & CV tailoring → matching alerts →
observability/data quality/search → security hardening → chaos & postmortem →
cost analysis. Known gaps (mobile parity for the newest features, prep-task
reminders, free-text retrospectives) are listed in the ADRs.

**Backend (FastAPI + PostgreSQL)** — JWT auth (`POST /api/auth/login`,
`GET /api/auth/me`, bcrypt); user-scoped CRUD for sources, jobs (manual add +
search/filter, with a `source_id` filter and a preview-first bulk cleanup —
ADR 023), versioned master CV and applications (pipeline status, notes);
audit logging for CV and application mutations; Alembic migrations + idempotent
seed. 566 backend tests (350 run without PostgreSQL, 216 integration tests
skipped when it is unreachable) and 110 Angular specs.

**Scraping engine (Celery + RabbitMQ)** — pluggable scrapers (`scrapers/`:
career page via schema.org/JSON-LD, RSS via feedparser, aggregator adapters,
discovery providers). `scrape_source` runs circuit-breaker check → rate limit →
fetch → parse → normalize → dedup insert → publish `job.new` → update source
health. Discovery sources (`scrapers/discovery.py`) cover ATS JSON boards
(Ashby, Greenhouse, Lever, Workable, SmartRecruiters, Recruitee, Personio,
Workday), generic JSON APIs and search providers (Google CSE, Bing, Brave,
SerpApi, Bright Data — the paid route to LinkedIn/Indeed). Reprocessing is
backed by the durable `scrape_runs` failed-run log with admin DLQ list + replay.
Versioned `job.new` events live in `api/events/` (JSON on a topic exchange).

**Manual (watchlist) sources** — `type = manual` (ADR 018) tracks a board the
engine cannot fetch (login-walled candidate dashboards, anti-bot boards,
directories): the beat sweep never dispatches it, the scrape task records a
`skipped` run instead of failing and the preview explains why. A cadence
(`config.cadence_days`, default 7, validated 1–365 against the contract published
by `GET /api/sources/manual-metadata`) schedules the hand check instead, and the
sweep raises **one** in-app reminder per due source until
`POST /api/sources/{id}/check` marks it checked (stamps `last_scraped`, clears
the reminder and pushes `next_check_at` out); the Sources UI on web and mobile
shows the due badge, the next due date with a "due in / overdue by N days" hint
and the *Mark checked* button, and keeps a free-form `config.notes` per board.

**JD parsing & CV tailoring** — a spaCy worker extracts skills, years of
experience, education level and keywords into `jobs.parsed_jd` (JSONB), backed
by a curated taxonomy (`app/data/skills_taxonomy.json`) with word-boundary
matching and a `match_skills` score. Rule-based tailoring
(`cv_tailor.tailor_cv`) scores/reorders/selects experience and project blocks,
reorders skills (matched first) and leads the summary with JD-matched strengths,
reporting `used_fallback` instead of silently returning the top blocks. An
optional **second** variant is a full LLM rewrite kept *alongside* the
deterministic one (enabled in Admin → LLM with a stored API key; no env flag),
schema-validated and degrading gracefully; its prompt asks for a CV tailored for
the job (master CV as single source of truth, roles that do not support the
application may be omitted) that fits two pages. Both variants render a PDF via
Jinja2 templates (Classic and ATS-safe) behind `GET /api/cv/generated/{id}/pdf`;
the same endpoint accepts `?format=docx`, and `POST /api/cv/pdf` (`?format=`,
plus `?template=` for the PDF) renders straight from the editor, so both also
hand back an editable Word copy built on demand from the stored structure. The
PDF stays the canonical artifact — it is the only one stored and page-measured
(ADR 017). Both export endpoints also accept `?language=pt-BR`: the copy is
translated on demand by the LLM from the same structure and rendered fresh, with
the section headings taken from a fixed PT-BR catalog so a translated CV never
mixes *Resumo* with *Summary* (ADR 024). The skill-group labels travel to the
model with the copy, so a CV that groups its skills by taxonomy reads
*Ferramentas* rather than *Tools*. English is the stored language and needs
no LLM; the client learns whether translation is available from
`GET /api/cv/capabilities` rather than by provoking a 409. Every export opens with the same header — the name over one flowing
contact line (`email • phone • location • links`), set at the 8pt at which all
five fields fit a single row of the A4 text block, with the DOCX put on the same
page box (ADR 021).
The Skills section is grouped into labelled lines either way: the deterministic
variant groups the flat list by taxonomy (skills the taxonomy does not know land
in an `Additional` bucket, never `Other`), while the LLM variant authors its own
2–5 job-relevant groups and the renderer prefers those. The importer splits that
section on real separators only — commas, semicolons, pipes, bullets and runs of
2+ spaces, never a single space or a slash — so multi-word and slashed skills stay
atomic ("Apache Thrift", "Test-Driven Development (TDD)", "CI/CD"), and *every*
group label in front of values is dropped instead of being imported as a skill:
known ones ("Cloud & DevOps: AWS, Docker") and compounds a CV invented for itself
("Frameworks & Tools: Qt, Protobuf/gRPC"), since a label is recognised by its shape
(a few words, none of them a skill — which is what leaves "CKA: Certified
Kubernetes Administrator" alone). Each entry then resolves to the skills it names,
so a compound lands in the group its parts agree on ("JavaScript/TypeScript" under
Languages) and a JD asking for TypeScript is matched by a CV that lists it as half
of one. A CV that labels its own groups therefore parses back into exactly the
taxonomy's categories (ADR 020/022).
The two variants are committed one after the other — the deterministic one first —
so the 202 from `POST /api/jobs/{id}/tailor` reports which variants the run will
produce and the web/mobile panels keep polling until *all* of them have landed
instead of settling on the first artifact and hiding the AI rewrite.

**Applications, retrospectives & interview prep** — a per-application workspace
(`/applications/:id`) with the target job (`GET /api/applications/{id}`), the
pipeline fields (status, applied date, notes, retrospective), the job
description and the tailored-CV + ATS panel; `Application.generated_cv_id`
records the artifact that was sent. Applications keep a per-record
`lessons_learned` note (migration `0016`) plus a cross-application feed
(`GET /api/applications/lessons`). Interview prep tasks live in `prep_tasks`
(migration `0017`) with full CRUD under `/api/prep-tasks`, ordered to surface
unfinished work first, then the nearest due date.

**Matching alerts & notifications** — alert rules (keywords, companies, tags,
remote-only, min years, channels, active toggle) with full CRUD
(`/api/alert-rules`). `workers/consume_events.py` consumes `job.new` and
enqueues `match_job`, which evaluates the job against every active rule of its
owner (`app/services/matcher.py`). Delivery is in-app (`notifications` table) and
by email (SMTP, Mailpit in dev, Jinja2 template) with per-notification delivery
status; `/api/notifications` lists, marks-read and reads-all.

**Observability, data quality & search** — PostgreSQL FTS with a generated
`search_vector` (title A > company B > description C), GIN index and
`plainto_tsquery`/`ts_rank` scoring (migration `0006`). A `scrape_quality` table
(migration `0007`) tracks company/title/skill normalization, completeness scoring
and fuzzy cross-source duplicate detection, dispatched from the same `job.new`
consumer as alert matching, with an admin Data Quality dashboard. OpenTelemetry
instruments FastAPI + Celery into Jaeger (OTLP) with trace IDs bridged to
structlog; Prometheus/Grafana and worker metrics (scrapes total/duration) are
provisioned by docker-compose.

**Frontend (Angular)** — login + auth guard + JWT interceptor; source
management with quick filters (all / manual / automated / unhealthy / due /
avoided) and a per-source jobs count that opens that board's jobs in the jobs
list (`/jobs?source_id=…`, the filter the API already exposes — a manual
watchlist stays unlinked until it owns a job); job listing with
keyword/company/tag/date/source search, manual add, a
preview-then-confirm bulk cleanup (age and/or source, applications protected by
default — ADR 023) and a
detail view (parsed requirements, *add to applications*, pipeline badge once
tracked); master CV editor (contact, summary, experience, education, skills,
projects, certifications, languages) with version history, PDF/DOCX/ODT import,
live preview and Classic/ATS-safe PDF export (plus a PT-BR copy translated on
demand, ADR 024); a kanban pipeline (saved → applied
→ interview → offer → rejected) with Angular CDK drag & drop whose cards open the
per-application workspace; interview prep and lessons-learned pages; a
five-tab admin panel (Overview, Sources, Quality, Dead-Letter Queue, Audit Log);
onboarding panel for new users; client-side pagination (12/page).

**Mobile (React Native / Expo SDK 57)** — mirrors the web UI: login, jobs +
detail, applications kanban and workspace (dual `rule`/`llm` tailoring variants,
inline edit, *Use this one*), master CV editor (edit/preview, import, export),
sources (CRUD + auth), alerts, notifications and the admin panel. React
Navigation 7, TanStack Query, Zustand (keychain-backed session via
`expo-secure-store`), react-hook-form + zod, and design tokens ported 1:1 from
`frontend/src/styles.scss`. Remaining polish: an e2e smoke test on a device and
the Android release build (EAS).

## License

[MIT](LICENSE)
