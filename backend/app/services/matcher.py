"""Matching engine: decide whether a job satisfies an alert rule."""

import re

from app.models.alert_rule import AlertRule
from app.models.job import Job


def _term_in_text(text: str, term: str) -> bool:
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])")
    return bool(pattern.search((text or "").lower()))


def job_matches_rule(job: Job, rule: AlertRule) -> bool:
    """Return True when a job satisfies every criterion of an alert rule."""
    haystack = " ".join(
        filter(None, [job.title, job.description, job.company, " ".join(job.tags)])
    )

    if rule.keywords and not any(_term_in_text(haystack, kw) for kw in rule.keywords):
        return False

    if rule.companies and not any(
        job.company and company.lower() in job.company.lower() for company in rule.companies
    ):
        return False

    if rule.tags and not (set(rule.tags) & set(job.tags)):
        return False

    if rule.remote_only and not re.search(
        r"\bremote\b", (f"{job.title} {job.description or ''}").lower()
    ):
        return False

    if rule.min_years_experience is not None:
        years = (job.parsed_jd or {}).get("years_experience")
        if years is None or years < rule.min_years_experience:
            return False

    return True
