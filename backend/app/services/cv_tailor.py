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
from app.services.text_norm import fold_text, fold_words

logger = logging.getLogger(__name__)

_SKILL_RE_CACHE: dict[str, re.Pattern] = {}

# Tailoring preserves the whole employment history (ADR 027). Relevance decides
# *how much of a role* survives, never *whether the role exists*: a CV that
# silently drops a job reads as an unexplained gap, and the dates of a role whose
# stack looks foreign are exactly the evidence a reader needs. So a role that
# matches the JD keeps up to `_BULLETS_MATCHED` bullets and one that shares no
# keyword keeps `_BULLETS_UNMATCHED` — a different stack still carries
# transferable proof of complexity, scale and ownership.
_BULLETS_MATCHED = 6
_BULLETS_UNMATCHED = 2

# Projects are not a timeline, so dropping an unrelated one leaves no gap. When
# none matches, keep this many top-scored ones so the section is never empty (a
# "no match" is signalled via `relevance`/`used_fallback`).
_PROJECT_FALLBACK_TOP_N = 3

_NUMBERED_LINE_RE = re.compile(r"^\d+[.)]\s*(.+)$")

# The `llm` variant produces a *printable* CV, so its prompt carries an explicit
# page budget instead of an open-ended "be maximally relevant" instruction. The
# model cannot measure pages (page length is decided by the template and fonts),
# so the budget is stated both as the goal and as the levers the model controls
# (how many bullets each role keeps, how long the summary is). Nothing is trimmed
# afterwards: the worker measures the rendered PDF (`cv_artifact_pages`) and
# warns (`llm_rewrite_over_page_budget`) when the guidance was not followed,
# leaving both variants for the user to compare.
#
# The lever is bullets, never roles (ADR 027): the previous prompt budgeted the
# page by keeping "3-4 roles", which turned every extra job in the history into a
# gap. The prompt now asks the model to *fill* two pages and caps the bullets
# instead, and `_restore_missing_roles` re-inserts any role the model drops
# anyway — the history is a contract, not a suggestion.
#
# Calibrated on the default `classic` template (A4, 10pt, 1.6cm/1.8cm margins):
# ~600-750 words — a summary plus roughly 16-20 bullets across a normal 4-6 role
# history — fills two pages without spilling into a third. Re-tune these numbers
# if that stylesheet changes.
LLM_TARGET_PAGES = 2
_LLM_TARGET_WORDS = "600-750"
_LLM_TARGET_BULLETS = "3-8"
_LLM_MIN_BULLETS = 2


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
    # True when nothing matched the JD, so the result is the master CV with its
    # bullets condensed for space rather than for the job (surfaced so the
    # UI/result can say "nothing matched" instead of silently presenting an
    # untailored CV as a tailored one).
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


def _select_bullets(block: dict, jd_skills: list[str], keep: int) -> list[str]:
    """The ``keep`` most job-relevant bullets of a role, in their original order.

    Bullets are ranked by how many JD skills they mention and ties keep the
    master CV's order (parsers write the strongest bullet first), so a condensed
    role still leads with evidence rather than with whichever bullet happened to
    be last. Nothing is rewritten: a selected bullet is verbatim from the CV.
    """
    bullets = [b for b in block.get("bullets", []) or [] if isinstance(b, str)]
    if keep <= 0 or len(bullets) <= keep:
        return bullets
    ranked = sorted(
        range(len(bullets)),
        key=lambda index: (
            -sum(1 for skill in jd_skills if _contains_skill(bullets[index], skill)),
            index,
        ),
    )
    return [bullets[index] for index in sorted(ranked[:keep])]


def _condensed_block(
    block: dict, jd_skills: list[str], matched: int, *, condense: bool
) -> dict:
    """A role as it appears in the tailored CV: same facts, fewer bullets."""
    item = dict(block)
    if not condense:
        return item
    keep = _BULLETS_MATCHED if matched else _BULLETS_UNMATCHED
    item["bullets"] = _select_bullets(block, jd_skills, keep)
    return item


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
    condense_irrelevant: bool = True,
) -> TailoredCV:
    """Tailor a CV structure to a JD's required skills.

    The employment history is never filtered (ADR 027): every role is kept, in
    the master CV's order (reverse-chronological as parsed), and relevance only
    decides how many of its bullets each one keeps. ``condense_irrelevant=False``
    keeps every bullet as well, for callers that want an untailored copy.
    """
    cv_skills = [str(s) for s in cv_structure.get("skills", [])]
    matching = match_skills(jd_skills, cv_skills)

    experience: list[dict] = []
    matched_roles = 0
    for index, block in enumerate(cv_structure.get("experience", []) or []):
        score = len(_score_block(block, jd_skills, annotations, index))
        matched_roles += 1 if score else 0
        experience.append(
            _condensed_block(block, jd_skills, score, condense=condense_irrelevant)
        )
    # True exactly when no role matched the JD (e.g. the JD parsed no skills at
    # all). The CV is then the master CV with condensed bullets — never a
    # truncated history — and the flag says so instead of silently presenting an
    # untailored CV as a tailored one.
    used_fallback = bool(experience) and not matched_roles

    proj_scored = _order_blocks_with_scores(
        cv_structure.get("projects", []), jd_skills, annotations
    )
    projects = [block for _, _, block in proj_scored]
    if condense_irrelevant:
        matched_projects = [entry for entry in proj_scored if entry[0] > 0]
        projects = [
            block
            for _, _, block in (matched_projects or proj_scored[:_PROJECT_FALLBACK_TOP_N])
        ]

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
    """Serialise the master CV as *valid* JSON within ``limit`` characters.

    Trimming follows the retention rule (ADR 027): projects go first, then each
    role's bullets are cut down to ``_BULLETS_UNMATCHED`` — never below, and
    least relevant role first — and only after that are whole roles dropped, the
    least relevant first and never the last one. The reference the model gets is
    the history it must reproduce, so shrinking bullets is always preferable to
    deleting an employer the prompt is about to require.
    """
    payload = dict(cv_structure)
    payload["experience"] = [
        {**role, "bullets": list(role.get("bullets", []) or [])}
        for role in cv_structure.get("experience", []) or []
        if isinstance(role, dict)
    ]
    payload["projects"] = list(cv_structure.get("projects", []) or [])
    dropped = {"roles": 0, "role_bullets": 0, "projects": 0, "bullets": 0}

    def _fits() -> bool:
        return len(json.dumps(payload)) <= limit

    if _fits():
        return json.dumps(payload), dropped

    # 1. Projects: not a timeline, so dropping one leaves no gap.
    ranked = _order_blocks_with_scores(payload["projects"], jd_skills, None)
    for _score, _index, block in reversed(ranked):
        if _fits():
            break
        payload["projects"] = [item for item in payload["projects"] if item is not block]
        dropped["projects"] += 1

    # 2. Bullets above the per-role minimum, least relevant role first.
    ranked = _order_blocks_with_scores(payload["experience"], jd_skills, None)
    for _score, _index, block in reversed(ranked):
        bullets = block.get("bullets", [])
        while len(bullets) > _BULLETS_UNMATCHED and not _fits():
            bullets.pop()
            dropped["role_bullets"] += 1

    # 3. Long bullets are halved in place: still valid JSON, still a real bullet.
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

    # 4. Whole roles, least relevant first — but the history always keeps one.
    if not _fits():
        ranked = _order_blocks_with_scores(payload["experience"], jd_skills, None)
        for _score, _index, block in reversed(ranked):
            if _fits() or len(payload["experience"]) <= 1:
                break
            payload["experience"] = [
                item for item in payload["experience"] if item is not block
            ]
            dropped["roles"] += 1

    if not _fits():
        # Last resort: the optional sections are the least load-bearing part of
        # the reference. Still valid JSON — which is the point.
        for key in ("projects", "certifications", "languages", "links"):
            payload[key] = []
    return json.dumps(payload), dropped


def _role_words(value: object) -> str:
    """Normalised words of a company/title, for comparing the two CVs."""
    return " ".join(fold_words(value))


_MONTH_NAMES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_NAME_RE = re.compile(r"\b([a-z]{3,9})\.?\s*,?\s*((?:19|20)\d{2})\b")
_YEAR_MONTH_RE = re.compile(r"\b((?:19|20)\d{2})[-/](\d{1,2})\b")
_SLASH_MONTH_RE = re.compile(r"\b(\d{1,2})/((?:19|20)\d{2})\b")
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_PRESENT_WORDS = {"present", "now", "current", "atual"}


def _role_date(value: object) -> str:
    """One date as ``YYYY-MM``/``YYYY``/``present``, however it was written.

    The master CV stores what the parser normalised (``2022-07``, ``Present``)
    while a model usually writes ``Jul 2022``. Both name the same month, so a
    role is matched on when it happened, not on how it is spelled.
    """
    text = fold_text(value)
    if not text:
        return ""
    if text in _PRESENT_WORDS:
        return "present"
    match = _MONTH_NAME_RE.search(text)
    if match and match.group(1)[:3] in _MONTH_NAMES:
        return f"{match.group(2)}-{_MONTH_NAMES[match.group(1)[:3]]:02d}"
    for pattern, year_group, month_group in ((_YEAR_MONTH_RE, 1, 2), (_SLASH_MONTH_RE, 2, 1)):
        match = pattern.search(text)
        if match and 1 <= int(match.group(month_group)) <= 12:
            return f"{match.group(year_group)}-{int(match.group(month_group)):02d}"
    match = _YEAR_RE.search(text)
    return match.group(1) if match else text


def _role_range(role: dict) -> tuple[str, str]:
    """A role's dates, folded to ``(start, end)``."""
    return _role_date(role.get("start_date")), _role_date(role.get("end_date"))


def _same_date(first: str, second: str) -> bool:
    """Whether two folded dates name the same time, tolerating a year-only spelling.

    ``2022`` and ``2022-07`` are the same start for matching purposes: a reply
    that kept only the year is a reformatting, not a different job.
    """
    if first == second:
        return True
    if len(first) == 4 or len(second) == 4:
        return first[:4] == second[:4]
    return False


def _same_period(master_role: dict, tailored_role: dict) -> bool:
    """Whether two roles claim the same period — the strongest identity key.

    This is the only key that survives *any* rewording. A missing end date is
    tolerated: the model dropping "Present" is not a different job, so only a
    contradicting date separates the two.
    """
    master_start, master_end = _role_range(master_role)
    tailored_start, tailored_end = _role_range(tailored_role)
    if not master_start or not tailored_start or not _same_date(master_start, tailored_start):
        return False
    if not master_end or not tailored_end:
        return True
    return _same_date(master_end, tailored_end)


def _different_period(master_role: dict, tailored_role: dict) -> bool:
    """Whether both roles carry a start date and the two clearly disagree.

    Two periods can never be one job, whatever the names say — this is what keeps
    a promotion at one employer two roles.
    """
    master_start, _master_end = _role_range(master_role)
    tailored_start, _tailored_end = _role_range(tailored_role)
    return bool(master_start and tailored_start and not _same_date(master_start, tailored_start))


def _role_word_set(role: dict) -> set[str]:
    """Every word of a role's employer and its title."""
    return set(fold_words(role.get("company"))) | set(fold_words(role.get("title")))


def _titles_match(master_title: str, tailored_title: str) -> bool:
    """Same title, or one contained in the other (``Sr. Java Developer``)."""
    if not master_title or not tailored_title:
        return False
    return (
        master_title == tailored_title
        or master_title in tailored_title
        or tailored_title in master_title
    )


def _is_same_role(master_role: dict, tailored_role: dict) -> bool:
    """Whether two roles are the same job, tolerating a reworded title.

    The prompt forbids rewording titles, but a model that writes "Sr. Java
    Developer" for "Java Developer" must not end up duplicated in the history —
    the guard may add a role, never a second copy of one.

    Identity is tested in three tiers, strongest first, and any tier matching
    means "same job":

    1. the period, plus at least one shared word. Dates are what a rewrite
       cannot change, and the shared word keeps two genuinely different jobs
       that ran concurrently from being confused;
    2. the employer, word for word, plus a title that matches or is contained in
       the other;
    3. the *set* of employer and title words, which is what survives a stored CV
       whose two fields are swapped: ``title="Acme", company="Engineer"``
       describes the same job as ``title="Engineer", company="Acme"``.

    A promotion inside one employer therefore stays two roles, which is the only
    case the company rule was ever about — and two roles whose periods clearly
    disagree are never one job, whatever their names say.
    """
    if _different_period(master_role, tailored_role):
        return False
    if _same_period(master_role, tailored_role) and (
        _role_word_set(master_role) & _role_word_set(tailored_role)
    ):
        return True
    master_company = _role_words(master_role.get("company"))
    if (
        master_company
        and master_company == _role_words(tailored_role.get("company"))
        and _titles_match(
            _role_words(master_role.get("title")), _role_words(tailored_role.get("title"))
        )
    ):
        return True
    master_words = _role_word_set(master_role)
    return bool(master_words) and master_words == _role_word_set(tailored_role)


def _pick_role(master_role: dict, candidates: list[dict]) -> dict | None:
    """The reply role that best matches ``master_role``, or ``None``.

    A reply can hold two roles that both look like the master's (the same title
    twice at one employer), so an exact period wins over a merely similar one.
    """
    matches = [role for role in candidates if _is_same_role(master_role, role)]
    if not matches:
        return None
    return next((role for role in matches if _same_period(master_role, role)), matches[0])


def _dedupe_roles(roles: list[dict]) -> tuple[list[dict], int]:
    """Keep the first of any two roles that are the same job; count the rest.

    Identity is not transitive (A~B and B~C do not make A~C), so duplicates are
    removed explicitly instead of being assumed away: the final history can
    never list one job twice.
    """
    kept: list[dict] = []
    removed = 0
    for role in roles:
        if any(_is_same_role(kept_role, role) for kept_role in kept):
            removed += 1
            continue
        kept.append(role)
    return kept, removed


def _restore_missing_roles(
    structure: dict, cv_structure: dict, jd_skills: list[str]
) -> tuple[int, int, int]:
    """Re-insert roles the model dropped; ``(restored, unmatched, duplicated)``.

    The prompt requires the complete history but a prompt is not a guarantee, so
    the rule is enforced here (ADR 027). Every role of the master CV missing from
    the reply is re-inserted in its original position with its own dates and its
    own ``_BULLETS_UNMATCHED`` strongest bullets — verbatim, nothing invented —
    so a dropped role can only ever cost wording, never a gap in the timeline.

    ``unmatched`` counts reply roles that could not be traced back to the master
    CV. They are kept (deleting an unrecognisable entry would be a second silent
    edit) and reported, because they are the model drifting on "never invent".
    ``duplicated`` counts reply roles that are a second copy of one already kept:
    recognising one job twice is what made a tailored CV list every role twice,
    so the extra copy is dropped and the event is reported.
    """
    master_roles = [
        role for role in cv_structure.get("experience", []) or [] if isinstance(role, dict)
    ]
    reply_roles = [
        role for role in structure.get("experience", []) or [] if isinstance(role, dict)
    ]
    if not master_roles:
        return 0, 0, 0

    remaining = list(reply_roles)
    merged: list[dict] = []
    restored = 0
    for master_role in master_roles:
        match = _pick_role(master_role, remaining)
        if match is not None:
            remaining.remove(match)
            merged.append(match)
            continue
        restored += 1
        merged.append(
            {
                "company": str(master_role.get("company", "")),
                "title": str(master_role.get("title", "")),
                "start_date": master_role.get("start_date"),
                "end_date": master_role.get("end_date"),
                "bullets": _select_bullets(master_role, jd_skills, _BULLETS_UNMATCHED),
            }
        )

    final, duplicated = _dedupe_roles([*merged, *remaining])
    if not restored and not duplicated:
        # Nothing to fix: the reply's own order stays the model's call.
        return 0, len(remaining), 0
    structure["experience"] = final
    reply_ids = {id(role) for role in remaining}
    return restored, sum(1 for role in final if id(role) in reply_ids), duplicated


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
    # to spend. The budget is spent on bullets: the history is complete (ADR 027),
    # because a role the model leaves out becomes an unexplained gap no wording
    # can compensate for.
    system = (
        "You are an expert resume writer. Produce a tailored CV for the target "
        "job, using the candidate's master CV as the only source of truth. The "
        f"CV has up to {LLM_TARGET_PAGES} pages to fill: with a standard one-column "
        f"layout that is roughly {_LLM_TARGET_WORDS} words. You may "
        "reorder sections, tighten wording and lead with the job's language. "
        "The employment history is fixed: every role in the master CV must "
        "appear, with its employer, title and dates, in the same order — NEVER "
        "omit a role, because a missing role reads as an unexplained employment "
        "gap. Spend the budget on bullets instead: give the 2-3 roles that best "
        f"support this application up to {_LLM_TARGET_BULLETS} bullets each, and give "
        f"every other role at least {_LLM_MIN_BULLETS}. A role whose stack "
        "differs from this job can still be relevant, e.g.: delivered complexity, scale, "
        "ownership and adjacent-domain experience are evidence a hiring manager "
        "wants, so do not judge relevance by keyword overlap alone; write its "
        "bullets around what transfers. Projects and bullets that do not help "
        "this application may be shortened or left out. Every fact you include "
        "— employers, titles, dates, degrees, skills, numbers and languages — "
        "must be exactly as given in the master CV: NEVER invent experience, "
        "employers, dates, numbers or skills, and never split or merge roles. "
        "In each role, `company` is the employer and `title` is the candidate's "
        "job title — never swap the two fields. "
        "Group the skills section yourself: in `skill_groups`, "
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
            "llm_cv_input_truncated limit=%d roles=%d role_bullets=%d "
            "projects=%d bullets=%d",
            half,
            dropped["roles"],
            dropped["role_bullets"],
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
    result = structure.model_dump()
    # The prompt asks for the whole history; this makes it true even when the
    # model ignores the instruction (ADR 027). Validation runs first, so the
    # restored roles are re-inserted into a structure that already type-checked.
    restored, unmatched, duplicated = _restore_missing_roles(result, cv_structure, jd_skills or [])
    if duplicated:
        logger.info("llm_cv_roles_duplicated removed=%d", duplicated)
    if restored or unmatched:
        logger.info(
            "llm_cv_roles_restored restored=%d unmatched=%d",
            restored,
            unmatched,
        )
    return result, _coerce_self_score(payload.get("ats_self_score"))
