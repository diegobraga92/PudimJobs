"""Unit tests for data quality scoring and duplicate detection."""

import uuid
from datetime import date

from app.models.job import Job
from app.services.quality import collect_issues, completeness_score, is_duplicate_of

USER_ID = "11111111-1111-1111-1111-111111111111"


def _job(**overrides) -> Job:
    data = dict(
        id=uuid.uuid4(),
        user_id=USER_ID,
        title="Senior Python Engineer",
        company="Acme",
        description="x" * 300,
        posted_date=date(2026, 8, 1),
        tags=["python"],
    )
    data.update(overrides)
    return Job(**data)


def test_completeness_score_full():
    assert completeness_score(_job()) == 1.0


def test_completeness_score_missing_fields():
    job = _job(description=None, posted_date=None, tags=[])
    assert completeness_score(job) == 0.5


def test_issues_collected():
    job = _job(description="short", posted_date=None, tags=[])
    issues = collect_issues(job, is_duplicate=True, canonical_id="abc")
    assert "short description" in issues
    assert "missing posted date" in issues
    assert "no tags" in issues
    assert "possible duplicate of abc" in issues


def test_duplicate_detection_similar_title_and_company():
    first = _job()
    candidate = _job(
        title="Senior Python Engineer ",
        company="Acme",
        posted_date=date(2026, 8, 2),
    )
    assert is_duplicate_of(candidate, [first]) is first


def test_duplicate_detection_different_company():
    first = _job()
    candidate = _job(title="Senior Python Engineer", company="Different")
    assert is_duplicate_of(candidate, [first]) is None


def test_duplicate_detection_different_dates():
    first = _job(posted_date=date(2026, 1, 1))
    candidate = _job(posted_date=date(2026, 6, 1))
    assert is_duplicate_of(candidate, [first]) is None


def test_duplicate_detection_ignores_self():
    first = _job()
    assert is_duplicate_of(first, [first]) is None
