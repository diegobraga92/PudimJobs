"""Integration test for the data quality Celery task."""

from datetime import date

from sqlalchemy import select
from workers.tasks.quality import _assess_quality

from app.models import Job, ScrapeQuality
from tests.helpers import create_user


async def test_assess_quality_normalizes_and_scores(test_engine, db_session):
    user = await create_user(db_session)
    job = Job(
        user_id=user.id,
        title="Sr. Software Engineer",
        company="Google LLC",
        description="x" * 300,
        posted_date=date(2026, 8, 1),
        tags=["react.js", "docker"],
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    result = await _assess_quality(str(job.id))

    assert result["normalized_company"] == "Google"
    assert result["normalized_title"] == "Senior Software Engineer"
    assert result["completeness_score"] == 1.0
    assert result["is_duplicate"] is False

    quality = (await db_session.execute(select(ScrapeQuality))).scalars().all()
    assert len(quality) == 1
    assert quality[0].normalized_company == "Google"

    # Skill tags were normalized in place.
    await db_session.refresh(job)
    assert "react" in job.tags


async def test_assess_quality_flags_duplicate(test_engine, db_session):
    user = await create_user(db_session)
    first = Job(
        user_id=user.id,
        title="Backend Engineer",
        company="Acme",
        description="x" * 300,
        posted_date=date(2026, 8, 1),
        tags=["python"],
    )
    duplicate = Job(
        user_id=user.id,
        title="Backend Engineer ",
        company="Acme",
        description="y" * 300,
        posted_date=date(2026, 8, 1),
        tags=["python"],
    )
    db_session.add_all([first, duplicate])
    await db_session.commit()
    await db_session.refresh(duplicate)

    result = await _assess_quality(str(duplicate.id))
    assert result["is_duplicate"] is True
    assert result["issues"]  # duplicate flagged in issues


async def test_assess_quality_short_description_issues(test_engine, db_session):
    user = await create_user(db_session)
    job = Job(
        user_id=user.id,
        title="QA Engineer",
        company="Acme",
        description="short",
        posted_date=None,
        tags=[],
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    result = await _assess_quality(str(job.id))
    assert result["completeness_score"] < 0.6
    assert "short description" in result["issues"]
    assert "missing posted date" in result["issues"]
