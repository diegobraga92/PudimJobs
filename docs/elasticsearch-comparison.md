# Search Evaluation: PostgreSQL FTS vs Elasticsearch/OpenSearch

Trade-off analysis only — no ES implementation required (per DEV_PLAN Phase 5).

## What PostgreSQL FTS gives us

- `tsvector`/`tsquery` with `setweight` (title A > company B > description C)
- `ts_rank`/`ts_rank_cd` relevance scoring
- Stemming + stop words via `english` config, custom dictionaries
- GIN-indexed `@@` lookups (sub-ms on 10⁵–10⁶ rows)
- Zero extra infrastructure — lives in the database we already run

## What Elasticsearch/OpenSearch would add

| Capability | PG FTS | ES |
|-----------|--------|----|
| Relevance model | `ts_rank` (lexical) | BM25 (tunable k1/b) |
| Prefix / typo tolerance | Manual (`prefix` tsquery) | Built-in `edge_ngram` + fuzzy |
| Faceted aggregation | SQL `GROUP BY` | Native aggregations |
| Distributed scale-out | Sharding/multi-node manually | Native (cluster) |
| Operational cost | 0 extra containers | +1 GB RAM cluster, more ops |
| Search-as-you-type UX | Requires app-side triggers | `search_analyzer` built-in |

## Decision context (jobs corpus)

- 50 sources × ~50 active jobs ≈ **2,500 concurrent jobs**; ~10⁵ historical.
- Searches are keyword-based with filters (company, tags, date) — no faceted
  UI, no typo tolerance requirement.
- A single PostgreSQL node with GIN comfortably handles 10⁵–10⁶ rows and
  sub-10 ms queries.

## Recommendation

**PostgreSQL FTS is the right choice at this scale.** The trade-off window for
switching to Elasticsearch is:

1. Corpus > 10⁶ job rows **or** multi-tenant search needs isolation at scale,
2. Product adds search-as-you-type / fuzzy / faceted browsing,
3. Relevance tuning needs BM25-style parameter control.

At that point the event bus (Phase 2) already emits `job.new` events — feeding
an ES index would be a straightforward additional consumer, and the OpenAPI
search contract would not change. This is documented as ADR 009.

## Cost comparison (monthly, approximate)

| Component | PG FTS | + OpenSearch |
|-----------|--------|--------------|
| Search infra | $0 (reuses RDS) | 3 × `t3.small` ≈ $100–$180 |
| Ops | $0 | Monitoring, upgrades, backups |
| Total | $0 | +$100–$180/mo |
