"""Single-URL job import: fetch one posting and build a reviewable draft (ADR 025).

Nothing is persisted here. The endpoint returns the draft, the user reviews and
edits it in the Add-job dialog, and the normal ``POST /api/jobs`` saves it — the
same "preview, then confirm" rule the CV import (ADR 011), the source preview and
the bulk cleanup (ADR 023) already follow.

Extraction order is the project's standard one (ADR 006): deterministic first
(schema.org JSON-LD, then the CSS heuristics the engine uses), and the optional
LLM only to fill the gaps that are still empty. A failed or absent LLM never
fails the import; it just leaves the field blank for the user to type.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace

import structlog
from bs4 import BeautifulSoup
from scrapers.utils import (
    RobotsDecision,
    as_optional_str,
    coerce_date,
    domain_of,
    redact_sensitive,
    robots_decision,
)

from app.config import settings
from app.models.enums import SourceType
from app.services.llm_client import chat_json
from app.services.llm_config import LlmRuntimeConfig, llm_variant_wanted
from app.services.skill_matcher import extract_skills

logger = structlog.get_logger(__name__)

# One cheap call, not a full read of the page: same ceiling the CV structuring
# call uses. Kept under the proxy idle timeout together with the fetch.
_LLM_TIMEOUT_SECONDS = 20.0
_LLM_MAX_TOKENS = 1_200
# Tags are a filter aid, not a taxonomy dump.
_MAX_TAGS = 10
# A posting body is long, but not unbounded; protects the JSON response.
_MAX_DESCRIPTION_CHARS = 20_000
# `CareerPageScraper.normalize` substitutes this for a missing company; the form
# needs an empty field instead, so the user is asked to fill it.
_PLACEHOLDER_COMPANY = "Unknown"

_LLM_SYSTEM = (
    "You extract job-posting fields from the visible text of a web page. "
    'Return ONLY a JSON object with the keys "title", "company", "location", '
    '"posted_date" (ISO date, YYYY-MM-DD) and "description". '
    'Copy the posting body verbatim into "description" — do not paraphrase, '
    "summarize or add sections. Use null for anything the page does not state, and "
    "never invent an employer, a date, a location or a requirement."
)


@dataclass
class ImportedJob:
    """Draft extracted from one posting URL (mirrors ``JobImportPreview``)."""

    fetched_url: str
    status_code: int | None = None
    url: str | None = None
    title: str = ""
    company: str = ""
    location: str | None = None
    description: str | None = None
    posted_date: date | None = None
    tags: list[str] = field(default_factory=list)
    extraction: str = "none"
    llm_used: bool = False
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def html_to_text(html: str | None) -> str | None:
    """Visible text of an HTML fragment, keeping the block structure.

    Postings arrive as HTML (JSON-LD ``description``) or as already-extracted
    text (CSS selectors). Both end up in a plain ``<textarea>``, so markup has to
    go; ``"\\n"`` as the separator keeps paragraphs and list items apart instead
    of gluing the whole posting into one line.
    """
    if not html or not html.strip():
        return None
    text = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
    return text.strip() or None


def _timeout_message(timeout: float) -> str:
    return f"timed out after {timeout:g}s — the site may be slow or JS-rendered"


def _robots_error(decision: RobotsDecision) -> str:
    """Explain a robots.txt refusal, keeping "says no" apart from "unreachable"."""
    if decision.reason == "disallowed":
        return "robots.txt disallows this page"
    detail = decision.error or (
        f"HTTP {decision.status_code}" if decision.status_code else "fetch failed"
    )
    return f"robots.txt unreachable ({detail}) — try again"


def _status_of(exc: Exception) -> int | None:
    return getattr(getattr(exc, "response", None), "status_code", None)


def _parse(scraper, page) -> tuple[list, str]:
    """Parse with provenance, tolerating scrapers without the hook."""
    hook = getattr(scraper, "parse_with_extraction", None)
    if callable(hook):
        return hook(page)
    return scraper.parse(page), "css"


def _is_incomplete(draft: ImportedJob) -> bool:
    return not (draft.title and draft.company and draft.description)


async def import_job_from_url(
    url: str, *, llm_config: LlmRuntimeConfig | None = None
) -> ImportedJob:
    """Fetch ``url`` and return the extracted draft; ``error`` explains a failure.

    Every failure mode (blocked URL, unreachable host, timeout, unreadable page)
    is reported in the result instead of raised: the caller answers HTTP 200 so
    the dialog can show the reason next to the fields the user was editing.
    """
    target = url.strip()
    if settings.job_import_respect_robots:
        # `robots_decision` performs a blocking HTTP fetch; keep it off the loop.
        decision = await asyncio.to_thread(robots_decision, target)
        if not decision.allowed:
            return ImportedJob(fetched_url=target, error=_robots_error(decision))

    # Local import: only this endpoint needs the scraper package, and the API
    # process should not pay for it at startup (same pattern as the source
    # preview in `app/routers/sources.py`).
    from scrapers.registry import get_scraper

    try:
        scraper = get_scraper(SimpleNamespace(type=SourceType.career_page, config={}))
    except ValueError as exc:  # pragma: no cover - the registry always has the type
        return ImportedJob(fetched_url=target, error=str(exc))

    timeout = settings.job_import_timeout_seconds
    try:
        page = await asyncio.wait_for(scraper.fetch(target), timeout=timeout)
    except TimeoutError:
        return ImportedJob(fetched_url=target, error=_timeout_message(timeout))
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return ImportedJob(
            fetched_url=target,
            status_code=_status_of(exc),
            error=redact_sensitive(str(exc))[:300],
        )

    raw_jobs, extraction = _parse(scraper, page)
    draft = ImportedJob(
        fetched_url=page.final_url or target,
        status_code=page.status_code,
        url=page.final_url or target,
        extraction=extraction,
    )
    normalized = scraper.normalize(raw_jobs)
    if normalized:
        _apply(normalized[0], draft)

    if llm_config is not None and llm_variant_wanted(llm_config) and _is_incomplete(draft):
        await _fill_gaps_with_llm(page, draft, llm_config)
    # Warned after the LLM pass, so a description it wrote is not reported as
    # missing and one it could not write is explained exactly once.
    if draft.description is None:
        draft.warnings.append("the page has no readable job description")
    if not draft.tags and draft.description:
        # Taxonomy instead of an LLM call: cheap, deterministic, and the field is
        # editable anyway. `extract_skills` is spaCy-free (unlike `parse_jd`), so
        # the API process does not load the model for a few tags.
        draft.tags = extract_skills(draft.description[:5_000])[:_MAX_TAGS]
    if not draft.title:
        draft.warnings.append("title missing — type it in")
    if not draft.company:
        draft.warnings.append("company missing — type it in")

    logger.info(
        "job_import_fetched",
        host=domain_of(target),
        status_code=draft.status_code,
        extraction=draft.extraction,
        llm_used=draft.llm_used,
        tags=len(draft.tags),
        warnings=len(draft.warnings),
    )
    return draft


def _apply(item: dict, draft: ImportedJob) -> None:
    """Copy a normalized scraper row into the draft, normalizing the edges."""
    draft.title = (item.get("title") or "").strip()
    company = (item.get("company") or "").strip()
    draft.company = "" if company == _PLACEHOLDER_COMPANY else company
    draft.location = as_optional_str(item.get("location"))
    description = html_to_text(item.get("description"))
    draft.description = description[:_MAX_DESCRIPTION_CHARS] if description else None
    draft.posted_date = coerce_date(item.get("posted_date"))
    draft.tags = [str(tag) for tag in item.get("tags") or []][:_MAX_TAGS]
    if item.get("url"):
        draft.url = str(item["url"])


async def _fill_gaps_with_llm(page, draft: ImportedJob, config: LlmRuntimeConfig) -> None:
    """Ask the LLM for the fields the deterministic passes left empty.

    Never overwrites a value the page itself provided, so a wrong guess can only
    fill a blank the user would have had to type anyway.
    """
    text = html_to_text(page.html_content)
    if not text:
        # A JS-rendered board returns a shell: there is nothing to read.
        draft.warnings.append("the page text is empty (JS-rendered board?)")
        return
    payload = await chat_json(
        config,
        system=_LLM_SYSTEM,
        user=(
            f"Page URL: {page.final_url}\n\n"
            f"Visible page text:\n\n{text[: settings.job_import_llm_max_chars]}"
        ),
        max_tokens=_LLM_MAX_TOKENS,
        temperature=0,
        timeout=_LLM_TIMEOUT_SECONDS,
        label="JD import",
    )
    if payload is None:
        # `chat_json` already logged why; the user only needs the consequence.
        draft.warnings.append("the AI reader was unavailable — check the fields")
        return

    filled = False
    if not draft.title:
        draft.title = as_optional_str(payload.get("title")) or ""
        filled = filled or bool(draft.title)
    if not draft.company:
        draft.company = as_optional_str(payload.get("company")) or ""
        filled = filled or bool(draft.company)
    if not draft.location:
        draft.location = as_optional_str(payload.get("location"))
        filled = filled or bool(draft.location)
    if draft.posted_date is None:
        draft.posted_date = coerce_date(payload.get("posted_date"))
        filled = filled or draft.posted_date is not None
    if draft.description is None:
        # Models sometimes hand back HTML even when asked for plain text.
        description = html_to_text(as_optional_str(payload.get("description")))
        if description:
            draft.description = description[:_MAX_DESCRIPTION_CHARS]
            draft.warnings.append("description written by the AI — check it")
            filled = True

    draft.llm_used = filled
    if filled and draft.extraction == "none":
        draft.extraction = "llm"
