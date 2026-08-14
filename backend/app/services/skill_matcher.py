"""Skill taxonomy matching utilities.

``extract_skills`` finds taxonomy skills (and their aliases — e.g. "k8s",
"react.js") in free text; ``match_skills`` compares JD requirements against a
CV's skill list, canonicalizing aliases on both sides.
"""

import json
import re
from pathlib import Path

_TAXONOMY_PATH = Path(__file__).parent.parent / "data" / "skills_taxonomy.json"
_TAXONOMY: dict[str, list[str]] = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))

# The taxonomy's "aliases" key maps canonical skills to common synonyms; it is
# not itself a skill group.
_SKILL_GROUPS: dict[str, list[str]] = {
    name: skills for name, skills in _TAXONOMY.items() if name != "aliases"
}
_ALIASES: dict[str, list[str]] = _TAXONOMY.get("aliases", {})

# Exclude too-short tokens (e.g. "c", "r", "go") to avoid false positives.
ALL_SKILLS: list[str] = [
    skill for group in _SKILL_GROUPS.values() for skill in group if len(skill) >= 3
]


def _skill_pattern(text: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(text) + r"(?![a-z0-9])", re.IGNORECASE)


# One pattern per canonical skill *and* per alias (canonical wins the match).
# Aliases shorter than 3 chars ("go", "ml", "ts") are skipped like the
# too-short-token rule above, to keep false positives out.
_PATTERNS: list[tuple[str, re.Pattern]] = sorted(
    (
        (canonical, _skill_pattern(text))
        for canonical in ALL_SKILLS
        for text in [canonical, *(_ALIASES.get(canonical, []))]
        if len(text) >= 3
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

_ALIAS_LOOKUP: dict[str, str] = {
    canonical: canonical for canonical in ALL_SKILLS
}
for _canonical, _aliases in _ALIASES.items():
    _ALIAS_LOOKUP[_canonical] = _canonical
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias.lower()] = _canonical


def canonical_skill(skill: str) -> str:
    """Map a skill (or one of its aliases) to its canonical taxonomy name."""
    stripped = skill.strip()
    return _ALIAS_LOOKUP.get(stripped.lower(), stripped)


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
    for group in _SKILL_GROUPS.values():
        for skill in group:
            if skill in found and skill not in seen:
                ordered.append(skill)
                seen.add(skill)
    return ordered


def match_skills(jd_skills: list[str], cv_skills: list[str]) -> dict:
    """Compare JD-required skills against the CV's skills.

    Skills are canonicalized via the taxonomy's alias table on both sides
    ("k8s" == "kubernetes"). Returns matched/missing lists and a relevance
    score in [0, 1].
    """
    jd_set = {canonical_skill(s).lower() for s in jd_skills}
    cv_set = {canonical_skill(s).lower() for s in cv_skills}
    matched = [s for s in jd_skills if canonical_skill(s).lower() in cv_set]
    missing = [s for s in jd_skills if canonical_skill(s).lower() not in cv_set]
    relevance = len(matched) / len(jd_set) if jd_set else 0.0
    return {"matched": matched, "missing": missing, "relevance": relevance}
