# PudimJobs — Job Application Tracker

> **A job hunting assistant** — scrapes job listings from multiple sources, enriches and deduplicates them, helps you tailor your CV to each job description, and tracks your applications from *saved* to *offer*.
>
> Flagship project for async pipelines, data engineering, search, and resilient external integrations.

---

## Who this is for

**Job seekers** — PudimJobs watches your target companies and feeds for you:
new postings are scraped, deduplicated, and matched against your saved
searches (alerts in-app and by email). The "Tailor CV" button produces a
job-specific CV PDF from your master CV, and the kanban pipeline tracks each
application from *saved* through *offer*.

**Hiring managers / HR** — this is a portfolio project that demonstrates how a
small engineering team would build a production job board: an event-driven
scraping pipeline with circuit breakers and a dead-letter queue, a data
quality pipeline with normalization and dashboards, relevance-ranked search,
and versioned CV generation. See [docs/tradeoffs.md](docs/tradeoffs.md) for the
engineering decisions behind each component.

**Engineers / interviewers** — the interesting depth lives in the docs:
- [Development plan](docs/DEV_PLAN.md) — 8 phases, every checkbox traceable to code
- [Architecture decision records](docs/adr/) — 9 ADRs (FastAPI, data model, events, reprocessing, resilience, tailoring, alerting, data quality, search)
- [Resilience](docs/stride-threat-model.md) · [runbooks](docs/runbooks/) · [postmortem](docs/postmortems/)
- [Database performance](docs/database-performance.md) — real `EXPLAIN ANALYZE` numbers
- [Cost & capacity](docs/cost-estimate.md) · [docs/capacity-plan.md](docs/capacity-plan.md)
- [C4 architecture diagram](docs/architecture-c4.puml)

---

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | Python 3.12 + FastAPI | REST API, auth, CRUD, orchestration |
| **Workers** | Celery + RabbitMQ | Async scraping, JD parsing, CV tailoring, matching alerts |
| **Database** | PostgreSQL 16 (asyncpg / SQLAlchemy) | Sources, jobs, master CV, applications, audit log |
| **Cache / broker** | Redis | Celery result backend, rate limiting |
| **Search** | PostgreSQL Full-Text Search | Keyword search over jobs (Elasticsearch tradeoff documented) |
| **Frontend** | Angular 17 + TypeScript | Source management, job search, CV editor, application pipeline |
| **Mobile** | React Native (Expo SDK 57, Android-first) | Mobile mirror of the web UI: jobs, CV editor, kanban, sources, alerts, notifications, admin |
| **Observability** | OpenTelemetry → Jaeger, Prometheus, Grafana, structlog | Traces, metrics, structured logs, RED + data-quality dashboards |
| **Infrastructure** | Docker Compose (dev), Terraform + AWS (prod) | Local & cloud deployment |

```
┌─────────────┐      ┌──────────────┐      ┌───────────────────┐
│   Angular   │ ───▶ │    FastAPI   │ ───▶ │ PostgreSQL 16     │
│   frontend  │      │    backend   │      │ (sources, jobs…)  │
└─────────────┘      └──────┬───────┘      └───────────────────┘
                            │  /health, /metrics
                            │
                     ┌──────▼────────┐      ┌───────────────────┐
                     │ RabbitMQ      │ ◀─── │ Celery workers    │
                     │ (event bus)   │      │ (scrapers, NLP)   │
                     └───────────────┘      └───────────────────┘
```

## Project Structure

```
PudimJobs/
├── backend/          # FastAPI application (Python 3.12)
│   └── app/          #   config, database, models, routers, services, data, templates
├── frontend/         # Angular 17 application
│   └── src/app/      #   components, services, routing, guards, interceptors
├── mobile/           # React Native (Android-first) client — mirrors the web UI
│   └── src/          #   screens, components, api, hooks, theme, i18n, navigation
├── scrapers/         # Scraper implementations & adapters (per-source)
├── workers/          # Celery app, tasks, event consumer, metrics
├── api/              # Event schemas/producer + hand-written OpenAPI specs
├── infra/            # Terraform (RDS, ECR) + Prometheus/Grafana provisioning
├── scripts/          # Load test + chaos experiment scripts
├── docs/             # DEV_PLAN, 9 ADRs, SLOs, runbooks, postmortems, tradeoffs
└── docker-compose.yml
```

## Quick Start (Local Development)

Requirements: Docker + Docker Compose.

```bash
# Start everything (PostgreSQL, RabbitMQ, Redis, backend, frontend)
docker compose up

# Or via the Makefile
make up

# Frontend:      http://localhost:9400   (UI; proxies /api → backend internally)
# RabbitMQ UI:   http://localhost:9672   (pudimjobs / pudimjobs_dev)
# Mailpit:       http://localhost:9025   (dev email inbox)
# Grafana:       http://localhost:9300   (admin / admin)
# Prometheus:    http://localhost:9409
# Jaeger UI:     http://localhost:9668
```

**Mobile app (Android):** the React Native client in [`mobile/`](mobile/) talks
to the FastAPI backend directly (see `mobile/README.md`). The backend is bound
to an optional host port (`PJ_BACKEND_PORT`, default `8000`) so the app can
reach `/api` from an emulator (`10.0.2.2`) or device. Dev seed credentials:
`admin@pudimjobs.dev` / `admin123`.

```bash
cd mobile && npm install && npm run android
```

`docker compose up` launches the backend with hot reload, so Python changes
apply immediately. Only the frontend and the admin dashboards are bound to host
ports (all configurable via `.env` — see [`.env.example`](.env.example));
PostgreSQL, Redis, RabbitMQ AMQP and the FastAPI backend stay on Docker's
internal network, where the Angular dev server proxies `/api` → `backend:8000`.

## LAN Server Deployment

PudimJobs is designed to run on a shared LAN server without colliding with the
webservers already running there. All host port bindings are configurable via a
`.env` file and default to a `9xxx` range that avoids the usual suspects
(`80`, `3000`, `4200`, `5432`, `6379`, `8000`, `9090`, …). Services that only
consume each other over Docker's internal network (PostgreSQL, Redis, RabbitMQ
AMQP, FastAPI, Jaeger OTLP, Mailpit SMTP) are **not** exposed to the host at all.

### 1. Configure `.env`

```bash
cp .env.example .env
```

Then edit `.env`:

1. **Check for port conflicts** on the server and adjust any value that is
   already in use:

   ```bash
   ss -tlnp | grep -E ':(9400|9300|9409|9668|9672|9025)\b' || echo "all free"
   # or, to see everything Docker has already bound:
   docker ps --format '{{.Names}}\t{{.Ports}}'
   ```

2. **Add the server's LAN IP** to `PJ_CORS_ORIGINS` if you plan to open the
   backend Swagger UI (`/docs`) or call the API directly from a browser on
   another machine. The normal UI flow proxies `/api` through the frontend, so
   it works without this:

   ```env
   PJ_CORS_ORIGINS=http://localhost:9400,http://127.0.0.1:9400,http://192.168.1.50:9400
   ```

### 2. Start the stack

```bash
docker compose up -d
# or, if you keep the config in a non-default location:
docker compose --env-file .env up -d
```

### 3. Access from the LAN

Replace `SERVER_IP` with the server's LAN address (`hostname -I`):

| What | URL |
|------|-----|
| **App UI** | `http://SERVER_IP:9400` |
| Grafana dashboards | `http://SERVER_IP:9300` (admin / admin) |
| RabbitMQ management | `http://SERVER_IP:9672` (pudimjobs / pudimjobs_dev) |
| Mailpit (dev email) | `http://SERVER_IP:9025` |
| Jaeger tracing UI | `http://SERVER_IP:9668` |
| Prometheus | `http://SERVER_IP:9409` |

### Port reference

All host ports come from `.env` (see [`.env.example`](.env.example)):

| Variable | Service | Default |
|----------|---------|---------|
| `PJ_FRONTEND_PORT` | Angular UI | `9400` |
| `PJ_GRAFANA_PORT` | Grafana | `9300` |
| `PJ_PROMETHEUS_PORT` | Prometheus | `9409` |
| `PJ_JAEGER_UI_PORT` | Jaeger UI | `9668` |
| `PJ_RABBITMQ_MGMT_PORT` | RabbitMQ management | `9672` |
| `PJ_MAILPIT_PORT` | Mailpit UI | `9025` |
| `PJ_CORS_ORIGINS` | Allowed browser origins (comma-separated) | `http://localhost:9400,…` |

PostgreSQL, Redis, RabbitMQ AMQP and the FastAPI backend are **not** exposed to
the host. To reach them from the server itself, use `docker compose exec`:

```bash
docker compose exec postgres psql -U pudimjobs -d pudimjobs
docker compose exec backend python -c "import httpx; print(httpx.get('http://localhost:8000/health').json())"
```

> 💡 Need the API reachable from the LAN for tooling (e.g. the scripts in
> `scripts/`)? Add a host binding to the `backend` service in
> `docker-compose.yml` (`ports: - "${PJ_BACKEND_PORT:-8000}:8000"`) and set
> `PJ_BACKEND_PORT` in `.env`.

## Development Commands

```bash
make test       # Backend tests (pytest)
make lint       # Backend lint (ruff)
make logs       # Stream all service logs
make up         # Start services
make down       # Stop services
```

Backend tests can also be run directly:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest            # runs tests/ with asyncio mode auto
ruff check .      # lint
```

Integration tests need a PostgreSQL test database. They default to
`postgresql+asyncpg://pudimjobs:pudimjobs_test@localhost:5433/pudimjobs_test`
and are skipped automatically when no database is reachable. Override with:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db pytest
```

Local development helpers:

```bash
cd backend
alembic upgrade head      # apply migrations
python -m app.seed        # create the admin user (idempotent)
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm ci
npm start                 # dev server on :4200
npm test                  # unit tests (Karma + Jasmine)
npm run build             # production build
```

## Status & Roadmap

See [docs/DEV_PLAN.md](docs/DEV_PLAN.md) for the full development plan.

| Phase | Status |
|-------|--------|
| 0 — Project skeleton, infra & CI/CD | ✅ Done |
| 1 — Core data models & basic CRUD | ✅ Done |
| 2 — Scraping engine & reprocessing | ✅ Done |
| 3 — JD parsing & CV tailoring | ✅ Done |
| 4 — Matching alerts & notifications | ✅ Done |
| 5 — Observability, data quality & search | ✅ Done |
| 6 — Security hardening | ✅ Done |
| 7 — Chaos & incident postmortem | ✅ Done |
| 8 — Cost analysis & portfolio polish | 🔜 Next |

### What's implemented so far

**Backend (FastAPI + PostgreSQL)**
- JWT authentication (`POST /api/auth/login`, `GET /api/auth/me`) with bcrypt hashing
- User-scoped CRUD: sources, jobs (manual add + search/filter), master CV
  (versioned), applications (pipeline status, notes)
- Audit logging for CV modifications and application status changes
- Alembic migrations (`alembic upgrade head`) and an idempotent seed
  (`python -m app.seed`)
- 45 unit + integration tests (PostgreSQL + Redis test services via
  `TEST_DATABASE_URL` / `REDIS_URL`)

**Scraping engine (Celery + RabbitMQ)**
- Celery worker + Beat scheduler in `workers/`, wired into docker-compose
- Pluggable scrapers in `scrapers/` (career page via schema.org/JSON-LD, RSS
  via feedparser, aggregator base, discovery providers)
- `scrape_source` task: circuit-breaker check → rate limit → fetch → parse →
  normalize → dedup insert → publish `job.new` event → update source health
- Discovery sources (`scrapers/discovery.py`): ATS feeds (Ashby, Greenhouse,
  Lever, Workable) and search APIs (Google CSE, Bing, Brave, SerpApi, Bright
  Data) — provider selected per source; search providers fetch each result
  page with per-domain robots + rate limiting; `serpapi`/`brightdata` cover
  LinkedIn Jobs and Indeed via paid third-party APIs
- Resilience: Redis-backed per-source circuit breaker (5 failures → pause 1h),
  per-domain rate limiting, robots.txt checks, user-agent rotation,
  exponential-backoff retries, RabbitMQ DLX
- Reprocessing: `scrape_runs` durable failed-run log; admin endpoints to list
  the DLQ and replay failed runs
- Versioned `job.new` events in `api/events/` (JSON on a topic exchange,
  `job.new.v1` routing key)
- Admin dashboard in the frontend: stats, source health, DLQ with replay

**JD parsing & CV tailoring**
- JD parsing worker (spaCy): extracts skills, years of experience, education
  level, keywords into `jobs.parsed_jd` (JSONB)
- Curated skills taxonomy (`app/data/skills_taxonomy.json`) + word-boundary
  matching with a `match_skills` relevance score
- Rule-based tailoring engine (`cv_tailor.tailor_cv`): scores/reorders/selects
  experience & project blocks, reorders skills (matched first), optional LLM
  rephrasing of bullets behind a feature flag (`TAILORING_LLM_ENABLED`)
- PDF generation: Jinja2 template + weasyprint; tailored CVs stored as new
  (non-current) `master_cv` versions + `generated_cvs` rows
- CV import: `POST /api/cv/parse` uploads a PDF/DOCX and returns a structured
  `CVStructure` (rule-based parser, optional LLM upgrade — ADR 011); the
  editor is pre-filled for review before saving
- API: `POST /api/jobs/{id}/parse`, `POST /api/jobs/{id}/tailor`,
  `GET /api/jobs/{id}/parsed`, `POST /api/cv/parse`,
  `GET /api/cv/generated`, `GET /api/cv/generated/{id}/pdf`
- Frontend: "Tailor CV for this job" button + parsed-JD panel on the job
  detail page; generated-CV list with PDF download and "Import PDF/DOCX" on
  the CV editor

**Matching alerts & notifications**
- Alert rules (saved searches): keywords, companies, tags, remote-only,
  min years of experience, channels, active toggle — `alert_rules` table +
  full CRUD API + frontend page
- Event-driven matching: `workers/consume_events.py` consumes `job.new`
  RabbitMQ events and enqueues `match_job`; `match_job` evaluates the job
  against all active rules for its owner (`app/services/matcher.py`)
- Delivery: in-app notifications (`notifications` table) + email via SMTP
  (Mailpit for local dev, Jinja2 template); per-notification delivery status
  (created/sent/failed) for observability
- API: `/api/alert-rules`, `/api/notifications` (list, mark-read, read-all)
- Frontend: Alerts page (CRUD + pause/resume) and Notifications page

**Observability, data quality & search**
- PostgreSQL Full-Text Search: generated `search_vector` (title A > company B
  > description C) + GIN index; `plainto_tsquery`/`ts_rank` ranking with a
  per-result `score` (replaces ILIKE) — migration `0006`
- Data quality pipeline: `scrape_quality` table; company/title/skill
  normalization (mapping files + taxonomy aliases), completeness scoring,
  fuzzy cross-source duplicate detection — dispatched from the same `job.new`
  event consumer as alert matching (migration `0007`)
- Admin "Data Quality" dashboard: overview cards, per-source breakdown,
  flagged-jobs list with normalization + issues
- OpenTelemetry: FastAPI + Celery instrumentation → Jaeger (OTLP), trace IDs
  bridged to structured logs; docker-compose now runs Prometheus, Grafana
  (provisioned RED/scraper dashboard), and Jaeger
- Worker Prometheus metrics wired into the scrape task (scrapes total,
  duration); `/metrics` on a sidecar port
- Load test script (`scripts/load_test.py`) + real `EXPLAIN ANALYZE` results
  in `docs/database-performance.md`; PostgreSQL-vs-Elasticsearch evaluation in
  `docs/elasticsearch-comparison.md`

**Security hardening (Phase 6)**
- STRIDE threat model for API + scrapers (`docs/stride-threat-model.md`)
- API rate limiting with `slowapi` (Redis-backed): login 5/min, authenticated
  API 120/min; 429 responses
- Audit investigation API (`GET /api/admin/audit` with user/action/entity/date
  filters + `/audit/actions` facets) and an Audit Log tab in the admin UI with
  expandable change-diffs
- CI security gates: `pip-audit` on Python deps + Trivy container scan
- Secrets rotation guide (`docs/secrets-rotation.md`)

**Resilience, chaos & postmortems (Phase 7)**
- Chaos experiment scripts (`scripts/chaos/`): kill RabbitMQ, break scraper
  HTML, exhaust worker memory, break a normalization rule — each injects a
  failure and verifies the system's response
- Blameless postmortem: `docs/postmortems/001-scraper-outage-data-quality.md`
  (simulated job-board HTML change → circuit breaker → DLQ → re-scrape
  recovery, with corrective actions)
- Four runbooks in `docs/runbooks/`: scraper failure, RabbitMQ backlog, data
  quality degradation, database failover

**Frontend (Angular)**
- Login page + auth guard + JWT interceptor
- Source management (add / edit / delete)
- Job listing with keyword/company/tag/date search + manual add + detail view
  with "add to applications"
- Master CV editor (summary, experience, education, skills, projects) with
  version history and PDF/DOCX import to pre-fill the form
- Application pipeline (Kanban: saved → applied → interview → offer → rejected)
- Admin dashboard (source health, scrape stats, dead-letter queue)

**Demo credentials** (seeded by `python -m app.seed`, dev only):
`admin@pudimjobs.dev` / `admin123`

## Documentation

**Planning & decisions**
- [Development Plan](docs/DEV_PLAN.md) — phased roadmap with completion checklists (Phases 0–8 ✅)
- [Architecture Decision Records](docs/adr/) — **9 ADRs** (001–009)
- [Tradeoffs](docs/tradeoffs.md) — every decision at a glance, linked to ADRs

**Operational**
- [SLOs & Error Budgets](docs/slo.md) — availability 99.5%, freshness, latency
- [Database Performance](docs/database-performance.md) — real `EXPLAIN ANALYZE` results
- [Search Evaluation](docs/elasticsearch-comparison.md) — PostgreSQL FTS vs OpenSearch
- [Cost Estimate](docs/cost-estimate.md) · [Capacity Plan](docs/capacity-plan.md)
- [Secrets Rotation](docs/secrets-rotation.md)
- [C4 Architecture Diagram](docs/architecture-c4.puml)

**Security & resilience**
- [STRIDE Threat Model](docs/stride-threat-model.md)
- [Runbooks](docs/runbooks/) — scraper failure, RabbitMQ backlog, data quality, database failover
- [Postmortems](docs/postmortems/) — simulated scraper-outage incident
- [Chaos Experiments](scripts/chaos/README.md) — failure-injection scripts

## Demo Video

A walkthrough script is outlined in [docs/DEV_PLAN.md](docs/DEV_PLAN.md) (Phase 8):
scraping workflow → data quality dashboard → CV tailoring → alert notification →
reprocessing. To record: start the stack, run `python scripts/chaos/break_scraper_html.py`
to show resilience, then run the tailoring + alert flows described in the README.

## License

[MIT](LICENSE)
