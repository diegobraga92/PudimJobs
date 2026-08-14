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

# When no CV block matches the JD skills, keep this many top-scored blocks so
# the tailored CV is never empty (a "no match" is signalled via `relevance`).
_FALLBACK_TOP_N = 3

_NUMBERED_LINE_RE = re.compile(r"^\d+[.)]\s*(.+)$")


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
        matched_blocks = [entry for entry in exp_scored if entry[0] > 0]
        exp_scored = matched_blocks or exp_scored[:_FALLBACK_TOP_N]
    experience = [block for _, _, block in exp_scored]

    proj_scored = _order_blocks_with_scores(
        cv_structure.get("projects", []), jd_skills, annotations
    )
    if drop_irrelevant:
        matched_blocks = [entry for entry in proj_scored if entry[0] > 0]
        proj_scored = matched_blocks or proj_scored[:_FALLBACK_TOP_N]
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


def _parse_rephrased(content: str) -> list[str]:
    """Parse the LLM's reply into plain bullet strings (robust to numbering)."""
    lines: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = _NUMBERED_LINE_RE.match(line)
        lines.append(match.group(1).strip() if match else line)
    return lines


async def enhance_with_llm(
    bullets: list[str],
    jd_skills: list[str],
    *,
    config: LlmRuntimeConfig | None = None,
    max_bullets: int | None = None,
) -> list[str]:
    """Rephrase bullets using JD language via an OpenAI-compatible API.

    Feature-flagged: returns bullets unchanged unless the effective config has
    ``enabled`` set and an API key configured. At most ``max_bullets`` (default
    ``settings.tailor_llm_max_bullets``, per ADR 006) bullets are sent per
    call; a short or malformed reply is padded with the originals. Any API
    failure degrades gracefully to the original bullets.
    """
    if config is None:
        config = LlmRuntimeConfig(
            enabled=settings.tailoring_llm_enabled,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    if not config.enabled or not config.api_key or not bullets:
        return bullets
    cap = settings.tailor_llm_max_bullets if max_bullets is None else max_bullets
    cap = max(1, cap)
    head, tail = bullets[:cap], bullets[cap:]
    prompt = (
        "Rephrase the following CV bullet points to emphasize these skills: "
        f"{', '.join(jd_skills)}. Keep them concise (max 2 lines each), first "
        "person past tense, no fabrication. Return ONLY a numbered list.\n\n"
        + "\n".join(f"{i + 1}. {b}" for i, b in enumerate(head))
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You rewrite CV bullet points to emphasize "
                                "specific skills. Never invent facts, dates, "
                                "or employers."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        rephrased = _parse_rephrased(content)
        if not rephrased:
            return bullets
        # Keep the count stable: pad a short reply with the originals (head),
        # and leave any bullets beyond the cap untouched.
        return (rephrased + head)[: len(head)] + tail
    except Exception:
        logger.warning("LLM enhancement failed; using original bullets", exc_info=True)
        return bullets
