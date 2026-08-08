# Event Schema Changelog

## Compatibility Rules

1. **Additive only** — a new field MUST be optional with a sensible default
   (e.g. `None`, `False`, `[]`). Consumers of older versions must be able to
   deserialize the payload without error.
2. **Deprecation window** — a deprecated field keeps its default for **two**
   schema versions before removal.
3. **Consumers declare versions** — each consumer records the highest schema
   version it understands and treats higher versions as forward-compatible.

## Versions

### v1 (initial)

Fields: `version`, `event_id`, `job_id`, `source_id`, `title`, `company`,
`url`, `posted_date`, `tags`, `timestamp`.

Published on routing key `job.new.v1`.

### v2 (planned)

Adds `salary_range: str | None = None` and `remote: bool | None = None`.
Published on routing key `job.new.v2`. Consumers bound to `job.new.#` receive
both v1 and v2 payloads; the `version` field disambiguates.
