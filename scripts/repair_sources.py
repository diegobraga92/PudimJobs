"""Dry-run-first repairs for source configs and already-stored jobs.

The private source catalog is not part of the repository, so these data fixes
cannot ship as a migration. Run this script against the database instead; it
only *writes* when ``--apply`` is passed.

Examples::

    # We Work Remotely: split "Company: Role" titles and strip HTML from feeds.
    python scripts/repair_sources.py --url-contains weworkremotely \\
        --set-config company_from_title=true --set-config strip_html=true \\
        --fix-rss-titles

    # Programathor: drop cards labelled as expired.
    python scripts/repair_sources.py --url-contains programathor \\
        --set-config 'exclude_pattern=\\bexpirad[ao]s?\\b'

    # Stop fetching boards whose selectors no longer work.
    python scripts/repair_sources.py --url-contains infojobs --avoid \\
        --avoid-reason "listing cards are client-rendered"
    python scripts/repair_sources.py --url-contains toughbyte --avoid \\
        --avoid-reason "selectors no longer match"

    # RemoteYeah: remove rows stored before detail/JSON-LD enrichment existed.
    python scripts/repair_sources.py --url-contains remoteyeah \\
        --delete-bare-jobs --bare-company Unknown

Remove ``--apply`` to preview every count and sample row. The script never
deletes a source, and avoiding is reversible with ``--unavoid``.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

from sqlalchemy import delete, func, or_, select

# Allow running as `python scripts/repair_sources.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from scrapers.registry import get_scraper  # noqa: E402
from scrapers.utils import robots_decision  # noqa: E402

from app.database import async_session_factory  # noqa: E402
from app.models import Job, Source  # noqa: E402
from app.models.enums import SourceType  # noqa: E402
from app.services.source_watchlist import set_avoided  # noqa: E402

_TITLE_COMPANY_RE = re.compile(r"^(?P<company>[^:]{1,80}):\s+(?P<title>.+)$")
_UNKNOWN_COMPANIES = {"", "unknown"}


def split_company_title(title: str) -> tuple[str, str] | None:
    """Split ``"Acme Corp: Senior Engineer"`` into ``(title, company)``."""
    match = _TITLE_COMPANY_RE.match((title or "").strip())
    if not match:
        return None
    return match.group("title").strip(), match.group("company").strip()


def job_haystack(job) -> str:
    """Text a cleanup pattern is matched against (same fields as the scraper)."""
    return " ".join(
        filter(
            None,
            [job.title, job.company, job.description, job.url, " ".join(job.tags or [])],
        )
    )


def needs_detail_refresh(job) -> bool:
    """True when a stored row is missing the fields a detail fetch can fill."""
    return (
        not job.description
        or len(job.description.strip()) < 80
        or (job.company or "").strip().lower() in _UNKNOWN_COMPANIES
        or job.posted_date is None
    )


def apply_detail_fields(job, candidate) -> list[str]:
    """Fill a stored job from a parsed detail row; return the changed fields.

    Only missing/short data is replaced, so a good stored description is not
    overwritten by a card snippet or an "Unknown" company.
    """
    changed: list[str] = []
    if candidate.title and candidate.title.strip() and candidate.title != job.title:
        job.title = candidate.title.strip()
        changed.append("title")
    company = (candidate.company or "").strip()
    if company and company.lower() not in _UNKNOWN_COMPANIES and company != job.company:
        job.company = company
        changed.append("company")
    description = (candidate.description or "").strip()
    if description and len(description) > len((job.description or "").strip()):
        job.description = candidate.description
        changed.append("description")
    if candidate.posted_date and not job.posted_date:
        job.posted_date = candidate.posted_date
        changed.append("posted_date")
    if candidate.tags and not job.tags:
        job.tags = list(candidate.tags)
        changed.append("tags")
    return changed


def apply_listing_fields(job, item: dict) -> list[str]:
    """Update a feed row from its current feed entry; return the changed fields."""
    changed: list[str] = []
    title = (item.get("title") or "").strip()
    if title and title != job.title:
        job.title = title
        changed.append("title")
    company = (item.get("company") or "").strip()
    if company and company.lower() not in _UNKNOWN_COMPANIES and company != job.company:
        job.company = company
        changed.append("company")
    description = item.get("description")
    if description and description != job.description:
        job.description = description
        changed.append("description")
    if item.get("posted_date") and item["posted_date"] != job.posted_date:
        job.posted_date = item["posted_date"]
        changed.append("posted_date")
    tags = item.get("tags") or []
    if tags and tags != (job.tags or []):
        job.tags = list(tags)
        changed.append("tags")
    return changed


def _detail_target(candidates: list, job) -> object | None:
    """The parsed detail row for ``job`` (URL match first, then the first row)."""
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.url and job.url and candidate.url.rstrip("/") == job.url.rstrip("/"):
            return candidate
    return candidates[0]


def parse_config_assignments(values: list[str]) -> dict:
    """Parse ``KEY=JSON`` pairs; bare strings remain strings.

    JSON is preferred so booleans/numbers/lists keep their type:
    ``company_from_title=true`` becomes ``True``, not the string ``"true"``.
    """
    config: dict = {}
    for item in values:
        key, separator, raw = item.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError(f"expected KEY=VALUE, got {item!r}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        config[key] = value
    return config


def _source_matches(source: Source, url_terms: list[str], name_terms: list[str]) -> bool:
    url = (source.url or "").lower()
    name = (source.name or "").lower()
    return any(term.lower() in url for term in url_terms) or any(
        term.lower() in name for term in name_terms
    )


def _feed_page_url(url: str, page: int) -> str:
    """Page 1 is the stored feed URL; later pages use WordPress' ``paged``."""
    if page <= 1:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}paged={page}"


def _robots_blocker(url: str) -> str | None:
    """Printable reason when ``url`` may not be fetched, else ``None``.

    Keeps the script honest about *why* it skipped: a robots.txt outage is not
    a ``Disallow`` and is worth retrying later.
    """
    decision = robots_decision(url)
    if decision.allowed:
        return None
    if decision.reason == "disallowed":
        return f"robots.txt disallows {decision.robots_url}"
    detail = decision.error or (
        f"HTTP {decision.status_code}" if decision.status_code else "fetch failed"
    )
    return f"robots.txt unreachable ({detail}); retry later"


async def _reparse_rss(
    source: Source, session, *, apply: bool, pages: int = 1
) -> int:
    """Refresh stored RSS rows from the current feed, without fetching details."""
    if source.type != SourceType.rss:
        print("  reparse rss → skipped (source is not type=rss)")
        return 0
    if source.respect_robots_txt:
        blocker = _robots_blocker(source.url)
        if blocker:
            print(f"  reparse rss → skipped ({blocker})")
            return 0

    scraper = get_scraper(source)
    jobs = (
        (await session.execute(select(Job).where(Job.source_id == source.id))).scalars().all()
    )
    by_url = {job.url.rstrip("/"): job for job in jobs if job.url}
    changed = 0
    entries = 0
    samples: list[tuple[str, str, list[str]]] = []
    for page_number in range(1, max(1, pages) + 1):
        page = await scraper.fetch(_feed_page_url(source.url, page_number))
        normalized = scraper.normalize(scraper.parse(page))
        entries += len(normalized)
        for item in normalized:
            url = str(item.get("url") or "").rstrip("/")
            job = by_url.get(url)
            if job is None:
                continue
            fields = apply_listing_fields(job, item)
            if fields:
                changed += 1
                if len(samples) < 5:
                    samples.append((job.title, url, fields))
    print(
        f"  reparse rss → {changed} job(s) updated from {entries} feed entries "
        f"({max(1, pages)} page(s))"
    )
    for title, url, fields in samples:
        print(f"    {title!r} ({url}) → {', '.join(fields)}")
    if apply:
        await session.flush()
    return changed


async def _reparse_list(source: Source, session, *, apply: bool) -> int:
    """Refresh stored list-mode rows from the current listing page."""
    if source.type != SourceType.aggregator or (source.config or {}).get("detail"):
        print("  reparse list → skipped (source is not an aggregator in list mode)")
        return 0
    scraper = get_scraper(source)
    list_url = scraper.first_fetch_url(source.url)
    if source.respect_robots_txt:
        blocker = _robots_blocker(list_url)
        if blocker:
            print(f"  reparse list → skipped ({blocker})")
            return 0
    page = await scraper.fetch(list_url)
    normalized = scraper.normalize(scraper.parse(page))
    jobs = (
        (await session.execute(select(Job).where(Job.source_id == source.id))).scalars().all()
    )
    by_url = {job.url.rstrip("/"): job for job in jobs if job.url}
    changed = 0
    samples: list[tuple[str, str, list[str]]] = []
    for item in normalized:
        url = str(item.get("url") or "").rstrip("/")
        job = by_url.get(url)
        if job is None:
            continue
        fields = apply_listing_fields(job, item)
        if fields:
            changed += 1
            if len(samples) < 5:
                samples.append((job.title, url, fields))
    print(f"  reparse list → {changed} job(s) updated from {len(normalized)} cards")
    for title, url, fields in samples:
        print(f"    {title!r} ({url}) → {', '.join(fields)}")
    if apply:
        await session.flush()
    return changed


async def _refresh_details(source: Source, session, args: argparse.Namespace) -> int:
    """Fetch every stored detail URL that is missing data and merge the result."""
    if source.type != SourceType.aggregator or not (source.config or {}).get("detail"):
        print("  refresh details → skipped (source is not an aggregator in detail mode)")
        return 0

    jobs = (
        (
            await session.execute(
                select(Job).where(Job.source_id == source.id).order_by(Job.created_at)
            )
        )
        .scalars()
        .all()
    )
    targets = jobs if args.refresh_all else [job for job in jobs if needs_detail_refresh(job)]
    if args.max_jobs is not None:
        targets = targets[: args.max_jobs]
    if not targets:
        print("  refresh details → no rows need a detail fetch")
        return 0

    scraper = get_scraper(source)
    delay = args.rate_limit if args.rate_limit is not None else source.rate_limit_seconds
    updated = 0
    skipped = 0
    failed = 0
    last_request = 0.0
    print(
        f"  refresh details → {len(targets)} job(s), {delay}s between requests"
        + (" (dry run: fetched but not written)" if not args.apply else "")
    )
    for index, job in enumerate(targets, start=1):
        if not job.url:
            skipped += 1
            continue
        if source.respect_robots_txt and _robots_blocker(job.url):
            skipped += 1
            continue
        if last_request:
            wait = delay - (time.monotonic() - last_request)
            if wait > 0:
                await asyncio.sleep(wait)
        last_request = time.monotonic()
        try:
            page = await scraper.fetch(job.url)
            candidate = _detail_target(scraper.parse(page), job)
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the batch
            failed += 1
            print(f"    [{index}/{len(targets)}] {job.url} → {type(exc).__name__}: {exc}")
            continue
        if candidate is None:
            skipped += 1
            continue
        fields = apply_detail_fields(job, candidate)
        if fields:
            updated += 1
        if index % 10 == 0 or index == len(targets):
            print(
                f"    [{index}/{len(targets)}] updated={updated} "
                f"skipped={skipped} failed={failed}"
            )
        if args.apply and fields and updated % 25 == 0:
            # Commit periodically: a 100-job batch at 30s/request can run for
            # almost an hour, and losing all of it to one late failure is worse
            # than the tiny extra transaction overhead.
            await session.commit()
    if args.apply and updated:
        await session.commit()
    print(
        f"  refresh details → updated={updated} skipped={skipped} failed={failed}"
        + ("" if args.apply else " (dry run)")
    )
    return updated


async def _repair(args: argparse.Namespace) -> int:
    assignments = parse_config_assignments(args.set_config)
    async with async_session_factory() as session:
        sources = (await session.execute(select(Source).order_by(Source.name))).scalars().all()
        matched = [
            source
            for source in sources
            if _source_matches(source, args.url_contains, args.name_contains)
        ]
        if not matched:
            print("No source matched the --url-contains/--name-contains filters.")
            return 1

        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"{mode}: {len(matched)} source(s) matched")

        for source in matched:
            print(f"\n[{source.name}] {source.url} ({source.id})")

            if assignments:
                config = {**(source.config or {}), **assignments}
                print(f"  config → {json.dumps(config, ensure_ascii=False, sort_keys=True)}")
                if args.apply:
                    source.config = config

            if args.avoid:
                print(f"  avoid → {args.avoid_reason or 'no reason given'}")
                if args.apply:
                    set_avoided(source, True, args.avoid_reason)
            elif args.unavoid:
                print("  restore from avoid")
                if args.apply:
                    set_avoided(source, False)

            if args.fix_rss_titles:
                jobs = (
                    await session.execute(
                        select(Job).where(Job.source_id == source.id).order_by(Job.created_at)
                    )
                ).scalars().all()
                fixes: list[tuple[Job, str, str]] = []
                for job in jobs:
                    split = split_company_title(job.title)
                    if split is None:
                        continue
                    new_title, new_company = split
                    if job.title != new_title or job.company != new_company:
                        fixes.append((job, new_title, new_company))
                print(f"  title/company splits → {len(fixes)} job(s)")
                for job, new_title, new_company in fixes[:5]:
                    print(f"    {job.title!r} → {new_title!r}; company={new_company!r}")
                if args.apply:
                    for job, new_title, new_company in fixes:
                        job.title = new_title
                        job.company = new_company


            if args.reparse_rss:
                await _reparse_rss(
                    source, session, apply=args.apply, pages=args.rss_pages
                )

            if args.reparse_list:
                await _reparse_list(source, session, apply=args.apply)

            if args.refresh_details:
                await _refresh_details(source, session, args)

            if args.delete_matching or args.delete_all_jobs:
                jobs = (
                    await session.execute(select(Job).where(Job.source_id == source.id))
                ).scalars().all()
                if args.delete_all_jobs:
                    doomed = list(jobs)
                    label = "all jobs"
                else:
                    patterns = [
                        re.compile(pattern, re.IGNORECASE)
                        for pattern in args.delete_matching
                    ]
                    doomed = [
                        job
                        for job in jobs
                        if any(pattern.search(job_haystack(job)) for pattern in patterns)
                    ]
                    label = f"jobs matching {args.delete_matching!r}"
                print(f"  delete → {len(doomed)} job(s) ({label})")
                for job in doomed[:5]:
                    print(f"    {job.title!r} ({job.url})")
                if args.apply and doomed:
                    await session.execute(delete(Job).where(Job.id.in_([job.id for job in doomed])))

            if args.delete_bare_jobs:
                bare = (
                    await session.execute(
                        select(Job).where(
                            Job.source_id == source.id,
                            Job.company == args.bare_company,
                            or_(
                                Job.description.is_(None),
                                func.length(func.trim(Job.description))
                                < args.bare_max_description,
                            ),
                        )
                    )
                ).scalars().all()
                print(
                    "  bare jobs → "
                    f"{len(bare)} job(s) with company={args.bare_company!r} and "
                    f"description shorter than {args.bare_max_description} chars"
                )
                for job in bare[:5]:
                    print(f"    {job.title!r} ({job.url})")
                if args.apply and bare:
                    await session.execute(delete(Job).where(Job.id.in_([job.id for job in bare])))

        if args.apply:
            await session.commit()
            print("\nChanges committed.")
        else:
            await session.rollback()
            print("\nDry run only; pass --apply to write these changes.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url-contains",
        action="append",
        default=[],
        help="match sources whose URL contains this text (repeatable)",
    )
    parser.add_argument(
        "--name-contains",
        action="append",
        default=[],
        help="match sources whose name contains this text (repeatable)",
    )
    parser.add_argument(
        "--set-config",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="merge a config key, e.g. company_from_title=true (repeatable)",
    )
    parser.add_argument("--fix-rss-titles", action="store_true")
    parser.add_argument(
        "--reparse-rss",
        action="store_true",
        help="refresh stored RSS rows from the current feed (one HTTP request)",
    )
    parser.add_argument(
        "--reparse-list",
        action="store_true",
        help="refresh stored aggregator rows from the current listing page",
    )
    parser.add_argument(
        "--rss-pages",
        type=int,
        default=1,
        help="feed pages to walk with --reparse-rss (WordPress ?paged=N)",
    )
    parser.add_argument(
        "--refresh-details",
        action="store_true",
        help="fetch stored detail URLs missing company/description/date",
    )
    parser.add_argument(
        "--refresh-all",
        action="store_true",
        help="with --refresh-details, refetch every stored row (not only incomplete ones)",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="cap rows fetched by --refresh-details",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=None,
        help="seconds between --refresh-details requests (default: source setting)",
    )
    parser.add_argument(
        "--delete-matching",
        action="append",
        default=[],
        metavar="REGEX",
        help="delete jobs whose title/company/description/tags match (repeatable)",
    )
    parser.add_argument(
        "--delete-all-jobs",
        action="store_true",
        help="delete every stored job for the matched source(s)",
    )
    parser.add_argument("--delete-bare-jobs", action="store_true")
    parser.add_argument("--bare-company", default="Unknown")
    parser.add_argument("--bare-max-description", type=int, default=40)
    parser.add_argument("--avoid", action="store_true")
    parser.add_argument("--unavoid", action="store_true")
    parser.add_argument("--avoid-reason", default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the changes (without it the script only reports)",
    )
    args = parser.parse_args(argv)

    if not args.url_contains and not args.name_contains:
        parser.error("provide --url-contains and/or --name-contains")
    if not (
        args.set_config
        or args.fix_rss_titles
        or args.reparse_rss
        or args.reparse_list
        or args.refresh_details
        or args.delete_matching
        or args.delete_all_jobs
        or args.delete_bare_jobs
        or args.avoid
        or args.unavoid
    ):
        parser.error("nothing to do: choose a config/title/cleanup/avoid action")
    if args.avoid and args.unavoid:
        parser.error("--avoid and --unavoid are mutually exclusive")

    try:
        return asyncio.run(_repair(args))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

