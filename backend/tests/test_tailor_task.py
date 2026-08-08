"""Integration test for the CV tailoring Celery task."""

from sqlalchemy import select
from workers.tasks.tailor import _run_tailor

from app.models import GeneratedCV, Job, MasterCV
from tests.helpers import create_user

CV_STRUCTURE = {
    "summary": "Backend engineer",
    "experience": [
        {
            "title": "Python Developer",
            "company": "Acme",
            "bullets": ["Built FastAPI services on AWS", "Managed PostgreSQL"],
        }
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "fastapi", "postgresql"],
    "projects": [{"name": "Job Tracker", "description": "FastAPI + PostgreSQL"}],
}


async def test_tailor_task_creates_cv_version_and_pdf(test_engine, db_session):
    user = await create_user(db_session)
    cv = MasterCV(
        user_id=user.id,
        label="CV v1",
        version=1,
        is_current=True,
        structured_json=CV_STRUCTURE,
    )
    job = Job(
        user_id=user.id,
        title="Senior Backend Engineer",
        company="Acme",
        description=(
            "We need a Senior Backend Engineer with Python and FastAPI experience, "
            "building services on AWS with PostgreSQL. 5+ years required."
        ),
    )
    db_session.add_all([cv, job])
    await db_session.commit()
    await db_session.refresh(cv)
    await db_session.refresh(job)

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["generated_cv_id"]
    assert result["matched_skills"] == ["python", "fastapi", "postgresql"]

    # New CV version was created (not current) with a tailored label.
    versions = (await db_session.execute(select(MasterCV))).scalars().all()
    assert len(versions) == 2
    tailored_version = next(v for v in versions if v.label.startswith("Tailored for"))
    assert tailored_version.is_current is False
    assert tailored_version.structured_json["experience"][0]["title"] == "Python Developer"

    # The generated PDF artifact is persisted and valid.
    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(generated) == 1
    assert generated[0].pdf[:4] == b"%PDF"
    assert generated[0].job_id == job.id


async def test_tailor_task_parses_jd_on_demand(test_engine, db_session):
    user = await create_user(db_session)
    cv = MasterCV(
        user_id=user.id,
        label="CV v1",
        version=1,
        is_current=True,
        structured_json=CV_STRUCTURE,
    )
    job = Job(
        user_id=user.id,
        title="Backend Engineer",
        company="Acme",
        description="Python developer. FastAPI and Docker.",
    )
    db_session.add_all([cv, job])
    await db_session.commit()
    await db_session.refresh(cv)
    await db_session.refresh(job)

    result = await _run_tailor(str(job.id), str(cv.id))
    assert result["generated_cv_id"]

    await db_session.refresh(job)
    assert job.parsed_jd is not None
    assert "python" in job.parsed_jd["skills"]
