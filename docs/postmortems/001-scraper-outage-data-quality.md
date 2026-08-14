# Postmortem 001: Scraper Outage & Data Quality Degradation

> **Simulated incident** for portfolio/operational-readiness demonstration.
> The timeline and impacts are scripted (see `scripts/chaos/break_scraper_html.py`)
> and follow the standard blameless-postmortem template.

| Field | Value |
|-------|-------|
| **Incident ID** | INC-001 |
| **Severity** | SEV-2 (partial service degradation, no data loss) |
| **Detected** | 2026-08-15 14:03 UTC (automated) |
| **Resolved** | 2026-08-15 16:10 UTC |
| **Duration** | 2h 07m |
| **Status** | Resolved — action items assigned |

## Summary

A major job board redesigned its career page, changing the CSS class structure
its listings used. `CareerPageScraper` could not extract any job listings from
the new markup. Within 30 minutes the Redis-backed circuit breaker tripped
(5 consecutive failures), pausing scraping for the source entirely. The
`scrape_runs` table recorded failed runs with
`error = "'title' key missing in normalized output"`. The data-quality
dashboard showed the source's completeness dropping to 0 and 0 new jobs.

## Impact

- **Jobs missed:** ~40 job postings published during the 2h window were not
  ingested until the post-recovery re-scrape.
- **Alert coverage:** 12 users with alert rules matching this source received
  no notifications for new postings during the window.
- **Data loss:** none. The ~40 missed postings were recovered by re-scraping
  the source after the hotfix.

## Timeline (UTC)

| Time | Event |
|------|-------|
| 14:01 | Job board deploys new career-page layout. |
| 14:02 | Beat sweep enqueues the source's scrape. |
| 14:02–14:07 | 3 scrape attempts fail; Celery retries with backoff (1m→2m→4m). |
| 14:07 | Circuit breaker records 5th failure → source paused (health `failing`). |
| 14:03 | Data quality task (`assess_quality`) has no new jobs to assess; dashboard avg completeness unaffected but per-source shows `0 jobs`. |
| 15:10 | Operator notices `failing` source in the Admin UI during routine check. |
| 15:45 | Root cause identified: selectors in `career_page.py` no longer match. |
| 15:50 | Hotfix released with updated selectors + pre-normalization validation. |
| 16:00 | Re-scrape of the source recovers the postings published during the window. |
| 16:10 | 40 jobs recovered; source healthy; alerts back to normal. |

## Root Cause

**Primary:** `CareerPageScraper` relied on hardcoded CSS selectors
(`_TITLE_SELECTORS`, `_COMPANY_SELECTORS`) with no structural validation
before normalization. A site redesign silently broke extraction.

**Contributing:** No automated alerting on `source.health == failing` — the
circuit breaker paused the source correctly, but nobody was paged; the outage
was only caught on a routine dashboard check.

## Why It Wasn't Caught Earlier

1. The scraper tests use **fixed HTML fixtures** that matched the old markup;
   they didn't guard against *empty* parse results being treated as "0 jobs"
   rather than "parse failed".
2. The data-quality dashboard tracks completeness of **assessed** jobs, so a
   source producing zero jobs didn't move the aggregate number.

## What Worked

- **Circuit breaker** paused the source before it could hammer the target.
- **Re-scrape after the hotfix** recovered all missed postings.
- **DLQ + replay** surfaced the failures and re-enqueued the source.
- **Retry + backoff** absorbed transient failures without manual action.

## Corrective Actions

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Add pre-normalization validation: reject a scrape when `title`/`company` missing from **every** parsed item (fail fast, record error) | eng | Done — empty parses fail the scrape (2026-08-14) |
| 2 | Add Grafana alert on `source_health == failing` / circuit-breaker open (page on-call) | ops | Assigned |
| 3 | Scraper unit tests: add fixtures with changed/no-match markup asserting a *failed* scrape (not 0 jobs) | eng | Assigned |
| 4 | Data-quality dashboard: add per-source "expected jobs / actual jobs" drift metric | eng | Assigned |
| 5 | Schedule quarterly scraper-structure validation (re-run chaos script `break_scraper_html.py`) | ops | Assigned |

## Lessons Learned

- Parsers should **fail loudly** when a page yields no structured data, not
  silently return an empty list (implemented: empty parses now fail the run).
- Without stored raw input, recovery is a re-scrape — bounded by whether the
  site still serves the postings.
- Automated detection (health flag) without automated alerting is only
  half the loop.
