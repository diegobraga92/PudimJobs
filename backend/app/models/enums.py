"""Domain enums shared by the ORM models and the API schemas."""

import enum


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Return the list of member *values* (used as DB/API values)."""
    return [member.value for member in enum_cls]


class SourceType(enum.StrEnum):
    career_page = "career_page"
    aggregator = "aggregator"
    rss = "rss"


class SourceAuthType(enum.StrEnum):
    none = "none"
    cookies = "cookies"
    token = "token"


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
