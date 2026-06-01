# ADR 001: Use Python + FastAPI for the Backend

## Status

Accepted (2026-01-06)

## Context

The PudimJobs backend needs to:

- Expose a REST API for the Angular frontend
- Integrate with PostgreSQL via async drivers
- Support Celery workers for asynchronous scraping and data processing
- Generate OpenAPI documentation automatically
- Be well-suited for data processing tasks (parsing HTML, text processing)
- Run efficiently with async I/O for database and HTTP calls

Options considered:

1. **FastAPI** — Async-native Python framework with Pydantic validation and auto-generated OpenAPI
2. **Django** — Full-featured framework with ORM, admin, ecosystem; less async-native
3. **Flask** — Lightweight but sync-only by default; requires extensions for async
4. **Node.js + Express** — Well-suited for I/O but less ideal for data/ML tasks
5. **Go** — Performant but higher development velocity cost for Python-oriented team

## Decision

Use **Python + FastAPI** as the backend framework.

## Consequences

### Positive

- **Native async/await** — Works naturally with asyncpg, SQLAlchemy async, and httpx
- **Automatic OpenAPI** — FastAPI generates OpenAPI 3.1 docs from Pydantic models, reducing contract drift
- **Pydantic v2** — Fast, well-typed validation for request/response models
- **Great Celery integration** — FastAPI's async support pairs well with Celery tasks for scraping and processing
- **Strong data ecosystem** — Python's spaCy, BeautifulSoup, pandas, and scikit-learn are needed in later phases
- **Active community** — FastAPI is widely adopted with extensive documentation

### Negative / Risks

- **Smaller ecosystem than Django** — Fewer "batteries included" packages; admin panel, auth, and ORM must be assembled manually
- **Celery + FastAPI boilerplate** — Unlike Django-Celery which auto-configures, Celery must be wired up explicitly in FastAPI (acceptable for Phase 1+)
- **No built-in admin** — Will need a custom admin interface or integrate a library like SQLAdmin
- **Runtime performance** — Python is slower than Go or Rust for CPU-bound tasks; scraping workers may need horizontal scaling sooner

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Django | Heavy ORM overhead, less async-native; overkill for API-focused service |
| Flask | Requires async extensions (Quart) or manual ASGI setup; less structured validation |
| Node.js/Express | Weaker ecosystem for data processing (no spaCy, BeautifulSoup equivalent) |
| Go | Higher development cost; team convention is Python for data projects |