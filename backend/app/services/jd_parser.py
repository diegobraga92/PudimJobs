"""JD parsing with spaCy NER + regex skill extraction.

spaCy is only needed for keyword extraction; when the model is unavailable the
parser degrades gracefully (skills, years and education are pure regex and
taxonomy based).
"""

import re
from dataclasses import dataclass, field

import spacy

from app.services.skill_matcher import extract_skills

_nlp = None

_YEARS_EXPERIENCE_RE = re.compile(
    r"(\d{1,2})(?:\s*[-\u2013]\s*(\d{1,2}))?\s*\+?\s*(?:years?|yrs?)\s*"
    r"(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience\b",
    re.IGNORECASE,
)
_YEARS_ANY_RE = re.compile(
    r"(?:at\s*least\s*|minimum(?:\s+of)?\s*|min\.?\s*)?"
    r"(\d{1,2})(?:\s*[-\u2013]\s*(\d{1,2}))?\s*\+?\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_SENIORITY_PATTERNS: tuple[tuple[re.Pattern, int], ...] = (
    (re.compile(r"\bsenior\b", re.IGNORECASE), 5),
    (re.compile(r"\bmid(?:[- ]level)?\b", re.IGNORECASE), 3),
    (re.compile(r"\bjunior\b", re.IGNORECASE), 1),
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
        except OSError:
            # Model not installed: only keyword extraction is degraded.
            _nlp = False
    return _nlp or None


def _extract_years(text: str) -> int | None:
    """Best-effort years-of-experience extraction.

    Prefers an explicit ``N years (of) experience`` statement, then a bare
    ``N+ years`` / ``at least N years`` pattern, and finally conservative
    seniority hints (senior/mid/junior) when no number is stated. Ranges
    ("3-5 years") resolve to the upper bound.
    """
    for pattern in (_YEARS_EXPERIENCE_RE, _YEARS_ANY_RE):
        match = pattern.search(text)
        if match:
            lower = int(match.group(1))
            return max(lower, int(match.group(2))) if match.group(2) else lower
    for pattern, years in _SENIORITY_PATTERNS:
        if pattern.search(text):
            return years
    return None


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
    keywords: list[str] = []
    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text[:5000])  # cap input for parsing speed
        keywords = _extract_keywords(doc)
    return ParsedJD(
        skills=extract_skills(text),
        years_experience=_extract_years(text),
        education_level=_extract_education(text),
        keywords=keywords,
    )


def parsed_jd_to_dict(parsed: ParsedJD) -> dict:
    return {
        "skills": parsed.skills,
        "years_experience": parsed.years_experience,
        "education_level": parsed.education_level,
        "keywords": parsed.keywords,
    }
