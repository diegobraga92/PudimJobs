"""Integration tests for the CV tailoring Celery task (ADR 016)."""

import pytest
from sqlalchemy import select
from workers.tasks import tailor as tailor_module
from workers.tasks.tailor import _run_tailor

from app.models import Application, CVVariant, GeneratedCV, Job, MasterCV
from app.services.llm_config import LlmRuntimeConfig
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


@pytest.fixture(autouse=True)
def _no_llm_configured_by_default(monkeypatch):
    """Keep the ambient environment out of this module's LLM decisions.

    The `llm` variant is gated by the LLM config alone (ADR 016, amended), so a
    developer running the suite with `OPENAI_API_KEY`/`TAILORING_LLM_ENABLED`
    exported would silently get a second artifact in every test here. Tests that
    want the variant override this with their own `get_llm_config` stub.
    """

    async def _disabled_config(_session):
        return LlmRuntimeConfig(enabled=False, api_key="", base_url="", model="")

    monkeypatch.setattr(tailor_module, "get_llm_config", _disabled_config)


async def test_tailor_task_stores_a_self_contained_artifact(test_engine, db_session):
    """The artifact owns its content; no new master-CV version is minted."""
    _, cv, job = await _seed_cv_job(
        db_session,
        description="We need Python and FastAPI on AWS with PostgreSQL. 5+ years required.",
    )

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["generated_cv_id"]
    assert result["variant"] == "rule"
    assert result["matched_skills"] == ["python", "fastapi", "postgresql"]
    assert result["already_exists"] is False

    # The master CV history stays clean: only the original version remains.
    versions = (await db_session.execute(select(MasterCV))).scalars().all()
    assert len(versions) == 1
    assert versions[0].id == cv.id

    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(generated) == 1
    artifact = generated[0]
    assert artifact.variant == CVVariant.rule
    assert artifact.job_id == job.id
    assert artifact.source_master_cv_id == cv.id
    assert artifact.pdf[:4] == b"%PDF"
    assert artifact.structured_json is not None
    assert artifact.structured_json["experience"][0]["title"] == "Python Developer"
    # The deterministic variant is auto-scored on creation.
    assert artifact.ats_score is not None
    assert artifact.ats_report["score"] == artifact.ats_score


async def test_tailor_task_strengthens_the_summary(test_engine, db_session):
    """The deterministic variant is not a verbatim copy of the master CV."""
    _, cv, job = await _seed_cv_job(db_session)

    result = await _run_tailor(str(job.id), str(cv.id))

    generated = (await db_session.execute(select(GeneratedCV))).scalars().one()
    summary = generated.structured_json["summary"]
    assert summary.startswith("Backend engineer.")
    assert "Core strengths" in summary
    assert result["used_fallback"] is False


async def test_tailor_task_signals_a_no_match_fallback(test_engine, db_session):
    """Nothing matching the JD must be reported, not silently presented."""
    _, cv, job = await _seed_cv_job(db_session, description="Rust and Go systems programming.")

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["used_fallback"] is True
    assert result["relevance"] == 0.0


async def test_tailor_task_parses_jd_on_demand(test_engine, db_session):
    _, cv, job = await _seed_cv_job(db_session, description="Python developer. FastAPI and Docker.")

    result = await _run_tailor(str(job.id), str(cv.id))
    assert result["generated_cv_id"]

    await db_session.refresh(job)
    assert job.parsed_jd is not None
    assert "python" in job.parsed_jd["skills"]


async def test_tailor_task_is_idempotent(test_engine, db_session):
    """Re-tailoring the same job + source CV version reuses the artifact."""
    _, cv, job = await _seed_cv_job(db_session)

    first = await _run_tailor(str(job.id), str(cv.id))
    second = await _run_tailor(str(job.id), str(cv.id))

    assert second["already_exists"] is True
    assert second["generated_cv_id"] == first["generated_cv_id"]

    versions = (await db_session.execute(select(MasterCV))).scalars().all()
    assert len(versions) == 1  # the master CV was never versioned

    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(generated) == 1


async def test_tailor_task_links_application_to_the_rule_artifact(test_engine, db_session):
    """Passing ``application_id`` records which artifact the app was sent with."""
    user, cv, job = await _seed_cv_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    result = await _run_tailor(str(job.id), str(cv.id), str(application.id))

    await db_session.refresh(application)
    assert str(application.generated_cv_id) == result["generated_cv_id"]


async def test_tailor_task_links_reused_artifact(test_engine, db_session):
    """Re-tailoring links the application to the pre-existing artifact."""
    user, cv, job = await _seed_cv_job(db_session)
    application = Application(user_id=user.id, job_id=job.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    first = await _run_tailor(str(job.id), str(cv.id))
    result = await _run_tailor(str(job.id), str(cv.id), str(application.id))

    assert result["already_exists"] is True
    await db_session.refresh(application)
    assert str(application.generated_cv_id) == first["generated_cv_id"]


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
    assert application.generated_cv_id is None


async def test_tailor_task_produces_only_the_rule_variant_when_no_llm_is_configured(
    test_engine, db_session
):
    """With no usable LLM config the run degrades to the deterministic variant."""
    _, cv, job = await _seed_cv_job(db_session)

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["llm_generated_cv_id"] is None
    assert result["generated_cv_ids"] == {"rule": result["generated_cv_id"]}


async def test_tailor_task_adds_the_llm_variant_when_enabled(test_engine, db_session, monkeypatch):
    """An enabled LLM config + API key alone opts the run into the second variant."""
    _, cv, job = await _seed_cv_job(db_session)

    async def _enabled_config(_session):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    async def _fake_rewrite(structure, **_kwargs):
        return ({**structure, "summary": "Rewritten for the job"}, 88)

    monkeypatch.setattr(tailor_module, "get_llm_config", _enabled_config)
    monkeypatch.setattr(tailor_module, "generate_tailored_cv_with_llm", _fake_rewrite)

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["llm_generated_cv_id"] is not None
    assert set(result["generated_cv_ids"]) == {"rule", "llm"}

    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    by_variant = {item.variant: item for item in generated}
    assert set(by_variant) == {CVVariant.rule, CVVariant.llm}
    assert by_variant[CVVariant.rule].structured_json["summary"] != "Rewritten for the job"
    assert by_variant[CVVariant.llm].structured_json["summary"] == "Rewritten for the job"
    # The LLM's own estimate is stored separately from the comparable score.
    assert by_variant[CVVariant.llm].ats_report["llm_self_score"] == 88
    assert "llm_self_score" not in (by_variant[CVVariant.rule].ats_report or {})


async def test_tailor_task_llm_variant_can_be_skipped_after_a_failure(
    test_engine, db_session, monkeypatch
):
    """A failing rewrite degrades gracefully — the rule artifact still ships."""
    _, cv, job = await _seed_cv_job(db_session)

    async def _enabled_config(_session):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    async def _failing_rewrite(_structure, **_kwargs):
        return None

    monkeypatch.setattr(tailor_module, "get_llm_config", _enabled_config)
    monkeypatch.setattr(tailor_module, "generate_tailored_cv_with_llm", _failing_rewrite)

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["llm_generated_cv_id"] is None
    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert [item.variant for item in generated] == [CVVariant.rule]


def test_llm_variant_skip_reason_names_the_missing_condition():
    """A skipped variant has to be explainable — nothing else fails silently.

    Skipping the AI rewrite is a graceful no-op, so this reason string is the
    only feedback an operator gets for "I only see the deterministic CV". Only
    the LLM config is consulted — there is no worker flag to check (ADR 016).
    """
    disabled = LlmRuntimeConfig(enabled=False, api_key="sk-x", base_url="http://llm", model="m")
    assert "disabled" in tailor_module._llm_variant_skip_reason(disabled)
    assert tailor_module._llm_variant_wanted(disabled) is False

    no_key = LlmRuntimeConfig(enabled=True, api_key="", base_url="http://llm", model="m")
    assert "API key" in tailor_module._llm_variant_skip_reason(no_key)
    assert tailor_module._llm_variant_wanted(no_key) is False

    usable = LlmRuntimeConfig(enabled=True, api_key="sk-x", base_url="http://llm", model="m")
    assert tailor_module._llm_variant_skip_reason(usable) == ""
    assert tailor_module._llm_variant_wanted(usable) is True
