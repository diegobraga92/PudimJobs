"""Tests for the rule-based CV tailoring engine."""

import json
import logging

from app.services.cv_tailor import (
    LLM_TARGET_PAGES,
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
        "skill_groups",
        "projects",
        "certifications",
        "languages",
    }
    # The deterministic variant authors no groups: the renderer groups the flat
    # list by taxonomy instead.
    assert structure["skill_groups"] == []
    restored = TailoredCV.from_structure(structure)
    assert restored.summary == tailored.summary
    assert restored.experience == tailored.experience
    assert restored.skills == tailored.skills
    assert restored.skill_groups == []
    assert restored.projects == tailored.projects


def test_tailored_cv_round_trips_llm_skill_groups():
    """The LLM variant's labelled categories survive serialisation (PDF rendering)."""
    tailored = tailor_cv(CV, ["python"])
    tailored.skill_groups = [("Backend", ["python", "fastapi"])]

    structure = tailored.as_structure()
    assert structure["skill_groups"] == [
        {"label": "Backend", "items": ["python", "fastapi"]}
    ]

    restored = TailoredCV.from_structure(structure)
    assert restored.skill_groups == [("Backend", ["python", "fastapi"])]


def test_from_structure_ignores_malformed_skill_groups():
    """A hand-edited or older artifact must never crash the PDF render."""
    structure = {
        "summary": "x",
        "skills": ["python"],
        "skill_groups": [
            "not-a-group",
            {"label": "", "items": ["python"]},
            {"label": "Backend"},  # no items
            {"label": "Languages", "items": []},
        ],
    }
    assert TailoredCV.from_structure(structure).skill_groups == []


def test_resolved_skill_groups_prefers_the_authored_categories():
    """One rule, shared by the PDF and the DOCX renderers."""
    tailored = tailor_cv(CV, ["python"])
    tailored.skill_groups = [("Backend", ["python", "fastapi"])]
    assert tailored.resolved_skill_groups() == [("Backend", ["python", "fastapi"])]


def test_resolved_skill_groups_falls_back_to_the_taxonomy():
    """No authored groups -> grouped by taxonomy, unknowns under "Additional"."""
    tailored = tailor_cv({**CV, "skills": ["python", "stakeholder management"]}, ["python"])
    assert tailored.skill_groups == []
    assert tailored.resolved_skill_groups() == [
        ("Languages", ["python"]),
        ("Additional", ["stakeholder management"]),
    ]


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
    from app.services import llm_client

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": {**CV, "summary": "Rewritten"}, "ats_self_score": 77})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

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


async def test_generate_tailored_cv_with_llm_keeps_the_authored_skill_groups(monkeypatch):
    """The model owns the skills section, so its groups must survive validation."""
    from app.services import llm_client

    groups = [{"label": "Backend", "items": ["python"]}]
    fake = _FakeLLMClient()
    fake.reply = json.dumps(
        {"cv": {**CV, "skill_groups": groups}, "ats_self_score": 70}
    )
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

    result = await generate_tailored_cv_with_llm(
        CV, jd_text="Python role", jd_skills=["python"], config=_enabled_llm_config()
    )

    assert result is not None
    structure, _ = result
    assert structure["skill_groups"] == groups


async def test_generate_tailored_cv_with_llm_rejects_an_invalid_structure(monkeypatch):
    from app.services import llm_client

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": {"experience": "not-a-list"}, "ats_self_score": 90})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

    assert (
        await generate_tailored_cv_with_llm(CV, jd_text="x", config=_enabled_llm_config()) is None
    )


async def test_generate_tailored_cv_with_llm_degrades_on_failure(monkeypatch):
    from app.services import llm_client

    class _BoomClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("llm down")

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: _BoomClient())

    assert (
        await generate_tailored_cv_with_llm(CV, jd_text="x", config=_enabled_llm_config()) is None
    )


# --- the AI variant's prompt: a tailored selection, not a restatement --------


async def test_generate_tailored_cv_with_llm_prompt_asks_for_a_two_page_tailored_cv(
    monkeypatch,
):
    """The AI variant is a *selection* for this job, not a restatement of the CV.

    The previous prompt asked the model to "rewrite the candidate's CV so it is
    maximally relevant" while also demanding that *every* fact be kept — leaving
    no way to shorten anything, so relevance was demonstrated by adding and
    splitting bullets and the artifact came back several pages long. These
    assertions pin the framing (a CV tailored for the job, the master CV as the
    reference) and the page budget.
    """
    from app.services import llm_client

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": CV, "ats_self_score": 50})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

    await generate_tailored_cv_with_llm(
        CV,
        jd_text="Python role",
        jd_title="Backend",
        jd_skills=["python"],
        config=_enabled_llm_config(),
    )

    system = fake.requests[0]["messages"][0]["content"]
    user = fake.requests[0]["messages"][1]["content"]
    assert "tailored CV for the target job" in system
    assert "source of truth" in system
    assert f"at most {LLM_TARGET_PAGES} pages" in system
    assert "MAY omit" in system  # omitting is what makes the budget reachable
    assert "NEVER invent" in system  # truthfulness is unchanged
    assert "skill_groups" in system  # the model owns the skills section...
    assert "never use an 'Other' group" in system  # ...and never names a bucket "Other"
    assert "Rewrite the candidate's CV" not in system
    assert "Master CV — the only source of truth" in user


async def test_generate_tailored_cv_with_llm_accepts_a_shorter_cv(monkeypatch):
    """Dropping a role is a valid answer, not a schema error (ADR 016).

    The prompt grants permission to omit, so the contract has to accept a
    structure with fewer entries than the master CV.
    """
    from app.services import llm_client

    shortened = {**CV, "experience": CV["experience"][:1], "projects": []}
    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": shortened, "ats_self_score": 60})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

    result = await generate_tailored_cv_with_llm(
        CV, jd_text="Python role", jd_skills=["python"], config=_enabled_llm_config()
    )

    assert result is not None
    structure, self_score = result
    assert len(structure["experience"]) == 1
    assert structure["projects"] == []
    assert self_score == 60


async def test_generate_tailored_cv_with_llm_trims_an_oversized_master_cv(
    monkeypatch, caplog
):
    """An oversized master CV is trimmed into *valid* JSON, never sliced raw.

    A byte-slice of the serialised JSON sent the model a syntactically broken
    reference while asking it to write the CV from that reference — a gap that
    gets filled from imagination. Whole entries are dropped instead.
    """
    from app.services import cv_tailor, llm_client

    fake = _FakeLLMClient()
    fake.reply = json.dumps({"cv": CV, "ats_self_score": 50})
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)
    monkeypatch.setattr(cv_tailor.settings, "tailor_llm_max_chars", 2_000)

    bulky = {
        **CV,
        "experience": [
            {
                "title": "Engineer",
                "company": f"Company {i}",
                "bullets": [f"Built python services number {i} on AWS"] * 3,
            }
            for i in range(40)
        ],
    }
    with caplog.at_level(logging.INFO, logger="app.services.cv_tailor"):
        result = await generate_tailored_cv_with_llm(
            bulky,
            jd_text="Python role",
            jd_skills=["python"],
            config=_enabled_llm_config(),
        )

    assert result is not None
    user = fake.requests[0]["messages"][1]["content"]
    reference = user.split("source of truth (JSON):\n", 1)[1]
    assert len(reference) <= 1_000  # half of the monkeypatched budget
    parsed = json.loads(reference)  # the reference always parses
    assert 0 < len(parsed["experience"]) < 40
    assert "llm_cv_input_truncated" in caplog.text


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
        # Read by `llm_client._rejects_json_mode` (retry-on-400 path).
        self.status_code = 200
        self.text = ""

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
    from app.services import llm_client

    config = LlmRuntimeConfig(
        enabled=True,
        api_key="sk-x",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    fake = _FakeLLMClient()
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

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
    from app.services import llm_client

    config = LlmRuntimeConfig(
        enabled=True,
        api_key="sk-x",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    fake = _FakeLLMClient()
    fake.reply = "1. Only one"
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)

    out = await enhance_with_llm(["a", "b", "c"], ["python"], config=config, max_bullets=5)
    assert out[0] == "Only one"
    assert len(out) == 3  # padded with originals to keep the count stable
