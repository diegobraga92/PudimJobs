# ADR 009: Search Architecture

## Status

Accepted (2026-08-08)

## Context

Phase 1 shipped keyword search as `ILIKE` over title/company/description.
Phase 5 must deliver relevance-ranked search with defensible performance and a
documented trade-off against a dedicated search engine (Elasticsearch /
OpenSearch).

## Decision

### PostgreSQL Full-Text Search (FTS) as the primary search engine

- A **generated stored `tsvector` column** (`search_vector`) with
  `setweight(to_tsvector('english', title), 'A') || ... company 'B' ...
  description 'C'` — title-weighted, maintained by the database.
- A **GIN index** (`ix_jobs_search_vector`) powers `@@` lookups.
- Queries use `plainto_tsquery` + `ts_rank`, ordered by rank (title matches
  outrank description-only matches).
- The API exposes a per-result `score` so the UI can show relevance.

Performance (real `EXPLAIN ANALYZE`, 2k rows): FTS ≈ 0.7 ms vs ILIKE ≈ 2.1 ms;
the GIN index engages at ≥10⁴–10⁵ rows where seq scans stop being optimal.

### Elasticsearch/OpenSearch: documented, not deployed

Full trade-off analysis in `docs/elasticsearch-comparison.md`. PG FTS is
selected because:

- The corpus (≈2.5k live jobs, ~10⁵ historical) is far below the scale where
  ES becomes necessary.
- No faceted browsing, typo tolerance, or search-as-you-type requirements.
- ES adds a ~1 GB cluster and operational burden for no measurable benefit now.

### Migration path

If a future phase needs BM25, fuzzy search, or multi-tenant isolation at scale,
the existing `job.new` event bus (ADR 003) feeds an ES index as an additional
consumer without changing the API contract.

## Consequences

### Positive

- Relevance-ranked search with near-zero infra cost.
- Generated column = no application-side index maintenance.
- The evaluation document satisfies the plan's ES-comparison requirement.

### Negative / Risks

- FTS lacks native fuzzy/typo tolerance and fine-grained relevance tuning.
- English-only config; other languages require additional dictionaries.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Elasticsearch/OpenSearch now | Infra cost ≫ benefit at this scale |
| Keep ILIKE | 3× slower, no relevance, no stemming |
| pg_trgm (similarity) | Different feature set (fuzzy vs keyword); not additive to FTS |
