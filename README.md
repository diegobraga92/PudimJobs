# PudimJobs — Job Application Tracker

> **A job hunting assistant** — scrapes job listings from multiple sources, enriches and deduplicates them, helps you tailor your CV to each job description, and tracks your applications from *saved* to *offer*.
>
> Flagship project for async pipelines, data engineering, search, and resilient external integrations.

## Architecture

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API** | Python 3.12 + FastAPI | REST API, auth, CRUD, orchestration |
| **Workers** | Celery + RabbitMQ | Async scraping, JD parsing, CV tailoring, matching alerts |
| **Database** | PostgreSQL 16 (asyncpg / SQLAlchemy) | Sources, jobs, master CV, applications, audit log |
| **Cache / broker** | Redis | Celery result backend, rate limiting |
| **Search** | PostgreSQL Full-Text Search | Keyword search over jobs (Elasticsearch tradeoff documented) |
| **Frontend** | Angular 17 + TypeScript | Source management, job search, CV editor, application pipeline |
| **Observability** | OpenTelemetry, Prometheus, structlog, ELK (planned) | Traces, metrics, structured logs, dashboards |
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
│   └── app/          #   config, database, logging, metrics, routers
├── frontend/         # Angular 17 application
│   └── src/app/      #   components, services, routing
├── scrapers/         # Scraper implementations & adapters (per-source)
├── workers/          # Celery tasks (scraping, parsing, matching, tailoring)
├── api/openapi/      # Hand-written OpenAPI contract specs
├── infra/            # Terraform (RDS, compute, ECR)
├── docs/             # DEV_PLAN, ADRs, SLOs, runbooks, tradeoffs
└── docker-compose.yml
```

## Quick Start (Local Development)

Requirements: Docker + Docker Compose.

```bash
# Start everything (PostgreSQL, RabbitMQ, Redis, backend, frontend)
docker compose up

# Or via the Makefile
make up

# Frontend:  http://localhost:4200
# Backend:   http://localhost:8000  (/health, /docs, /metrics)
# RabbitMQ:  http://localhost:15672 (pudimjobs / pudimjobs_dev)
```

`docker compose up` launches the backend with hot reload, so Python changes
apply immediately. The Angular dev server proxies `/api` → `backend:8000`.

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
| 3 — CV parsing & tailoring | 🔜 Next |
| 4 — Matching alerts & notifications | ⏳ Planned |
| 5 — Observability, data quality & search | ⏳ Planned |
| 6 — Security hardening | ⏳ Planned |
| 7 — Chaos & incident postmortem | ⏳ Planned |
| 8 — Cost analysis & portfolio polish | ⏳ Planned |

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
  via feedparser, aggregator base)
- `scrape_source` task: circuit-breaker check → rate limit → fetch → parse →
  normalize → dedup insert → publish `job.new` event → update source health
- Resilience: Redis-backed per-source circuit breaker (5 failures → pause 1h),
  per-domain rate limiting, robots.txt checks, user-agent rotation,
  exponential-backoff retries, RabbitMQ DLX
- Reprocessing: `scrape_runs` durable failed-run log; admin endpoints to list
  the DLQ, replay runs, and re-parse stored raw HTML
- Versioned `job.new` events in `api/events/` (JSON on a topic exchange,
  `job.new.v1` routing key)
- Admin dashboard in the frontend: stats, source health, DLQ with replay

**Frontend (Angular)**
- Login page + auth guard + JWT interceptor
- Source management (add / edit / delete)
- Job listing with keyword/company/tag/date search + manual add + detail view
  with "add to applications"
- Master CV editor (summary, experience, education, skills, projects) with
  version history
- Application pipeline (Kanban: saved → applied → interview → offer → rejected)
- Admin dashboard (source health, scrape stats, dead-letter queue)

**Demo credentials** (seeded by `python -m app.seed`, dev only):
`admin@pudimjobs.dev` / `admin123`

## Documentation

- [Development Plan](docs/DEV_PLAN.md) — phased roadmap with completion checklists
- [Architecture Decision Records](docs/adr/) — 9 planned ADRs (1 written: FastAPI choice)
- [SLOs & Error Budgets](docs/slo.md) — availability, freshness, latency targets
- [Tradeoffs](docs/tradeoffs.md) — planned summary of engineering tradeoffs
- [Database Performance](docs/database-performance.md) — planned `EXPLAIN ANALYZE` report
- [Incident Postmortems](docs/postmortems/) — planned postmortem & runbooks

## License

[MIT](LICENSE)
