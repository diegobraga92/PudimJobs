"""Normalization helpers for the data quality pipeline.

Company/title normalization uses curated mapping files; skill normalization
uses the skill taxonomy's alias table. Values fall back to the original when
no mapping applies.
"""

import json
import re
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"
_COMPANY_MAP: dict[str, str] = json.loads(
    (_DATA_DIR / "company_map.json").read_text(encoding="utf-8")
)
_TITLE_MAP: dict[str, str] = json.loads((_DATA_DIR / "title_map.json").read_text(encoding="utf-8"))
_TAXONOMY: dict = json.loads((_DATA_DIR / "skills_taxonomy.json").read_text(encoding="utf-8"))
_SKILL_ALIASES: dict[str, list[str]] = _TAXONOMY.get("aliases", {})

_SUFFIX_PATTERN = re.compile(r"\b(inc|llc|ltd|corp|corporation|gmbh|sa|sarl)\b\.?$", re.IGNORECASE)


def normalize_company(company: str | None) -> str:
    """Map company variants to a canonical name; strip legal suffixes otherwise."""
    if not company:
        return ""
    key = company.strip().lower()
    if key in _COMPANY_MAP:
        return _COMPANY_MAP[key]
    cleaned = _SUFFIX_PATTERN.sub("", company.strip()).strip()
    return cleaned or company.strip()


def normalize_title(title: str | None) -> str:
    """Map common title abbreviations/variants to canonical titles."""
    if not title:
        return ""
    key = title.strip().lower()
    if key in _TITLE_MAP:
        return _TITLE_MAP[key]
    return title.strip()


def normalize_skill(skill: str | None) -> str:
    """Map a skill to its canonical taxonomy name via the alias table."""
    if not skill:
        return ""
    lower = skill.strip().lower()
    for canonical, aliases in _SKILL_ALIASES.items():
        if lower == canonical or lower in [a.lower() for a in aliases]:
            return canonical
    return skill.strip()


def normalize_skills(skills: list[str]) -> list[str]:
    return [normalize_skill(skill) for skill in skills]
