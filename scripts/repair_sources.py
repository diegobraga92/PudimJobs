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
from pathlib import Path

from sqlalchemy import delete, func, or_, select

# Allow running as `python scripts/repair_sources.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT / "backend"), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from app.database import async_session_factory  # noqa: E402
from app.models import Job, Source  # noqa: E402
from app.services.source_watchlist import set_avoided  # noqa: E402

_TITLE_COMPANY_RE = re.compile(r"^(?P<company>[^:]{1,80}):\s+(?P<title>.+)$")


def split_company_title(title: str) -> tuple[str, str] | None:
    """Split ``"Acme Corp: Senior Engineer"`` into ``(title, company)``."""
    match = _TITLE_COMPANY_RE.match((title or "").strip())
    if not match:
        return None
    return match.group("title").strip(), match.group("company").strip()


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

