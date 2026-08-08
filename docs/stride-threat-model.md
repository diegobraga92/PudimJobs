# STRIDE Threat Model — PudimJobs

Simple STRIDE analysis for the API and scraping engine. Phase 6 deliverable.

## API

| Threat | Scenario | Mitigation | Status |
|--------|----------|-----------|--------|
| **S**poofing | Attacker forges a JWT | Signed HS256 with server secret; 24h expiry; bcrypt passwords | Implemented |
| **T**ampering | Modify a request in transit | TLS in production; request validation via Pydantic | Implemented |
| **R**epudiation | "I didn't do that" | `audit_logs` records CV/app/reprocessing mutations with user + timestamp; admin search UI | Implemented (Phase 6) |
| **I**nformation disclosure | User A reads user B's data | Every query scoped by `user_id`; admin endpoints behind `require_admin` | Implemented |
| **D**enial of service | Brute-force login / API flood | slowapi rate limits on login (5/min) and authenticated API (120/min) | Implemented (Phase 6) |
| **E**levation of privilege | User gains admin | Role checked in `require_admin` on every admin route | Implemented |

## Scraping engine (workers)

| Threat | Scenario | Mitigation | Status |
|--------|----------|-----------|--------|
| **S**poofing | A malicious site injects fake job data | Scraped data validated by Pydantic/ORM types; `raw_html` stored separately | Implemented |
| **T**ampering | Scraper payload tampered with | HTTPS fetches; user-agent rotation; no signed payloads needed (read-only) | Implemented |
| **I**nformation disclosure | Secrets leak into scraper tasks | Workers read only env vars needed (DB, broker); no cloud credentials mounted | Implemented |
| **D**enial of service | Scraping a target too fast / SSRF | Per-domain rate limiting + circuit breakers (Phase 2); robots.txt respect | Implemented |
| **E**levation of privilege | Worker escalates to DB admin | Workers use the application DB user (least privilege); no superuser | Implemented |

## Dependencies & supply chain

| Threat | Mitigation | Status |
|--------|-----------|--------|
| Known CVEs in pip packages | `pip-audit` in CI (Phase 6) | Implemented |
| Vulnerable base image | Trivy scan of Docker images in CI (Phase 6) | Implemented |
| Compromised dependency | `requirements.txt` pinned with `>=` + lock discipline; review on upgrade | Ongoing |

## Secrets

| Threat | Mitigation |
|--------|-----------|
| Dev secret in production | Secrets via env vars only; `.env` gitignored; rotation guide (`docs/secrets-rotation.md`) |

## Residual risks (accepted)

- No refresh-token rotation yet (access token expiry is the only bound).
- Rate limits are per-IP/per-token, not per-account — distributed brute force is
  partially mitigated by bcrypt cost.
- TLS is configured at the load balancer in production (Phase 8), not in the
  dev compose stack.
