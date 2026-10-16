"""Tests for the jobs API (manual CRUD + search/filter)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.models.audit_log import AuditLog
from app.models.job import Job
from app.routers import jobs as jobs_router
from app.services.llm_config import LlmRuntimeConfig
from tests.helpers import create_user


async def _create_job(client, **overrides) -> dict:
    payload = {"title": "Backend Engineer", "company": "Acme", "description": "Python API"}
    payload.update(overrides)
    response = await client.post("/api/jobs", json=payload)
    assert response.status_code == 201
    return response.json()


async def _backdate(db_session, job_id: str, days: int) -> None:
    """Move a job's ``created_at`` into the past (scrapers do this over time)."""
    await db_session.execute(
        update(Job)
        .where(Job.id == uuid.UUID(job_id))
        .values(created_at=datetime.now(UTC) - timedelta(days=days))
    )
    await db_session.commit()


async def test_create_job_manual(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/jobs",
        json={
            "title": "Senior Python Engineer",
            "company": "Acme",
            "description": "Build APIs with FastAPI.",
            "url": "https://acme.example/jobs/1",
            "tags": ["python", "fastapi"],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Senior Python Engineer"
    assert body["tags"] == ["python", "fastapi"]
    assert body["source_id"] is None


async def test_job_search_filters(auth_client):
    client, _, _ = auth_client
    for payload in [
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "description": "Python and Postgres",
            "tags": ["python"],
        },
        {
            "title": "Frontend Engineer",
            "company": "Beta",
            "description": "TypeScript and Angular",
            "tags": ["angular"],
        },
    ]:
        response = await client.post("/api/jobs", json=payload)
        assert response.status_code == 201

    by_keyword = await client.get("/api/jobs", params={"q": "backend"})
    assert len(by_keyword.json()) == 1
    assert by_keyword.json()[0]["company"] == "Acme"

    by_company = await client.get("/api/jobs", params={"company": "beta"})
    assert len(by_company.json()) == 1
    assert by_company.json()[0]["company"] == "Beta"

    by_tags = await client.get("/api/jobs", params={"tags": "python"})
    assert len(by_tags.json()) == 1

    no_match = await client.get("/api/jobs", params={"q": "rust"})
    assert no_match.json() == []


async def test_create_job_with_foreign_source_rejected(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/jobs",
        json={
            "title": "X",
            "company": "Y",
            "source_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert response.status_code == 404


async def test_job_detail_includes_description(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "SRE", "company": "Acme", "description": "On-call rotations"},
    )
    job_id = created.json()["id"]

    detail = await client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["description"] == "On-call rotations"


async def test_jobs_require_auth(client):
    assert (await client.get("/api/jobs")).status_code == 401


async def test_hidden_jobs_excluded_by_default_and_toggleable(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Secret Ops", "company": "Acme", "description": "Hidden work"},
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    assert created.json()["hidden"] is False

    # Toggle hidden on via the update endpoint.
    hidden = await client.put(f"/api/jobs/{job_id}", json={"hidden": True})
    assert hidden.status_code == 200
    assert hidden.json()["hidden"] is True

    # Hidden jobs are excluded from the default listing…
    listed = await client.get("/api/jobs")
    assert all(job["id"] != job_id for job in listed.json())

    # …but returned when include_hidden is requested.
    with_hidden = await client.get("/api/jobs", params={"include_hidden": "true"})
    assert any(job["id"] == job_id and job["hidden"] is True for job in with_hidden.json())

    # And they can be unhidden again.
    visible = await client.put(f"/api/jobs/{job_id}", json={"hidden": False})
    assert visible.json()["hidden"] is False
    listed = await client.get("/api/jobs")
    assert any(job["id"] == job_id for job in listed.json())


async def test_hide_applied_filters_out_applied_jobs(auth_client):
    client, _, _ = auth_client
    await client.post("/api/jobs", json={"title": "Plain", "company": "Acme"})
    saved = (await client.post("/api/jobs", json={"title": "Saved", "company": "Beta"})).json()
    applied = (await client.post("/api/jobs", json={"title": "Applied", "company": "Gamma"})).json()

    # "saved" is a bookmark — the job stays visible; "applied" should be hidden.
    await client.post("/api/applications", json={"job_id": saved["id"], "status": "saved"})
    await client.post("/api/applications", json={"job_id": applied["id"], "status": "applied"})

    filtered = await client.get("/api/jobs", params={"hide_applied": "true"})
    titles = [job["title"] for job in filtered.json()]
    assert "Applied" not in titles
    assert "Saved" in titles
    assert "Plain" in titles

    # Without the filter every job is present again.
    unfiltered = await client.get("/api/jobs")
    assert len(unfiltered.json()) == 3


async def test_hide_applied_applies_to_keyword_search(auth_client):
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Backend Engineer", "company": "Acme", "description": "Python API"},
    )
    job_id = created.json()["id"]
    await client.post("/api/applications", json={"job_id": job_id, "status": "interview"})

    without = await client.get("/api/jobs", params={"q": "backend", "hide_applied": "true"})
    assert without.json() == []

    with_filter_off = await client.get(
        "/api/jobs", params={"q": "backend", "hide_applied": "false"}
    )
    assert len(with_filter_off.json()) == 1


async def test_tailor_enqueue_announces_the_variants_the_run_will_produce(auth_client, monkeypatch):
    """The client polls until the promised artifacts exist, so the 202 body must
    name them — the deterministic variant lands long before the AI rewrite
    (ADR 016) and stopping at the first artifact stranded the panel."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Backend Engineer", "company": "Acme", "description": "Python API"},
    )
    job_id = created.json()["id"]

    queued: list[tuple[str, str | None, str | None]] = []
    monkeypatch.setattr(jobs_router, "enqueue_tailor", lambda *args: queued.append(args))

    # No LLM row and no env key: the run degrades to the deterministic variant.
    accepted = await client.post(f"/api/jobs/{job_id}/tailor", json={})

    assert accepted.status_code == 202
    body = accepted.json()
    assert body["enqueued"] is True
    assert body["job_id"] == job_id
    assert body["variants"] == ["rule"]
    assert len(queued) == 1


async def test_tailor_enqueue_announces_the_ai_variant_when_the_llm_is_enabled(
    auth_client, monkeypatch
):
    """With a usable LLM config the run also produces the `llm` rewrite, and the
    client must wait for it instead of settling on `rule`."""
    client, _, _ = auth_client
    created = await client.post(
        "/api/jobs",
        json={"title": "Backend Engineer", "company": "Acme", "description": "Python API"},
    )
    job_id = created.json()["id"]

    async def _enabled_config(_db):
        return LlmRuntimeConfig(
            enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
        )

    monkeypatch.setattr(jobs_router, "get_llm_config", _enabled_config)
    monkeypatch.setattr(jobs_router, "enqueue_tailor", lambda *args: None)

    accepted = await client.post(f"/api/jobs/{job_id}/tailor", json={})

    assert accepted.status_code == 202
    assert accepted.json()["variants"] == ["rule", "llm"]


# --- Bulk cleanup (ADR 023) -------------------------------------------------


async def test_cleanup_dry_run_previews_without_deleting(auth_client, db_session):
    """`dry_run` is the default: the client shows the count before committing."""
    client, _, _ = auth_client
    old_one = await _create_job(client, title="Old one")
    old_two = await _create_job(client, title="Old two")
    recent = await _create_job(client, title="Recent")
    await _backdate(db_session, old_one["id"], days=120)
    await _backdate(db_session, old_two["id"], days=90)

    preview = await client.post("/api/jobs/cleanup", json={"older_than_days": 60})

    assert preview.status_code == 200
    assert preview.json() == {"matched": 2, "deleted": 0, "protected": 0, "dry_run": True}

    listed = await client.get("/api/jobs")
    assert len(listed.json()) == 3
    assert recent["id"] in {job["id"] for job in listed.json()}


async def test_cleanup_deletes_jobs_older_than_the_cutoff(auth_client, db_session):
    client, _, _ = auth_client
    old = await _create_job(client, title="Old")
    recent = await _create_job(client, title="Recent")
    await _backdate(db_session, old["id"], days=120)

    response = await client.post(
        "/api/jobs/cleanup", json={"older_than_days": 60, "dry_run": False}
    )

    assert response.json() == {"matched": 1, "deleted": 1, "protected": 0, "dry_run": False}
    remaining = [job["id"] for job in (await client.get("/api/jobs")).json()]
    assert remaining == [recent["id"]]


async def test_cleanup_protects_jobs_with_applications_by_default(auth_client, db_session):
    """A tracked job survives: deleting it would cascade its application away."""
    client, _, _ = auth_client
    job = await _create_job(client)
    await _backdate(db_session, job["id"], days=120)
    await client.post("/api/applications", json={"job_id": job["id"], "status": "interview"})

    response = await client.post(
        "/api/jobs/cleanup", json={"older_than_days": 60, "dry_run": False}
    )

    assert response.json() == {"matched": 1, "deleted": 0, "protected": 1, "dry_run": False}
    assert (await client.get(f"/api/jobs/{job['id']}")).status_code == 200
    assert len((await client.get("/api/applications")).json()) == 1


async def test_cleanup_include_with_applications_deletes_them_too(auth_client, db_session):
    """The opt-in checkbox is the only way a tracked job is removed."""
    client, _, _ = auth_client
    job = await _create_job(client)
    await _backdate(db_session, job["id"], days=120)
    await client.post("/api/applications", json={"job_id": job["id"], "status": "saved"})

    response = await client.post(
        "/api/jobs/cleanup",
        json={"older_than_days": 60, "include_with_applications": True, "dry_run": False},
    )

    assert response.json() == {"matched": 1, "deleted": 1, "protected": 0, "dry_run": False}
    assert (await client.get("/api/jobs")).json() == []
    assert (await client.get("/api/applications")).json() == []



async def test_cleanup_by_source_ignores_job_age(auth_client):
    """A source-only run deletes every job from it, however recent."""
    client, _, _ = auth_client
    source_id = (
        await client.post(
            "/api/sources",
            json={
                "name": "Acme Careers",
                "url": "https://acme.example/careers",
                "type": "career_page",
            },
        )
    ).json()["id"]
    from_source = await _create_job(client, title="From source", source_id=source_id)
    await _create_job(client, title="Manual")

    response = await client.post(
        "/api/jobs/cleanup", json={"source_id": source_id, "dry_run": False}
    )

    assert response.json() == {"matched": 1, "deleted": 1, "protected": 0, "dry_run": False}
    remaining = (await client.get("/api/jobs")).json()
    assert [job["title"] for job in remaining] == ["Manual"]
    assert from_source["id"] not in {job["id"] for job in remaining}


async def test_cleanup_combines_age_and_source_as_an_and(auth_client, db_session):
    """Both filters narrow: a recent job from the source is spared."""
    client, _, _ = auth_client
    source_id = (
        await client.post(
            "/api/sources",
            json={
                "name": "Acme Careers",
                "url": "https://acme.example/careers",
                "type": "career_page",
            },
        )
    ).json()["id"]
    old_from_source = await _create_job(client, title="Old from source", source_id=source_id)
    recent_from_source = await _create_job(client, title="Recent from source", source_id=source_id)
    old_manual = await _create_job(client, title="Old manual")
    # Only the two *old* jobs are backdated: the recent one from the same source
    # must survive, which is what makes the two filters an AND rather than an OR.
    for job in (old_from_source, old_manual):
        await _backdate(db_session, job["id"], days=120)

    response = await client.post(
        "/api/jobs/cleanup",
        json={"older_than_days": 60, "source_id": source_id, "dry_run": False},
    )

    assert response.json()["matched"] == 1
    assert response.json()["deleted"] == 1
    survivors = {job["id"] for job in (await client.get("/api/jobs")).json()}
    assert survivors == {recent_from_source["id"], old_manual["id"]}



async def test_cleanup_requires_a_criterion(auth_client):
    """An empty body would mean "delete everything" — refuse it loudly."""
    client, _, _ = auth_client
    response = await client.post("/api/jobs/cleanup", json={})

    assert response.status_code == 400
    assert "older_than_days" in response.json()["detail"]


async def test_cleanup_rejects_an_unknown_source(auth_client):
    client, _, _ = auth_client
    await _create_job(client)

    response = await client.post(
        "/api/jobs/cleanup", json={"source_id": str(uuid.uuid4()), "dry_run": False}
    )

    assert response.status_code == 404
    assert len((await client.get("/api/jobs")).json()) == 1


async def test_cleanup_never_touches_another_users_old_jobs(auth_client, db_session):
    client, user, _ = auth_client
    mine = await _create_job(client)
    await _backdate(db_session, mine["id"], days=120)

    other = await create_user(db_session, email="other-owner@example.com")
    theirs = Job(user_id=other.id, title="Theirs", company="Beta")
    db_session.add(theirs)
    await db_session.commit()
    await db_session.refresh(theirs)
    await db_session.execute(
        update(Job)
        .where(Job.id == theirs.id)
        .values(created_at=datetime.now(UTC) - timedelta(days=120))
    )
    await db_session.commit()

    response = await client.post(
        "/api/jobs/cleanup", json={"older_than_days": 60, "dry_run": False}
    )

    assert response.json() == {"matched": 1, "deleted": 1, "protected": 0, "dry_run": False}
    assert user.id != other.id
    survivors = (await db_session.execute(select(Job.id).where(Job.id == theirs.id))).all()
    assert survivors == [(theirs.id,)]


async def test_cleanup_writes_an_audit_log(auth_client, db_session):
    client, user, _ = auth_client
    job = await _create_job(client)
    await _backdate(db_session, job["id"], days=120)

    await client.post("/api/jobs/cleanup", json={"older_than_days": 60, "dry_run": False})

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "bulk_deleted")
    )
    entry = result.scalar_one()
    assert entry.entity_type == "job"
    assert entry.changes["deleted"] == 1
    assert entry.changes["older_than_days"] == 60

