# Engineering Tradeoffs

Every significant decision is captured in an ADR under `docs/adr/`. This page
summarises the trade-offs at a glance.

| Decision | ADR | Chosen over | Why |
|----------|-----|-------------|-----|
| Python + FastAPI backend | 001 | Django, Flask, Node.js, Go | Async-native; best data/ML ecosystem (spaCy, bs4) |
| UUID PKs, JSONB CV, string enums | 002 | auto-increment, native PG enums, normalised CV tables | No sequence coordination for async workers; migration safety; snapshot-able CV |
| Versioned JSON events | 003 | Avro/Protobuf schema registry | Lighter infra; additive-only versioning is enough at this scale |
| DB-backed DLQ (`scrape_runs`) | 004 | Consuming RabbitMQ DLQ directly | Queryable, auditable, survives broker restarts; failed runs replayable |
| Redis circuit breaker | 005 | In-process state | Shared across workers, survives restarts, auto-resets by TTL |
| Rule-based + optional LLM tailoring | 006 | LLM-only | Deterministic + free by default; LLM is a feature-flagged polish layer |
| Dedicated RabbitMQ consumer | 007 | Chaining match inside scrape | Broker buffers `job.new`; one event feeds many consumers |
| Dedicated `scrape_quality` table | 008 | Columns on `jobs` | Independent lifecycle; re-assessments are an upsert |
| PostgreSQL FTS | 009 | Elasticsearch/OpenSearch | $0 extra infra; sub-ms at 10⁵ rows; ES only needed beyond 10⁶ |
| Normalized extract only (no raw HTML) | 004 | Re-fetch on reprocess | Avoids copyright/ToS and storage exposure; recovery = re-scrape |
| `NullPool` connections | database-performance.md | Pooled sessions | Correct for short-lived worker tasks; switch at >1k req/s |

## Related operational docs

- [SLOs](slo.md) — availability 99.5%, scraping freshness, search latency
- [Threat model](stride-threat-model.md) — STRIDE for API + scrapers
- [Database performance](database-performance.md) — `EXPLAIN ANALYZE` + index plan
- [Search evaluation](elasticsearch-comparison.md) — PG FTS vs OpenSearch
- [Secrets rotation](secrets-rotation.md) — per-secret rotation procedures
- [Cost estimate](cost-estimate.md) · [Capacity plan](capacity-plan.md)
- [Runbooks](runbooks/) · [Postmortems](postmortems/)
