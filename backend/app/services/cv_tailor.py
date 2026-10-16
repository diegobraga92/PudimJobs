"""Rule-based CV tailoring engine + optional full-LLM variant."""

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.config import settings
from app.schemas.master_cv import CVStructure
from app.services.cv_schema import CV_JSON_SCHEMA
from app.services.llm_client import chat_json, chat_text
from app.services.llm_config import LlmRuntimeConfig
from app.services.skill_matcher import group_skills, match_skills, resolve_skills

logger = logging.getLogger(__name__)

_SKILL_RE_CACHE: dict[str, re.Pattern] = {}

# When no CV block matches the JD skills, keep this many top-scored blocks so
# the tailored CV is never empty (a "no match" is signalled via `relevance`).
_FALLBACK_TOP_N = 3

_NUMBERED_LINE_RE = re.compile(r"^\d+[.)]\s*(.+)$")

# The `llm` variant produces a *printable* CV, so its prompt carries an explicit
# page budget instead of an open-ended "be maximally relevant" instruction. The
# model cannot measure pages (page length is decided by the template and fonts),
# so the budget is stated both as the goal and as the levers the model controls
# (how many roles/bullets to keep, how long the summary is). Nothing is trimmed
# afterwards: the worker measures the rendered PDF (`cv_artifact_pages`) and
# warns (`llm_rewrite_over_page_budget`) when the guidance was not followed,
# leaving both variants for the user to compare.
#
# Calibrated on the default `classic` template (A4, 10pt, 1.6cm/1.8cm margins):
# ~550-650 words, i.e. about 15 bullets across 3-4 roles, renders in two pages.
# Re-tune these numbers if that stylesheet changes.
LLM_TARGET_PAGES = 2
_LLM_TARGET_WORDS = "550-650"
_LLM_TARGET_ROLES = "3-4"
_LLM_TARGET_BULLETS = "3-6"


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
    # LLM-authored skills categories. Empty for the deterministic variant, whose
    # renderer groups the flat `skills` list by taxonomy instead.
    skill_groups: list[tuple[str, list[str]]] = field(default_factory=list)
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
            "skill_groups": [
                {"label": label, "items": items} for label, items in self.skill_groups
            ],
            "projects": self.projects,
            "certifications": self.certifications,
            "languages": self.languages,
        }

    @classmethod
    def from_structure(cls, structure: dict) -> "TailoredCV":
        """Rebuild a ``TailoredCV`` from a persisted CV structure (PDF rendering)."""

        def _strings(key: str) -> list[str]:
            return [str(value) for value in structure.get(key, []) or []]

        def _skill_groups() -> list[tuple[str, list[str]]]:
            groups: list[tuple[str, list[str]]] = []
            for raw in structure.get("skill_groups") or []:
                if not isinstance(raw, dict):
                    continue
                label = str(raw.get("label", "") or "").strip()
                items = [str(item) for item in raw.get("items") or []]
                if label and items:
                    groups.append((label, items))
            return groups

        return cls(
            summary=str(structure.get("summary", "") or ""),
            experience=list(structure.get("experience") or []),
            education=list(structure.get("education") or []),
            skills=_strings("skills"),
            skill_groups=_skill_groups(),
            projects=list(structure.get("projects") or []),
            full_name=str(structure.get("full_name", "") or ""),
            email=str(structure.get("email", "") or ""),
            phone=str(structure.get("phone", "") or ""),
            location=str(structure.get("location", "") or ""),
            links=_strings("links"),
            certifications=_strings("certifications"),
            languages=_strings("languages"),
        )

    def resolved_skill_groups(self) -> list[tuple[str, list[str]]]:
        """The labelled skills categories every renderer should draw.

        The LLM variant authors its own job-relevant labels; the deterministic
        variant leaves ``skill_groups`` empty and gets the taxonomy grouping
        instead (which buckets skills the taxonomy does not know under
        "Additional", never "Other"). PDF and DOCX both call this, so the two
        exports can never disagree about that rule.
        """
        return self.skill_groups or group_skills(self.skills)


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
    """The CV's own skills, led by the entries that cover a JD skill.

    A JD skill is only added when the CV has no entry for it. Otherwise a CV
    saying "k8s" — or "JavaScript/TypeScript" for a JD asking TypeScript — would
    render the same skill twice, once in the JD's wording and once in its own.
    """
    matched_lower = {s.lower() for s in matched}
    resolved = {
        entry: {part.lower() for part in resolve_skills(entry)} for entry in cv_skills
    }
    covered = {part for parts in resolved.values() for part in parts}

    def _covers_matched(entry: str) -> bool:
        return bool(resolved[entry] & matched_lower)

    leading = [entry for entry in cv_skills if _covers_matched(entry)]
    trailing = [entry for entry in cv_skills if not _covers_matched(entry)]
    injected = [skill for skill in matched if skill.lower() not in covered]
    return list(dict.fromkeys([*injected, *leading, *trailing]))


def _tailored_summary(base: str, matched: list[str]) -> str:
    """Lead the summary with the JD-matched strengths (ADR 016)."""
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
    """Rephrase bullets using JD language via an OpenAI-compatible API."""
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
    content = await chat_text(
        config,
        system=(
            "You rewrite CV bullet points to emphasize specific skills. "
            "Never invent facts, dates, or employers."
        ),
        user=prompt,
        max_tokens=1024,
        temperature=0.4,
        timeout=30,
        label="LLM bullet rephrase",
    )
    if content is None:
        logger.warning("LLM enhancement failed; using original bullets")
        return bullets
    rephrased = _parse_rephrased(content)
    if not rephrased:
        return bullets
    # Keep the count stable: pad a short reply with the originals (head),
    # and leave any bullets beyond the cap untouched.
    return (rephrased + head)[: len(head)] + tail


def _coerce_self_score(value: object) -> int | None:
    """Clamp the LLM's self-estimate into 0..100, or ``None`` when unusable."""
    try:
        score = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _truncate_text(text: str, limit: int) -> str:
    """Shorten ``text`` to ``limit`` characters, preferring a line boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind("\n")
    return cut[:boundary] if boundary >= limit // 2 else cut


def _fit_cv_for_prompt(
    cv_structure: dict, limit: int, jd_skills: list[str]
) -> tuple[str, dict[str, int]]:
    """Serialise the master CV as *valid* JSON within ``limit`` characters."""
    payload = dict(cv_structure)
    payload["experience"] = list(cv_structure.get("experience", []) or [])
    payload["projects"] = list(cv_structure.get("projects", []) or [])
    dropped = {"experience": 0, "projects": 0, "bullets": 0}

    def _fits() -> bool:
        return len(json.dumps(payload)) <= limit

    if _fits():
        return json.dumps(payload), dropped

    # Projects first, then experience: the experience history carries the
    # application, so it goes last.
    for key in ("projects", "experience"):
        ranked = _order_blocks_with_scores(payload[key], jd_skills, None)
        for _score, _index, block in reversed(ranked):
            if _fits():
                break
            payload[key] = [item for item in payload[key] if item is not block]
            dropped[key] += 1

    while not _fits():
        candidates = [
            (len(bullet), block, index)
            for block in [*payload["experience"], *payload["projects"]]
            for index, bullet in enumerate(block.get("bullets", []) or [])
            if isinstance(bullet, str) and len(bullet) >= 16
        ]
        if not candidates:
            break
        _length, block, index = max(candidates, key=lambda item: item[0])
        block["bullets"][index] = block["bullets"][index][: len(block["bullets"][index]) // 2]
        dropped["bullets"] += 1

    if not _fits():
        # Last resort: the optional sections are the least load-bearing part of
        # the reference. Still valid JSON — which is the point.
        for key in ("projects", "certifications", "languages", "links"):
            payload[key] = []
    return json.dumps(payload), dropped


async def generate_tailored_cv_with_llm(
    cv_structure: dict,
    *,
    jd_text: str,
    jd_title: str = "",
    jd_skills: list[str] | None = None,
    config: LlmRuntimeConfig | None = None,
) -> tuple[dict, int | None] | None:
    """Produce a tailored CV for one job via an LLM (ADR 016)."""
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
    # Framing matters more than any hard cap: asking for "the CV, rewritten so it
    # is maximally relevant" while demanding that *every* fact be kept leaves no
    # way to shorten anything, so the model showed relevance by adding and
    # splitting bullets — the artifact came back several pages long. Tailoring is
    # a *selection* for one job, so the prompt says so and gives it a page budget
    # to spend.
    system = (
        "You are an expert resume writer. Produce a tailored CV for the target "
        "job, using the candidate's master CV as the only source of truth. Aim "
        f"for at most {LLM_TARGET_PAGES} pages: with a standard one-column "
        f"layout that is roughly {_LLM_TARGET_WORDS} words, so keep the "
        f"{_LLM_TARGET_ROLES} roles that best support this application, with "
        f"{_LLM_TARGET_BULLETS} bullets each, and leave out or shorten the "
        "rest. Tailoring means selecting: you MAY omit roles, projects and "
        "bullets that do not help this application, and you may reorder "
        "sections, tighten wording and lead with the job's language. Every fact "
        "you include — employers, titles, dates, degrees, skills, numbers and "
        "languages — must be exactly as given in the master CV: NEVER invent "
        "experience, employers, dates, numbers or skills, and never split or "
        "merge roles. Group the skills section yourself: in `skill_groups`, "
        "return 2-5 labelled categories that fit this job (e.g. Languages, "
        "Frameworks, Cloud & DevOps, Soft Skills), putting every skill from "
        "`skills` into exactly one group — never use an 'Other' group — and "
        "keep the flat `skills` list too. Return ONLY a JSON object of the shape "
        '{"cv": ' + CV_JSON_SCHEMA + ', "ats_self_score": 0} where '
        "ats_self_score is your own integer 0-100 estimate of how well the "
        "tailored CV matches the job."
    )
    cv_json, dropped = _fit_cv_for_prompt(cv_structure, half, jd_skills or [])
    if any(dropped.values()):
        # An oversized master CV is trimmed into valid JSON, never sliced: see
        # `_fit_cv_for_prompt`. stdlib logging, so the detail goes in the message.
        logger.info(
            "llm_cv_input_truncated limit=%d experience=%d projects=%d bullets=%d",
            half,
            dropped["experience"],
            dropped["projects"],
            dropped["bullets"],
        )
    user = (
        f"Target job title: {jd_title or '(unspecified)'}\n"
        f"Required skills: {', '.join(jd_skills or []) or '(none parsed)'}\n\n"
        f"Job description:\n{_truncate_text(jd_text, half)}\n\n"
        f"Master CV — the only source of truth (JSON):\n{cv_json}"
    )
    payload = await chat_json(
        config,
        system=system,
        user=user,
        max_tokens=4000,
        temperature=0.2,
        timeout=60,
        label="LLM CV rewrite",
    )
    if payload is None:
        # `chat_json` already logged exactly why (transport, empty content, ...).
        logger.warning("LLM CV rewrite failed; keeping the deterministic variant")
        return None
    try:
        structure = CVStructure.model_validate(payload.get("cv"))
    except ValidationError:
        logger.warning("LLM CV rewrite returned an invalid structure; ignoring", exc_info=True)
        return None
    return structure.model_dump(), _coerce_self_score(payload.get("ats_self_score"))
