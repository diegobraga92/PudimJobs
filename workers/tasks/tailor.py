"""CV tailoring Celery task (ADR 016).

Produces one or two *self-contained* tailored-CV artifacts for a job:

* ``rule`` — always, from the deterministic engine (strengthened: the summary
  leads with the JD-matched strengths and a no-match fallback is signalled); and
* ``llm`` — when enabled, a full LLM rewrite kept alongside the rule variant so
  the user can compare and choose.

Each artifact is a ``generated_cvs`` row owning its own ``structured_json`` and
rendered PDF, and is scored with the deterministic ATS scorer (comparable across
variants). The master CV is never modified, so tailored output no longer leaks
into the master version history.

Re-running is idempotent per ``(user, job, source CV version, variant)`` — with
one exception: a stored artifact that has no content (``structured_json`` NULL,
as left behind by pre-ADR-016 rows) does *not* count as produced, and the run
repairs that same row in place instead of reusing an empty card forever.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import select

from app.database import async_session_factory
from app.models import Application, CVVariant, GeneratedCV, Job, MasterCV, User
from app.services.ats_scorer import derive_keywords, score_ats
from app.services.cv_tailor import TailoredCV, generate_tailored_cv_with_llm, tailor_cv
from app.services.jd_parser import parse_jd, parsed_jd_to_dict
from app.services.llm_config import LlmRuntimeConfig, get_llm_config
from app.services.pdf_generator import generate_pdf
from workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _pdf_name(user: User | None) -> str:
    """Best-effort display name: title-cased email local part (no name field)."""
    if user is None:
        return ""
    local = user.email.split("@")[0]
    return " ".join(part.capitalize() for part in local.split(".") if part)


async def _find_generated(
    session, cv: MasterCV, job: Job, variant: CVVariant
) -> GeneratedCV | None:
    """Return an existing artifact for this job + source CV version + variant."""
    result = await session.execute(
        select(GeneratedCV).where(
            GeneratedCV.user_id == cv.user_id,
            GeneratedCV.job_id == job.id,
            GeneratedCV.source_master_cv_id == cv.id,
            GeneratedCV.variant == variant,
        )
    )
    return result.scalar_one_or_none()


def _has_content(row: GeneratedCV) -> bool:
    """True when an artifact actually carries its own CV content.

    Rows written before ADR 016 (or by a run that persisted a PDF without the
    structured payload) exist with ``structured_json`` NULL: there is nothing to
    preview and no ATS report to show. Counting such a row as "already produced"
    is what made a broken card impossible to regenerate.
    """
    return bool(row.structured_json)


async def _link_application(
    session, application_id: str | None, cv: MasterCV, job: Job, generated_cv_id: uuid.UUID
) -> None:
    """Point an application at the CV artifact it was sent with.

    Best-effort and guarded: a missing, foreign, or mismatched id is ignored, so
    a stale request can never cross-link another user's pipeline. Does not
    commit — the caller commits.
    """
    if not application_id:
        return
    application = await session.get(Application, uuid.UUID(application_id))
    if application is None or application.user_id != cv.user_id or application.job_id != job.id:
        logger.warning("cv_tailor_application_link_skipped", application_id=application_id)
        return
    application.generated_cv_id = generated_cv_id


async def _store_variant(
    session,
    *,
    cv: MasterCV,
    job: Job,
    user: User | None,
    variant: CVVariant,
    structure: dict,
    jd_skills: list[str],
    jd_keywords: list[str],
    jd_text: str,
    llm_self_score: int | None = None,
    existing: GeneratedCV | None = None,
) -> GeneratedCV:
    """Render, deterministically score and persist one tailored artifact.

    ``existing`` is a *content-less* row for the same key: it is repaired in
    place instead of being duplicated. Reusing its id keeps ``created_at``, the
    ``applications.generated_cv_id`` link and variant uniqueness intact, so a
    legacy empty artifact cannot linger in the panel forever (ADR 016).
    """
    tailored = TailoredCV.from_structure(structure)
    pdf_bytes = generate_pdf(tailored, name=_pdf_name(user), email=user.email if user else "")
    # Both variants use the *deterministic* scorer so their scores are comparable;
    # the LLM's own estimate is recorded separately when it provided one.
    report = await score_ats(
        structure,
        jd_skills=jd_skills,
        jd_keywords=jd_keywords,
        jd_text=jd_text,
        job_title=job.title,
    )
    if llm_self_score is not None:
        report["llm_self_score"] = llm_self_score
    generated = existing if existing is not None else GeneratedCV(
        user_id=cv.user_id,
        source_master_cv_id=cv.id,
        job_id=job.id,
        variant=variant,
    )
    generated.structured_json = structure
    generated.pdf = pdf_bytes
    generated.ats_score = report["score"]
    generated.ats_report = report
    if existing is None:
        session.add(generated)
    else:
        logger.info(
            "cv_tailored_empty_artifact_repaired",
            generated_cv_id=str(generated.id),
            variant=variant.value,
        )
    await session.commit()
    await session.refresh(generated)
    return generated


def _llm_variant_skip_reason(config: LlmRuntimeConfig) -> str:
    """Why the full-LLM variant will not be produced, or ``""`` when it will.

    Enabling the LLM in Admin -> LLM is what opts a deployment into the second
    variant (ADR 016); there is no separate flag. Naming the missing half is the
    point: a skipped variant used to leave no trace at all, so "I only got the
    deterministic CV" was indistinguishable from a bug.
    """
    if not config.enabled:
        return "the LLM is disabled in Admin -> LLM"
    if not config.api_key:
        return "no LLM API key is configured"
    return ""


def _llm_variant_wanted(config: LlmRuntimeConfig) -> bool:
    """The full-LLM variant needs an enabled LLM config with a usable API key."""
    return not _llm_variant_skip_reason(config)


async def _run_tailor(job_id: str, cv_id: str | None, application_id: str | None = None) -> dict:
    job_uuid = uuid.UUID(job_id)
    async with async_session_factory() as session:
        job = await session.get(Job, job_uuid)
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        if cv_id:
            cv = await session.get(MasterCV, uuid.UUID(cv_id))
        else:
            result = await session.execute(
                select(MasterCV).where(
                    MasterCV.user_id == job.user_id, MasterCV.is_current.is_(True)
                )
            )
            cv = result.scalar_one_or_none()
        if cv is None:
            raise ValueError(f"No master CV found for job {job_id}")

        user = await session.get(User, job.user_id)

        # Ensure the JD is parsed (parse on demand if the job has no result yet).
        if not job.parsed_jd:
            parsed = parse_jd(job.description)
            job.parsed_jd = parsed_jd_to_dict(parsed)
            await session.commit()
        jd_skills = job.parsed_jd.get("skills", []) or []
        jd_text = job.description or ""
        jd_keywords = derive_keywords(jd_text) if jd_text else []

        llm_config = await get_llm_config(session)

        # Which variants should exist after this run.
        wanted: list[CVVariant] = [CVVariant.rule]
        if _llm_variant_wanted(llm_config):
            wanted.append(CVVariant.llm)
        else:
            # Never skip silently: the user sees a single CV and needs to know
            # which of the two conditions is missing (ADR 016).
            logger.info(
                "cv_tailored_llm_variant_skipped",
                job_id=job_id,
                reason=_llm_variant_skip_reason(llm_config),
            )

        existing: dict[CVVariant, GeneratedCV] = {}
        # Content-less rows are kept aside: they must not satisfy the
        # idempotency shortcut, and the run repairs them in place instead.
        empty: dict[CVVariant, GeneratedCV] = {}
        for variant in wanted:
            found = await _find_generated(session, cv, job, variant)
            if found is None:
                continue
            if _has_content(found):
                existing[variant] = found
            else:
                empty[variant] = found
        if empty:
            logger.info(
                "cv_tailored_empty_artifact_found",
                job_id=job_id,
                variants=sorted(variant.value for variant in empty),
                generated_cv_ids=[str(row.id) for row in empty.values()],
            )

        # Idempotency: re-tailoring the same job against the same source CV
        # version reuses the artifacts instead of minting new ones.
        if len(existing) == len(wanted):
            rule = existing[CVVariant.rule]
            await _link_application(session, application_id, cv, job, rule.id)
            await session.commit()
            logger.info("cv_tailored_reused", job_id=job_id, generated_cv_id=str(rule.id))
            return {
                "generated_cv_id": str(rule.id),
                "variant": rule.variant.value,
                "generated_cv_ids": {
                    variant.value: str(row.id) for variant, row in existing.items()
                },
                "llm_generated_cv_id": (
                    str(existing[CVVariant.llm].id) if CVVariant.llm in existing else None
                ),
                "relevance": None,
                "matched_skills": [],
                "missing_skills": [],
                "used_fallback": False,
                "already_exists": True,
            }

        # Deterministic variant (always produced).
        tailored = tailor_cv(cv.structured_json, jd_skills, annotations=cv.annotations)
        products: dict[CVVariant, GeneratedCV] = dict(existing)
        if CVVariant.rule not in products:
            products[CVVariant.rule] = await _store_variant(
                session,
                cv=cv,
                job=job,
                user=user,
                variant=CVVariant.rule,
                structure=tailored.as_structure(),
                jd_skills=jd_skills,
                jd_keywords=jd_keywords,
                jd_text=jd_text,
                existing=empty.get(CVVariant.rule),
            )

        # Optional full-LLM variant, kept alongside the deterministic one. A
        # failure here degrades gracefully — the rule artifact still ships.
        if CVVariant.llm in wanted and CVVariant.llm not in products:
            rewritten = await generate_tailored_cv_with_llm(
                cv.structured_json,
                jd_text=jd_text,
                jd_title=job.title,
                jd_skills=jd_skills,
                config=llm_config,
            )
            if rewritten is not None:
                structure, self_score = rewritten
                products[CVVariant.llm] = await _store_variant(
                    session,
                    cv=cv,
                    job=job,
                    user=user,
                    variant=CVVariant.llm,
                    structure=structure,
                    jd_skills=jd_skills,
                    jd_keywords=jd_keywords,
                    jd_text=jd_text,
                    llm_self_score=self_score,
                    existing=empty.get(CVVariant.llm),
                )

        # Auto-link the deterministic variant only; the LLM variant is linked when
        # the user explicitly picks it (ADR 016).
        rule = products[CVVariant.rule]
        await _link_application(session, application_id, cv, job, rule.id)
        await session.commit()

        logger.info(
            "cv_tailored",
            job_id=job_id,
            generated_cv_id=str(rule.id),
            variants=sorted(variant.value for variant in products),
            matched=len(tailored.matched_skills),
            relevance=tailored.relevance,
        )
        return {
            "generated_cv_id": str(rule.id),
            "variant": CVVariant.rule.value,
            "generated_cv_ids": {
                variant.value: str(row.id) for variant, row in products.items()
            },
            "llm_generated_cv_id": (
                str(products[CVVariant.llm].id) if CVVariant.llm in products else None
            ),
            "relevance": round(tailored.relevance, 3),
            "matched_skills": tailored.matched_skills,
            "missing_skills": tailored.missing_skills,
            "used_fallback": tailored.used_fallback,
            "already_exists": False,
        }


@celery_app.task(
    name="workers.tasks.tailor.tailor_cv_task",
    autoretry_for=(Exception,),
    max_retries=2,
    default_retry_delay=30,
)
def tailor_cv_task(job_id: str, cv_id: str | None = None, application_id: str | None = None) -> dict:
    return asyncio.run(_run_tailor(job_id, cv_id, application_id))
