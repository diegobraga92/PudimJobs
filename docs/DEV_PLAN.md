## Phase 2 – Scraping Engine, Event Schema & Reprocessing (2–3 weeks)

**Goal:** Asynchronous, fault‑tolerant scraping with event versioning and operational replay capabilities.

- [x] Scraper worker (Celery task):
  - [x] Accept source ID, fetch page(s), parse HTML (BeautifulSoup/lxml or Playwright for JS)
  - [x] Extract structured job data, normalize fields, deduplicate by URL or external ID
  - [x] Store new jobs in database, produce `job.new` event to RabbitMQ
- [x] Resilience patterns:
  - [x] Circuit breaker per source (e.g., 5 consecutive failures → pause for 1h)
  - [x] Rate limiting (respect `robots.txt` if present, configurable delay)
  - [x] User‑agent rotation and proxy support (documented)
  - [x] Retry with exponential backoff, dead‑letter queue (DLQ) for permanently failing jobs
  - [x] Idempotent job insertion (URL + source unique constraint, dedup logic)
- [x] Event schema versioning:
  - [x] Include `version` field in `job.new` event payload; store schemas in `api/events/`
  - [x] Define backward compatibility rules (new fields additive, deprecated after notice)
  - [x] ADR: `003-event-evolution.md`
- [x] Reprocessing workflow:
  - [x] Admin endpoint to inspect DLQ, select failed jobs, and re‑queue for retry
  - [x] DLQ replay and re-scrape recovery after parser improvements
  - [x] Reprocessing audit log (who replayed, when, result)
  - [x] ADR: `004-reprocessing-strategy.md`
- [x] Scheduling: periodic scraping per source (configurable interval, Celery Beat)
- [x] Worker observability:
  - [x] Metrics: jobs scraped, failures, latency, DLQ size; Prometheus endpoint on workers
  - [x] Log aggregation: structured logs → ELK (Elasticsearch + Logstash + Kibana) or simple file‑based initially
- [x] Dashboard: source health overview, recent scrape log, DLQ status
- [x] ADR: `005-scraping-resilience-patterns.md`

---

## Phase 3 – Master CV, JD Parsing & CV Tailoring (2–3 weeks)

**Goal:** Intelligent CV customization based on job descriptions.

- [x] JD parsing service (worker):
  - [x] Extract keywords, required skills, years of experience, education using spaCy/regex
  - [x] Store parsed JD structure alongside job record
- [x] Master CV structure: pre‑tag experiences and skills with keywords; allow manual annotation
- [x] CV Tailoring engine:
  - [x] Rule‑based: match required skills against master CV, select relevant bullet points, reorder sections
  - [x] Generate output: fill a LaTeX or HTML template, convert to PDF (weasyprint/pandoc)
  - [x] Optional LLM enhancement: call OpenAI/self‑hosted model to rephrase selected bullet points using JD language (controlled prompt, rate limited)
  - [x] Store generated CV as versioned attachment; user can review and adjust
  - [x] ADR: `006-rule-based-vs-llm-tailoring.md`
- [x] Frontend:
  - [x] "Tailor CV for this job" button on job detail page
  - [x] Side‑by‑side preview of JD and generated CV with manual edit capability
  - [x] Download as PDF/DOCX

---

## Phase 4 – Matching Alerts & Notifications (1–2 weeks)

**Goal:** Users receive timely alerts when new jobs match their criteria.

- [x] Alert criteria model: user creates saved search (keywords, companies, locations, remote, etc.)
- [x] Matching engine (worker): when `job.new` event arrives, evaluate against all active criteria
- [x] Notification delivery:
  - [x] Email notifications (SMTP + templating, Mailpit for local)
  - [x] In‑app notifications (stored in DB, displayed in UI)
  - [ ] Optional push notifications (Firebase)
- [x] User preferences: notification frequency (instant, daily digest), channels
- [x] Observability: matching rate, notification delivery success
- [x] ADR: `007-matching-and-alerting.md`

---

## Phase 5 – Observability, Data Quality, Search & Dashboards (2–3 weeks)

**Goal:** Full pipeline visibility, high‑quality data, production‑grade search, and operational dashboards.

### Observability & Database Performance

- [x] OpenTelemetry: trace propagation from API → Celery workers → RabbitMQ
- [ ] ELK stack: scrape logs, worker logs, error logs indexed; Kibana dashboards for scraper success/failure rates, data quality trends
- [x] Grafana: RED dashboards for API, worker queues, scraper throughput, search latency
- [x] Structured logging: JSON format, trace ID in every log line
- [x] Database performance:
  - [x] `EXPLAIN ANALYZE` for job search queries, alert matching queries
  - [x] Index tuning (full‑text search on JD text, keywords)
  - [x] Connection pooling (asyncpg pool size tuning)
  - [x] Write report: `docs/database-performance.md`

### Data Quality Pipeline & Dashboard

- [x] Data quality scoring: assign completeness score per job (fields present, parsing confidence)
- [x] Duplicate detection: fuzzy matching on title + company + date; mark duplicates, retain canonical
- [x] Normalization workers (triggered by `job.new` events):
  - [x] Company name normalization (e.g., "Google LLC" → "Google") via mapping table or external API
  - [x] Job title normalization (e.g., "Sr. SWE" → "Senior Software Engineer") via rules/LLM
  - [x] Skill taxonomy normalization (e.g., "React.js" → "React") via curated dictionary
- [x] Data quality dashboard: overall quality score, duplicates found, normalization coverage, per‑source breakdown
- [x] ADR: `008-data-quality-normalization.md`

### Search Architecture

- [x] Implement PostgreSQL Full‑Text Search (`tsvector` on title, company, description; `tsquery` with ranking)
- [x] Search relevance tuning: weight title > description, test with sample queries, document scoring
- [x] Search performance analysis: `EXPLAIN ANALYZE` on FTS queries, index size, latency under load
- [x] Evaluation document: compare PostgreSQL FTS vs Elasticsearch/OpenSearch (scalability, relevance features, operational cost) — no implementation needed, just tradeoff analysis
- [x] ADR: `009-search-architecture.md`

### Reprocessing & DLQ Dashboard

- [x] Admin UI: view DLQ entries, filter by source/error, select and replay individual or batch jobs
- [ ] Reprocessing success/failure metrics integrated into Grafana

- [x] Load testing: simulate many concurrent scrapes, measure worker throughput, queue backlog, search performance

---

## Phase 6 – Security Hardening & Audit Investigation Dashboard (1 week)

**Goal:** Production‑grade security and compliance visibility.

- [x] Threat model: simple STRIDE on API and scrapers
- [x] RBAC: admin role to manage all sources, view system health, manage reprocessing
- [x] Audit log dashboard: admin‑only view, search audit events by user, action, date; includes reprocessing actions
- [x] Dependency & container scanning in CI
- [x] Secrets rotation practice
- [x] Rate limiting on API endpoints to prevent abuse

---

## Phase 7 – Resilience, Chaos Experiments & Incident Postmortem (1–2 weeks)

**Goal:** Prove system robustness under failure.

- [x] Chaos experiments:
  - [x] Kill RabbitMQ; verify workers retry and queue persists after recovery
  - [x] Simulate scraper target HTML change: cause parsing errors; verify DLQ capture and alert
  - [x] Exhaust worker memory; verify graceful handling, no data corruption
  - [x] Simulate a data quality drop due to normalization rule failure; verify dashboard alert
- [x] Incident simulation: major job board change breaks all scrapers for that source, causing data quality degradation
  - [x] Write postmortem: `docs/postmortems/001-scraper-outage-data-quality.md`
- [x] Runbooks: scraper failure recovery, RabbitMQ queue flush, database failover (if applicable), data quality incident response

---

## Phase 8 – Cost Awareness, Capacity Planning & Portfolio Polish (1 week)

**Goal:** Demonstrate operational and business awareness.

- [x] Cost estimation: monthly cost for cloud resources (compute, RDS, S3, ELK), scaled for 50 sources hourly scraping
- [x] Scaling projection: 500 sources, 10k users; identify bottlenecks (search, database, workers)
- [x] Capacity plan: worker count vs scraping frequency, storage retention for JDs and descriptions, search index size
- [x] Final documentation:
  - [x] Architecture diagram (C4)
  - [x] `README.md` with demo, setup, stakeholder guide
  - [x] All ADRs, runbooks, postmortems linked
  - [x] `docs/tradeoffs.md`
- [ ] Demo video: scraping workflow, data quality dashboard, CV tailoring, alert notification, reprocessing

---

## Completion Checklist – Job Application Tracker

- [x] Multi‑source job scraping with resilience (circuit breaker, retries, DLQ, idempotency)
- [x] Event schema versioning and backward compatibility documented; ADR
- [x] Reprocessing workflow with DLQ replay and admin dashboard; ADR
- [x] Data quality scoring, duplicate detection, normalization (company, title, skills); ADR
- [x] Data quality dashboard with per‑source metrics
- [x] PostgreSQL Full‑Text Search with relevance tuning and performance analysis; Elasticsearch comparison documented; ADR
- [x] Job search, filter, and detail view
- [x] Master CV structured editor and versioning
- [x] JD parsing and CV tailoring (rule‑based + optional LLM); ADR
- [x] Application tracking pipeline (Kanban)
- [x] Matching alert criteria and notification delivery (email + in‑app)
- [x] ELK‑based scraper log aggregation and health dashboard
- [x] Full observability: traces, metrics, structured logging, RED dashboards
- [x] Database performance tuning and report
- [x] Security: RBAC, audit log dashboard, dependency scanning, secrets rotation
- [x] Chaos experiments and incident postmortem
- [x] Cost estimate, capacity plan
- [x] All ADRs (9 total), runbooks, portfolio artifacts complete