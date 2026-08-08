# ADR 003: Event Schema Evolution

## Status

Accepted (2026-08-08)

## Context

The scraping engine publishes a `job.new` event to RabbitMQ whenever a new job
is stored. Future consumers (matching alerts in Phase 4, data-quality workers
in Phase 5) will consume these events. Producers and consumers evolve
independently, so the event contract needs explicit versioning rules to avoid
breaking consumers when new job attributes (e.g. `salary_range`, `remote`)
are added later.

## Decision

### Versioned JSON payloads on a topic exchange

- Events are JSON, published to the durable topic exchange `pudimjobs.events`.
- Routing keys are version-scoped: `job.new.v1`, `job.new.v2`, …
- Every event carries a `version` field (integer, starting at 1).
- A consumer binds with the wildcard `job.new.#` and checks the `version`
  field before parsing — a pattern that keeps the topology stable while the
  payload evolves.

### Compatibility contract

1. **Additive only** — new fields MUST be optional with a sensible default
   (`None`, `false`, `[]`). Existing consumers must be able to deserialize a
   newer payload without error.
2. **Deprecation window** — a deprecated field keeps its default for **two**
   schema versions before removal.
3. **Version bump** — any change other than adding an optional field is a new
   `version`, not an in-place edit of an existing one.

### Schema location

Schemas live in `api/events/` (Pydantic models + the `kombu` producer) so both
the API and the workers import the same definitions. A `CHANGELOG.md` records
per-version field lists and planned additions.

## Consequences

### Positive

- Consumers are safe against producer evolution.
- The routing key encodes the version for observability and testability.
- Pydantic validates payloads on both sides.

### Negative / Risks

- Consumers must be version-aware (check `version` before accessing fields).
- A missing `version` guard is a silent failure class; mitigated by a
  documented convention and code review.

## Alternatives Not Selected

| Option | Reason for Rejection |
|--------|---------------------|
| Avro/Protobuf with schema registry | Heavier infra for a small event set; JSON + versioning is sufficient |
| Versionless single schema with all-optional fields | Loses the ability to signal breaking changes |
| Queue-per-version (`job.new.v1.queue`) | Fragments consumers; wildcard binding is simpler |
