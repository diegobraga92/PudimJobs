# Scraping & source coverage

How to onboard a job board, what the engine can collect **today**, what it
cannot, why, and what would unlock the rest. Companion to ADR 005 (resilience),
ADR 010 (discovery sources) and ADR 018 (manual watchlist sources).

## What a source can consume

| Source `type` | Adapter / provider | Consumes | Two-stage? |
|---|---|---|---|
| `career_page` | JSON-LD `JobPosting` → CSS fallback | one static HTML page | no |
| `aggregator` | `generic_html_list`, `embedded_json_list` | one static HTML *listing* page + optional `next_page` | yes, with `"detail": true` |
| `rss` | `feedparser` | RSS 2.0 / Atom feed (`url` **is** the feed URL) | no |
| `discovery` (ATS) | `ashby`, `greenhouse`, `lever`, `workable`, `smartrecruiters`, `recruitee`, `personio`, `workday` | public JSON board endpoint | no |
| `discovery` (JSON) | `json_list` | any JSON API (`paths` + `url_tpl`) | no |
| `discovery` (search) | `google_cse`, `bing`, `brave`, `serpapi`, `brightdata` | search results → detail pages | **yes** |
| `manual` | none — hand-checked | nothing; the user re-checks the board and the app reminds them | no |

Hard limits of the engine — these decide almost every verdict below:

1. **No JavaScript rendering** (`httpx` + BeautifulSoup). Client-side data
   (Angular, pure SPA) is invisible unless it is embedded as JSON
   (`embedded_json_list` reads `__NEXT_DATA__` / `window.__NUXT__`).
2. **No cookie/session auth.** `source_auth` supports `none`, `token` (bearer)
   and `api_key` only; cookie auth was removed deliberately
   (`app/models/source_auth.py`) because automating logged-in sessions violates
   most sites' terms of service. Candidate dashboards are unreachable by design.
3. **Static selectors.** Schema drift breaks a source; the parser fails a run
   when *every* item is missing `title`/`company` (see the postmortem in
   `operations.md`).
4. **Two-stage detail fetching** is available to `discovery` providers and to
   `generic_html_list` with `"detail": true` + `detail_*_selector`.

## Adding a source

| Field | Value |
|---|---|
| Name | free text |
| URL | human page URL (`rss`: **must** be the feed URL; `discovery`: reference only) |
| Type | `career_page` \| `aggregator` \| `rss` \| `discovery` \| `manual` |
| Adapter (aggregator) | `generic_html_list`, `embedded_json_list` |
| Provider (discovery) | from `GET /sources/providers`; required for this type |
| Cadence + notes (manual) | from `GET /sources/manual-metadata` (`cadence_days` 1–365, plus free-form `notes`); the form merges them into the existing `config` |
| Config JSON | merged into `config` (required/optional keys come from `/sources/providers` and `/sources/adapters`; create/update return 422 on a broken config) |
| Rate limit (s) | default `30`, per-domain cooldown before every request |
| Respect robots.txt | default **on** (checked against the actual fetch URL and each pagination hop) |
| Auth (optional) | `token` (Bearer) or `api_key` (search providers read `FetchAuth.api_key`, not `token`) |

Config keys understood by the pipeline (`workers/tasks/scrape.py`):

| Key | Meaning | Default |
|---|---|---|
| `max_pages` | listing pages to walk via `next_page_url` | `1` |
| `max_results` | detail pages fetched / jobs returned | `20` |
| `allow_empty` | do not fail when the parse yields 0 jobs | `false` |

**Verification loop.** `POST /api/admin/sources/{id}/scrape` (admin, 202) enqueues
a run; otherwise Beat sweeps every 15 min (`SCRAPE_SWEEP_INTERVAL_MINUTES`) for
sources older than 60 min (`SCRAPE_FRESHNESS_MINUTES`). `POST /api/sources/preview`
runs the scraper once and returns sample jobs without persisting anything — the
*Preview* button on the Sources form. Worker-side alternative:

```bash
docker compose exec worker python -c \
  "from workers.tasks.scrape import scrape_source; print(scrape_source.apply(args=['<SOURCE_UUID>']).get())"
```

Adding many sources at once: `POST /api/sources/import` or
`scripts/import_sources.py --file <private.json> --token <JWT>` (idempotent,
never imports credentials — keeps the list out of the repo).

## Manual watchlist sources (`type = manual`)

For a board the engine must not (or cannot) fetch — login-walled candidate
dashboards, anti-bot boards, directories — create the source with
`type = manual`. It is never fetched:

- the beat sweep (`workers/tasks/sweep.py`) excludes manual sources from
  dispatch, so no `scrape_source` task is ever enqueued for them;
- `POST /api/admin/sources/{id}/scrape` and any direct `scrape_source` call
  record a `skipped` run (`manual source; check it by hand`) and never trip the
  circuit breaker;
- `POST /api/sources/preview` short-circuits with an explanatory `error`
  instead of fetching anything.

Instead the app schedules a re-check and reminds the user in-app.

| Config key | Meaning | Default |
|---|---|---|
| `cadence_days` | days between hand checks; must be 1–365 or the API answers **422** (the read path still clamps junk) | `7` |
| `notes` | free-form reminder of what to look for by hand (optional) | — |
| `next_check_at` | ISO due date; rewritten on every check, settable as an override | `last_scraped` (else `created_at`) + cadence |
| `reminded_at` | internal stamp of the last reminder; cleared by a check | — |

`GET /api/sources/manual-metadata` publishes this contract
(`cadence_days: {default, min, max}` + `optional_config` + `example_config`) so
the web and mobile forms read the bounds instead of hard-coding them. Because
`PUT /api/sources/{id}` replaces `config` wholesale, both clients **merge** the
form values into the source's existing config — otherwise an edit would drop
`next_check_at`/`reminded_at` and the sweep would re-remind a source that was
just checked.

`POST /api/sources/{id}/check` is the *Mark checked* action: it stamps
`last_scraped`, resets health to `healthy`, clears `reminded_at` and pushes
`next_check_at` one cadence out. The sweep creates **one** in-app notification
per due source and stops until that source is checked, so the watchlist nags
once per period rather than once per sweep. The Sources UI (web and mobile)
shows the due badge, the next due date with a "due in / overdue by N days"
hint, the notes field and the *Mark checked* button (the auth panel is hidden:
manual sources are never fetched, so credentials mean nothing).

## Collectible today (no code changes)

**ATS JSON boards** (`type = discovery`): Solvd (`ashby` `{org}`), Teramind
(`lever` `{company}`), Janea Systems (`greenhouse` `{board_token}`), any Workable
board (`workable` `{org}`); providers also accept `company` and `max_results`.
`smartrecruiters`, `recruitee`, `personio` and `workday` are implemented and
verified live. Personio's XML feed carries no job URL, so `url_tpl`
(`https://{company}.jobs.personio.de/job/{id}`) is **required** and must be
confirmed per tenant with the preview.

**RSS / Atom** (`type = rss`): We Work Remotely
(`weworkremotely.com/remote-jobs.rss`), NoDesk (`nodesk.co/remote-jobs/index.xml`),
Jobspresso, RemoteYeah, Dexian Brasil, Rangertech (feed href declared in the
search page). Remote Habit only feeds interviews/tools → use its HTML listing.
RemoteOK/Remotive expose JSON (use `json_list`), not job RSS.

**Server-rendered HTML** (`type = aggregator` + `generic_html_list`): Programathor,
GeekHunter, Remote.com, aijobs.ai, dev.pro, HireWithNear, MWDN, Sigma Software,
JobConvo employer boards, Akvelon (PeopleForce), Remote Habit, Job na Gringa,
Init-i8, Remotify Europe, JustRemote, remote4me, Toughbyte, WorkingNomads;
Empregos.com.br needs `embedded_json_list`; InfoJobs must be probed on its **job
search** route, not `/empregos` (that is a company directory).

```json
{
  "adapter": "generic_html_list",
  "item_selector": "li.job-card",
  "title_selector": "h2 a",
  "url_selector": "h2 a",
  "company_selector": ".company-name",
  "next_page_selector": "a.next",
  "max_pages": 3
}
```

Rules of thumb: `item_selector` must match **every** card and the title/URL
selectors are evaluated *inside* it (cards without title or URL are skipped); a
listing that only links out with no title/company yields **0 jobs** — add
`"detail": true` with `detail_*_selector`, or accept an `Unknown` company.

**Paid search providers** (`type = discovery`, key via `PUT /sources/{id}/auth`
with `auth_type=api_key`): `brightdata` for LinkedIn (`{"engine": "linkedin",
"query": "...", "location": "Brazil", "customer": "...", "zone": "..."}`) and
Indeed; `serpapi` `google_jobs` for Glassdoor, Dice, Catho, Jobot, Levels.fyi,
Landing.jobs, Wellfound, Hays, Michael Page, Robert Half, SimplyHired, Welcome to
the Jungle; `google_cse`/`bing`/`brave` for open-web sourcing
(`{"query": "site:jobs.lever.co python remote"}`).
Two-stage providers parse detail pages with JSON-LD first; without it, set
`{"detail_strategy": "selectors", "selectors": {"title_selectors": "...",
"company_selectors": "..."}}`.

## Out of scope (documented, not attempted)

- **Login-walled dashboards / talent networks** (Outlier, Alignerr, Toptal,
  Turing, Upwork, Revelo, Lemon.io, FlexJobs, VanHack, Proxify and similar) —
  need authenticated candidate context (cookies + often 2FA/SSO). Track them as
  `type = manual` sources instead (ADR 018): the user re-checks them by hand and
  the app reminds them when due.
- **ToS / anti-bot by direct scraping** — LinkedIn, Indeed, Glassdoor, Dice,
  Himalayas, Stack Overflow Jobs. Use the paid providers above.
- **Not listings / dead** — DuckDuckGo *query* URLs (no provider; use
  `google_cse`/`bing`/`brave`), `jobboardsearch.com` and `readytotouch.com`
  (directories), archived `lerrua/remote-jobs-brazil`, single-job URLs, 404/5xx
  boards.

## Compliance, maintenance

`respect_robots_txt` is on by default and applies to every real fetch
(provider-built endpoints and detail pages included); disallowed sources are
recorded as `skipped` and never trip the circuit breaker. `rate_limit_seconds`
is a per-domain cooldown before *every* request, so 30 sources at the default is
deliberately slow. Third-party keys are stored encrypted and billed per query.

| Symptom | Likely cause | Action |
|---|---|---|
| `parse produced 0 jobs` | selectors drifted / site became JS-rendered | re-inspect; fix selectors or drop the source |
| `authentication failed (HTTP 401/403)` | expired/incorrect API key | re-save the key on the source |
| `skipped: robots.txt disallows` | disallowed path | do not bypass; use a provider instead |
| Repeated failures | circuit breaker open | fix the root cause, then let the breaker close |
| Company stored as `Unknown` | listing has no company node | add `company_selector` or accept it |

**Deferred** — an opt-in headless renderer (separate Playwright container behind
an env flag, keeping robots/rate-limit/response-size limits) is the only way to
reach the remaining pure-JS SPAs; ADR 005/010 defer it as "per-site opt-in
later".
