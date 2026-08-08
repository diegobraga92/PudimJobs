# ADR 002: Data Model Design

## Status

Accepted (2026-08-08)

## Context

PudimJobs needs to persist four core domains before scraping exists:

- **Sources** — job boards / career pages / RSS feeds that will later be scraped
- **Jobs** — job postings (manually added in Phase 1, scraped from Phase 2)
- **Master CV** — a structured, versioned CV the user maintains
- **Applications** — one per job, tracking the pipeline status

Additional constraints from the product plan:

- Every table is owned by a user (data isolation / RBAC seed).
- Scraped jobs must be insertable idempotently (URL + source uniqueness).
- The master CV will be *parsed and tailored* in Phase 3, so it must be
  machine-readable but flexible enough to evolve.
- PostgreSQL is the only database (dev and prod); asyncpg is the driver.

## Decision

### UUID primary keys everywhere

All tables use `uuid.UUID` primary keys with client-generated `uuid.uuid4()`
defaults. Auto-increment integers are rejected because:

- Async workers (Phase 2) will create rows independently; UUIDs avoid
  coordination and sequence gaps.
- IDs are exposed in URLs/APIs; sequential IDs leak data cardinality.

### `user_id` column on every owned table

`sources`, `jobs`, `master_cv`, and `applications` all carry `user_id` with a
foreign key to `users(id)` (`ON DELETE CASCADE`). All queries scope by the
authenticated user's ID, which implements the "user sees only own data"
requirement without relying on row-level security.

### Master CV as versioned `structured_json` (JSONB)

`master_cv` stores the CV content as a JSONB document with a per-user
monotonically increasing `version` and a single `is_current` flag:

- Creates are immutable snapshots; editing produces a *new* version. This
  matches the plan's "versioned attachment" requirement and gives free history.
- A defined JSON shape (`summary`, `experience[]`, `education[]`, `skills[]`,
  `projects[]`) is validated by Pydantic on write, while JSONB keeps the
  storage schema unchanged as the shape evolves in Phase 3.

Rejected alternative: fully normalized tables (`cv_experience`,
`cv_education`, …). More join complexity, no Phase 1 benefit, and would make
snapshotting/versioning harder.

### JSONB tags on jobs

`jobs.tags` is a JSONB text array. Filtering uses the native `?|` overlap
operator against a `text[]` parameter. PostgreSQL-only — acceptable because
the project is PostgreSQL-exclusive.

### Enums as string enums (not native PG enum types)

`source.type`, `source.health`, and `application.status` are Python
`enum.StrEnum` classes mapped with `native_enum=False`. SQLAlchemy emits
`VARCHAR` + `CHECK` constraints. Rationale:

- Alembic migrations with native PG enums are notoriously brittle (type
  rename/drop issues); string enums keep migrations additive and simple.
- The application is the single writer, so DB-level `CHECK` + app-level
  Pydantic validation is sufficient protection.

### Uniqueness for idempotent inserts

`jobs` has a composite unique constraint on `(source_id, url)`. PostgreSQL's
NULL semantics mean manually-added jobs (no source/URL) are not constrained,
while scraped jobs (Phase 2) can rely on it for deduplication.

## Consequences

### Positive

- Clean user isolation with simple `WHERE user_id = :id` predicates.
- CV history is free and queryable.
- Idempotent job ingestion is database-enforced.
- Migrations stay simple (no PG-enum gymnastics).

### Negative / Risks

- JSONB CV content is not directly queryable via SQL joins — the tailoring
  engine must load and parse it in Python (Phase 3).
- Tag filtering with `?|` requires explicit `text[]` casts (asyncpg binds
  Python lists as JSONB otherwise).
- Client-generated UUIDs make data deduplication/reconciliation across
  environments slightly harder to eyeball.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Integer auto-increment PKs | Sequence coordination across async workers; leaks cardinality |
| Normalized CV tables | No Phase 1 benefit; complicates snapshotting |
| Native PostgreSQL enums | Alembic migration fragility |
| SQLite/other DBs | PostgreSQL FTS (Phase 5) is a core feature; JSONB and `?|` rely on PG |
