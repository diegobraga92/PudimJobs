"""Bulk-create PudimJobs sources from a local catalog file.

Keeps a private board list out of the repository: the catalog lives on disk (or
in a secret manager) and this script only POSTs it to *your* API.

Usage::

    python scripts/import_sources.py --file ~/sources.json --token "$JWT"
    python scripts/import_sources.py --file ~/sources.json --token "$JWT" --dry-run

The file is either a JSON array or ``{"sources": [...]}``, each entry shaped like
the API's source model::

    [
      {"name": "Acme board", "url": "https://boards.example/acme",
       "type": "discovery",
       "config": {"provider": "greenhouse", "board_token": "acme"}},
      {"name": "Acme feed", "url": "https://boards.example/feed.xml", "type": "rss"}
    ]

Service ``type`` reasoning: ``discovery`` for ATS/JSON/search providers,
``aggregator`` for selector-driven HTML boards, ``rss`` for feeds and
``career_page`` for a single listing.

Credentials are never imported — set them per source afterwards with
``PUT /api/sources/{id}/auth``. Imports are idempotent (matched on ``url`` +
``type``), so re-running the same file is safe. Get a token with
``POST /api/auth/login``.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def load_catalog(path: str | Path) -> list[dict]:
    """Read a catalog file into a list of source payloads.

    Accepts a bare JSON array or an object with a ``sources`` key, and validates
    that every entry has the keys the API requires.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("sources")
    if not isinstance(data, list) or not data:
        raise ValueError("catalog must be a non-empty JSON array (or {'sources': [...]})")
    catalog: list[dict] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"entry {index} is not an object")
        missing = [key for key in ("name", "url", "type") if not entry.get(key)]
        if missing:
            raise ValueError(f"entry {index} is missing: {', '.join(missing)}")
        catalog.append(entry)
    return catalog


async def import_catalog(
    base_url: str, token: str, catalog: list[dict], *, dry_run: bool = False
) -> dict:
    """POST the catalog to ``/api/sources/import`` and return the report."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/sources/import",
            headers={"Authorization": f"Bearer {token}"},
            json={"sources": catalog, "dry_run": dry_run},
        )
        response.raise_for_status()
        return response.json()


async def _run(args: argparse.Namespace) -> int:
    try:
        catalog = load_catalog(args.file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"catalog error: {exc}", file=sys.stderr)
        return 2

    print(f"{len(catalog)} source(s) in {args.file}" + (" [dry run]" if args.dry_run else ""))
    try:
        report = await import_catalog(
            args.base_url, args.token, catalog, dry_run=args.dry_run
        )
    except httpx.HTTPStatusError as exc:
        print(
            f"API error {exc.response.status_code}: {exc.response.text[:300]}",
            file=sys.stderr,
        )
        return 1
    except httpx.HTTPError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 1

    for item in report.get("results", []):
        detail = f" — {item['reason']}" if item.get("reason") else ""
        print(f"  [{item['status']:7}] {item['name']}{detail}")
    print(
        f"created={report.get('created', 0)} "
        f"skipped={report.get('skipped', 0)} invalid={report.get('invalid', 0)}"
    )
    return 1 if report.get("invalid") else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, help="JSON catalog to import")
    parser.add_argument("--token", required=True, help="JWT from POST /api/auth/login")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be created without writing",
    )
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
