"""Localised CV section headings and export languages (ADR 024).

The headings a CV renders are *chrome*, not content: they are the same words on
every document in a given language, so they are translated from a fixed catalog
rather than asked of the LLM. Only the free text inside a section goes through
``cv_translator``, which keeps the headings deterministic and the translation
prompt focused on the parts a machine cannot guess.
"""

from dataclasses import dataclass

# The export languages the API offers, in the order the UI shows them. The first
# entry is the default and the only one that needs no LLM (ADR 024).
EXPORT_LANGUAGES: tuple[str, ...] = ("en", "pt-BR")
DEFAULT_LANGUAGE = EXPORT_LANGUAGES[0]

# How each language is named *to the LLM*. Asking for "pt-BR" gets an English
# answer far too often; asking for "Brazilian Portuguese" does not.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "pt-BR": "Brazilian Portuguese",
}


@dataclass(frozen=True)
class CVLabels:
    """The section headings one rendered CV uses."""

    locale: str
    summary: str
    experience: str
    skills: str
    projects: str
    education: str
    certifications: str
    languages: str
    # The open-ended end date of the current role, as the date range renders it.
    present: str


_EN = CVLabels(
    locale="en",
    summary="Summary",
    experience="Experience",
    skills="Skills",
    projects="Projects",
    education="Education",
    certifications="Certifications",
    languages="Languages",
    present="Present",
)

# Brazilian Portuguese headings. "Competências" over "Habilidades" for the skills
# section: it is the word BR recruiters and ATS keyword lists actually use, and it
# does not collide with the "Idiomas" section the way "Habilidades" would.
_PT_BR = CVLabels(
    locale="pt-BR",
    summary="Resumo",
    experience="Experiência",
    skills="Competências",
    projects="Projetos",
    education="Formação",
    certifications="Certificações",
    languages="Idiomas",
    present="Atual",
)

_CATALOG: dict[str, CVLabels] = {"en": _EN, "pt-BR": _PT_BR}

# English is the default everywhere a language is not threaded through (the DOM
# template's HTML ``lang`` attribute, an unlocalised internal render).
DEFAULT_LABELS = _EN


def is_export_language(language: str) -> bool:
    """True when ``language`` is one of the languages the API can export."""
    return language in _CATALOG


def labels_for(language: str) -> CVLabels:
    """The headings for ``language``; unknown codes fall back to English.

    Callers that accept user input validate with ``is_export_language`` first, so
    this fallback only covers internal callers that never pass a code through.
    """
    return _CATALOG.get(language, DEFAULT_LABELS)


def language_name(language: str) -> str:
    """The name of ``language`` as the translation prompt should say it."""
    return _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES[DEFAULT_LANGUAGE])
