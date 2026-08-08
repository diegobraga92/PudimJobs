# ADR 008: Data Quality & Normalization

## Status

Accepted (2026-08-08)

## Context

Scraped jobs arrive with inconsistent values: "Google LLC" vs "Google",
"Sr. SWE" vs "Senior Software Engineer", "React.js" vs "React". The product
needs reliable search, deduplication, and credible data-quality reporting.

## Decision

### A dedicated `scrape_quality` table (not columns on `jobs`)

Each job gets exactly one `scrape_quality` row: `completeness_score`,
`normalized_company`, `normalized_title`, `is_duplicate`, `canonical_job_id`,
`issues[]`. Rationale:

- Keeps `jobs` focused on what scrapers produce; quality metadata is
  independently queryable and replaceable (re-assessments update the row).
- A separate table lets us add assessment dimensions without touching the
  ingestion path.

### Multi-pass normalization

1. **Company** — exact lookup against `app/data/company_map.json`
   ("Google LLC" → "Google"), falling back to legal-suffix stripping
   ("Acme Manufacturing Inc." → "Acme Manufacturing").
2. **Title** — dictionary of common variants in `title_map.json`
   ("Sr. SWE" → "Senior Software Engineer"); unmapped titles pass through.
3. **Skills** — the skill taxonomy's `aliases` table maps synonyms to
   canonicals ("React.js" → "react"); normalized tags are written back to
   `jobs.tags` in place.

### Completeness scoring

Weighted sum in [0, 1]: title 0.3, company 0.2, description ≥ 200 chars 0.2,
posted_date 0.15, tags 0.15. Simple, explainable, and enough to flag
low-quality rows in dashboards.

### Duplicate detection (fuzzy, cross-source)

`difflib.SequenceMatcher` on title + company with threshold 0.9 and posted-date
proximity ≤ 1 day; the earliest job is canonical. This catches near-identical
postings across sources (e.g. an aggregator and a career page).

### Triggering

A `data quality` Celery task is dispatched from the same `job.new` event
consumer as alert matching — one event, multiple consumers (reuses ADR 003/007
infrastructure).

## Consequences

### Positive

- Search/dedup operate on normalized values; duplicates are flaggable.
- Quality dashboards are cheap aggregate queries over one table.
- Failures are isolated (per-job assessment; no ingestion coupling).

### Negative / Risks

- Fuzzy matching is O(n) per job against recent jobs; bounded by a 500-job
  window and only run once per job.
- Dictionaries are static files — they must be maintained (a DB-backed or
  LLM-driven normalizer is a future enhancement).

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Columns on `jobs` | Couples ingestion schema to quality metadata |
| External company API | Cost + network dependency for marginal benefit at this scale |
| Exact-match dedup only | Misses near-duplicate postings across sources |
