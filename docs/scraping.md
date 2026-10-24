# Scraping & source coverage

How to onboard a job board, what the engine can collect **today**, what it
cannot, why, and what would unlock the rest. Companion to ADR 005 (resilience),
ADR 010 (discovery sources) and ADR 018 (manual watchlist sources).

## What a source can consume

| Source `type` | Adapter / provider | Consumes | Two-stage? |
|---|---|---|---|
| `career_page` | JSON-LD `JobPosting` → CSS fallback | one static HTML page | no |
| `aggregator` | `generic_html_list`, `embedded_json_list` | one static HTML *listing* page + optional pagination (`next_page_selector` or `next_page_tpl`) | yes, with `"detail": true` |
| `rss` | `feedparser` | RSS 2.0 / Atom feed (`url` **is** the feed URL) | no |
| `discovery` (ATS) | `ashby`, `greenhouse`, `lever`, `workable`, `smartrecruiters`, `recruitee`, `personio`, `workday` | public JSON board endpoint | no |
| `discovery` (JSON) | `json_list`, `adzuna`, `jooble`, `jsearch` | any JSON API (`paths` + `url_tpl`/`url`); the keyed vendors ship their own defaults | no |
| `discovery` (search) | `google_cse`, `bing`, `brave`, `serpapi`, `brightdata` | search results → detail pages (or the results page itself with `parse_listing`) | **yes** |
| `manual` | none — hand-checked | nothing; the user re-checks the board and the app reminds them | no |

Hard limits of the engine — these decide almost every verdict below:

1. **No JavaScript rendering** (`httpx` + BeautifulSoup). Client-side data
   (Angular, pure SPA) is invisible unless it is embedded as JSON
   (`embedded_json_list` reads `__NEXT_DATA__` / `window.__NUXT__`) or the page
   fetches it from a JSON API we can call ourselves (`json_list` — Working
   Nomads, RemoteOK, FullStack Talent).
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
| Cadence (manual) | from `GET /sources/manual-metadata` (`cadence_days` 1–365); the form merges it into the existing `config` |
| Notes | free-form, human-only text (any type) stored in the source's own `notes` column — never scraped, never part of `config` |
| Config JSON | merged into `config` (required/optional keys come from `/sources/providers` and `/sources/adapters`; create/update return 422 on a broken config) |
| Rate limit (s) | default `30`, per-domain cooldown before every request |
| Scrape frequency | optional per-source interval (`scrape_interval_minutes`, 60–20160); `null` inherits the global sweep freshness and the global value is always a floor. Hidden for `manual` sources, which use `cadence_days` |
| Respect robots.txt | default **on** (checked against the URL that gets fetched — the board for renderer providers, see `robots_url` — and each pagination hop) |
| Auth (optional) | `token` (Bearer) or `api_key` (search providers read `FetchAuth.api_key`, not `token`) |

### Detected locations

Every parser fills `RawJob.location` when the source reports a location, and the
worker stores it in `jobs.location`:

- **ATS APIs** (`ashby`, `greenhouse`, `lever`, `workable`, `smartrecruiters`,
  `recruitee`, `personio`, `workday`): the board payload's location fields
  (`location`, `fullLocation`, `locationsText`, the Personio office(s), …).
- **JSON/aggregator payloads**: the configured `location_path`.
- **JSON-LD** `JobPosting.jobLocation` (career pages and detail-mode boards),
  including `jobLocationType: "TELECOMMUTE"` → `Remote` and
  `applicantLocationRequirements` as the fallback.
- **HTML list cards**: `location_selector`. In `detail: true` mode the card's
  value is remembered for its detail URL, so a board whose detail page omits
  the location still stores the one printed on the listing.
- **RSS**: `region`/`location` entry fields, region-like categories when
  `include_region` is set, and Jobspresso's author suffix (`Algolia ⚲ Brazil`).

`config["locations"]` gates ingestion on that value (see below): a matching term
keeps the job, a non-matching detected location drops it, and a job with **no**
detected location is always kept. The jobs API filters on the same field with
`GET /api/jobs?location=brazil,remote` (comma-separated OR, case-insensitive);
unknown-location rows are included unless `location_unknown=false` is sent.

Config keys understood by the pipeline (`workers/tasks/scrape.py`):

| Key | Meaning | Default |
|---|---|---|
| `max_pages` | listing pages to walk via `next_page_url` (in a sweep: pages read **per query**, so the run budget is `max_pages × len(queries)`) | `1` |
| `next_page_selector` | `generic_html_list`: CSS selector for the next-page `<a>`. Preferred when present — a real link also disappears on the last page, so the walk ends by itself | — |
| `next_page_tpl` | pages 2..`max_pages` are **built** from this template, rendered with any config key plus `{page}` (`…/search?term={term}&page={page}`; relative templates resolve against the page they were read from). A JSON blob (`embedded_json_list`) has no `<a>` to follow, so here it is the only way to page; `generic_html_list` falls back to it when no `next_page_selector` is set (dev.pro's pager renders the *current* page as a `<span>` and the lowest number first, so "the next link" cannot be expressed as a selector) | — |
| `url_tpl` | `generic_html_list` / `json_list`: page 1 is built from this template instead of the stored URL (`{page}` = 1 here, plus every other config key), so a term or locale can live in the config. In `embedded_json_list` the same key means the *job* URL (`{url}` from `url_path`) | — |
| `max_results` | detail pages fetched / jobs returned (ignored for a sweep — `max_boards` owns that cap) | `20` (keyed search APIs lower it to `5`) |
| `allow_empty` | do not fail when the parse yields 0 jobs | `false` (`true` for `sweep_ats`) |
| `exclude_pattern` | case-insensitive regex tested against a card/job's text (aggregator adapters). Use it for stale labels such as `\bexpirad[ao]s?\b`; matching rows are dropped before storage | — |
| `parse_listing` | parse the *results page itself* instead of fetching each job (search providers: one paid call per run) | `false` |
| `query` / `queries` | search providers: one query, or a non-empty list consumed in order (each with its own pagination) | `query` |
| `sweep_ats` | search providers (`google_cse`, `bing`, `brave`): treat results as ATS board URLs and read the public board APIs instead of fetching each hit | `false` |
| `keywords` / `exclude_keywords` | sweep-only whole-term filters over title, tags and description (`c++` works); excludes win | — |
| `locations` | ingestion-time location gate for **every** source type: keep a job when any term matches its detected location (case/accent-insensitive, whole term). Jobs with **no** detected location are always kept; `[]`/empty disables the gate | — |
| `max_boards` / `max_jobs` | sweep-only caps: boards per run; kept jobs per run (`0` = no cap) | `40` / `0` |
| `board_rate_limit_seconds` | sweep-only: cooldown between two board fetches (the source `rate_limit_seconds` still governs the search API) | `3` |
| `min_boards_per_query` | sweep-only: floor reserved for the queries not visited yet. The rest of `max_boards` is split **equally** between the remaining queries, so query #1 cannot spend the budget on its own | `2` |
| `seed_urls` | sweep-only: board or job URLs read on **every** run, before the index is even asked (`https://job-boards.greenhouse.io/alpaca/jobs/123` is enough — the board is resolved from it). The vocabulary-free way to cover a board the index never ranks for the queries | — |
| `query_hints` | search providers: extra wording appended to **every** query (`["remote brazil"]` turns `golang site:greenhouse.io` into two queries). Only widens what the index offers — the `keywords`/`locations` filters still decide what is kept | — |
| `board_max_jobs` | sweep-only: postings read from one board before paging stops (`ats_board_truncated` is logged when the cap cuts a full page). Falls back to `max_results`, then 1000 | `1000` |
| `board_reread_days` | sweep-only: a board read less than this many days ago goes **behind** every board that is unread or last read earlier, so the budget rotates over the boards the index offers instead of re-reading the same slice (`0` disables rotation: the index order wins again) | `3` |
| `max_jobs_per_board` | sweep-only: postings one board may contribute to a run (`0` = no cap). A blunt instrument — it truncates the *same* board on every visit, so prefer `board_reread_days`/`max_boards` when a board eats the run | `0` |
| `sweep_max_seconds` | sweep-only: wall-clock budget for the run (`0` = no cap) | `0` |
| `match_in` | sweep-only: `title` restricts `keywords`/`exclude_keywords` to title + tags (the location gate always reads the detected location only) | `anywhere` |
| `max_age_days` | discovery providers: drop postings older than this many days (`0` = keep everything). Only acts on **dated** postings — undated rows are kept and counted as `undated` in the run log | `0` |

**URL arguments and search terms.** A stored `url` is fetched **verbatim** by
`career_page`, `aggregator` and `rss` (`first_fetch_url` defaults to identity),
so every argument the board understands already works — no config needed:

```
https://www.infojobs.com.br/empregos.aspx?palabra=Rust      (?palabra= is the board's own filter)
https://www.trabalhabrasil.com.br/vagas-de-emprego/rust     (term in the path)
https://www.geekhunter.com/pt/vagas?workModality=remote     (remote-only listing)
```

One source per term is the simplest setup. When the same board should cover
*several* terms without duplicating the config, keep the term in the config and
the URL in `url_tpl` (rendered with every other config key, `{page}` reserved and
set to `1` here):

```json
{
  "adapter": "generic_html_list",
  "term": "rust",
  "url_tpl": "https://remoteyeah.com/remote-{term}-jobs-in-brazil",
  "next_page_tpl": "https://remoteyeah.com/remote-{term}-jobs-in-brazil/page/{page}#jobs",
  "max_pages": 2,
  "detail": true,
  "item_selector": "article.job-card",
  "title_selector": "a.job-card-title",
  "url_selector": "a[href*='/jobs/']",
  "company_selector": ".job-card-company",
  "detail_title_selector": "h1",
  "detail_company_selector": "a[href*='/remote-companies/']",
  "detail_description_selector": ".prose",
  "max_results": 31
}
```

On RemoteYeah `item_selector: "li"` matches the **“recent applications” ticker**,
not the cards, so it yields a handful of titles and nothing else. The real cards
are `article.job-card`; they carry title, company and tags, but no description.
`detail: true` fetches each card's job page, whose `JobPosting` JSON-LD supplies
the full description, posting date and skills. `max_results` bounds those detail
fetches (rust: 25 on page 1, 31 across both pages), and each one waits for the
source's `rate_limit_seconds` cooldown.

The keyed discovery providers do the same thing with their own placeholders
(`{api_key}`, `{page_size}`); see the `json_list` section below. A `url_tpl` that
cannot be rendered (a placeholder with no matching config key) fails the source,
the same way a bad `json_list` template does.

**Listing mode (`parse_listing`).** Search providers normally pay one request
per job (results page → detail pages). When the results page already carries the
fields a row needs, set `parse_listing: true` plus the `generic_html_list`
selectors (`item_selector`, `title_selector`, `url_selector`, `company_selector`,
`location_selector`, `description_selector`) and the run costs **one** request:
`discover_urls` returns nothing, so the worker parses the results page directly.
`serpapi` accepts `parse_mode: results` (jobs come from the SERP payload itself —
title, company, location, extensions, `apply_options[0].link`; relative dates
such as `"3 days ago"` are converted to a real date and jobs without any link are
dropped). Prefer listing mode for `brightdata` (`endpoint: unlocker`, i.e. a Web
Unlocker zone) — a detail fetch through a paid renderer costs another credit.

**Keyed JSON APIs.** `json_list` and the three vendor providers (`adzuna`,
`jooble`, `jsearch`) cover APIs that answer with JSON but want a key. The config
says *how* to ask; the key itself is a **credential** (`PUT
/api/sources/{id}/auth` with `auth_type=api_key`), so it never shows up in
`config`, in `GET /api/sources` or in a run's error message (payloads and URLs
are redacted before they are stored or returned).

| Config key | Meaning |
|---|---|
| `url` / `url_tpl` | endpoint template; any config key plus the reserved `{api_key}`, `{page}` and `{page_size}` renders into it (`{api_key}` in the template means "the key goes right here") |
| `auth` | where the key travels: `"query"` or `{"in": "query", "name": "app_key"}`, `{"in": "header", "name": "X-Api-Key"}`, or nothing at all so the `{api_key}` marker above decides. Names default to `X-API-Key` |
| `method` + `body` | `POST` + a JSON `body` template for vendors that only answer to POST; body placeholders render as **text**, so quote them (`"page": "{page}"`, not `"page": {page}`) |
| `next_page_tpl` / `next_page_path` / `max_pages` | pagination. Providers that page through the body (Jooble) keep the same URL and send `{page}` in the body — the worker knows such a URL is not "no more pages" (`pagination_in_body`). `next_page_path` reads the API's own flag (a dotted path such as `meta.hasNextPage`) and stops the walk when it is false or missing, so a board that grows does not need `max_pages` retuned |
| `url_path` + `job_url_tpl` | `url_path` extracts the item's link; when the payload only carries an id/slug (`url_path: "id"`), `job_url_tpl` renders any item field plus `{url}` into the public posting URL (`"https://talent.fullstack.com/jobs/{id}"`) instead of letting the id resolve against the API host. A placeholder with no matching field fails the run |
| `items_path`, `title_path`, … | field mapping, exactly as for any other `json_list` source |

| Provider | Endpoint / key | Notes |
|---|---|---|
| `adzuna` | `api.adzuna.com/v1/api/jobs/{country}/search/{page}`, `app_key` in the query | `app_id` is **not** a secret and stays in `config`; `country` defaults to `br`, `results_per_page` to `page_size` (20), jobs come from `results[]` |
| `jooble` | `jooble.org/api/{api_key}` — POST, key in the path | the body is `{"keywords": "{query}", "location": "{location}", "page": "{page}"}`; jobs come from `jobs[]` |
| `jsearch` | `jsearch.p.rapidapi.com/search` — GET | RapidAPI wants the key **and** the host it was issued for, so the provider sends `X-RapidAPI-Key` + `X-RapidAPI-Host`; jobs come from `data[]` |

Only `query` (plus `app_id` for Adzuna) is required — everything else is
pre-filled and can be overridden per source. A run for one of these without a
stored key is recorded as `skipped` with the reason (`this source needs an API
key …`) **before** the first request, instead of failing with the vendor's 401:
add the key in the source's *Authentication* panel. Because keys are billed per
call, keyed providers cap `max_results` at **5** by default; an explicit
`max_results` in the config always wins.

**Verification loop.** `POST /api/admin/sources/{id}/scrape` (admin, 202) enqueues
a run; otherwise Beat sweeps every 15 min (`SCRAPE_SWEEP_INTERVAL_MINUTES`) for
sources whose `last_scraped` is older than `max(SCRAPE_FRESHNESS_MINUTES,
scrape_interval_minutes)`. A source with no interval keeps the 60-minute default;
setting a longer cadence (daily, weekly, …) is the intended way to keep paid
search APIs within their free tier. The API returns `next_scrape_at` and
`scrape_due` for the source list, and the form seeds new `search_api` providers
with a weekly interval. `POST /api/sources/preview`
runs the scraper once and returns sample jobs without persisting anything — the
*Preview* button on the Sources form. When the form is editing an existing
source it sends that source's `source_id`, so the preview borrows the stored
credentials while still testing the unsaved URL/config. A **new** keyed source
has nowhere to borrow a key from: save it, add the key in *Authentication*, then
edit it and preview again. A preview without a required key returns
`<provider> needs an API key …` before making the request; when the vendor
rejects the request anyway, its (redacted, capped) response body is included in
the error. Worker-side alternative:

```bash
docker compose exec worker python -c \
  "from workers.tasks.scrape import scrape_source; print(scrape_source.apply(args=['<SOURCE_UUID>']).get())"
```

Adding many sources at once: `POST /api/sources/import` or
`scripts/import_sources.py --file <private.json> --token <JWT>` (idempotent,
never imports credentials — keeps the list out of the repo).

### Diagnosing a source

`GET /api/sources/{id}/diagnostics` returns a read-only snapshot for one owned
source: stored job count, rows with an unknown company / short description /
missing posting date, the latest `ScrapeRun` status and error, whether the
stored config still validates, and the avoid/health flags. It answers "is this a
fetch problem or a parser problem?" without spending a scrape; use
`POST /api/sources/{id}/preview` when the question is "what does this config
parse right now?".

### Repairing sources and stored jobs

Some fixes are data, not code: a feed reshaped its titles, a card gained an
"expired" label, or selectors stopped matching. `scripts/repair_sources.py`
patches those rows **dry-run first** (it writes only with `--apply`):

```bash
# We Work Remotely titles/companies + HTML in descriptions (historical rows too)
python scripts/repair_sources.py --url-contains weworkremotely \
  --set-config company_from_title=true --set-config strip_html=true \
  --fix-rss-titles

# Programathor: never store cards labelled as expired
python scripts/repair_sources.py --url-contains programathor \
  --set-config 'exclude_pattern=\bexpirad[ao]s?\b'

# Gupy: filter unwanted embedded-JSON rows (title/description/tag text)
python scripts/repair_sources.py --url-contains gupy \
  --set-config 'exclude_pattern=\b(talent pool|banco de talentos)\b'

# Stop fetching boards whose selectors no longer work (reversible)
python scripts/repair_sources.py --url-contains infojobs --avoid \
  --avoid-reason "listing cards are client-rendered"
python scripts/repair_sources.py --url-contains toughbyte --avoid \
  --avoid-reason "selectors no longer match"

# RemoteYeah: drop rows stored bare before detail/JSON-LD enrichment
python scripts/repair_sources.py --url-contains remoteyeah \
  --delete-bare-jobs --bare-company Unknown
```

Every command previews the matching source(s), config diff, affected job count
and a few sample rows. Re-running with `--apply` is idempotent: config merges,
title splits skip already-split rows, and avoided sources keep their original
"avoided since" timestamp. Avoided boards are never fetched or reminded about;
use `--unavoid` to restore one after its parser is fixed.

The same script can repair already-stored rows **without** re-scraping the
whole source:

```bash
# Rebuild feed rows from the current feed (WordPress ?paged=N is supported).
python scripts/repair_sources.py --url-contains jobspresso \
  --reparse-rss --rss-pages 4 --apply

# Refresh list-mode rows (company/location/date/tags) without fetching details.
python scripts/repair_sources.py --url-contains aijobs --reparse-list --apply

# Fetch stored detail URLs that are missing company/description/date.
# Start with --max-jobs 1 as a dry run, then run the full batch with --apply.
python scripts/repair_sources.py --url-contains nerdin \
  --refresh-details --max-jobs 1
python scripts/repair_sources.py --url-contains nerdin \
  --refresh-details --apply

# Delete rows by text (expired labels, talent pools) or wipe a noisy source.
python scripts/repair_sources.py --url-contains programathor \
  --delete-matching '\bVencida\b' --apply
python scripts/repair_sources.py --url-contains term=golang \
  --delete-all-jobs --apply
```

`--refresh-details` only targets incomplete rows by default (missing/short
description, `Unknown` company or no date); add `--refresh-all` to refetch every
stored URL. Each request honours `source.respect_robots_txt`, and
`--rate-limit N` can override the source cooldown for a one-off batch.

Each source is scraped by at most one run at a time: the worker takes a Redis
lock per source and the sweep skips sources with a live `running` run. A run
older than `SCRAPE_RUN_STALE_MINUTES` (30) is marked `failed` by the next sweep,
so a killed worker cannot leave a source "running" forever. Queued tasks carry
`SCRAPE_TASK_EXPIRES_SECONDS` (30 min) and Celery's soft/hard limits are 20/25
min, deliberately below RabbitMQ's `consumer_timeout`; a scrape that overruns is
failed on its `ScrapeRun` instead of taking the worker's consumer down. A source
skipped because of robots.txt or a missing key is retried once a day rather than
every sweep, and its health becomes `degraded` so the UI does not report it as
healthy.

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
| `next_check_at` | ISO due date; rewritten on every check, settable as an override | `last_scraped` (else `created_at`) + cadence |
| `reminded_at` | internal stamp of the last reminder; cleared by a check | — |

Free-form notes are **not** part of this config: they live in the `sources.notes`
column (`POST`/`PUT` take a top-level `notes`, blank clears it) and any source
type can carry one.

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
hint, the notes field (available for every source type) and the *Mark checked*
button (the auth panel is hidden: manual sources are never fetched, so
credentials mean nothing).

## Collectible today (config only)

**ATS JSON boards** (`type = discovery`): Solvd (`ashby` `{org}`), Teramind
(`lever` `{company}`), Janea Systems (`greenhouse` `{board_token}`), any Workable
board (`workable` `{org}`); providers also accept `company` and `max_results`.
`smartrecruiters`, `recruitee`, `personio` and `workday` are implemented and
verified live. Personio's XML feed carries no job URL, so `url_tpl`
(`https://{company}.jobs.personio.de/job/{id}`) is **required** and must be
confirmed per tenant with the preview. For these sources the stored `url` is a
**reference only** — the provider builds the real endpoint from `{org}` /
`{company}` / `{board_token}` — so a careers page that moves does not break the
source as long as the ATS key is right (Solvd's `careers.solvd.com` no longer
resolves; store `solvd.com/careers/` and keep the `ashby` source, whose
`?location=` argument the provider ignores — the filter is the board's UI state,
not a feed parameter).

**RSS / Atom** (`type = rss`): We Work Remotely
(`weworkremotely.com/remote-jobs.rss`), NoDesk (`nodesk.co/remote-jobs/index.xml`),
Jobspresso (`jobspresso.co/jobs/feed/` — the bare `/feed/` is the *blog* and
carries **0** jobs), RemoteYeah, Dexian Brasil, Rangertech (feed href declared in
the search page). Remote Habit only feeds interviews/tools → use its HTML
listing. RemoteOK / Remotive / Working Nomads expose JSON (use `json_list`), not
job RSS.

Feeds whose metadata describes the *board* rather than the employer support
opt-in config flags:

| RSS config key | Meaning | Default |
|---|---|---|
| `company_from_title` | split `"Company: Job title"` entries (We Work Remotely) | `false` |
| `company_from_title_at` | split `"Job title at Company"` entries (NoDesk) | `false` |
| `company_from_author` | use the entry author as the employer, dropping any `<br>⚲ location` suffix (Jobspresso) | `false` |
| `include_categories` | add every feed `<category>` to the job tags | `false` |
| `include_region` | add only region-like categories (Remote, Americas, Brazil, …) plus an explicit `<region>`/`<location>` entry field | `false` |
| `strip_html` | convert an HTML `<description>`/`<summary>` into plain text | `false` |

The flags are opt-in so an existing feed keeps the rows it had before. A
board-shaped feed is configured like this:

```json
{
  "company_from_title": true,
  "include_region": true,
  "strip_html": true
}
```

NoDesk uses `{"company_from_title_at": true}` and Jobspresso
`{"company_from_author": true}` (both feeds already carry the full description
and date, so no other flag is needed). Relative dates from Brazilian boards
(`"há 2 horas"`, `"2 semanas atrás"`, `"ontem"`) are parsed by `date_selector` /
`date_from_node` just like the English forms.

**Server-rendered HTML** (`type = aggregator` + `generic_html_list`): Programathor,
GeekHunter, Remote.com, aijobs.ai, dev.pro, TrabalhaBrasil, InfoJobs, Nerdin
(`www.nerdin.com.br/vagas.php`, cards `.vaga-card`, next page `?pagina=2`), MWDN
(`jobs.mwdn.com/careers/` — a **Comeet** embed, 40 cards under
`.comeet-positions-list li`), SkipTheDrive (its **job-category** pages, e.g.
`/job-category/remote-part-time-jobs/`, each carry 20 `/job/<slug>/` cards — the
homepage does not), JobConvo employer boards, Akvelon
(PeopleForce), Remote Habit, Job na Gringa, Init-i8, JustRemote,
remote4me, Toughbyte. InfoJobs only works on its **job search** route
(`/empregos.aspx?palabra=<term>` — `/empregos` is a company directory). Working
Nomads *looks* server-rendered but is AngularJS fed by a JSON API → collect it
with `json_list` against `https://www.workingnomads.com/api/exposed_jobs/`;
`jobs.hirewithnear.com/#/` is a hash-route SPA, so it stays `manual` (see below).
`career.sigma.software` and `remotifyeurope.com` are **not** in this list: both
return a shell with 0 job rows (see the JS-only shells below). Jobsora is
collected from its **path** routes (`/empregos-rust`, `/empregos-golang`;
query-string routes are disallowed by robots.txt) in list mode, and Velozient's
Elementor careers tabs expose 45 static `li` cards with a configured company
fallback. Neither needs a detail fetch.

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
selectors are evaluated *inside* it (cards without title or URL are skipped; a row
that is itself an `<a>` contributes its own `href`, which is how dev.pro's
`a.position-row` rows parse); a
listing that only links out with no title/company yields **0 jobs** — add
`"detail": true` with `detail_*_selector`, or accept an `Unknown` company.
Optional extras: `date_selector` (a `<time>` node, absolute or relative),
`description_selector` (a card snippet, kept alongside the `Location: …` suffix
built from `location_selector`) and `title_exclude_selector` for a status badge
rendered inside the title heading (Nerdin's `.vaga-nova-badge`). These are shared
with search providers in listing mode (`parse_listing`), so a working card
definition can be reused verbatim from a paid provider config.

Verified card configurations (each parsed live; job counts at the time of
writing):

| Board | URL | Config | Jobs/run |
|---|---|---|---|
| dev.pro | `career.dev.pro/open-positions/` | `{"item_selector": "a.position-row", "title_selector": "h3", "location_selector": ".position-info span", "next_page_tpl": "https://career.dev.pro/open-positions/page/{page}/", "max_pages": 4}` — the pager shows the current page as a `<span>` and the *lowest* number first, so "next" cannot be a selector | 35 (10/10/10/5) |
| TrabalhaBrasil | `/vagas-de-emprego/<term>` | `{"term": "rust", "url_tpl": "https://www.trabalhabrasil.com.br/vagas-de-emprego/{term}", "item_selector": "article.job-card", "title_selector": "h2.job-title", "url_selector": "a.job-link", "company_selector": ".job-company", "location_selector": ".job-location"}` — the term route is SSR, the homepage is a directory, and paging is JS | 15 |
| InfoJobs | `/empregos.aspx?palabra=<term>` | `{"term": "Python", "url_tpl": "https://www.infojobs.com.br/empregos.aspx?palabra={term}", "item_selector": "div.js_cardLink", "title_selector": "h2.js_vacancyTitle", "url_selector": "a[href*='/vaga-de-']"}` | 20 — but only **2** on `palabra=Rust` (that page's card slice is client-rendered), so preview the term you store |
| GeekHunter | `/pt/vagas?workModality=remote` | `{"item_selector": "article", "title_selector": "h3 a", "url_selector": "h3 a", "next_page_selector": "a[rel=next]", "max_pages": 3}` — list mode has no company (chakra hashes the classes); adding `"detail": true` makes each job page's JSON-LD (tried before the `detail_*_selectors`) supply company, date and description | 25/page |
| RemoteYeah | `/remote-<term>-jobs-in-brazil` | the `url_tpl` + `next_page_tpl` recipe in *URL arguments and search terms* above: `detail: true` + `item_selector: "article.job-card"` (a bare `li` matches the recent-applications ticker, not job cards); each detail page's JSON-LD supplies the description, date and skills | 31 / 38 |

`max_results` does **not** cap list-mode rows (it bounds detail fetches and
`embedded_json_list` items); what bounds a multi-page walk is `max_pages`, and one
request is paid per page plus per detail page, all under the source's
`rate_limit_seconds` cooldown.

**Embedded JSON** (`type = aggregator` + `embedded_json_list`): boards that render
their listing with a JS framework but ship the data in the page. `payload_script`
names the `<script id>` (default `__NEXT_DATA__`) or `payload_global` a
`window.<name>` assignment (`__NUXT__`); `items_path` points at the array. Boards
verified live:

| Board | URL | `items_path` | Field notes |
|---|---|---|---|
| Gupy | `portal.gupy.io/job-search/term=<term>` | `props.pageProps.initialJobList.data` | `name`, absolute `jobUrl`, `description`, `careerPageName`, `publishedDate`, `workplaceType`; pages via `&page=N` and `pagination.total/limit` says how many |
| Remote Rocketship | `www.remoterocketship.com/remote-jobs/` | `props.pageProps.initialJobOpenings` | `roleTitle`, `url` (the **original** ATS link), `company.name`, `location`, `created_at`, `jobDescriptionSummary`, `techStack`; pages via `?page=N` |
| Empregos.com.br | job search route | probe | still to be mapped |

```json
{
  "adapter": "embedded_json_list",
  "payload_script": "__NEXT_DATA__",
  "items_path": "props.pageProps.initialJobOpenings",
  "id_path": "id",
  "title_path": "roleTitle",
  "url_path": "url",
  "company_path": "company.name",
  "location_path": "location",
  "date_path": "created_at",
  "description_path": "jobDescriptionSummary",
  "tags_path": "techStack",
  "next_page_tpl": "https://www.remoterocketship.com/remote-jobs/?page={page}",
  "max_pages": 3
}
```

Rules of thumb: a JSON blob has no `<a>` to follow, so pagination is **built** from
`next_page_tpl` (`{page}` starts at 2) and is opt-in — without `max_pages` the
adapter never pages. `items_path` that resolves to a non-array raises; when the
blob is missing entirely the adapter falls back to JSON-LD on the same page. A
localised route can carry a *marketing sample* instead of the listing (Remote
Rocketship's `/br/` exposes a 5-job `jobsSample`; the real list is
`/remote-jobs/`), so confirm `items_path` against the page you actually store.

When a listing page embeds a `JobPosting` JSON-LD block per card, the worker
**enriches** the rows produced by the card parser (matching by URL or external
id) instead of appending a second copy: missing company, description, date and
skills are filled from JSON-LD in place. If the card parser returns nothing, the
JSON-LD records become the fallback. A row that only exists in the card stays a
card-only row; a row that only exists in JSON-LD is not duplicated.

**Root-array JSON APIs.** `json_list`'s contract demands a non-empty
`items_path`, but `"."` resolves to the payload itself — that is how Working
Nomads is collected (`/api/exposed_jobs/` is a bare array of
`{url,title,description,company_name,category_name,tags,location,pub_date}`, so
`"tags"` is a comma-separated string that `tags_path` already splits).

**Id-only JSON boards (FullStack Talent).** `talent.fullstack.com/jobs` is an
Angular shell, but the board reads a public, unauthenticated API:
`https://api-v1.fullstack.com/api/job-postings/public` answers
`{data: [...], meta: {hasNextPage, pageCount, filteredCount, ...}}` with `id`,
`jobTitle`, `region`, `regionGroup`, `city`, `state`, `createdAt` and
`skillsNames` per posting. The page size is fixed at `take=30` (any other value
is rejected with `Invalid take value`), and one `filter` argument carries
`key=value` pairs joined by `&` (encode `=` as `%3D` and `&` as `%26`):

| Filter | Postings | Query argument |
|---|---|---|
| Latam | 2450 | `filter=regionGroup%3DLatam` |
| Brazil | 275 | `filter=region%3D*Brazil*` |
| São Paulo | 25 | `filter=countryId%3D<country-uuid>%26cityId%3D<city-uuid>` |
| every country | 2897 | omit `filter` |

The public posting page is `talent.fullstack.com/jobs/<id>`, so `url_path: "id"`
plus `job_url_tpl` yields a readable link; `company` is a fixed string because
the board lists a single company:

```json
{
  "provider": "json_list",
  "url_tpl": "https://api-v1.fullstack.com/api/job-postings/public?page={page}&take=30&filter=regionGroup%3DLatam",
  "max_pages": 200,
  "next_page_path": "meta.hasNextPage",
  "items_path": "data",
  "id_path": "id",
  "title_path": "jobTitle",
  "url_path": "id",
  "job_url_tpl": "https://talent.fullstack.com/jobs/{id}",
  "location_path": "region",
  "date_path": "createdAt",
  "tags_path": "skillsNames",
  "company": "FullStack"
}
```

At 30 postings per request, Latam is 82 requests — a live run took 5m10s at
`rate_limit_seconds: 3` (the API answers in a second or two; the documented
ceiling is 20 req/min, so a 3 s cooldown leaves headroom), and a daily
`scrape_interval_minutes` is plenty.
`order`/`orderBy` are accepted but ignored, so every run walks the board and
dedupes on `external_id`; `next_page_path` ends the walk on the last page instead
of over-fetching up to `max_pages`. The **list payload carries no description**:
`/api/job-postings/{id}` does, but it costs one request per posting, so these
rows hold title, company, location, date and `skillsNames` as tags, and
`POST /api/jobs/{id}/parse` has no body to read. Narrow the volume with the
Brazil/São Paulo filter, `max_age_days`, or a `locations` eligibility gate
(keyword filters only apply to sweeps).

**Paid search providers** (`type = discovery`, key via `PUT /sources/{id}/auth`
with `auth_type=api_key`): `brightdata` for LinkedIn (`{"engine": "linkedin",
"query": "...", "location": "Brazil", "zone": "web_unlocker1",
"parse_listing": true, "item_selector": "...", ...}`) and Indeed; `serpapi`
`google_jobs` for Glassdoor, Dice, Catho, Jobot, Levels.fyi, Landing.jobs,
Wellfound, Hays, Michael Page, Robert Half, SimplyHired, Welcome to the Jungle;
`google_cse`/`bing`/`brave` for open-web sourcing
(`{"query": "site:jobs.lever.co python remote"}`).
Two-stage providers parse detail pages with JSON-LD first; without it, set
`{"detail_strategy": "selectors", "selectors": {"title_selectors": "...",
"company_selectors": "..."}}`. A `JobPosting` that omits `url`/`@id` falls back
to the fetched page's URL (so it is not dropped during normalization), and a
comma-separated `skills` string is split into individual tags.

**ATS sweeps from search results.** A search engine is useful for *finding*
companies that use an ATS, but its index is a poor place to read jobs: boards
are client-rendered, locations are often missing and snippets go stale. With
`"sweep_ats": true`, `google_cse`/`bing`/`brave` recognise public board URLs in
their results (`jobs.ashbyhq.com/{org}`, `jobs.lever.co/{company}`,
`boards.greenhouse.io/{token}`, `jobs.smartrecruiters.com/{company}`, plus the
EU Lever/Greenhouse hosts) and register the matching board API instead of
fetching every hit. One search result therefore becomes one live board read,
deduplicated per org and capped by `max_boards` (default 40).

```json
{
  "provider": "brave",
  "query": "rust engineer",
  "sweep_ats": true,
  "keywords": ["rust", "tokio"],
  "exclude_keywords": ["intern", "sales"],
  "locations": ["brazil", "latam", "americas", "worldwide"],
  "max_boards": 15,
  "max_jobs": 50
}
```

A board returns every open job, so the sweep filters locally: `keywords` and
`exclude_keywords` are whole-term, case-insensitive matches over title, tags and
description (`c++` is handled correctly), and `locations` is a
case/accent-insensitive, whole-term match against each posting's **detected
location** (`RawJob.location`, stored in `jobs.location`) — a country named in
the body does not keep an opening based elsewhere. `locations` is an
**eligibility** gate, not a remote-only flag: list the regions you can actually
work from (`brazil`, `latam`, `south america`, `americas`, `worldwide`, …). A
bare `remote` is a poor term on these boards — Ashby, Lever, Greenhouse and
SmartRecruiters use it for US-only roles as often as for worldwide ones — and
the abbreviations match literally: `amer` keeps `Remote, AMER` but not `AMERS`
or `Americas` (add `amers` if a board spells it that way; `americas` already
covers the latter). Postings whose board reports no location are kept
(`unknown` in the run log); dropping them used to hide whole boards behind an
"empty" sweep. This gate is not sweep-only: the worker applies
`config["locations"]` to every source type after normalization, and the Sources
form exposes it as a comma-separated field. A batch emptied by the gate
is a successful run, not an empty-parse failure (the `location_filter kept=…
skipped=… unknown=…` log line records what happened). `match_in: "title"`
keeps the keyword/exclude match on title + tags only, which is what a board dump
needs: the company blurb mentions Rust once and every opening would match.
`max_jobs` caps the jobs kept per run (`0` means no cap). Once `max_boards` boards
have been registered, search paging stops, so extra result pages are not billed. A
sweep is `allow_empty` by default because zero matches is a valid result, and a
board that 404s or exceeds the response cap is logged (`ats_board_fetch_failed
url=… error=…`) and skipped rather than failing the source. Board APIs are
public: the search provider's API key is never forwarded to them, and they are
exempt from the `robots.txt` check (the search endpoint is still checked).

Greenhouse boards are read with `?content=true`, because the plain listing omits
the posting body and the keyword/location filter was therefore matching titles
only (GitLab's board went from 1 to 14 matches once the body was included). A
host that rejects the parameter falls back to the plain listing (logged as
`greenhouse_content_fallback`), which still yields every title and date.
Greenhouse dates come from `first_published` (falling back to `updated_at`):
`updated_at` moves on every edit, so a fresh posting could look old. Only the
first 2 KB of a description is stored, but the filters match the whole text
(Greenhouse and Lever both pass the full body as `match_text`): a tech stack
usually sits far past the first paragraph.

**Freshness.** `max_age_days` is a per-source window applied to every discovery
batch, sweep or not: board payloads and results-mode search payloads (Google
Jobs) alike. It only acts on **dated** postings — undated rows are always kept,
because a source that publishes no dates would otherwise look like an empty
board. Google Jobs reports the age as an `extensions` chip ("5 days ago"), not
as `detected_extensions.posted_at`; both are read, and only chips that read
like an age are parsed, so a salary or a contract length cannot become a
posting date. Each run logs `discovery_age_filter max_age_days=… stale=…
undated=… kept=…` when the window is set; `undated` equal to `kept` means the
source reports no dates at all and the window is doing nothing.

**Budgeting a sweep over several queries.** A sweep with a `queries` list walks
*every* query, not only the pages of the first one: `max_pages` counts pages per
query, so a run may fetch `max_pages × len(queries)` search pages. `max_boards` is
split **equally** between the queries that have not run yet (a query that finds
fewer boards than its share leaves the difference to the ones after it), with
`min_boards_per_query` as the floor. Before that, queries were served in order:
on a measured 12-query sweep the first two (both Ashby) spent 30 of the 50 slots
and both `site:greenhouse.io` queries registered two boards each — both of them
already read, so those queries added no coverage at all. Board fetches use
their own short cooldown (`board_rate_limit_seconds`, default 3 s) while the
search API keeps the source's `rate_limit_seconds`; `sweep_max_seconds` stops the
run when the wall clock is spent. A board JSON carries every opening with its
full description, so board reads get a larger response cap (16 MB) than the
2 MB page default — Ashby's `openai` board alone is ~13 MB. Each run logs one
`ats_sweep_summary boards=… offered=… jobs=… stale=… undated=… queries=… seeds=…
first=…` line plus one `ats_sweep_query query=… offered=… read=… blocked=… dead=…`
line per query; `offered` counts every board the queries surfaced, so `blocked` boards
are exactly what a larger `max_boards` (or fewer queries) would buy, while
`read > offered` means the query re-registered a board an earlier one had already
paid for. `stale`/`undated` are the freshness gate's counters (see **Freshness**
above) and `first` counts the boards read for the first time inside the rotation
window (equal to `boards` means the sweep is still exploring; `0` means it only
re-read what it already knew). Per board the sweep logs `ats_sweep_board query=…
ats=… url=… visit=first|repeat` when it registers it (`query=seed` for
`seed_urls`, `query=deferred` for the boards drained at the end of the run) and
`ats_sweep_board_jobs url=… openings=… kept=…` after filtering, which is what
tells a dead/empty board
(`openings=0`) from an over-strict filter (`openings>0 kept=0`). A board that
answers 404/410 is remembered in Redis for a week (`ats_board_miss:<url>`, logged
as `ats_board_dead url=… status=…`) and skipped by later sweeps without spending
a slot (`ats_sweep_board_skipped url=… reason=dead`): the index keeps returning
moved or misnamed boards, and re-reading them was ~8% of the read budget in the
audit. Other failures (5xx, size cap) are retried on the next run. Grep one run's
board manifest with `grep ats_sweep_board <log>`.

**Rotation: coverage across runs, not per run.** A sweep offers more boards than
`max_boards` affords — 171 offered against 50 read in the audited run — and the
boards that lose that race lost it *every* run: the query list and the index
ranking barely move day to day. Among the ~120 boards left out, a posting went
unseen for as long as it stayed open, however well it matched. Storage already
dedupes per source on URL and `external_id` (`_store_jobs`/`_existing_keys`), so
re-reading a board costs one request and stores nothing twice; the only real
cost is the per-run board budget. Boards are therefore ranked by **last read**
before their snippet score: never read first, then the ones due again (older
than `board_reread_days`, default 3), then the ones read inside the window, each
bucket oldest-read-first. It is a permutation, never a filter.

With `P = ⌈offered / max_boards⌉` runs per cycle and one run per day, a board is
read about once every `P` runs, so a posting that stays open for `L` runs is
missed with `P(miss) ≈ max(0, (P − L)/P)`. For 171 offered boards and a 50-board
budget, `P = 4`: anything that lives a day or two is caught by the cycle instead
of by luck. That is also why `max_age_days` has to stay above `3 × P` days (21
days here): a posting shorter-lived than the cycle can be gone before its board
comes round again. Two guards keep the scheme honest:

- **Only a successful read counts.** The timestamp is written when the board
  payload comes back, never at registration, so a board that answers 5xx keeps
  its place at the front of the queue instead of being rotated as if reviewed.
- **Redis is optional.** Recency lives in `ats_board_seen:<source>:<url>`
  (30-day TTL, `backend/app/services/board_memory.py`). If Redis is down or
  flushed, the lookup degrades to "never read", which restores the plain index
  order and logs `board_seen_lookup_failed` once: a degraded run loosens the
  rotation, it never fails the scrape. `board_reread_days: 0` (or a scraper
  built without a source id) disables rotation entirely and does no lookups.

**Leftover budget is spent, not lost.** The equal per-query share parks boards
whenever a later query comes back thinner than its share. Those boards are
remembered during the run and read after the last search page (`drain_urls`,
logged as `ats_sweep_deferred registered=… parked=… dead=… blocked=… boards=…`),
so a query with unused slots no longer costs its boards a whole cycle. This is
what recovers the measured 240-offered/152-read baseline: 88 boards were offered
and affordable but never registered.

**A board is read whole, and the cap is logged.** Lever and SmartRecruiters page
(`skip` and `offset` respectively, 100 postings per request); Greenhouse, Ashby,
Workable, Recruitee, Personio and Workday answer with the entire board. Reading
only the first page used to be silent: a 715-posting Lever board was stored as
its 100 first postings and nothing in the log said so (Bluelight's board, and
SmartRecruiters' `Ubisoft2` at `totalFound: 344`). A paginated board is now read
page by page and folded back into one payload (`ats_board_read url=… pages=…
postings=…`), until the board is exhausted or `board_max_jobs` (default 1000) is
reached — the cap is reported as `ats_board_truncated url=… postings=…
cap=…` so a truncated board never looks complete. `limit`/`board_page_size`
still sizes a single request, and `max_results` still caps what is *kept*.

**Which boards a sweep can even see.** A budget can only spend boards the index
offers, and the index only offers boards its ranking likes. Measured on Brave
(2026-10-24): the sweep's `golang site:greenhouse.io` returns 8 Greenhouse
boards on page 1 and never Alpaca's on pages 1–4, while the same search with a
region — `golang remote brazil site:greenhouse.io` — returns three of Alpaca's
postings, two of which pass the source's own keyword and location filters
(`match_in: anywhere`; with `match_in: title` both are dropped, because their
bodies, not their titles, mention Go). Two levers close that gap, neither of
which invents vocabulary for the queries: `query_hints` appends wording the
source owner chose to every query, and `seed_urls` names a board directly so it
is read every run whatever the ranking does. Both are retrieval hints only — a
posting is still kept or dropped by `keywords`/`exclude_keywords`/`locations`.
A hit in the index that no longer exists on the board (a stale result, or a
company that moved ATS) is expected noise, not a miss: the board answers 404 or
is absent, and that is logged and remembered, not retried forever.

**How deep a sweep reads, and where it stops.** Brave's `offset` is a *page*
number, so `max_pages: 2` reads pages 1–2 of every query. Measured on the 12-query
sweep (2026-10-22): page 1 offered 171 boards and page 2 took that run to 210 (its
own cap; the same two pages offer 244 under `max_boards: 240`). Replaying the
offsets directly, page 3 added two boards, page 4 one and page 5 none — the API
stops serving new boards after the second page for these `site:` queries, so two
pages capture its whole set and further pages only re-spend the search cooldown.
Page 2 is not a second helping of page 1: in the run that read both pages end to
end, 97 of the 229 boards read were nowhere in the baseline (102 were absent from
the front-end's page-1 list alone), while page 2 added only two boards *within*
that list — it is a different slice of the index. A page is also not 20 boards: a
board with many matching postings fills several result slots (GitLab took 4 of 20
on one query), so a page yields ~14 distinct orgs, which is why `offered` sits well
below `20 × pages × queries`. The remaining gap against the `search.brave.com`
front-end is upstream index coverage, not request parameters: replaying the same
queries with `country`/`search_lang` returned the same boards
(`country=BR&search_lang=pt` is even rejected with HTTP 422), and 17 of the 150
boards the front-end showed on page 1 never came back at any offset (0–4).
Reading those 17 directly explains them: 4 answer 404, 2 are empty, 8 have no
opening matching the filters, and the remaining 3 (okta, worldquant, avride)
carry 24 kept jobs — the priced residual of this discovery mechanism.

**What a healthy sweep looks like.** The bar the 2026-10-22 audit settled on:
`offered` may exceed `boards` by up to one page — the last page fetched overflows
`max_boards` — and anything larger means the budget is binding; `max_jobs` must sit
above what a full run keeps, because once spent it stops discovery too and a short
`boards` reads as a board-budget problem. Coverage should sit at the two-page
ceiling: 132 of the 150 boards the front-end showed on page 1, of which 127 are on
page 1 and 5 only on page 2 (the other 18 never come back at any offset: 4 are 404,
2 empty, 8 without a matching opening, 3 worth 24 jobs); a board lost to a timeout
or a 404 is the only reason to fall short. And job-level parity on spot checks —
every job a spot-checked board shows inside `max_age_days` is stored with the
board's own posting date. Job counts are pre-dedupe by URL/requisition id only, so a
role re-posted under a new id is stored once per id (one Workato title existed five
times on 2026-10-22); that is storage-by-id, not a parsing bug. Nothing prunes jobs
that a board stops listing: a withdrawn posting, or one stored before
`max_age_days` was configured, stays in `jobs` until the user hides it.

**Bright Data endpoints.** `endpoint` picks which Bright Data API to call, and
it must match the zone the key belongs to: `unlocker` (default for
`engine: linkedin`/`indeed`, or when the config sets `url`/`url_tpl`) POSTs
`{"zone", "url"}` to `https://api.brightdata.com/request`; `serp` POSTs to
`https://api.brightdata.com/serp/req?customer=&zone=`. `zone` is required either
way, and an explicit `https://` value in `endpoint` overrides the built-in URL if
Bright Data moves it. `robots.txt` is always checked against the **board** the
provider renders (LinkedIn/Indeed), never against the API endpoint. Pagination
needs `page_tpl` (`{"page_tpl": "{page}0"}` → `start=20` on page 2) plus
`max_pages`, because every page is another billed render; without `page_tpl`
(and for `url`/`url_tpl` targets, which pin one page) there is a single render.
`serpapi` also accepts `link_source: google` to store
the `google.com/search?ibp=htl;jobs…` link instead of the `apply_options[].link`
board URL (the default, and the only one that works outside a browser session).
`gl`/`hl` pin the Google Jobs country and interface language (for example
`{"gl": "us", "hl": "en"}` for broad English-language remote searches). Country
indexes differ sharply: a Brazil-localised query for `c++ remote` can return
`Fully empty` even though the same query from the US index returns dozens of
`Anywhere` roles. For worldwide remote coverage, omit `location` (Google rejects
`Worldwide` as a location) and use `gl: "us"`; review work-authorization and
clearance requirements in the results. The provider appends the source's API key
to `serpapi_pagination.next`, because SerpApi returns that URL without one and
page 2+ would otherwise 401 — each page is still another billed search, so cap
it with `max_pages`.
`remote_only: true` keeps only results whose `detected_extensions.work_from_home`
is set (or whose title/location/extensions contain a remote marker such as
`Remote`, `Remoto`, `Home office`). `via_filter: "glassdoor"` (a string, a list,
or `true` as shorthand for Glassdoor) keeps results attributed to that board in
`via`/`apply_options`; leave it off for recall, since Google's attribution is
incomplete and drops valid Glassdoor jobs.

## Out of scope (documented, not attempted)

Moved out of these buckets: FullStack Talent (`talent.fullstack.com`) is now
collected through its public JSON API — see *Id-only JSON boards* above.

- **Login-walled dashboards / talent networks** (Outlier, Alignerr, Toptal,
  Turing, Upwork, Revelo, Lemon.io, FlexJobs, VanHack, Proxify and similar) —
  need authenticated candidate context (cookies + often 2FA/SSO). Track them as
  `type = manual` sources instead (ADR 018): the user re-checks them by hand and
  the app reminds them when due. Verified into this bucket: arc.dev, beon.tech,
  Crossover, Encora (`careers.encora.com`), Greenhouse's
  candidate dashboard, Impulso, Randstad, Remotar, Trampos, Tecla, X-Team
  (`x-team.com/remote-jobs` 404s; `jobs.x-team.com` is a shell — see the JS-only
  shells below), Vagas.com.br's *meu-perfil* — none of
  them render job rows into the initial HTML.
- **ToS / anti-bot by direct scraping** — LinkedIn, Indeed, Glassdoor, Dice,
  Catho, Jobot, Levels.fyi, Landing.jobs, Wellfound, Hays, Michael Page, Robert
  Half, SimplyHired, Welcome to the Jungle, Himalayas, Stack Overflow Jobs. Use
  the paid providers above (`serpapi` `google_jobs` covers most of them);
  Friday Glee, Outscal, VanHack and YellowIpe block the request outright
  (HTTP 526 / TLS), so they are `manual` until a provider is wired up.
- **Not listings / dead** — DuckDuckGo *query* URLs (returns a 25 KB JS shell with
  no results; use `google_cse`/`bing`/`brave` with the same `site:` query instead,
  e.g. `{"provider": "google_cse", "query": "site:jobs.lever.co rust remote"}`),
  `jobboardsearch.com` and `readytotouch.com`
  (directories: no job rows to extract), archived `lerrua/remote-jobs-brazil`,
  single-job URLs, 404/5xx boards (`careers.solvd.com` no longer resolves,
  `x-team.com/remote-jobs` is gone).
- **JS-only shells** (a 200 with all the markup but **0** job rows/links; nothing
  to select). Verified: `career.sigma.software/what-we-offer/vacancies/` (the
  `?location=` filter changes only the UI state), `remotifyeurope.com/remote-jobs`
  (its JSON-LD blocks describe the *site*, not jobs), `br.jobsora.com/empregos`,
  `remotar.com.br` (`__NEXT_DATA__` present but `pageProps` is empty),
  `jobs.x-team.com` (`x-team.com/remote-jobs` is a 404 and the current host is an
  SPA shell), `app.tecla.io/jobs`, `work.turing.com/jobs`, `himalayas.app`
  (HTTP 403). Keep them `manual` (ADR 018) or wire up a provider — a stored URL
  with extra query arguments does not help when the listing is fetched by JS.
- **Hash-route SPAs** — `jobs.hirewithnear.com/#/` renders its list from the URL
  fragment, so a fetch only ever returns the shell; keep it `manual` (or probe the
  API it calls) until an opt-in renderer exists.


## Compliance, maintenance

`respect_robots_txt` is on by default and applies to every real page fetch (paid
renderer calls and detail pages included); disallowed sources are recorded as
`skipped` and never trip the circuit breaker. A robots.txt fetch that fails
(timeout, DNS/TLS, 5xx) is **not** treated as a `Disallow`: the attempt is
denied conservatively, recorded as `robots.txt unreachable`, retried after a
short backoff (15 min) and cached for only 60 s, so one network blip cannot
freeze a healthy source. A 4xx response means "no restrictions published"
(RFC 9309) and allows the fetch. For renderer providers the check
follows `robots_url` back to the **board** that is being rendered (LinkedIn,
Indeed), not to the vendor's API host — the vendor's endpoint is not the site we
are scraping. A pure API provider (SerpApi) returns `None` from `robots_url` for
its own `/search` endpoint, so its `Disallow: /search?` cannot skip every
scheduled run; the board/detail links it discovers are still checked normally.
`rate_limit_seconds` is a per-domain cooldown before *every* request, so 30
sources at the default is deliberately slow. Third-party keys are stored
encrypted and billed per query — hence `parse_listing` (`serpapi`:
`parse_mode: results`) and `page_tpl` breadcrumbs above: one render per page
instead of one per job.

| Symptom | Likely cause | Action |
|---|---|---|
| `parse produced 0 jobs` | selectors drifted / site became JS-rendered | re-inspect; fix selectors or drop the source |
| SerpApi returns `Fully empty` / 0 raw results | query or country index too narrow (e.g. `gl=br` + `location=Brazil`) | remove `location`, use `gl: "us"`/`hl: "en"`, and preview again |
| `authentication failed (HTTP 401/403)` | expired/incorrect API key | re-save the key on the source |
| `skipped: robots.txt disallows this source` | disallowed path (a rule) | do not bypass; use a provider instead |
| `skipped: robots.txt unreachable at …` | timeout/DNS/TLS/5xx while fetching robots.txt (transient) | retried automatically after 15 min; use *Re-check now* in the health panel |
| Repeated failures | circuit breaker open | fix the root cause, then let the breaker close |
| Company stored as `Unknown` | listing has no company node | add `company_selector` or accept it |

**Deferred** — an opt-in headless renderer (separate Playwright container behind
an env flag, keeping robots/rate-limit/response-size limits) is the only way to
reach the remaining pure-JS SPAs; ADR 005/010 defer it as "per-site opt-in
later".
