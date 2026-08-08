"""Data quality scoring and duplicate detection for jobs."""

from collections.abc import Iterable
from difflib import SequenceMatcher

from app.models.job import Job

DESCRIPTION_LENGTH_TARGET = 200


def completeness_score(job: Job) -> float:
    """Weighted completeness score in [0, 1] based on present fields."""
    score = 0.0
    if job.title:
        score += 0.3
    if job.company:
        score += 0.2
    if job.description and len(job.description) >= DESCRIPTION_LENGTH_TARGET:
        score += 0.2
    if job.posted_date:
        score += 0.15
    if job.tags:
        score += 0.15
    return round(score, 3)


def collect_issues(job: Job, *, is_duplicate: bool, canonical_id) -> list[str]:
    issues: list[str] = []
    if not job.description or len(job.description) < DESCRIPTION_LENGTH_TARGET:
        issues.append("short description")
    if not job.posted_date:
        issues.append("missing posted date")
    if not job.tags:
        issues.append("no tags")
    if is_duplicate and canonical_id:
        issues.append(f"possible duplicate of {canonical_id}")
    return issues


def is_duplicate_of(candidate: Job, others: Iterable[Job], threshold: float = 0.9) -> Job | None:
    """Fuzzy-match title + company with close posted dates; return the duplicate."""
    if not candidate.title or not candidate.company:
        return None
    for other in others:
        if other.id == candidate.id:
            continue
        title_ratio = SequenceMatcher(
            None, candidate.title.lower(), other.title.lower()
        ).ratio()
        company_ratio = SequenceMatcher(
            None, candidate.company.lower(), other.company.lower()
        ).ratio()
        if title_ratio >= threshold and company_ratio >= threshold:
            if candidate.posted_date and other.posted_date:
                if abs((candidate.posted_date - other.posted_date).days) <= 1:
                    return other
            else:
                return other
    return None
