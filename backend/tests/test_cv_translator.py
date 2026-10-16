"""Tests for on-demand CV translation and localised headings (ADR 024)."""

from dataclasses import replace

from app.services import cv_translator
from app.services.cv_labels import (
    DEFAULT_LANGUAGE,
    EXPORT_LANGUAGES,
    is_export_language,
    labels_for,
    language_name,
)
from app.services.llm_config import LlmRuntimeConfig

STRUCTURE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+55 11 91234-5678",
    "location": "Sao Paulo, Brazil",
    "links": ["https://github.com/janedoe"],
    "summary": "Backend engineer with FastAPI experience",
    "experience": [
        {
            "company": "Acme",
            "title": "Python Developer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": ["Built async pipelines"],
        }
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science", "year": "2015"}],
    "skills": ["python", "fastapi"],
    "skill_groups": [],
    "projects": [{"name": "PudimJobs", "description": "Job tracker", "link": None}],
    "certifications": ["AWS Solutions Architect"],
    "languages": ["English (fluent)"],
}

TRANSLATED = {
    **STRUCTURE,
    "summary": "Engenheira backend com experiência em FastAPI",
    "experience": [
        {
            "company": "Acme",
            "title": "Python Developer",
            "start_date": "2020-01",
            "end_date": None,
            "bullets": ["Construiu pipelines assíncronos"],
        }
    ],
    "languages": ["Inglês (fluente)"],
}

ENABLED = LlmRuntimeConfig(
    enabled=True, api_key="sk-x", base_url="http://llm", model="gpt-4o-mini"
)


def _reply(monkeypatch, payload):
    """Point the service's ``chat_json`` at a canned payload, recording the call."""
    calls: dict = {}

    async def _fake_chat_json(config, **kwargs):
        calls.update(kwargs)
        return payload

    monkeypatch.setattr(cv_translator, "chat_json", _fake_chat_json)
    return calls


async def test_translate_returns_the_validated_structure(monkeypatch):
    calls = _reply(monkeypatch, TRANSLATED)

    translated = await cv_translator.translate_cv_structure(
        STRUCTURE, target_language="pt-BR", config=ENABLED
    )

    assert translated["summary"] == TRANSLATED["summary"]
    # The non-translatable fields survive the round trip through CVStructure.
    assert translated["experience"][0]["company"] == "Acme"
    assert translated["email"] == "jane@example.com"
    assert calls["label"] == "LLM CV translation"
    assert "Brazilian Portuguese" in calls["system"]
    assert "JSON" in calls["user"]


async def test_translate_prompt_names_the_language_and_forbids_invention(monkeypatch):
    calls = _reply(monkeypatch, TRANSLATED)

    await cv_translator.translate_cv_structure(STRUCTURE, target_language="pt-BR", config=ENABLED)

    system = calls["system"]
    assert "professional CV translator" in system
    assert "NEVER translate or alter" in system
    assert "Never invent" in system


async def test_translate_is_skipped_when_the_llm_is_unusable(monkeypatch):
    """No API call at all without an enabled config *and* a key."""
    calls = _reply(monkeypatch, TRANSLATED)

    disabled = replace(ENABLED, enabled=False)
    keyless = replace(ENABLED, api_key="")
    for config in (disabled, keyless):
        assert (
            await cv_translator.translate_cv_structure(
                STRUCTURE, target_language="pt-BR", config=config
            )
            is None
        )
    assert calls == {}


async def test_translate_fails_when_the_llm_returns_nothing(monkeypatch):
    _reply(monkeypatch, None)

    assert (
        await cv_translator.translate_cv_structure(
            STRUCTURE, target_language="pt-BR", config=ENABLED
        )
        is None
    )


async def test_translate_discards_an_invalid_structure(monkeypatch):
    _reply(monkeypatch, {**TRANSLATED, "skills": [123]})

    assert (
        await cv_translator.translate_cv_structure(
            STRUCTURE, target_language="pt-BR", config=ENABLED
        )
        is None
    )


async def test_translate_discards_a_reply_that_drops_a_section(monkeypatch):
    """`{}` validates against CVStructure — it must still be rejected."""
    _reply(monkeypatch, {})

    assert (
        await cv_translator.translate_cv_structure(
            STRUCTURE, target_language="pt-BR", config=ENABLED
        )
        is None
    )


# --- Heading catalog --------------------------------------------------------


def test_export_languages_are_exactly_english_and_brazilian_portuguese():
    assert EXPORT_LANGUAGES == ("en", "pt-BR")
    assert DEFAULT_LANGUAGE == "en"
    assert is_export_language("pt-BR")
    assert not is_export_language("pt")
    assert not is_export_language("xx")


def test_labels_are_localised_and_unknown_codes_fall_back_to_english():
    pt_br = labels_for("pt-BR")
    assert (pt_br.summary, pt_br.experience, pt_br.skills) == (
        "Resumo",
        "Experiência",
        "Competências",
    )
    assert (pt_br.education, pt_br.certifications, pt_br.languages) == (
        "Formação",
        "Certificações",
        "Idiomas",
    )
    assert pt_br.present == "Atual"
    assert pt_br.locale == "pt-BR"

    assert labels_for("en").summary == "Summary"
    # Internal callers never pass a bad code, so the fallback is English.
    assert labels_for("de").summary == "Summary"
    assert labels_for("de").locale == "en"


def test_language_name_is_what_the_prompt_should_say():
    assert language_name("pt-BR") == "Brazilian Portuguese"
    assert language_name("en") == "English"
    assert language_name("de") == "English"
