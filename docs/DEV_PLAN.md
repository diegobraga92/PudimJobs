# Job Application Tracker – Development Plan (DEV_PLAN.md)

> Job hunting assistant: Python backend (FastAPI), Celery workers, RabbitMQ, Angular frontend.
> Multi‑source job scraping with deep resilience, data quality pipeline, search architecture, AI‑assisted CV tailoring, application tracking, and matching alerts.
> Flagship project for async pipelines, data engineering, search, and resilient external integrations.

---

## Cross‑Cutting Engineering Practices (applied throughout)

- **Architecture Decision Records (ADRs):** Every significant choice (scraping architecture, CV tailoring, matching engine, event evolution, search, reprocessing) documented in `docs/adr/`
- **Design Documents (RFCs):** Pre‑implementation for scraper resilience, CV parser, matching algorithm, data quality pipeline
- **Tradeoff Documents:** `docs/tradeoffs.md` summary linking to ADRs
- **Testing:** Unit, integration, contract, and load tests; CI quality gates enforced
- **Observability:** OpenTelemetry traces, Prometheus metrics, structured JSON logs; ELK stack for scraper log aggregation; RED dashboards for API, workers, and data quality
- **SLOs & Error Budgets:** Defined for scraping freshness (e.g., 95% of target sites scraped within 1h), notification delivery, search latency; alerting on error budget burn
- **Incident Runbooks:** For scraper failure (site HTML change), RabbitMQ queue backlog, notification delivery degradation, data quality drop
- **Blameless Postmortems:** At least one simulated (e.g., major job board HTML change causing scraper outage and data quality incident)
- **CI/CD & GitOps:** GitHub Actions, Docker builds, Kubernetes deployment (optional), ArgoCD (optional)
- **IaC:** Terraform for cloud resources (RDS, compute, S3), documented modules
- **Capacity Planning:** Scraping throughput, storage growth (JDs, resumes, search indices), worker scaling, cost projection
- **Stakeholder Communication:** README explains trade‑offs to job seekers, HR, and operations

---

## Security Requirements (Implemented Throughout)

- **Authentication & Authorisation:** JWT with refresh, RBAC (user / admin), secure storage on frontend
- **Audit Logs:** Track who modified master CV, submitted applications, viewed JDs, replayed jobs
- **Scraping Ethics & Compliance:** Respect `robots.txt`, rate limits, user‑agent rotation, terms of service awareness
- **Data Encryption:** At rest (database encryption) and in transit (TLS everywhere)
- **Secrets Management:** Environment variables / Vault; rotation documented
- **Input Sanitisation:** Protect against injection in JD parsing, CV generation, and search queries
- **Dependency & Container Scanning:** `pip audit`, Trivy in CI; block critical vulns

---

## Core Features

1. **Job Source Tracking** – Manage target company career pages, aggregators (Indeed, LinkedIn, etc.), and custom RSS feeds. Store last scrape timestamp, health status.
2. **Resilient Scraper Engine** – Background workers fetch job listings, parse into structured format, handle pagination/dynamic content, with circuit breakers, retries, dead‑letter queues, and reprocessing workflows.
3. **Data Quality Pipeline** – Normalize company names, job titles, skills taxonomy; deduplicate postings; assign quality scores; dashboard for monitoring.
4. **Search Architecture** – PostgreSQL Full‑Text Search with relevance tuning, evaluated against Elasticsearch/OpenSearch, documented tradeoffs.
5. **Job & JD Storage** – Database stores scraped jobs, full JD text, tags, normalized fields. Search and filter capabilities.
6. **Master CV Management** – Structured master CV (experiences, skills, education) with manual annotation and tagging.
7. **CV Tailoring** – Rule‑based engine selects and reorders master CV sections based on JD; optional LLM enhancement; generates tailored PDF.
8. **Application Tracking** – Pipeline view (saved/applied/interview/offer/rejected), notes, attached tailored CVs.
9. **Matching Alerts** – User criteria trigger notifications when new jobs match; email + in‑app delivery.

---

## Phase 0 – Project Skeleton, Infrastructure & CI/CD (2–3 days)

**Goal:** Scaffolded monorepo, backend and frontend talking, local infrastructure running.

- [ ] Monorepo: `backend/`, `frontend/`, `scrapers/`, `workers/`, `api/`, `docker-compose.yml`
- [ ] Backend (Python + FastAPI): `/health` endpoint, PostgreSQL connection (asyncpg/SQLAlchemy), structured logging
- [ ] Frontend (Angular + TypeScript): scaffold, call `/health`, display status
- [ ] Docker Compose: backend + PostgreSQL + RabbitMQ + Redis; local dev workflow
- [ ] API contracts: OpenAPI spec for initial endpoints (`api/openapi/health.yaml`, later job & CV schemas)
- [ ] Infrastructure: Terraform for RDS Postgres, compute (EC2/ECS/EKS minimal), document modules
- [ ] CI/CD: GitHub Actions for backend (lint, test, build), frontend (lint, test, build)
- [ ] Observability seed: structured logging with trace IDs, Prometheus `/metrics` on backend
- [ ] SLO draft: API availability 99.5%, document in `docs/slo.md`
- [ ] ADR: `001-choose-python-fastapi.md`

---

## Phase 1 – Core Data Models & Basic CRUD (2–3 weeks)

**Goal:** Users can manage sources, view manually added jobs, maintain master CV, and track applications without scraping yet.

- [ ] Database schema:
  - [ ] `sources` (name, URL, type, last_scraped, health)
  - [ ] `jobs` (title, company, description, URL, source, posted_date, tags, raw_html optional)
  - [ ] `master_cv` (structured JSON: sections like summary, experience[], education[], skills[], projects[])
  - [ ] `applications` (user_id, job_id, status, applied_date, notes, cv_version)
- [ ] Backend API:
  - [ ] CRUD for sources, jobs (manual add), master CV
  - [ ] Application tracking endpoints (list, create, update status)
  - [ ] Search jobs by keyword, company, date range
- [ ] Frontend:
  - [ ] Source management page
  - [ ] Job listing with search/filter
  - [ ] Master CV editor (form‑based for structured sections, preview)
  - [ ] Application pipeline (Kanban or status columns)
- [ ] RBAC seed: user sees only own data; admin features later
- [ ] Audit log: record changes to master CV and application status
- [ ] ADR: `002-data-model-design.md`

---

## Phase 2 – Scraping Engine, Event Schema & Reprocessing (2–3 weeks)

**Goal:** Asynchronous, fault‑tolerant scraping with event versioning and operational replay capabilities.

- [ ] Scraper worker (Celery task):
  - [ ] Accept source ID, fetch page(s), parse HTML (BeautifulSoup/lxml or Playwright for JS)
  - [ ] Extract structured job data, normalize fields, deduplicate by URL or external ID
  - [ ] Store new jobs in database, produce `job.new` event to RabbitMQ
- [ ] Resilience patterns:
  - [ ] Circuit breaker per source (e.g., 5 consecutive failures → pause for 1h)
  - [ ] Rate limiting (respect `robots.txt` if present, configurable delay)
  - [ ] User‑agent rotation and proxy support (documented)
  - [ ] Retry with exponential backoff, dead‑letter queue (DLQ) for permanently failing jobs
  - [ ] Idempotent job insertion (URL + source unique constraint, dedup logic)
- [ ] Event schema versioning:
  - [ ] Include `version` field in `job.new` event payload; store schemas in `api/events/`
  - [ ] Define backward compatibility rules (new fields additive, deprecated after notice)
  - [ ] ADR: `003-event-evolution.md`
- [ ] Reprocessing workflow:
  - [ ] Admin endpoint to inspect DLQ, select failed jobs, and re‑queue for retry
  - [ ] Replay capability for historical raw HTML (re‑parse after parser improvements)
  - [ ] Reprocessing audit log (who replayed, when, result)
  - [ ] ADR: `004-reprocessing-strategy.md`
- [ ] Scheduling: periodic scraping per source (configurable interval, Celery Beat)
- [ ] Worker observability:
  - [ ] Metrics: jobs scraped, failures, latency, DLQ size; Prometheus endpoint on workers
  - [ ] Log aggregation: structured logs → ELK (Elasticsearch + Logstash + Kibana) or simple file‑based initially
- [ ] Dashboard: source health overview, recent scrape log, DLQ status
- [ ] ADR: `005-scraping-resilience-patterns.md`

---

## Phase 3 – Master CV, JD Parsing & CV Tailoring (2–3 weeks)

**Goal:** Intelligent CV customization based on job descriptions.

- [ ] JD parsing service (worker):
  - [ ] Extract keywords, required skills, years of experience, education using spaCy/regex
  - [ ] Store parsed JD structure alongside job record
- [ ] Master CV structure: pre‑tag experiences and skills with keywords; allow manual annotation
- [ ] CV Tailoring engine:
  - [ ] Rule‑based: match required skills against master CV, select relevant bullet points, reorder sections
  - [ ] Generate output: fill a LaTeX or HTML template, convert to PDF (weasyprint/pandoc)
  - [ ] Optional LLM enhancement: call OpenAI/self‑hosted model to rephrase selected bullet points using JD language (controlled prompt, rate limited)
  - [ ] Store generated CV as versioned attachment; user can review and adjust
  - [ ] ADR: `006-rule-based-vs-llm-tailoring.md`
- [ ] Frontend:
  - [ ] "Tailor CV for this job" button on job detail page
  - [ ] Side‑by‑side preview of JD and generated CV with manual edit capability
  - [ ] Download as PDF/DOCX

---

## Phase 4 – Matching Alerts & Notifications (1–2 weeks)

**Goal:** Users receive timely alerts when new jobs match their criteria.

- [ ] Alert criteria model: user creates saved search (keywords, companies, locations, remote, etc.)
- [ ] Matching engine (worker): when `job.new` event arrives, evaluate against all active criteria
- [ ] Notification delivery:
  - [ ] Email notifications (SMTP + templating, Mailpit for local)
  - [ ] In‑app notifications (stored in DB, displayed in UI)
  - [ ] Optional push notifications (Firebase)
- [ ] User preferences: notification frequency (instant, daily digest), channels
- [ ] Observability: matching rate, notification delivery success
- [ ] ADR: `007-matching-and-alerting.md`

---

## Phase 5 – Observability, Data Quality, Search & Dashboards (2–3 weeks)

**Goal:** Full pipeline visibility, high‑quality data, production‑grade search, and operational dashboards.

### Observability & Database Performance

- [ ] OpenTelemetry: trace propagation from API → Celery workers → RabbitMQ
- [ ] ELK stack: scrape logs, worker logs, error logs indexed; Kibana dashboards for scraper success/failure rates, data quality trends
- [ ] Grafana: RED dashboards for API, worker queues, scraper throughput, search latency
- [ ] Structured logging: JSON format, trace ID in every log line
- [ ] Database performance:
  - [ ] `EXPLAIN ANALYZE` for job search queries, alert matching queries
  - [ ] Index tuning (full‑text search on JD text, keywords)
  - [ ] Connection pooling (asyncpg pool size tuning)
  - [ ] Write report: `docs/database-performance.md`

### Data Quality Pipeline & Dashboard

- [ ] Data quality scoring: assign completeness score per job (fields present, parsing confidence)
- [ ] Duplicate detection: fuzzy matching on title + company + date; mark duplicates, retain canonical
- [ ] Normalization workers (triggered by `job.new` events):
  - [ ] Company name normalization (e.g., "Google LLC" → "Google") via mapping table or external API
  - [ ] Job title normalization (e.g., "Sr. SWE" → "Senior Software Engineer") via rules/LLM
  - [ ] Skill taxonomy normalization (e.g., "React.js" → "React") via curated dictionary
- [ ] Data quality dashboard: overall quality score, duplicates found, normalization coverage, per‑source breakdown
- [ ] ADR: `008-data-quality-normalization.md`

### Search Architecture

- [ ] Implement PostgreSQL Full‑Text Search (`tsvector` on title, company, description; `tsquery` with ranking)
- [ ] Search relevance tuning: weight title > description, test with sample queries, document scoring
- [ ] Search performance analysis: `EXPLAIN ANALYZE` on FTS queries, index size, latency under load
- [ ] Evaluation document: compare PostgreSQL FTS vs Elasticsearch/OpenSearch (scalability, relevance features, operational cost) — no implementation needed, just tradeoff analysis
- [ ] ADR: `009-search-architecture.md`

### Reprocessing & DLQ Dashboard

- [ ] Admin UI: view DLQ entries, filter by source/error, select and replay individual or batch jobs
- [ ] Reprocessing success/failure metrics integrated into Grafana

- [ ] Load testing: simulate many concurrent scrapes, measure worker throughput, queue backlog, search performance

---

## Phase 6 – Security Hardening & Audit Investigation Dashboard (1 week)

**Goal:** Production‑grade security and compliance visibility.

- [ ] Threat model: simple STRIDE on API and scrapers
- [ ] RBAC: admin role to manage all sources, view system health, manage reprocessing
- [ ] Audit log dashboard: admin‑only view, search audit events by user, action, date; includes reprocessing actions
- [ ] Dependency & container scanning in CI
- [ ] Secrets rotation practice
- [ ] Rate limiting on API endpoints to prevent abuse

---

## Phase 7 – Resilience, Chaos Experiments & Incident Postmortem (1–2 weeks)

**Goal:** Prove system robustness under failure.

- [ ] Chaos experiments:
  - [ ] Kill RabbitMQ; verify workers retry and queue persists after recovery
  - [ ] Simulate scraper target HTML change: cause parsing errors; verify DLQ capture and alert
  - [ ] Exhaust worker memory; verify graceful handling, no data corruption
  - [ ] Simulate a data quality drop due to normalization rule failure; verify dashboard alert
- [ ] Incident simulation: major job board change breaks all scrapers for that source, causing data quality degradation
  - [ ] Write postmortem: `docs/postmortems/001-scraper-outage-data-quality.md`
- [ ] Runbooks: scraper failure recovery, RabbitMQ queue flush, database failover (if applicable), data quality incident response

---

## Phase 8 – Cost Awareness, Capacity Planning & Portfolio Polish (1 week)

**Goal:** Demonstrate operational and business awareness.

- [ ] Cost estimation: monthly cost for cloud resources (compute, RDS, S3, ELK), scaled for 50 sources hourly scraping
- [ ] Scaling projection: 500 sources, 10k users; identify bottlenecks (search, database, workers)
- [ ] Capacity plan: worker count vs scraping frequency, storage retention for JDs and raw HTML, search index size
- [ ] Final documentation:
  - [ ] Architecture diagram (C4)
  - [ ] `README.md` with demo, setup, stakeholder guide
  - [ ] All ADRs, runbooks, postmortems linked
  - [ ] `docs/tradeoffs.md`
- [ ] Demo video: scraping workflow, data quality dashboard, CV tailoring, alert notification, reprocessing

---

## Completion Checklist – Job Application Tracker

- [ ] Multi‑source job scraping with resilience (circuit breaker, retries, DLQ, idempotency)
- [ ] Event schema versioning and backward compatibility documented; ADR
- [ ] Reprocessing workflow with DLQ replay and admin dashboard; ADR
- [ ] Data quality scoring, duplicate detection, normalization (company, title, skills); ADR
- [ ] Data quality dashboard with per‑source metrics
- [ ] PostgreSQL Full‑Text Search with relevance tuning and performance analysis; Elasticsearch comparison documented; ADR
- [ ] Job search, filter, and detail view
- [ ] Master CV structured editor and versioning
- [ ] JD parsing and CV tailoring (rule‑based + optional LLM); ADR
- [ ] Application tracking pipeline (Kanban)
- [ ] Matching alert criteria and notification delivery (email + in‑app)
- [ ] ELK‑based scraper log aggregation and health dashboard
- [ ] Full observability: traces, metrics, structured logging, RED dashboards
- [ ] Database performance tuning and report
- [ ] Security: RBAC, audit log dashboard, dependency scanning, secrets rotation
- [ ] Chaos experiments and incident postmortem
- [ ] Cost estimate, capacity plan
- [ ] All ADRs (9 total), runbooks, portfolio artifacts complete