"""Unit tests for the matching engine (job vs alert rule)."""

from app.models.alert_rule import AlertRule
from app.models.job import Job
from app.services.matcher import job_matches_rule

USER_ID = "11111111-1111-1111-1111-111111111111"


def _job(**overrides) -> Job:
    data = dict(
        user_id=USER_ID,
        title="Senior Python Engineer",
        company="Acme",
        description="Building FastAPI services with PostgreSQL.",
        tags=["python"],
        parsed_jd={"years_experience": 5},
    )
    data.update(overrides)
    return Job(**data)


def _rule(**overrides) -> AlertRule:
    data = dict(
        user_id=USER_ID,
        name="Python jobs",
        keywords=["python"],
        companies=[],
        tags=[],
        remote_only=False,
        min_years_experience=None,
        channels=["in_app"],
    )
    data.update(overrides)
    return AlertRule(**data)


def test_matches_by_keyword():
    assert job_matches_rule(_job(), _rule(keywords=["python"]))


def test_no_match_when_keyword_absent():
    assert not job_matches_rule(_job(), _rule(keywords=["rust"]))


def test_matches_by_company():
    assert job_matches_rule(_job(), _rule(keywords=[], companies=["acme"]))


def test_company_filter_is_substring():
    assert job_matches_rule(_job(company="Acme Inc."), _rule(keywords=[], companies=["acme"]))


def test_matches_by_tags():
    assert job_matches_rule(_job(), _rule(keywords=[], tags=["python"]))


def test_tag_mismatch_blocks_match():
    assert not job_matches_rule(_job(), _rule(keywords=[], tags=["java"]))


def test_remote_only_requires_remote():
    assert not job_matches_rule(_job(), _rule(keywords=[], remote_only=True))
    assert job_matches_rule(
        _job(description="Remote friendly FastAPI role"), _rule(keywords=[], remote_only=True)
    )


def test_min_years_experience_filter():
    assert job_matches_rule(_job(), _rule(keywords=[], min_years_experience=3))
    assert not job_matches_rule(_job(), _rule(keywords=[], min_years_experience=7))


def test_min_years_unknown_passes():
    """A JD that doesn't state experience passes the min-years gate (fail-open)."""
    assert job_matches_rule(
        _job(parsed_jd={"years_experience": None}),
        _rule(keywords=[], min_years_experience=7),
    )
    assert not job_matches_rule(
        _job(parsed_jd={"years_experience": 3}),
        _rule(keywords=[], min_years_experience=7),
    )


def test_empty_rule_matches_everything():
    rule = _rule(keywords=[], companies=[], tags=[], remote_only=False, min_years_experience=None)
    assert job_matches_rule(_job(), rule)
