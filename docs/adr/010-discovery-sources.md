# ADR 010 — Discovery Sources (Search APIs, ATS Feeds, Gated HTML Scraping)

Status: accepted
Date: 2026-08-13

## Context

Sources come in three types today: `career_page`, `aggregator` (CSS-selector
adapters), and `rss`. All of them fetch a single listing URL and parse jobs from
it. There is no support for *discovering* jobs across the open web — e.g.
"find jobs matching `site:ashby.com Python Remote Brazil`" — or for boards that
expose a structured JSON feed instead of HTML.

Two new shapes are needed:

1. **ATS feeds** (Ashby, Greenhouse, Lever, Workable): a public JSON endpoint
   that returns complete job postings in one response.
2. **Search-based discovery** (Google CSE, Bing, Brave; or HTML-scraping
   Google/Bing/DuckDuckGo): a query returns *links* to job postings, which must
   then be fetched and parsed individually (two stages).

HTML-scraping of search engines is a ToS/robots.txt problem, so the plan is to
ship it but **disabled by default** (an operator opt-in flag), mirroring the
existing `SCRAPER_ALLOW_PRIVATE_NETWORKS` precedent.

## Decision

Introduce a new source type **`discovery`** with a pluggable **provider
registry** (`scrapers/discovery.py`), selected per source via
`sources.config["provider"]` — the same pattern as aggregator adapters.

- The scraper contract gains an optional async hook
  `discover_urls(page) -> list[str]` (default `[]`): when a results page yields
  detail URLs, the scrape task fetches each (with per-result-domain robots and
  rate limiting, capped by `max_results`) before falling back to `parse()`.
  Existing single-page scrapers are unchanged.
- ATS providers are one-stage (JSON endpoint → jobs); search providers are
  two-stage (results → links → detail pages).
- Search-API keys are stored encrypted via a new `api_key` source-auth type
  (string-backed enum → no migration); Google puts it in the query string,
  Bing/Brave in an `X-...`/`Ocp-Apim-...` header.
- A `GET /api/sources/providers` endpoint publishes provider metadata
  (family, `requires_key`) so the UI renders the dropdown data-driven.

## Alternatives considered

- Reusing the `aggregator` type with more adapters — rejected: discovery
  semantics are cross-domain and two-stage, unlike single-domain listing pages.
- Scraping `google.com/search` as the primary approach — rejected: ToS/robots;
  APIs are the supported path.
- In-process provider config without encrypted keys — rejected: search keys are
  secrets and must not sit in plaintext `sources.config`.

## Consequences

- New sources require zero DB migration (`type` and `auth_type` are string
  enums; `config` is JSONB).
- Discovery scrapes are more expensive (N detail fetches); per-domain rate
  limiting + `max_results` keep them polite.
- `scrape_runs` replay re-fetches a source but cannot re-run a past search
  query against a transient results page.
- Search-API quotas (Google ~100 free/day) apply; ATS APIs vary in auth
  (Ashby/Lever public, Greenhouse needs a board token).

## LinkedIn & Indeed (third-party search APIs)

LinkedIn Jobs and Indeed have no public API and cannot be fetched as static
HTML (login walls, JS rendering, anti-bot). They are supported through
**paid third-party search APIs**, added as ordinary `search_api` providers:

- `serpapi` — structured JSON via `https://serpapi.com/search` with
  `engine=linkedin_jobs|indeed|google_jobs`; the key is the encrypted
  `api_key` query param. Billed per search query (see vendor pricing).
- `brightdata` — renders the LinkedIn/Indeed search page through their
  Web Unlocker/SERP API (`Authorization: Bearer` + JSON POST) and returns raw
  HTML; result links are parsed with per-engine selectors (overridable).

Both are inherently opt-in (paid keys, no extra gate). The **preferred free
path** for known employers remains ATS-native feeds (`ashby`, `greenhouse`,
`lever`, `workable`) — most LinkedIn/Indeed postings originate there.
