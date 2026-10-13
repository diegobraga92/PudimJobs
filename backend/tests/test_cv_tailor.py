"""Tests for the rule-based CV tailoring engine."""

import json

from app.services.cv_tailor import (
    TailoredCV,
    _coerce_self_score,
    enhance_with_llm,
    generate_tailored_cv_with_llm,
    tailor_cv,
)
from app.services.llm_config import LlmRuntimeConfig

CV = {
    "summary": "Backend engineer",
    "experience": [
        {
            "title": "Python Developer",
            "company": "Acme",
            "bullets": ["Built FastAPI services on AWS"],
        },
        {
            "title": "Java Developer",
            "company": "Beta",
            "bullets": ["Maintained Spring applications"],
        },
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "java"],
    "projects": [{"name": "Job Tracker", "description": "FastAPI + PostgreSQL pipeline"}],
}


def test_tailor_orders_relevant_experience_first():
    tailored = tailor_cv(CV, ["python", "fastapi", "postgresql"])
    assert tailored.experience[0]["title"] == "Python Developer"
    assert tailored.matched_skills == ["python"]
    assert "fastapi" in tailored.missing_skills


def test_tailor_places_matched_skills_first():
    tailored = tailor_cv(CV, ["python"])
    assert tailored.skills[0] == "python"
    assert "java" in tailored.skills  # remaining skill kept


def test_tailor_drops_irrelevant_blocks():
    tailored = tailor_cv(CV, ["python", "fastapi"], drop_irrelevant=True)
    assert len(tailored.experience) == 1
    assert tailored.experience[0]["title"] == "Python Developer"


def test_tailor_keeps_all_when_not_dropping():
    tailored = tailor_cv(CV, ["python", "fastapi"], drop_irrelevant=False)
    assert len(tailored.experience) == 2


def test_tailor_relevance_zero_when_no_match():
    tailored = tailor_cv(CV, ["rust"])
    assert tailored.relevance == 0.0
    assert tailored.missing_skills == ["rust"]


def test_tailor_keeps_fallback_blocks_when_nothing_matches():
    """No skill match must never produce an empty CV — top blocks are kept."""
    tailored = tailor_cv(CV, ["rust"], drop_irrelevant=True)
    assert tailored.relevance == 0.0
    assert len(tailored.experience) == 2
    assert len(tailored.projects) == 1


def test_tailor_fallback_is_bounded():
    big_cv = {
        "summary": "x",
        "experience": [{"title": f"Role {i}", "company": "C", "bullets": []} for i in range(6)],
        "education": [],
        "skills": ["python"],
        "projects": [],
    }
    tailored = tailor_cv(big_cv, ["rust"], drop_irrelevant=True)
    assert len(tailored.experience) == 3  # capped by _FALLBACK_TOP_N


def test_tailor_uses_annotations_to_score():
    annotations = {"experience": [["python"], ["java"]]}
    tailored = tailor_cv(CV, ["java", "spring"], annotations=annotations)
    assert tailored.experience[0]["title"] == "Java Developer"


def test_tailor_summary_leads_with_matched_strengths():
    """The deterministic variant is no longer a verbatim copy (ADR 016)."""
    tailored = tailor_cv(CV, ["python", "fastapi"])
    assert tailored.summary.startswith("Backend engineer.")
    assert "Core strengths" in tailored.summary
    assert "python" in tailored.summary


def test_tailor_summary_untouched_when_it_already_mentions_the_skills():
    cv = {**CV, "summary": "Python and FastAPI engineer."}
    tailored = tailor_cv(cv, ["python", "fastapi"])
    assert tailored.summary == "Python and FastAPI engineer."


def test_tailor_summary_untouched_without_matches():
    tailored = tailor_cv(CV, ["rust"])
    assert tailored.summary == "Backend engineer"


def test_tailor_flags_the_no_match_fallback():
    """A silent fallback was a bug: it is now explicit on the result."""
    assert tailor_cv(CV, ["rust"], drop_irrelevant=True).used_fallback is True
    assert tailor_cv(CV, ["python"], drop_irrelevant=True).used_fallback is False


def test_tailored_cv_round_trips_through_a_structure():
    tailored = tailor_cv(CV, ["python", "fastapi"])
    structure = tailored.as_structure()
    assert set(structure) == {
        "full_name",
        "email",
        "phone",
        "location",
        "links",
        "summary",
        "experience",
        "education",
        "skills",
        "projects",
        "certifications",
        "languages",
    }
    restored = TailoredCV.from_structure(structure)
    assert restored.summary == tailored.summary
    assert restored.experience == tailored.experience
    assert restored.skills == tailored.skills
    assert restored.projects == tailored.projects


def test_coerce_self_score_clamps_and_tolerates_junk():
    assert _coerce_self_score(150) == 100
    assert _coerce_self_score(-5) == 0
    assert _coerce_self_score("82") == 82
    assert _coerce_self_score(None) is None
    assert _coerce_self_score("not-a-number") is None


def _enabled_llm_config() -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=True, api_key="sk-x", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    )


async def test_generate_tailored_cv_with_llm_disabled_returns_none():
    config = LlmRuntimeConfig(enabled=False, api_key="sk-x", base_url="", model="")
    assert await generate_tailored_cv_with_llm(CV, jd_text="Rust role", config=config) is None


async def test_generate_tailored_cv_with_llm_missing_key_returns_none():
    config = LlmRuntimeConfig(enabled=True, api_key="", base_url="url", model="m")
    assert await generate_tailored_cv_with_llm(CV, jd_text="Rust role", config=config) is None


async def test_generate_tailored_cv_with_llm_validates_the_reply(monkeypatch):
    from app.services import cv_tailor

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": {**CV, "summary": "Rewritten"}, "ats_self_score": 77})
    monkeypatch.setattr(cv_tailor.httpx, "AsyncClient", lambda *a, **k: fake)

    result = await generate_tailored_cv_with_llm(
        CV,
        jd_text="Python role",
        jd_title="Backend",
        jd_skills=["python"],
        config=_enabled_llm_config(),
    )

    assert result is not None
    structure, self_score = result
    assert structure["summary"] == "Rewritten"
    assert structure["skills"] == CV["skills"]
    assert self_score == 77


async def test_generate_tailored_cv_with_llm_rejects_an_invalid_structure(monkeypatch):
    from app.services import cv_tailor

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": {"experience": "not-a-list"}, "ats_self_score": 90})
    monkeypatch.setattr(cv_tailor.httpx, "AsyncClient", lambda *a, **k: fake)

    assert (
        await generate_tailored_cv_with_llm(CV, jd_text="x", config=_enabled_llm_config()) is None
    )


async def test_generate_tailored_cv_with_llm_degrades_on_failure(monkeypatch):
    from app.services import cv_tailor

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("llm down")

    monkeypatch.setattr(cv_tailor.httpx, "AsyncClient", lambda *a, **k: _BoomClient())

    assert (
        await generate_tailored_cv_with_llm(CV, jd_text="x", config=_enabled_llm_config()) is None
    )


async def test_enhance_with_llm_disabled_returns_bullets_unchanged():
    config = LlmRuntimeConfig(
        enabled=False, api_key="sk-x", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    )
    bullets = ["Built FastAPI services"]
    assert await enhance_with_llm(bullets, ["python", "fastapi"], config=config) == bullets


async def test_enhance_with_llm_missing_key_returns_bullets_unchanged():
    config = LlmRuntimeConfig(
        enabled=True, api_key="", base_url="https://api.openai.com/v1", model="gpt-4o-mini"
    )
    bullets = ["Built FastAPI services"]
    assert await enhance_with_llm(bullets, ["python"], config=config) == bullets


class _FakeLLMResponse:
    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeLLMClient:
    """In-memory stand-in for httpx.AsyncClient."""

    reply = "1. Rewritten bullet\n2. Another one"

    def __init__(self, *args, **kwargs):
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append(json)
        return _FakeLLMResponse(self.reply)


async def test_enhance_with_llm_caps_bullets_and_parses(monkeypatch):
    from app.services import cv_tailor

    config = LlmRuntimeConfig(
        enabled=True,
        api_key="sk-x",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    fake = _FakeLLMClient()
    monkeypatch.setattr(cv_tailor.httpx, "AsyncClient", lambda *a, **k: fake)

    bullets = [f"bullet {i}" for i in range(8)]
    out = await enhance_with_llm(bullets, ["python"], config=config, max_bullets=5)

    # Only the first 5 bullets were sent to the API.
    sent = fake.requests[0]["messages"][1]["content"]
    assert "1. bullet 0" in sent
    assert "6. bullet 5" not in sent
    # Numbered reply parsed; count preserved (rephrased head + untouched tail).
    assert out[0] == "Rewritten bullet"
    assert len(out) == 8
    assert out[5:] == bullets[5:]


async def test_enhance_with_llm_pads_short_reply(monkeypatch):
    from app.services import cv_tailor

    config = LlmRuntimeConfig(
        enabled=True,
        api_key="sk-x",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    fake = _FakeLLMClient()
    fake.reply = "1. Only one"
    monkeypatch.setattr(cv_tailor.httpx, "AsyncClient", lambda *a, **k: fake)

    out = await enhance_with_llm(["a", "b", "c"], ["python"], config=config, max_bullets=5)
    assert out[0] == "Only one"
    assert len(out) == 3  # padded with originals to keep the count stable
