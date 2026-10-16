"""Optional LLM translation of a CV structure, for a localised export (ADR 024).

Translating a CV is a *rewrite with a hard constraint*: the recruiter reads the
same facts in another language. The structure splits in two and the prompt states
the split: the **data** — skill entries, people, employers, institutions, dates,
numbers, links — is language-neutral and survives verbatim, while the **prose and
the CV's own labels** — summary, bullets, project descriptions, job titles,
degrees and skill-group labels — is translated. Section headings are not the
model's business: they come from ``cv_labels``.

One part of the structure would otherwise escape the model entirely. A CV that
never went through the LLM variant stores no ``skill_groups``; the renderers then
group its flat ``skills`` list by taxonomy, and those labels ("Languages",
"Tools") are English literals the model never sees — a PT-BR CV printed
``Tools:`` under a ``Competências`` heading. Grouping *before* the call turns
those labels into ordinary text to translate, which is why the reply is validated
against the enriched structure and never against the bare one.

The response is validated back through ``CVStructure``, so a translation that
drops or invents a field is discarded rather than rendered.

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
from app.services.skill_matcher import group_skills

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


def _with_taxonomy_skill_groups(structure: dict) -> dict:
    """Return ``structure`` with the taxonomy's skill groups filled in, if it has none.

    A CV that stores no ``skill_groups`` renders its skills grouped by the
    taxonomy (both renderers call ``group_skills`` for it), and those group labels
    are English literals that would never reach the model — the reason a PT-BR CV
    could print ``Tools:`` under a ``Competências`` heading. Grouping here, before
    the call, hands the labels over as ordinary text to translate.

    The filled structure is a *copy*: ``_localized_structure`` is also handed the
    ``structured_json`` of a stored artifact, and mutating it would write English
    group labels into the candidate's CV. A CV that already carries groups (the
    LLM variant) is passed through untouched — those labels are its own.
    """
    if structure.get("skill_groups"):
        return structure
    grouped = group_skills(list(structure.get("skills") or []))
    if not grouped:
        return structure
    return {
        **structure,
        "skill_groups": [{"label": label, "items": items} for label, items in grouped],
    }


def _system_prompt(target_language: str) -> str:
    return (
        f"You are a professional CV translator working into {target_language}. You receive a "
        "candidate's resume as a JSON object and return the same JSON object translated.\n"
        "Rules:\n"
        "1. Keep the JSON keys and the structure exactly as given: every array keeps its "
        "length and order, and every string field stays a string.\n"
        "2. TRANSLATE the prose and the CV's own headings: the summary; experience bullet "
        'points; project descriptions; the words of a job title ("Senior Software Engineer" '
        '-> "Engenheiro de Software Sênior"); a degree and its field of study ("Masters in '
        'Computer Science" -> "Mestrado em Ciência da Computação"); and the `label` of every '
        '`skill_groups` entry ("Tools" -> "Ferramentas").\n'
        f"3. Translate the free-text values of the `languages` field into {target_language} "
        '(e.g. "English (fluent)" -> the equivalent wording), because it is a list of spoken '
        "languages, not a list of technologies.\n"
        "4. NEVER translate or alter the CV's DATA: the skill entries themselves — the flat "
        "`skills` list and every `skill_groups[].items` entry — including programming "
        "languages and tool names (Python, FastAPI, AWS, Docker), in the candidate's own "
        "standard spelling because a machine matches them; people's names; employers; "
        "institutions; project and product names; emails; phone numbers; URLs; dates and "
        "numbers. A skill-group *label* is chrome and is translated; the skills under it are "
        "data and are not.\n"
        "5. Keep any proper noun inside a translated field as it is: translating a company, a "
        "product or an acronym is wrong even when the rest of the field is translated.\n"
        "6. Never leave a section that had content in the input empty in your answer: keep "
        "both skills fields populated, and every `skill_groups` entry you were given.\n"
        "7. Never invent, add, remove, merge or split anything. A translation that changes the "
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

    source = _with_taxonomy_skill_groups(structure)
    user = (
        f"Translate this resume into {language_name(target_language)}. "
        "Return the JSON object only.\n\n"
        f"{json.dumps(source, ensure_ascii=False)}"
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
    # `source`, not `structure`: the taxonomy group labels injected for the model
    # are content too, so a reply that flattens that section is a failed export.
    if _drops_content(source, translated):
        logger.warning("LLM CV translation dropped CV content; failing the export")
        return None
    return translated
