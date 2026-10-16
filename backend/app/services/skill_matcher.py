"""Skill taxonomy matching utilities."""

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

_ALIAS_LOOKUP: dict[str, str] = {canonical: canonical for canonical in ALL_SKILLS}
for _canonical, _aliases in _ALIASES.items():
    _ALIAS_LOOKUP[_canonical] = _canonical
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias.lower()] = _canonical

# Same patterns again, longest name first, for finding the known skill *inside* an
# entry a CV wrote as one token ("JavaScript/TypeScript", "Google BigQuery").
# `resolve_skills` walks them in length order so the longest match wins
# ("sql server" before "sql").
_RESOLVE_PATTERNS: list[tuple[str, re.Pattern]] = sorted(
    ((name, _skill_pattern(name)) for name in _ALIAS_LOOKUP if len(name) >= 3),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# A compound entry joins two skills the same way the parser's label splitter does.
_COMPOUND_SPLIT_RE = re.compile(r"\s*[/&]\s*")


# Human-readable labels for the taxonomy groups, used when a CV renders its
# skills grouped by category (the JSON keys are snake_case).
GROUP_LABELS: dict[str, str] = {
    "languages": "Languages",
    "frameworks": "Frameworks",
    "databases": "Databases",
    "cloud_devops": "Cloud & DevOps",
    "concepts": "Concepts",
    "tools": "Tools",
}
# Bucket for skills the taxonomy does not know (e.g. "communication"). It is
# labelled "Additional" rather than "Other": a literal "Other:" heading on a CV
# reads like a junk drawer to a hiring manager.
ADDITIONAL_GROUP = "Additional"

# Reverse index: canonical skill (lower-cased) -> its taxonomy group.
_SKILL_TO_GROUP: dict[str, str] = {
    skill.lower(): group for group, skills in _SKILL_GROUPS.items() for skill in skills
}


def canonical_skill(skill: str) -> str:
    """Map a skill (or one of its aliases) to its canonical taxonomy name."""
    stripped = skill.strip()
    return _ALIAS_LOOKUP.get(stripped.lower(), stripped)


def resolve_skills(entry: str) -> list[str]:
    """Canonical skills named by a single CV entry, which may be a compound.

    A CV writes one skill per token most of the time ("Kubernetes"), but the
    taxonomy has to survive the other spellings too: "JavaScript/TypeScript" names
    two skills, "Protobuf/gRPC" two more, and "Google BigQuery" one it happens to
    spell with a vendor prefix. Resolution walks three rungs and returns the entry
    unchanged when none of them apply, so an unknown skill never silently
    disappears from the owner's CV:

    1. the entry is already a canonical skill or a known alias;
    2. every ``/``- or ``&``-separated part is a known skill (a compound);
    3. the longest known skill name appears in the entry as a whole word.
    """
    stripped = entry.strip()
    if not stripped:
        return []
    exact = canonical_skill(stripped)
    if exact.lower() in _SKILL_TO_GROUP:
        return [exact]
    parts = [part.strip() for part in _COMPOUND_SPLIT_RE.split(stripped) if part.strip()]
    if len(parts) > 1:
        resolved = [canonical_skill(part) for part in parts]
        if all(part.lower() in _SKILL_TO_GROUP for part in resolved):
            return resolved
    for name, pattern in _RESOLVE_PATTERNS:
        if pattern.search(stripped):
            canonical = canonical_skill(name)
            if canonical.lower() in _SKILL_TO_GROUP:
                return [canonical]
    return [stripped]


def group_skills(skills: list[str]) -> list[tuple[str, list[str]]]:
    """Group a flat skill list into labelled categories for a CV section.

    An entry lands in the group its resolved skills agree on. A compound whose
    parts disagree ("AWS/PostgreSQL") says nothing useful about where it belongs,
    so it joins the unknown skills rather than being placed on a coin flip.
    Grouping never rewrites an entry: it only decides which line draws it.
    """
    buckets: dict[str, list[str]] = {}
    other: list[str] = []
    seen: set[frozenset[str]] = set()

    for raw in skills:
        if not isinstance(raw, str):
            continue
        display = raw.strip()
        if not display:
            continue
        resolved = resolve_skills(display)
        # "k8s" and "kubernetes" are the same skill, so an entry repeating a set an
        # earlier one already resolved to is dropped. A compound and one of its
        # parts are deliberately *not* treated as repeats: the CV's own spelling is
        # never rewritten, and dropping half of what its owner wrote is worse than
        # one redundant mention.
        key = frozenset(skill.lower() for skill in resolved)
        if key in seen:
            continue
        seen.add(key)
        groups = {
            _SKILL_TO_GROUP[skill.lower()]
            for skill in resolved
            if skill.lower() in _SKILL_TO_GROUP
        }
        if len(groups) == 1:
            buckets.setdefault(groups.pop(), []).append(display)
        else:
            other.append(display)

    grouped = [
        (GROUP_LABELS.get(group, group.replace("_", " ").title()), buckets[group])
        for group in _SKILL_GROUPS
        if buckets.get(group)
    ]
    if other:
        grouped.append((ADDITIONAL_GROUP, other))
    return grouped


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
    """Compare JD-required skills against the CV's skills."""
    jd_set = {canonical_skill(s).lower() for s in jd_skills}
    # `cv_set` is a superset of the CV's own spellings: a JD asking for
    # "TypeScript" has to be satisfied by a CV entry that says
    # "JavaScript/TypeScript", and one asking for "JavaScript" still is.
    cv_set = {canonical_skill(s).lower() for s in cv_skills}
    for entry in cv_skills:
        cv_set.update(resolved.lower() for resolved in resolve_skills(entry))
    matched = [s for s in jd_skills if canonical_skill(s).lower() in cv_set]
    missing = [s for s in jd_skills if canonical_skill(s).lower() not in cv_set]
    relevance = len(matched) / len(jd_set) if jd_set else 0.0
    return {"matched": matched, "missing": missing, "relevance": relevance}
