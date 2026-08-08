"""Matching engine Celery task.

Evaluates a freshly-stored job against every active alert rule owned by the
job's user. Matches create notifications (in-app and/or email) and record
delivery status for observability.
"""

import asyncio
import uuid

import structlog
from app.database import async_session_factory
from app.models import AlertRule, Job, Notification, User
from app.services.email import render_notification_email, send_email
from app.services.matcher import job_matches_rule
from sqlalchemy import select

from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _match_job(job_id: str) -> dict:
    async with async_session_factory() as session:
        job = await session.get(Job, uuid.UUID(job_id))
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        result = await session.execute(
            select(AlertRule).where(
                AlertRule.user_id == job.user_id, AlertRule.active.is_(True)
            )
        )
        rules = result.scalars().all()

        matches = []
        for rule in rules:
            if not job_matches_rule(job, rule):
                continue
            channels = rule.channels or ["in_app"]
            created = []
            for channel in channels:
                notification = Notification(
                    user_id=job.user_id,
                    job_id=job.id,
                    alert_rule_id=rule.id,
                    channel=channel,
                    title=f"New match: {job.title}",
                    message=f"{job.company} matches your alert \"{rule.name}\".",
                    status="created",
                )
                session.add(notification)
                await session.flush()

                if channel == "email":
                    try:
                        user = await session.get(User, job.user_id)
                        send_email(
                            to=user.email,
                            subject=f"New job match: {job.title}",
                            html=render_notification_email(
                                job_title=job.title,
                                job_company=job.company,
                                job_url=job.url,
                                rule_name=rule.name,
                            ),
                        )
                        notification.status = "sent"
                    except Exception as exc:  # noqa: BLE001 - email is best-effort
                        notification.status = "failed"
                        notification.error = str(exc)[:1024]
                else:
                    notification.status = "sent"

                created.append({"id": str(notification.id), "channel": channel, "status": notification.status})

            await session.commit()
            matches.append({"rule_id": str(rule.id), "rule": rule.name, "notifications": created})

        logger.info("match_evaluated", job_id=job_id, rules=len(rules), matches=len(matches))
        return {"job_id": job_id, "rules_evaluated": len(rules), "matches": matches}


@celery_app.task(
    name="workers.tasks.match.match_job",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def match_job(job_id: str) -> dict:
    return asyncio.run(_match_job(job_id))
