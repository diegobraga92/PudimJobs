"""Rule-based CV tailoring engine + optional full-LLM variant.

Given a job's parsed requirements and the master CV, selects the most relevant
experience/project blocks, reorders them, surfaces a tailored skills list and
leads the summary with the JD-matched strengths. Two optional LLM layers exist:

* ``enhance_with_llm`` rephrases individual bullets (ADR 006), and
* ``generate_tailored_cv_with_llm`` rewrites the whole CV as a *second* artifact
  kept alongside the deterministic one (ADR 016).

Both degrade gracefully: a disabled or failing LLM never fails the run.
"""

import json
import logging
import re
from dataclasses import dataclass, field

import httpx
from pydantic import ValidationError

from app.config import settings
from app.schemas.master_cv import CVStructure
from app.services.cv_schema import CV_JSON_SCHEMA, strip_code_fence
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
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])", re.IGNORECASE)
        _SKILL_RE_CACHE[skill] = pattern
    return bool(pattern.search(text))


@dataclass
class TailoredCV:
    summary: str
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    # Contact header (back-filled from the CV file; used by the PDF renderer).
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[str] = field(default_factory=list)
    # Kept verbatim: certifications/languages are short and never dropped.
    certifications: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    relevance: float = 0.0
    # True when nothing matched the JD and the top blocks were kept as a
    # placeholder (surfaced so the UI/result can say "nothing matched" instead of
    # silently presenting an untailored CV).
    used_fallback: bool = False

    def as_structure(self) -> dict:
        """Serialise to the ``CVStructure`` shape used by models and the PDF."""
        return {
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "location": self.location,
            "links": self.links,
            "summary": self.summary,
            "experience": self.experience,
            "education": self.education,
            "skills": self.skills,
            "projects": self.projects,
            "certifications": self.certifications,
            "languages": self.languages,
        }

    @classmethod
    def from_structure(cls, structure: dict) -> "TailoredCV":
        """Rebuild a ``TailoredCV`` from a persisted CV structure (PDF rendering)."""

        def _strings(key: str) -> list[str]:
            return [str(value) for value in structure.get(key, []) or []]

        return cls(
            summary=str(structure.get("summary", "") or ""),
            experience=list(structure.get("experience") or []),
            education=list(structure.get("education") or []),
            skills=_strings("skills"),
            projects=list(structure.get("projects") or []),
            full_name=str(structure.get("full_name", "") or ""),
            email=str(structure.get("email", "") or ""),
            phone=str(structure.get("phone", "") or ""),
            location=str(structure.get("location", "") or ""),
            links=_strings("links"),
            certifications=_strings("certifications"),
            languages=_strings("languages"),
        )


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


def _tailored_summary(base: str, matched: list[str]) -> str:
    """Lead the summary with the JD-matched strengths (ADR 016).

    Only skills already proven elsewhere in the CV are named, so nothing is
    invented; a summary that already mentions them all is returned untouched.
    This is what stops the deterministic variant from being a verbatim copy.
    """
    if not matched:
        return base.strip()
    missing = [skill for skill in matched if not _contains_skill(base, skill)]
    if not missing:
        return base.strip()
    strengths = ", ".join(missing)
    head = base.strip()
    if not head:
        return f"Core strengths: {strengths}."
    separator = "" if head.endswith((".", "!", "?")) else "."
    return f"{head}{separator} Core strengths: {strengths}."


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
    # `used_fallback` tracks the *experience* selection: it is True exactly when
    # no block matched the JD and the top-N placeholder was kept. That is the
    # case that used to be silent (e.g. the JD parsed no skills at all).
    used_fallback = False
    if drop_irrelevant:
        matched_blocks = [entry for entry in exp_scored if entry[0] > 0]
        if not matched_blocks and exp_scored:
            used_fallback = True
        exp_scored = matched_blocks or exp_scored[:_FALLBACK_TOP_N]
    experience = [block for _, _, block in exp_scored]

    proj_scored = _order_blocks_with_scores(
        cv_structure.get("projects", []), jd_skills, annotations
    )
    if drop_irrelevant:
        matched_blocks = [entry for entry in proj_scored if entry[0] > 0]
        proj_scored = matched_blocks or proj_scored[:_FALLBACK_TOP_N]
    projects = [block for _, _, block in proj_scored]

    def _strings(key: str) -> list[str]:
        return [str(value) for value in cv_structure.get(key, []) or []]

    return TailoredCV(
        summary=_tailored_summary(str(cv_structure.get("summary", "") or ""), matching["matched"]),
        experience=experience,
        education=cv_structure.get("education", []),
        skills=_tailored_skills(cv_skills, matching["matched"]),
        projects=projects,
        full_name=str(cv_structure.get("full_name", "") or ""),
        email=str(cv_structure.get("email", "") or ""),
        phone=str(cv_structure.get("phone", "") or ""),
        location=str(cv_structure.get("location", "") or ""),
        links=_strings("links"),
        certifications=_strings("certifications"),
        languages=_strings("languages"),
        matched_skills=matching["matched"],
        missing_skills=matching["missing"],
        relevance=matching["relevance"],
        used_fallback=used_fallback,
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


def _coerce_self_score(value: object) -> int | None:
    """Clamp the LLM's self-estimate into 0..100, or ``None`` when unusable."""
    try:
        score = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


async def generate_tailored_cv_with_llm(
    cv_structure: dict,
    *,
    jd_text: str,
    jd_title: str = "",
    jd_skills: list[str] | None = None,
    config: LlmRuntimeConfig | None = None,
) -> tuple[dict, int | None] | None:
    """Rewrite the whole CV for a job via an LLM (ADR 016).

    Returns ``(structure, self_estimated_score)`` where ``structure`` has been
    validated against ``CVStructure`` — or ``None`` when the LLM is disabled,
    errors, or returns something unparseable/invalid. Callers therefore keep the
    deterministic variant and never fail the run.

    This is the one place a model is asked to *produce* CV content rather than
    rephrase a bullet, so the prompt forbids fabrication and the reply is
    schema-validated before it is trusted.
    """
    if config is None:
        config = LlmRuntimeConfig(
            enabled=settings.tailoring_llm_enabled,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    if not config.enabled or not config.api_key:
        return None

    budget = max(1_000, settings.tailor_llm_max_chars)
    half = budget // 2
    system = (
        "You are an expert resume writer. Rewrite the candidate's CV so it is "
        "maximally relevant to the target job. Keep every fact — employers, "
        "titles, dates, degrees, skills and languages — exactly as given: NEVER "
        "invent experience, employers, dates, numbers or skills. You may reorder "
        "sections, tighten wording and lead with the job's language, but the "
        "candidate's history must stay truthful. Return ONLY a JSON object of the "
        'shape {"cv": ' + CV_JSON_SCHEMA + ', "ats_self_score": 0} where '
        "ats_self_score is your own integer 0-100 estimate of how well the "
        "rewritten CV matches the job."
    )
    user = (
        f"Target job title: {jd_title or '(unspecified)'}\n"
        f"Required skills: {', '.join(jd_skills or []) or '(none parsed)'}\n\n"
        f"Job description:\n{jd_text[:half]}\n\n"
        f"Current CV (JSON):\n{json.dumps(cv_structure)[:half]}"
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 4000,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        payload = json.loads(strip_code_fence(content))
    except Exception:
        logger.warning("LLM CV rewrite failed; keeping the deterministic variant", exc_info=True)
        return None
    if not isinstance(payload, dict):
        return None
    try:
        structure = CVStructure.model_validate(payload.get("cv"))
    except ValidationError:
        logger.warning("LLM CV rewrite returned an invalid structure; ignoring", exc_info=True)
        return None
    return structure.model_dump(), _coerce_self_score(payload.get("ats_self_score"))
