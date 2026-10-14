"""Tests for the ATS scoring service (deterministic core + LLM overlay)."""

import pytest

from app.services.ats_scorer import (
    WEIGHTS,
    build_report,
    cv_text,
    derive_keywords,
    score_ats,
)
from app.services.llm_config import LlmRuntimeConfig

# A CV that satisfies every completeness/readability check.
RICH_CV = {
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "+351 900 000 000",
    "location": "Lisbon, PT",
    "links": ["https://github.com/ada"],
    "summary": "Backend engineer with six years building Python services.",
    "experience": [
        {
            "company": "Acme",
            "title": "Python Developer",
            "start_date": "2021-01",
            "end_date": "2024-06",
            "bullets": ["Cut p95 API latency 40% by moving to async FastAPI handlers."],
        }
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "fastapi", "postgresql", "docker", "kubernetes"],
    "projects": [],
    "certifications": ["AWS Solutions Architect"],
    "languages": ["Portuguese", "English"],
}


def _factor(report: dict, key: str) -> dict:
    return next(factor for factor in report["factors"] if factor["key"] == key)


def test_report_has_all_four_factors_when_job_context_is_given():
    report = build_report(
        RICH_CV,
        jd_skills=["python", "fastapi", "rust"],
        jd_keywords=["fastapi", "async"],
    )

    assert [f["key"] for f in report["factors"]] == [
        "skills",
        "keywords",
        "completeness",
        "readability",
    ]
    assert sum(f["weight"] for f in report["factors"]) == pytest.approx(sum(WEIGHTS.values()))
    assert report["method"] == "heuristic"
    assert report["llm_summary"] is None
    # 2 of 3 required skills are present; every other factor is perfect.
    expected = 100 * (2 / 3 * WEIGHTS["skills"] + WEIGHTS["keywords"] + WEIGHTS["completeness"])
    expected += 100 * WEIGHTS["readability"]
    assert report["score"] == round(expected)
    assert report["matched_skills"] == ["python", "fastapi"]
    assert report["missing_skills"] == ["rust"]


def test_report_without_job_scores_content_only():
    report = build_report(RICH_CV)

    assert [f["key"] for f in report["factors"]] == ["completeness", "readability"]
    # Weights are renormalised over the factors that could be computed.
    assert report["score"] == 100
    assert report["matched_skills"] == []
    assert report["missing_skills"] == []
    assert _factor(report, "completeness")["detail"] == "All key sections present."


def test_missing_skills_and_keywords_drive_recommendations():
    report = build_report(
        {**RICH_CV, "skills": ["python"]},
        jd_skills=["python", "rust"],
        jd_keywords=["kubernetes"],
    )

    assert report["missing_skills"] == ["rust"]
    joined = " ".join(report["recommendations"])
    assert "rust" in joined
    assert "kubernetes" in joined


def test_recommendations_flag_unquantified_bullets_and_missing_summary():
    cv = {
        **RICH_CV,
        "summary": "",
        "experience": [
            {
                "company": "Acme",
                "title": "Dev",
                "start_date": "2020-01",
                "bullets": ["Shipped things"],
            }
        ],
    }
    report = build_report(cv)

    joined = " ".join(report["recommendations"])
    assert "Quantify impact with numbers" in joined
    assert "Open with a 2-4 sentence summary" in joined


def test_readability_warns_about_long_bullets_and_undated_roles():
    cv = {
        **RICH_CV,
        "experience": [{"company": "Acme", "title": "Dev", "bullets": ["x" * 300]}],
    }
    report = build_report(cv)

    readability = _factor(report, "readability")
    # Two of the four readability checks fail: long bullet + missing start date.
    assert readability["score"] == pytest.approx(0.5)
    assert readability["weight"] == WEIGHTS["readability"]
    assert len(report["warnings"]) == 2
    assert readability["detail"] == "2 issue(s) to fix."


def test_readability_accepts_certifications_instead_of_a_long_skill_list():
    cv = {**RICH_CV, "skills": ["python"], "certifications": ["AWS Solutions Architect"]}
    report = build_report(cv)

    assert _factor(report, "readability")["score"] == pytest.approx(1.0)
    assert report["warnings"] == []
    assert _factor(report, "readability")["detail"] == "No parsing blockers detected."


def test_derive_keywords_ranks_by_frequency_and_skips_stopwords():
    keywords = derive_keywords("FastAPI FastAPI FastAPI postgres postgres docker with the and")

    assert keywords[:3] == ["fastapi", "postgres", "docker"]
    assert "with" not in keywords
    assert "the" not in keywords
    assert len(derive_keywords("python " * 50, limit=3)) == 1
    assert derive_keywords("alpha bravo charlie delta echo", limit=3) == [
        "alpha",
        "bravo",
        "charlie",
    ]


def test_cv_text_includes_the_richer_cv_sections():
    text = cv_text(RICH_CV)

    assert "Ada Lovelace" in text
    assert "Lisbon, PT" in text
    assert "AWS Solutions Architect" in text
    assert "Portuguese" in text


def test_job_title_terms_join_the_keyword_pool_and_drive_a_mirror_tip():
    report = build_report(RICH_CV, job_title="Staff Rust Engineer")

    keywords = _factor(report, "keywords")
    # The title keeps the keyword factor alive even without a description.
    assert [f["key"] for f in report["factors"]] == ["keywords", "completeness", "readability"]
    assert keywords["detail"] == "1/3 job keywords appear in the CV."
    joined = " ".join(report["recommendations"])
    assert "Mirror the job title" in joined
    assert "rust" in joined
    assert "staff" in joined


def test_job_title_terms_are_deduped_against_jd_keywords():
    report = build_report(RICH_CV, jd_keywords=["engineer"], job_title="Backend Engineer")

    # "engineer" is counted once; "backend" joins from the title (both in the CV).
    assert _factor(report, "keywords")["detail"] == "2/2 job keywords appear in the CV."


def test_no_mirror_tip_when_the_cv_already_echoes_the_title():
    report = build_report(RICH_CV, job_title="Python Developer")

    assert not any("Mirror the job title" in tip for tip in report["recommendations"])


class _FakeReview:
    """Stands in for ``_llm_review``; records calls and can refuse to be used."""

    def __init__(self, result: dict | None = None, *, raises: bool = False) -> None:
        self.result = result
        self.raises = raises
        self.calls: list[str] = []

    async def __call__(self, report: dict, text: str, jd_text: str, config) -> dict | None:
        self.calls.append(jd_text)
        if self.raises:
            raise AssertionError("the LLM must not be consulted")
        return self.result


def _enabled_config() -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=True,
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )


async def test_score_ats_reports_the_llm_estimate_beside_the_baseline(monkeypatch):
    from app.services import ats_scorer

    review = _FakeReview(
        {"score": 10, "summary": "Weak match", "suggestions": ["Add rust if you know it"]}
    )
    monkeypatch.setattr(ats_scorer, "_llm_review", review)

    report = await score_ats(
        RICH_CV,
        jd_skills=["python", "rust"],
        jd_keywords=[],
        jd_text="Python and Rust.",
        llm_config=_enabled_config(),
    )

    base = build_report(RICH_CV, jd_skills=["python", "rust"], jd_keywords=[])["score"]
    assert report["method"] == "hybrid"
    # The LLM never moves the headline: it is an extra number beside it, so the
    # score stays reproducible and comparable across artifacts.
    assert report["score"] == base
    assert report["deterministic_score"] == base
    assert report["llm_score"] == 10
    assert report["llm_summary"] == "Weak match"
    assert "Add rust if you know it" in report["recommendations"]
    assert review.calls == ["Python and Rust."]


async def test_score_ats_clamps_an_out_of_range_llm_score(monkeypatch):
    from app.services import ats_scorer

    monkeypatch.setattr(ats_scorer, "_llm_review", _FakeReview({"score": 150}))
    report = await score_ats(RICH_CV, jd_skills=["python"], llm_config=_enabled_config())

    assert report["method"] == "hybrid"
    assert report["llm_score"] == 100
    assert report["score"] == report["deterministic_score"]


async def test_score_ats_skips_the_llm_when_disabled(monkeypatch):
    from app.services import ats_scorer

    review = _FakeReview(raises=True)
    monkeypatch.setattr(ats_scorer, "_llm_review", review)

    disabled = LlmRuntimeConfig(
        enabled=False, api_key="sk-test", base_url="https://x/v1", model="m"
    )
    report = await score_ats(RICH_CV, jd_skills=["python"], llm_config=disabled)

    assert report["method"] == "heuristic"
    assert review.calls == []
    assert report["score"] == build_report(RICH_CV, jd_skills=["python"])["score"]
    assert report["deterministic_score"] == report["score"]
    assert report["llm_score"] is None


async def test_score_ats_degrades_when_the_llm_review_fails(monkeypatch):
    from app.services import ats_scorer

    monkeypatch.setattr(ats_scorer, "_llm_review", _FakeReview(None))
    report = await score_ats(RICH_CV, jd_skills=["python"], llm_config=_enabled_config())

    assert report["method"] == "heuristic"
    assert report["llm_summary"] is None
    assert report["llm_score"] is None
    assert report["score"] == build_report(RICH_CV, jd_skills=["python"])["score"]
