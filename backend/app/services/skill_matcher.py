"""Skill taxonomy matching utilities."""

import json
import re
from pathlib import Path

_TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "skills_taxonomy.json"
_TAXONOMY: dict[str, list[str]] = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))

# Exclude too-short tokens (e.g. "c", "r", "go") to avoid false positives.
ALL_SKILLS: list[str] = [
    skill for group in _TAXONOMY.values() for skill in group if len(skill) >= 3
]

_PATTERNS: list[tuple[str, re.Pattern]] = sorted(
    (
        (skill, re.compile(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", re.IGNORECASE))
        for skill in ALL_SKILLS
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def extract_skills(text: str) -> list[str]:
    """Return the taxonomy skills found in ``text`` (taxonomy order)."""
    if not text:
        return []
    found: set[str] = set()
    for skill, pattern in _PATTERNS:
        if skill in found:
            continue
        if pattern.search(text):
            found.add(skill)

    ordered: list[str] = []
    seen: set[str] = set()
    for group in _TAXONOMY.values():
        for skill in group:
            if skill in found and skill not in seen:
                ordered.append(skill)
                seen.add(skill)
    return ordered


def match_skills(jd_skills: list[str], cv_skills: list[str]) -> dict:
    """Compare JD-required skills against the CV's skills.

    Returns matched/missing lists and a relevance score in [0, 1].
    """
    jd_set = {s.lower() for s in jd_skills}
    cv_set = {s.lower() for s in cv_skills}
    matched = [s for s in jd_skills if s.lower() in cv_set]
    missing = [s for s in jd_skills if s.lower() not in cv_set]
    relevance = len(matched) / len(jd_set) if jd_set else 0.0
    return {"matched": matched, "missing": missing, "relevance": relevance}
