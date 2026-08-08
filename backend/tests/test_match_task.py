"""Integration tests for the matching engine Celery task."""

from sqlalchemy import select
from workers.tasks.match import _match_job

from app.models import AlertRule, Job, Notification
from tests.helpers import create_user


async def test_match_job_creates_in_app_notification(test_engine, db_session):
    user = await create_user(db_session)
    rule = AlertRule(
        user_id=user.id,
        name="Python jobs",
        keywords=["python"],
        channels=["in_app"],
    )
    job = Job(
        user_id=user.id,
        title="Python Engineer",
        company="Acme",
        description="We build with Python and FastAPI.",
    )
    db_session.add_all([rule, job])
    await db_session.commit()
    await db_session.refresh(job)

    result = await _match_job(str(job.id))

    assert len(result["matches"]) == 1
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].channel == "in_app"
    assert notifications[0].status == "sent"
    assert notifications[0].read is False


async def test_match_job_skips_when_no_rule_matches(test_engine, db_session):
    user = await create_user(db_session)
    rule = AlertRule(user_id=user.id, name="Rust jobs", keywords=["rust"])
    job = Job(
        user_id=user.id,
        title="Python Engineer",
        company="Acme",
        description="We build with Python.",
    )
    db_session.add_all([rule, job])
    await db_session.commit()
    await db_session.refresh(job)

    result = await _match_job(str(job.id))

    assert result["matches"] == []
    assert (await db_session.execute(select(Notification))).scalars().all() == []


async def test_match_job_inactive_rule_is_ignored(test_engine, db_session):
    user = await create_user(db_session)
    rule = AlertRule(
        user_id=user.id, name="Off", keywords=["python"], active=False
    )
    job = Job(
        user_id=user.id, title="Python Engineer", company="Acme", description="Python role"
    )
    db_session.add_all([rule, job])
    await db_session.commit()
    await db_session.refresh(job)

    result = await _match_job(str(job.id))
    assert result["matches"] == []


async def test_match_job_email_channel(test_engine, db_session, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(
        "workers.tasks.match.send_email", lambda to, subject, html: sent.append(to)
    )

    user = await create_user(db_session)
    rule = AlertRule(
        user_id=user.id, name="Email me", keywords=["python"], channels=["email"]
    )
    job = Job(
        user_id=user.id, title="Python Engineer", company="Acme", description="Python role"
    )
    db_session.add_all([rule, job])
    await db_session.commit()
    await db_session.refresh(job)

    result = await _match_job(str(job.id))

    assert len(result["matches"]) == 1
    assert sent == [user.email]
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert notifications[0].channel == "email"
    assert notifications[0].status == "sent"
