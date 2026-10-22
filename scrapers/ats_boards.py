"""Resolve public ATS board URLs discovered by a search provider.

A search engine is good at finding *organisations* that use an ATS, but its
index is a poor place to read jobs: the boards are client-rendered, locations
are often not indexed, and results go stale.  Every supported ATS exposes a
public JSON board, so a discovery source can instead turn one search result
into one live board sweep.

This module deliberately knows only how to recognise a board URL and the
config its existing :mod:`scrapers.discovery` provider expects.  It does not
fetch anything, which keeps it dependency-free and easy to test.
"""

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

#: First path segments that are site chrome, not a board identifier.
_NON_BOARD_SEGMENTS = frozenset(
    {
        "api",
        "assets",
        "embed",
        "job_board",
        "jobs",
        "search",
        "static",
    }
)


@dataclass(frozen=True)
class AtsBoard:
    """One public ATS board discovered from a job URL."""

    ats: str
    config: dict

    @property
    def key(self) -> tuple[str, str]:
        """Deduplication key (one board per ATS org/token)."""
        identifier = (
            self.config.get("org")
            or self.config.get("company")
            or self.config.get("board_token")
            or ""
        )
        return self.ats, str(identifier).casefold()


def _path_segments(path: str) -> list[str]:
    return [unquote(segment).strip() for segment in path.split("/") if segment.strip()]


def _is_board_segment(segment: str) -> bool:
    return bool(segment) and segment.casefold() not in _NON_BOARD_SEGMENTS


def resolve_ats_board(url: str) -> AtsBoard | None:
    """Return the ATS board behind ``url``, or ``None`` for anything else.

    Supported URL shapes (the public job/career hosts, not their APIs):

    * ``jobs.ashbyhq.com/{org}[/...]``
    * ``jobs.lever.co/{company}[/...]`` and ``jobs.eu.lever.co/{company}``
    * ``boards.greenhouse.io/{token}[/...]`` and ``job-boards.greenhouse.io``
    * ``jobs.smartrecruiters.com/{company}[/...]`` and the ``careers.`` host
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").casefold()
    segments = _path_segments(parsed.path)
    if not segments or not _is_board_segment(segments[0]):
        return None
    identifier = segments[0]

    if host == "jobs.ashbyhq.com":
        return AtsBoard("ashby", {"org": identifier, "company": identifier})

    if host in {"jobs.lever.co", "jobs.eu.lever.co"}:
        config = {"company": identifier, "limit": 100}
        if host == "jobs.eu.lever.co":
            config["api_host"] = "api.eu.lever.co"
        return AtsBoard("lever", config)

    if host in {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "boards.eu.greenhouse.io",
        "job-boards.eu.greenhouse.io",
    }:
        config = {"board_token": identifier, "company": identifier}
        if "eu." in host:
            # `boards-api.eu.greenhouse.io` does not exist (NXDOMAIN): the EU
            # board API is served from the same host as the EU job board.
            config["api_host"] = "boards.eu.greenhouse.io"
        return AtsBoard("greenhouse", config)

    if host in {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"}:
        return AtsBoard("smartrecruiters", {"company": identifier})

    return None
