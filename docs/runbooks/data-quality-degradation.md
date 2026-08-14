# Runbook: Data Quality Degradation

**Symptoms:** Admin → Data Quality shows avg completeness dropping or
duplicates rising; specific sources underperforming in the per-source table.

## Investigation

1. Open **Admin → Data Quality** (or the API):
   ```bash
   curl -s http://localhost:8000/api/admin/quality/overview \
     -H "Authorization: Bearer $TOKEN"
   curl -s http://localhost:8000/api/admin/quality/by-source \
     -H "Authorization: Bearer $TOKEN"
   ```
2. Identify the affected source(s) and the dominant issue:
   - **Low completeness** → missing fields (short descriptions, no posted
     date, no tags) — usually a scraper/format change.
   - **Rising duplicates** → a new source is cross-posting known jobs.
   - **Normalization coverage dropping** → company/title mapping gaps.

## Resolution

### Completeness drop

1. Inspect raw scraped data (`GET /api/jobs/{id}` for affected jobs).
2. Fix the parser if the source format changed (see `scraper-failure.md`).
3. Re-scrape the affected source(s) to refresh jobs and quality:
   ```bash
   curl -X POST http://localhost:8000/api/admin/sources/<source_id>/scrape \
     -H "Authorization: Bearer $TOKEN"
   ```

### Duplicates rising

1. Confirm the duplicates are real (expand the job's `issues` — it records
   `possible duplicate of <canonical_id>`).
2. Adjust the fuzzy threshold in `app/services/quality.py`
   (`is_duplicate_of` `threshold`), or exclude the noisy source.
3. Re-assess the affected jobs (the `assess_quality` task reruns per job).

### Normalization gaps

1. Add the missing mapping to `app/data/company_map.json` or
   `title_map.json` (deploy = code change).
2. Re-run quality for affected jobs (re-trigger a scrape).

## Verification

- [ ] `quality/overview` average completeness back to baseline.
- [ ] Duplicate count stable.
- [ ] Per-source table shows healthy scores.
