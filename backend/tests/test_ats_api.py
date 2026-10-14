"""Integration tests for the ATS scoring endpoint (``POST /api/cv/ats-score``)."""

from sqlalchemy import select

from app.models import CVVariant
from app.models.audit_log import AuditLog
from app.models.generated_cv import GeneratedCV
from tests.helpers import create_user

CV_PAYLOAD = {
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "location": "Lisbon, PT",
    "summary": "Backend engineer focused on async Python services.",
    "experience": [
        {
            "company": "Acme",
            "title": "Python Developer",
            "start_date": "2021-01",
            "bullets": ["Cut p95 latency 40% with async FastAPI handlers."],
        }
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "fastapi", "postgresql", "docker", "kubernetes"],
    "certifications": [],
    "languages": ["English"],
}

JD_TEXT = "We need Python, FastAPI and PostgreSQL. Kubernetes and Terraform are a plus."


async def test_ats_score_returns_factors_and_gaps(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/ats-score",
        json={"cv": CV_PAYLOAD, "job_title": "Backend Engineer", "job_description": JD_TEXT},
    )

    assert response.status_code == 200
    body = response.json()
    assert 0 <= body["score"] <= 100
    # The headline mirrors the deterministic baseline; the LLM's own estimate is
    # a separate field and is absent when no reviewer ran (ADR 013).
    assert body["deterministic_score"] == body["score"]
    assert body["llm_score"] is None
    assert body["method"] == "heuristic"
    assert body["llm_summary"] is None
    assert [f["key"] for f in body["factors"]] == [
        "skills",
        "keywords",
        "completeness",
        "readability",
    ]
    assert "python" in [s.lower() for s in body["matched_skills"]]
    assert "fastapi" in [s.lower() for s in body["matched_skills"]]
    assert all(isinstance(skill, str) for skill in body["missing_skills"])
    assert isinstance(body["warnings"], list)


async def test_ats_score_parses_a_raw_description_without_a_job(auth_client):
    """Regression: a raw description alone must feed the weighted skills factor."""
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/ats-score",
        json={"cv": CV_PAYLOAD, "job_description": JD_TEXT},
    )

    assert response.status_code == 200
    body = response.json()
    skills = next(factor for factor in body["factors"] if factor["key"] == "skills")
    assert skills["score"] == 0.8
    assert skills["detail"] == "4/5 required skills found in the CV."
    assert [s.lower() for s in body["missing_skills"]] == ["terraform"]
    assert any("terraform" in tip and "required skills" in tip for tip in body["recommendations"])


async def test_ats_score_uses_an_explicit_job_title_without_a_description(auth_client):
    """A bare title still scores keyword coverage and suggests mirroring it."""
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/ats-score",
        json={"cv": CV_PAYLOAD, "job_title": "Staff Rust Engineer"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [f["key"] for f in body["factors"]] == ["keywords", "completeness", "readability"]
    assert any("Mirror the job title" in tip for tip in body["recommendations"])


async def test_ats_score_falls_back_to_the_stored_job_title(auth_client):
    client, _, _ = auth_client
    job = (
        await client.post("/api/jobs", json={"title": "Staff Rust Engineer", "company": "Acme"})
    ).json()

    response = await client.post("/api/cv/ats-score", json={"cv": CV_PAYLOAD, "job_id": job["id"]})

    assert response.status_code == 200
    keywords = next(f for f in response.json()["factors"] if f["key"] == "keywords")
    assert keywords["detail"] == "1/3 job keywords appear in the CV."


async def test_ats_score_scores_a_stored_job(auth_client):
    client, _, _ = auth_client
    job = (
        await client.post(
            "/api/jobs",
            json={"title": "Backend Engineer", "company": "Acme", "description": JD_TEXT},
        )
    ).json()

    response = await client.post("/api/cv/ats-score", json={"cv": CV_PAYLOAD, "job_id": job["id"]})

    assert response.status_code == 200
    assert response.json()["score"] >= 1


async def test_ats_score_rejects_a_job_owned_by_someone_else(auth_client):
    client, _, _ = auth_client
    response = await client.post(
        "/api/cv/ats-score",
        json={"cv": CV_PAYLOAD, "job_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404


async def test_ats_score_caches_the_report_on_an_owned_generated_cv(auth_client, db_session):
    client, user, _ = auth_client
    generated = GeneratedCV(user_id=user.id, pdf=b"%PDF-1.4 stub")
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    response = await client.post(
        "/api/cv/ats-score",
        json={
            "cv": CV_PAYLOAD,
            "job_description": JD_TEXT,
            "generated_cv_id": str(generated.id),
        },
    )
    assert response.status_code == 200

    await db_session.refresh(generated)
    assert generated.ats_score == response.json()["score"]
    assert generated.ats_report["score"] == response.json()["score"]
    assert generated.ats_report["deterministic_score"] == response.json()["score"]
    assert generated.ats_report["method"] == "heuristic"

    entries = (
        (await db_session.execute(select(AuditLog).where(AuditLog.entity_type == "generated_cv")))
        .scalars()
        .all()
    )
    assert [entry.action for entry in entries] == ["scored"]


async def test_get_generated_cv_exposes_the_cached_ats_report(auth_client, db_session):
    client, user, _ = auth_client
    generated = GeneratedCV(user_id=user.id, pdf=b"%PDF-1.4 stub")
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    scored = await client.post(
        "/api/cv/ats-score",
        json={
            "cv": CV_PAYLOAD,
            "job_description": JD_TEXT,
            "generated_cv_id": str(generated.id),
        },
    )
    assert scored.status_code == 200

    fetched = await client.get(f"/api/cv/generated/{generated.id}")

    assert fetched.status_code == 200
    assert fetched.json()["ats_score"] == scored.json()["score"]
    assert fetched.json()["ats_report"]["factors"] == scored.json()["factors"]


async def test_rescoring_keeps_the_ai_variants_own_estimate(auth_client, db_session):
    """Re-scoring must not lose the LLM variant's own estimate (ADR 016)."""
    client, user, _ = auth_client
    generated = GeneratedCV(
        user_id=user.id,
        pdf=b"%PDF-1.4 stub",
        variant=CVVariant.llm,
        ats_report={"llm_self_score": 88},
    )
    db_session.add(generated)
    await db_session.commit()
    await db_session.refresh(generated)

    response = await client.post(
        "/api/cv/ats-score",
        json={
            "cv": CV_PAYLOAD,
            "job_description": JD_TEXT,
            "generated_cv_id": str(generated.id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["llm_self_score"] == 88
    assert body["deterministic_score"] == body["score"]
    await db_session.refresh(generated)
    assert generated.ats_report["llm_self_score"] == 88
    assert generated.ats_score == body["score"]


async def test_get_generated_cv_hides_another_users_cv(auth_client, db_session):
    client, _, _ = auth_client
    other = await create_user(db_session, email="generated-owner@example.com")
    generated = GeneratedCV(user_id=other.id, pdf=b"%PDF-1.4 stub", ats_score=88)
    db_session.add(generated)
    await db_session.commit()

    response = await client.get(f"/api/cv/generated/{generated.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Generated CV not found"


async def test_ats_score_requires_auth(client):
    response = await client.post("/api/cv/ats-score", json={"cv": CV_PAYLOAD})

    assert response.status_code == 401
