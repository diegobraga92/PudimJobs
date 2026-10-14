"""Integration tests for the CV tailoring Celery task (ADR 016)."""

from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from structlog.testing import capture_logs
from workers.tasks import tailor as tailor_module
from workers.tasks.tailor import _run_tailor

from app.models import Application, CVVariant, GeneratedCV, Job, MasterCV
from app.services import llm_client
from app.services.cv_tailor import LLM_TARGET_PAGES
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
    # No score is computed at generation time: ATS scoring is on demand (ADR 013).
    assert artifact.ats_score is None
    assert artifact.ats_report is None


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
    # The LLM's own estimate is the only score kept at generation time; the
    # comparable deterministic score is produced on demand (ADR 013).
    assert by_variant[CVVariant.llm].ats_report == {"llm_self_score": 88}
    assert by_variant[CVVariant.llm].ats_score is None
    assert by_variant[CVVariant.rule].ats_report is None


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


# --- the page budget: measured, not enforced --------------------------------


def test_pdf_pages_counts_a_real_cv_and_survives_garbage():
    """The page count comes from the PDF itself, not from the structure."""
    from app.services.cv_tailor import TailoredCV
    from app.services.pdf_generator import generate_pdf

    assert tailor_module._pdf_pages(generate_pdf(TailoredCV(summary="Backend engineer"))) == 1
    assert tailor_module._pdf_pages(b"%PDF-1.4 truncated") is None


async def test_tailor_task_records_the_rendered_page_count(test_engine, db_session):
    """`cv_artifact_pages` is the measurement the AI page budget rests on.

    The prompt asks the AI variant for at most two pages, but the template and the
    fonts decide the real length — so what gets recorded is the page count of the
    PDF that was actually stored.
    """
    _, cv, job = await _seed_cv_job(db_session)

    with capture_logs() as logs:
        await _run_tailor(str(job.id), str(cv.id))

    generated = (await db_session.execute(select(GeneratedCV))).scalars().one()
    expected = len(PdfReader(BytesIO(generated.pdf)).pages)
    entries = [entry for entry in logs if entry["event"] == "cv_artifact_pages"]
    assert len(entries) == 1
    assert entries[0]["variant"] == "rule"
    assert entries[0]["pages"] == expected


async def test_tailor_task_warns_when_the_ai_variant_exceeds_the_page_budget(
    test_engine, db_session, monkeypatch
):
    """Over budget is reported, never "fixed" by deleting content (ADR 016).

    The over-long artifact is still stored and still selectable — the log line is
    what tells an operator the prompt guidance was not followed.
    """
    _, cv, job = await _seed_cv_job(db_session)

    async def _enabled_config(_session):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    async def _fake_rewrite(structure, **_kwargs):
        return ({**structure, "summary": "Rewritten for the job"}, 90)

    monkeypatch.setattr(tailor_module, "get_llm_config", _enabled_config)
    monkeypatch.setattr(tailor_module, "generate_tailored_cv_with_llm", _fake_rewrite)
    # Both variants render to a single page here, so force the over-budget path.
    monkeypatch.setattr(tailor_module, "_pdf_pages", lambda _pdf: LLM_TARGET_PAGES + 1)

    with capture_logs() as logs:
        result = await _run_tailor(str(job.id), str(cv.id))

    assert result["llm_generated_cv_id"] is not None  # nothing was dropped
    warnings = [entry for entry in logs if entry["event"] == "llm_rewrite_over_page_budget"]
    assert len(warnings) == 1  # the rule variant is never warned about
    assert warnings[0]["variant"] == "llm"
    assert warnings[0]["pages"] == LLM_TARGET_PAGES + 1
    assert warnings[0]["target_pages"] == LLM_TARGET_PAGES
    stored = [entry for entry in logs if entry["event"] == "cv_artifact_pages"]
    assert {entry["variant"] for entry in stored} == {"rule", "llm"}


# --- content-less artifacts (pre-ADR-016 rows) ------------------------------


async def _seed_stale_artifact(db_session, cv, job, variant: CVVariant) -> GeneratedCV:
    """A row as a pre-ADR-016 run left it: a PDF but no structure, no score."""
    stale = GeneratedCV(
        user_id=cv.user_id,
        source_master_cv_id=cv.id,
        job_id=job.id,
        variant=variant,
        structured_json=None,
        pdf=b"%PDF-1.4 stale",
        ats_score=None,
        ats_report=None,
    )
    db_session.add(stale)
    await db_session.commit()
    await db_session.refresh(stale)
    return stale


async def test_tailor_task_repairs_a_content_less_artifact_in_place(test_engine, db_session):
    """An artifact with no content is regenerated, not reused forever.

    ``structured_json`` NULL means the panel has nothing to preview and no ATS
    report: treating that row as "already produced" is what made a broken card
    impossible to heal by re-running.
    """
    user, cv, job = await _seed_cv_job(
        db_session, description="We need Python and FastAPI on AWS with PostgreSQL."
    )
    stale = await _seed_stale_artifact(db_session, cv, job, CVVariant.rule)
    application = Application(user_id=user.id, job_id=job.id, generated_cv_id=stale.id)
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    result = await _run_tailor(str(job.id), str(cv.id), str(application.id))

    assert result["already_exists"] is False  # the empty row is not "produced"
    assert result["generated_cv_id"] == str(stale.id)

    rows = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(rows) == 1  # repaired in place: no duplicate (variant is unique)
    repaired = rows[0]
    await db_session.refresh(repaired)  # the repair was committed by the task session
    assert repaired.id == stale.id
    assert repaired.structured_json is not None
    assert repaired.structured_json["experience"][0]["title"] == "Python Developer"
    assert repaired.ats_score is None
    assert repaired.ats_report is None
    assert repaired.pdf[:4] == b"%PDF"

    await db_session.refresh(application)
    assert application.generated_cv_id == stale.id  # the link survived the repair


async def test_tailor_task_repairs_empty_rule_and_still_adds_the_llm_variant(
    test_engine, db_session, monkeypatch
):
    """The production case: a stale empty rule artifact plus an enabled LLM."""
    _, cv, job = await _seed_cv_job(db_session)
    stale = await _seed_stale_artifact(db_session, cv, job, CVVariant.rule)

    async def _enabled_config(_session):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    async def _fake_rewrite(structure, **_kwargs):
        return ({**structure, "summary": "Rewritten for the job"}, 71)

    monkeypatch.setattr(tailor_module, "get_llm_config", _enabled_config)
    monkeypatch.setattr(tailor_module, "generate_tailored_cv_with_llm", _fake_rewrite)

    result = await _run_tailor(str(job.id), str(cv.id))

    assert result["already_exists"] is False
    assert result["generated_cv_id"] == str(stale.id)
    assert set(result["generated_cv_ids"]) == {"rule", "llm"}

    rows = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(rows) == 2  # the empty rule row was reused, the llm row is new
    for row in rows:
        await db_session.refresh(row)
    by_variant = {row.variant: row for row in rows}
    assert by_variant[CVVariant.rule].id == stale.id
    assert by_variant[CVVariant.rule].structured_json is not None
    assert by_variant[CVVariant.rule].ats_score is None
    assert by_variant[CVVariant.llm].structured_json["summary"] == "Rewritten for the job"


async def test_tailor_task_repairs_a_content_less_llm_variant(test_engine, db_session, monkeypatch):
    """The same rule applies to the optional variant, not just the rule one."""
    _, cv, job = await _seed_cv_job(db_session)
    stale = await _seed_stale_artifact(db_session, cv, job, CVVariant.llm)

    async def _enabled_config(_session):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    async def _fake_rewrite(structure, **_kwargs):
        return ({**structure, "summary": "Rewritten for the job"}, 71)

    monkeypatch.setattr(tailor_module, "get_llm_config", _enabled_config)
    monkeypatch.setattr(tailor_module, "generate_tailored_cv_with_llm", _fake_rewrite)

    result = await _run_tailor(str(job.id), str(cv.id))

    rows = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert len(rows) == 2
    for row in rows:
        await db_session.refresh(row)
    by_variant = {row.variant: row for row in rows}
    assert by_variant[CVVariant.llm].id == stale.id
    assert by_variant[CVVariant.llm].structured_json["summary"] == "Rewritten for the job"
    assert by_variant[CVVariant.llm].ats_score is None
    # The model's own estimate survives the repair, nothing else is scored here.
    assert by_variant[CVVariant.llm].ats_report == {"llm_self_score": 71}
    assert result["llm_generated_cv_id"] == str(stale.id)


class _EmptyReplyResponse:
    """A DeepSeek answer with content spent on the chain-of-thought."""

    status_code = 200
    text = ""

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {"content": "", "reasoning_content": "Step 1: read the job..."},
                    "finish_reason": "length",
                }
            ]
        }

    def raise_for_status(self) -> None:
        pass


class _EmptyReplyClient:
    def __init__(self, *args, **kwargs):
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append(json)
        return _EmptyReplyResponse()


async def test_tailor_task_survives_a_thinking_mode_reply_with_no_content(
    test_engine, db_session, monkeypatch
):
    """The production regression, end to end through worker → client.

    A thinking-mode model answers ``200 OK`` with an empty ``content``: the run
    must still ship the deterministic variant, must not create an `llm` artifact,
    must disable thinking on DeepSeek, and must log the reason instead of
    reporting success.
    """
    _, cv, job = await _seed_cv_job(db_session)

    async def _deepseek_config(_session):
        return LlmRuntimeConfig(
            enabled=True,
            api_key="sk-x",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )

    client = _EmptyReplyClient()
    monkeypatch.setattr(tailor_module, "get_llm_config", _deepseek_config)
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: client)

    with capture_logs() as logs:
        result = await _run_tailor(str(job.id), str(cv.id))

    assert result["llm_generated_cv_id"] is None
    assert result["generated_cv_ids"] == {"rule": result["generated_cv_id"]}
    # The toggle that fixes it is on the wire, not just in a unit test.
    assert client.requests[0]["thinking"] == {"type": "disabled"}
    assert client.requests[0]["response_format"] == {"type": "json_object"}
    assert any(entry["event"] == "llm_empty_content" for entry in logs)

    generated = (await db_session.execute(select(GeneratedCV))).scalars().all()
    assert [item.variant for item in generated] == [CVVariant.rule]
