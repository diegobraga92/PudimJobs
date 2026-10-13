"""Integration test for the CV tailoring Celery task."""

from sqlalchemy import select
from workers.tasks.tailor import _run_tailor

from app.models import Application, GeneratedCV, Job, MasterCV
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


async def test_tailor_task_is_idempotent(test_engine, db_session):
    """Re-tailoring the same job + source CV version reuses the artifact."""
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
        description="Python and FastAPI on AWS with PostgreSQL. 5+ years required.",
    )
    db_session.add_all([cv, job])
    await db_session.commit()
    await db_session.refresh(cv)
    await db_session.refresh(job)

    first = await _run_tailor(str(job.id), str(cv.id))
    second = await _run_tailor(str(job.id), str(cv.id))

    assert second["already_exists"] is True
    assert second["generated_cv_id"] == first["generated_cv_id"]

    versions = (await db_session.execute(select(MasterCV))).scalars().all()
    assert len(versions) == 2  # original + one tailored version

    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(generated) == 1


async def _seed_cv_job(db_session, *, description: str = "Python and FastAPI on AWS."):
    user = await create_user(db_session)
    cv = MasterCV(
        user_id=user.id,
        label="CV v1",
        version=1,
        is_current=True,
        structured_json=CV_STRUCTURE,
    )
    job = Job(user_id=user.id, title="Backend Engineer", company="Acme", description=description)
    db_session.add_all([cv, job])
    await db_session.commit()
    await db_session.refresh(cv)
    await db_session.refresh(job)
    return user, cv, job


async def test_tailor_task_links_application_cv_version(test_engine, db_session):
    """Passing ``application_id`` records which CV version the app was sent with."""
    user, cv, job = await _seed_cv_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    result = await _run_tailor(str(job.id), str(cv.id), str(application.id))

    await db_session.refresh(application)
    assert str(application.cv_version) == result["master_cv_id"]


async def test_tailor_task_links_reused_artifact(test_engine, db_session):
    """Re-tailoring links the application to the pre-existing artifact."""
    user, cv, job = await _seed_cv_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    await _run_tailor(str(job.id), str(cv.id))
    result = await _run_tailor(str(job.id), str(cv.id), str(application.id))

    assert result["already_exists"] is True
    await db_session.refresh(application)
    assert str(application.cv_version) == result["master_cv_id"]


async def test_tailor_task_ignores_application_for_other_job(test_engine, db_session):
    """A mismatched application id is ignored rather than cross-linked."""
    user, cv, job = await _seed_cv_job(db_session)
    other_job = Job(user_id=user.id, title="Other", company="Globex", description="Ruby.")
    db_session.add(other_job)
    await db_session.commit()
    await db_session.refresh(other_job)

    application = Application(user_id=user.id, job_id=other_job.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    await _run_tailor(str(job.id), str(cv.id), str(application.id))

    await db_session.refresh(application)
    assert application.cv_version is None
