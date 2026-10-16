"""Optional LLM translation of a CV structure, for a localised export (ADR 024).

Translating a CV is a *rewrite with a hard constraint*: the recruiter reads the
same facts in another language. The prompt therefore states the constraint the
way ``cv_tailor``'s rewrite does — every employer, title, date, number, degree,
link and technology name survives verbatim — and the response is validated back
through ``CVStructure``, so a translation that drops or invents a field is
discarded rather than rendered.

This runs on demand, at export time, and nothing is persisted: the same choice
DOCX export made (ADR 017). A stored `pt-BR` artifact would need a migration and
would go stale the moment the source CV is edited.
"""

import json
import logging

from pydantic import ValidationError

from app.schemas.master_cv import CVStructure
from app.services.cv_labels import language_name
from app.services.cv_schema import CV_JSON_SCHEMA
from app.services.llm_client import chat_json
from app.services.llm_config import LlmRuntimeConfig, llm_variant_wanted

logger = logging.getLogger(__name__)

# A full CV JSON is the same order of magnitude as the tailor rewrite, which asks
# for 4000.
_MAX_TOKENS = 4000
# Translation is deterministic work; sampling adds nothing but drift.
_TEMPERATURE = 0.1
_TIMEOUT_SECONDS = 60

# Every field of the structure, so a reply that quietly emptied one is caught.
_CONTENT_FIELDS = (
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
)


def _drops_content(original: dict, translated: dict) -> bool:
    """True when ``translated`` emptied a field ``original`` had filled.

    ``CVStructure`` gives every field a default, so ``{}`` validates happily and
    would render a blank CV — a *valid* reply is not necessarily a useful one.
    Nothing in a translation legitimately removes a section, so any field that
    went from filled to empty is a failed translation, not a terse one.
    """
    return any(original.get(field) and not translated.get(field) for field in _CONTENT_FIELDS)


def _system_prompt(target_language: str) -> str:
    return (
        f"You are a professional CV translator working into {target_language}. You receive a "
        "candidate's resume as a JSON object and return the same JSON object translated.\n"
        "Rules:\n"
        "1. Keep the JSON keys and the structure exactly as given: every array keeps its "
        "length and order, and every string field stays a string.\n"
        "2. Translate all human-readable text: the summary, experience bullet points, "
        "project descriptions, degree names, certifications and the labels in `skill_groups`.\n"
        f"3. Translate the free-text values of the `languages` field into {target_language} "
        '(e.g. "English (fluent)" -> the equivalent wording), because it is a list of spoken '
        "languages, not a list of technologies.\n"
        "4. Keep BOTH skills fields populated, translated the same way: the flat `skills` list "
        "and the `skill_groups` entries it is grouped by. Never leave a section that had "
        "content in the input empty in your answer.\n"
        "5. NEVER translate or alter: people's names, employers, institutions, product names, "
        "job titles' proper nouns, technology and tool names (Python, FastAPI, AWS, Docker), "
        "emails, phone numbers, URLs, dates and numbers. Keep the candidate's own standard "
        "spelling of a technology: a machine matches it.\n"
        "6. Never invent, add, remove, merge or split anything. A translation that changes the "
        "candidate's history is a failure, not a rewrite.\n"
        f"Return ONLY a JSON object of this shape: {CV_JSON_SCHEMA}"
    )


async def translate_cv_structure(
    structure: dict,
    *,
    target_language: str,
    config: LlmRuntimeConfig,
) -> dict | None:
    """Translate ``structure`` into ``target_language``; ``None`` on any failure.

    Uses the shared LLM client, so transport errors, an empty completion and an
    unparseable reply are already logged there. The caller degrades to an error
    response — a half-translated CV is worse than saying the export could not be
    produced.
    """
    if not llm_variant_wanted(config):
        # The caller gates on this too; the guard keeps the service honest when
        # reused (an LLM call needs an enabled config *and* a key).
        return None

    user = (
        f"Translate this resume into {language_name(target_language)}. "
        "Return the JSON object only.\n\n"
        f"{json.dumps(structure, ensure_ascii=False)}"
    )
    payload = await chat_json(
        config,
        system=_system_prompt(language_name(target_language)),
        user=user,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        timeout=_TIMEOUT_SECONDS,
        label="LLM CV translation",
    )
    if payload is None:
        return None
    try:
        translated = CVStructure.model_validate(payload).model_dump()
    except ValidationError:
        logger.warning(
            "LLM CV translation returned an invalid structure; failing the export", exc_info=True
        )
        return None
    if _drops_content(structure, translated):
        logger.warning("LLM CV translation dropped CV content; failing the export")
        return None
    return translated
