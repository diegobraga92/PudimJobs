"""Rule-based CV tailoring engine.

Given a job's parsed requirements and the master CV, selects the most relevant
experience/project blocks, reorders them, and surfaces a tailored skills list.
Optionally rephrases selected bullet points with an LLM (feature-flagged).
"""

import logging
import re
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.services.llm_config import LlmRuntimeConfig
from app.services.skill_matcher import match_skills

logger = logging.getLogger(__name__)

_SKILL_RE_CACHE: dict[str, re.Pattern] = {}


def _contains_skill(text: str, skill: str) -> bool:
    pattern = _SKILL_RE_CACHE.get(skill)
    if pattern is None:
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", re.IGNORECASE
        )
        _SKILL_RE_CACHE[skill] = pattern
    return bool(pattern.search(text))


@dataclass
class TailoredCV:
    summary: str
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    relevance: float = 0.0


def _block_text(block: dict) -> str:
    parts = [block.get("title", ""), block.get("company", "")]
    parts.extend(block.get("bullets", []))
    return " ".join(parts)


def _annotations_for(annotations: dict | None, section: str, index: int) -> list[str]:
    if not annotations:
        return []
    items = annotations.get(section) or []
    if index < len(items) and isinstance(items[index], list):
        return [str(tag).lower() for tag in items[index]]
    return []


def _score_block(
    block: dict, jd_skills: list[str], annotations: dict | None, index: int
) -> list[str]:
    text = _block_text(block)
    matched = [s for s in jd_skills if _contains_skill(text, s)]
    for tag in _annotations_for(annotations, "experience", index):
        for skill in jd_skills:
            if skill.lower() == tag and skill not in matched:
                matched.append(skill)
    return matched


def _order_blocks_with_scores(
    blocks: list[dict], jd_skills: list[str], annotations: dict | None
) -> list[tuple[int, int, dict]]:
    """Score blocks against JD skills; return ``(score, original_index, block)``."""
    scored = [
        (len(_score_block(block, jd_skills, annotations, i)), i, block)
        for i, block in enumerate(blocks)
    ]
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return scored


def _tailored_skills(cv_skills: list[str], matched: list[str]) -> list[str]:
    matched_lower = {s.lower() for s in matched}
    remaining = [s for s in cv_skills if s.lower() not in matched_lower]
    return list(dict.fromkeys([*matched, *remaining]))


def tailor_cv(
    cv_structure: dict,
    jd_skills: list[str],
    *,
    annotations: dict | None = None,
    drop_irrelevant: bool = True,
) -> TailoredCV:
    """Tailor a CV structure to a JD's required skills."""
    cv_skills = [str(s) for s in cv_structure.get("skills", [])]
    matching = match_skills(jd_skills, cv_skills)

    exp_scored = _order_blocks_with_scores(
        cv_structure.get("experience", []), jd_skills, annotations
    )
    if drop_irrelevant:
        exp_scored = [entry for entry in exp_scored if entry[0] > 0]
    experience = [block for _, _, block in exp_scored]

    proj_scored = _order_blocks_with_scores(
        cv_structure.get("projects", []), jd_skills, annotations
    )
    if drop_irrelevant:
        proj_scored = [entry for entry in proj_scored if entry[0] > 0]
    projects = [block for _, _, block in proj_scored]

    return TailoredCV(
        summary=cv_structure.get("summary", ""),
        experience=experience,
        education=cv_structure.get("education", []),
        skills=_tailored_skills(cv_skills, matching["matched"]),
        projects=projects,
        matched_skills=matching["matched"],
        missing_skills=matching["missing"],
        relevance=matching["relevance"],
    )


async def enhance_with_llm(
    bullets: list[str],
    jd_skills: list[str],
    *,
    config: LlmRuntimeConfig | None = None,
) -> list[str]:
    """Rephrase bullets using JD language via an OpenAI-compatible API.

    Feature-flagged: returns bullets unchanged unless the effective config has
    ``enabled`` set and an API key configured. Any API failure degrades
    gracefully to the original bullets.
    """
    if config is None:
        config = LlmRuntimeConfig(
            enabled=settings.tailoring_llm_enabled,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    if not config.enabled or not config.api_key:
        return bullets
    prompt = (
        "Rephrase the following CV bullet points to emphasize these skills: "
        f"{', '.join(jd_skills)}. Keep them concise (max 2 lines each), first "
        "person past tense, no fabrication. Return ONLY a numbered list.\n\n"
        + "\n".join(f"{i + 1}. {b}" for i, b in enumerate(bullets))
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.4,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return [
            line.split(". ", 1)[1] if ". " in line else line
            for line in content.splitlines()
            if line.strip()
        ][: len(bullets)]
    except Exception:
        logger.warning("LLM enhancement failed; using original bullets", exc_info=True)
        return bullets
