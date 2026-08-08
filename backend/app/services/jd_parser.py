"""JD parsing with spaCy NER + regex skill extraction."""

import re
from dataclasses import dataclass, field

import spacy

from app.services.skill_matcher import extract_skills

_nlp = None

_YEARS_RE = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?experience",
    re.IGNORECASE,
)
_EDUCATION_PATTERNS: dict[str, re.Pattern] = {
    "phd": re.compile(r"\b(ph\.?\s*d\.?|doctorate)\b", re.IGNORECASE),
    "master": re.compile(r"\b(m\.?\s*s\.?|master'?s|masters)\b", re.IGNORECASE),
    "bachelor": re.compile(
        r"\b(b\.?\s*s\.?|b\.?\s*a\.?|bachelor'?s|bachelors|bachelor)\b", re.IGNORECASE
    ),
}


@dataclass
class ParsedJD:
    """Structured requirements extracted from a job description."""

    skills: list[str] = field(default_factory=list)
    years_experience: int | None = None
    education_level: str | None = None
    keywords: list[str] = field(default_factory=list)


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError as exc:  # pragma: no cover - env setup
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' is not installed. "
                "Run: python -m spacy download en_core_web_sm"
            ) from exc
    return _nlp


def _extract_years(text: str) -> int | None:
    match = _YEARS_RE.search(text)
    return int(match.group(1)) if match else None


def _extract_education(text: str) -> str | None:
    for level, pattern in _EDUCATION_PATTERNS.items():
        if pattern.search(text):
            return level
    return None


def _extract_keywords(doc) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for chunk in doc.noun_chunks:
        token = chunk.root
        candidate = chunk.text.lower()
        if (
            len(candidate) >= 4
            and not token.is_stop
            and (candidate.isalnum() or " " in candidate)
            and candidate not in seen
        ):
            seen.add(candidate)
            keywords.append(candidate)
        if len(keywords) >= 15:
            break
    return keywords[:15]


def parse_jd(text: str | None) -> ParsedJD:
    """Parse a job description into structured requirements."""
    if not text or not text.strip():
        return ParsedJD()
    nlp = _get_nlp()
    doc = nlp(text[:5000])  # cap input for parsing speed
    return ParsedJD(
        skills=extract_skills(text),
        years_experience=_extract_years(text),
        education_level=_extract_education(text),
        keywords=_extract_keywords(doc),
    )


def parsed_jd_to_dict(parsed: ParsedJD) -> dict:
    return {
        "skills": parsed.skills,
        "years_experience": parsed.years_experience,
        "education_level": parsed.education_level,
        "keywords": parsed.keywords,
    }
