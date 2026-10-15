"""Domain enums shared by the ORM models and the API schemas."""

import enum


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Return the list of member *values* (used as DB/API values)."""
    return [member.value for member in enum_cls]


class SourceType(enum.StrEnum):
    career_page = "career_page"
    aggregator = "aggregator"
    rss = "rss"
    discovery = "discovery"
    # A board the engine cannot scrape automatically (login-walled SPA, anti-bot
    # or a directory). It is never fetched by the sweeper; the user re-checks it
    # by hand and the app reminds them when it is due (ADR 018).
    manual = "manual"


class SourceAuthType(enum.StrEnum):
    none = "none"
    token = "token"
    api_key = "api_key"


class SourceHealth(enum.StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    failing = "failing"


class ApplicationStatus(enum.StrEnum):
    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"


class PrepCategory(enum.StrEnum):
    """Kind of interview-preparation task."""

    technical = "technical"
    behavioral = "behavioral"
    research = "research"
    logistics = "logistics"
    other = "other"


class PrepStatus(enum.StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"


class CVVariant(enum.StrEnum):
    """How a tailored CV was produced (ADR 016)."""

    rule = "rule"
    llm = "llm"
