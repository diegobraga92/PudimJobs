"""ATS (Applicant Tracking System) scoring for tailored CVs (ADR 013).

Two layers:

* a **deterministic** baseline that always runs — skill coverage, keyword
  coverage, content completeness and ATS-readability heuristics — and
* an optional **LLM overlay** adding qualitative feedback (and nudging the
  score) when an OpenAI-compatible endpoint is configured.

Mirrors the graceful-degradation pattern used by the CV parser/tailor
(ADR 006/011): a missing or erroring LLM only drops the result back to the
deterministic baseline; it never fails the request.
"""

import json
import re

import httpx
import structlog

from app.services.llm_config import LlmRuntimeConfig
from app.services.skill_matcher import extract_skills, match_skills

logger = structlog.get_logger(__name__)

# Component weights (must sum to 1.0 for a full score with a JD).
WEIGHTS: dict[str, float] = {
    "skills": 0.40,
    "keywords": 0.15,
    "completeness": 0.20,
    "readability": 0.25,
}

_LABELS: dict[str, str] = {
    "skills": "Skill coverage",
    "keywords": "Keyword coverage",
    "completeness": "Content completeness",
    "readability": "ATS readability",
}

# Heuristic thresholds.
_MAX_BULLET_CHARS = 220
_MIN_SKILLS = 5
_MAX_SKILLS = 40
_MAX_KEYWORDS = 20
# How many significant terms a job title contributes to the keyword pool.
_MAX_TITLE_KEYWORDS = 6
_LLM_WEIGHT = 0.30  # blend: (1 - _LLM_WEIGHT) * heuristic + _LLM_WEIGHT * llm

_STOPWORD_TEXT = """
about above after again against all also am an and any are as at be because been
before being below between both but by can cannot could did do does doing down
during each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor
not now of off on once only or other our ours ourselves out over own same she
should so some such than that the their theirs them themselves then there these
they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves work
working role team teams using use used years experience strong good ability
"""
# Built from a string constant (not a literal) to keep this readable inline.
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def cv_text(cv: dict) -> str:
    """Flatten a structured CV to plain text for matching/scoring."""
    parts: list[str] = []
    for key in ("full_name", "location", "summary"):
        value = cv.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for exp in cv.get("experience") or []:
        parts.extend(p for p in (str(exp.get("title", "")), str(exp.get("company", ""))) if p)
        parts.extend(str(b) for b in exp.get("bullets") or [] if b)
    for edu in cv.get("education") or []:
        parts.extend(p for p in (str(edu.get("degree", "")), str(edu.get("institution", ""))) if p)
    for proj in cv.get("projects") or []:
        parts.extend(
            p for p in (str(proj.get("name", "")), str(proj.get("description", "") or "")) if p
        )
    parts.extend(str(s) for s in cv.get("skills") or [] if s)
    parts.extend(str(c) for c in cv.get("certifications") or [] if c)
    parts.extend(str(lang) for lang in cv.get("languages") or [] if lang)
    return "\n".join(parts)


def derive_keywords(jd_text: str, limit: int = _MAX_KEYWORDS) -> list[str]:
    """Frequency-based fallback keyword extraction (no spaCy required)."""
    counts: dict[str, int] = {}
    for token in re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{3,}", jd_text.lower()):
        if token in _STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [term for term, _ in ranked[:limit]]


def _skill_factor(cv: dict, jd_skills: list[str]) -> dict | None:
    if not jd_skills:
        return None
    cv_skills = [str(s) for s in cv.get("skills") or []] + extract_skills(cv_text(cv))
    matching = match_skills(jd_skills, cv_skills)
    matched = [str(s) for s in matching["matched"]]
    missing = [str(s) for s in matching["missing"]]
    return {
        "factor": {
            "key": "skills",
            "label": _LABELS["skills"],
            "score": round(matching["relevance"], 4),
            "weight": WEIGHTS["skills"],
            "detail": f"{len(matched)}/{len(jd_skills)} required skills found in the CV.",
        },
        "matched": matched,
        "missing": missing,
    }


def _keyword_factor(text: str, keywords: list[str]) -> dict | None:
    if not keywords:
        return None
    lowered = text.lower()
    present = [kw for kw in keywords if kw.lower() in lowered]
    missing = [kw for kw in keywords if kw.lower() not in lowered]
    return {
        "factor": {
            "key": "keywords",
            "label": _LABELS["keywords"],
            "score": round(len(present) / len(keywords), 4),
            "weight": WEIGHTS["keywords"],
            "detail": f"{len(present)}/{len(keywords)} job keywords appear in the CV.",
        },
        "missing": missing,
    }


def _completeness_factor(cv: dict) -> dict:
    experience = cv.get("experience") or []
    checks = {
        "contact details": bool(cv.get("email") or cv.get("full_name")),
        "professional summary": bool(str(cv.get("summary") or "").strip()),
        "at least one role with bullets": any(exp.get("bullets") for exp in experience),
        "education entry": bool(cv.get("education")),
        "skills listed": bool(cv.get("skills") or cv.get("certifications")),
    }
    passed = [name for name, ok in checks.items() if ok]
    missing = [name for name, ok in checks.items() if not ok]
    detail = "All key sections present." if not missing else "Missing: " + ", ".join(missing)
    return {
        "key": "completeness",
        "label": _LABELS["completeness"],
        "score": round(len(passed) / len(checks), 4),
        "weight": WEIGHTS["completeness"],
        "detail": detail,
    }


def _readability_factor(cv: dict) -> tuple[dict, list[str]]:
    experience = cv.get("experience") or []
    bullets = [str(b) for exp in experience for b in exp.get("bullets") or []]
    skills = [str(s) for s in cv.get("skills") or []]

    warnings: list[str] = []
    long_bullets = [b for b in bullets if len(b) > _MAX_BULLET_CHARS]
    if long_bullets:
        warnings.append(
            f"Shorten {len(long_bullets)} bullet(s) to under {_MAX_BULLET_CHARS} "
            "characters — long lines are often truncated by parsers."
        )
    undated = [exp for exp in experience if not exp.get("start_date")]
    if undated:
        warnings.append(
            "Add a start date (YYYY-MM) to every role; ATS parsers read tenure from dates."
        )
    if experience and not all(exp.get("bullets") for exp in experience):
        warnings.append("Give every role at least one bullet so responsibilities are parsed.")
    if len(skills) < _MIN_SKILLS and not cv.get("certifications"):
        warnings.append(f"List at least {_MIN_SKILLS} skills as plain comma-separated terms.")
    if len(skills) > _MAX_SKILLS:
        warnings.append(
            f"Trim the skills list to about {_MAX_SKILLS} entries to avoid keyword stuffing."
        )

    checks = [
        not long_bullets,
        not undated,
        len(skills) >= _MIN_SKILLS or bool(cv.get("certifications")),
        len(skills) <= _MAX_SKILLS,
    ]
    score = sum(1 for ok in checks if ok) / len(checks)
    return (
        {
            "key": "readability",
            "label": _LABELS["readability"],
            "score": round(score, 4),
            "weight": WEIGHTS["readability"],
            "detail": "No parsing blockers detected."
            if not warnings
            else f"{len(warnings)} issue(s) to fix.",
        },
        warnings,
    )


def _weighted_score(factors: list[dict]) -> int:
    total_weight = sum(factor["weight"] for factor in factors)
    if not total_weight:
        return 0
    weighted = sum(factor["score"] * factor["weight"] for factor in factors)
    return max(0, min(100, round(100 * weighted / total_weight)))


def _deterministic_recommendations(
    cv: dict,
    missing_skills: list[str],
    missing_keywords: list[str],
    *,
    text: str = "",
    job_title: str | None = None,
) -> list[str]:
    recommendations: list[str] = []
    if missing_skills:
        recommendations.append(
            "Add or emphasise these required skills: " + ", ".join(missing_skills[:12]) + "."
        )
    if missing_keywords:
        recommendations.append(
            "Work these job keywords into your summary or bullets: "
            + ", ".join(missing_keywords[:12])
            + "."
        )
    title_terms = _missing_title_terms(text, job_title)
    if title_terms:
        recommendations.append(
            "Mirror the job title in your summary or latest role: " + ", ".join(title_terms) + "."
        )
    bullets = [str(b) for exp in cv.get("experience") or [] for b in exp.get("bullets") or []]
    if bullets and not any(re.search(r"\d", b) for b in bullets):
        recommendations.append(
            "Quantify impact with numbers (percentages, latency, users, revenue) in bullets."
        )
    if not str(cv.get("summary") or "").strip():
        recommendations.append("Open with a 2-4 sentence summary mirroring the job title.")
    return recommendations


def _title_terms(job_title: str | None) -> list[str]:
    """Significant terms of a job title (``"Senior Data Engineer"`` → 3 terms)."""
    if not job_title:
        return []
    return derive_keywords(job_title, limit=_MAX_TITLE_KEYWORDS)


def _missing_title_terms(text: str, job_title: str | None) -> list[str]:
    """Title terms that never appear in the CV text (candidates to mirror)."""
    lowered = text.lower()
    return [term for term in _title_terms(job_title) if term not in lowered]


def _dedupe(items: list[str], limit: int = 10) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def build_report(
    cv: dict,
    *,
    jd_skills: list[str] | None = None,
    jd_keywords: list[str] | None = None,
    job_title: str | None = None,
) -> dict:
    """Compute the deterministic ATS report for ``cv`` against a job.

    ``job_title`` (when known) contributes its significant terms to the keyword
    pool and drives a "mirror the job title" recommendation, so a title-only
    request still yields meaningful keyword coverage (see ADR 013).
    """
    text = cv_text(cv)
    factors: list[dict] = []
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    missing_keywords: list[str] = []

    skill_result = _skill_factor(cv, [str(s) for s in jd_skills or []])
    if skill_result:
        factors.append(skill_result["factor"])
        matched_skills = skill_result["matched"]
        missing_skills = skill_result["missing"]

    keywords = _dedupe(
        [str(k) for k in jd_keywords or []] + _title_terms(job_title),
        limit=_MAX_KEYWORDS,
    )
    keyword_result = _keyword_factor(text, keywords)
    if keyword_result:
        factors.append(keyword_result["factor"])
        missing_keywords = keyword_result["missing"]

    factors.append(_completeness_factor(cv))
    readability, warnings = _readability_factor(cv)
    factors.append(readability)

    return {
        "score": _weighted_score(factors),
        "method": "heuristic",
        "factors": factors,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "recommendations": _deterministic_recommendations(
            cv,
            missing_skills,
            missing_keywords,
            text=text,
            job_title=job_title,
        ),
        "warnings": warnings,
        "llm_summary": None,
    }


async def _llm_review(
    report: dict, text: str, jd_text: str, config: LlmRuntimeConfig
) -> dict | None:
    """Ask the LLM for a qualitative review; return ``None`` on any failure."""
    schema = '{"score": 0, "summary": "string", "suggestions": ["string"]}'
    system = (
        "You are an ATS (applicant tracking system) reviewer. Judge how well the "
        "resume matches the job description. Return ONLY a JSON object matching "
        f"exactly this shape: {schema} where score is an integer 0-100. "
        "Never invent facts about the candidate; base suggestions on the provided text."
    )
    current = ", ".join(f"{f['label']}: {f['score']:.2f}" for f in report.get("factors", []))
    user = (
        f"Job description:\n{jd_text[:4000]}\n\n"
        f"Resume:\n{text[:6000]}\n\n"
        f"Current deterministic subscores: {current}"
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                    "max_tokens": 700,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        logger.warning("LLM ATS review failed; using deterministic score only", exc_info=True)
        return None


async def score_ats(
    cv: dict,
    *,
    jd_skills: list[str] | None = None,
    jd_keywords: list[str] | None = None,
    jd_text: str = "",
    job_title: str | None = None,
    llm_config: LlmRuntimeConfig | None = None,
) -> dict:
    """Return a full ATS report, optionally blended with an LLM review.

    The deterministic report is always produced; when ``llm_config`` is enabled
    and the API call succeeds, the LLM contributes a qualitative summary, extra
    suggestions and a 30% influence on the final score.
    """
    report = build_report(cv, jd_skills=jd_skills, jd_keywords=jd_keywords, job_title=job_title)

    if llm_config is None or not llm_config.enabled or not llm_config.api_key:
        return report

    review = await _llm_review(report, cv_text(cv), jd_text, llm_config)
    if not review:
        return report

    try:
        llm_score = int(review.get("score"))
    except (TypeError, ValueError):
        return report

    base = report["score"]
    report["score"] = max(0, min(100, round((1 - _LLM_WEIGHT) * base + _LLM_WEIGHT * llm_score)))
    report["method"] = "hybrid"
    if isinstance(review.get("summary"), str):
        report["llm_summary"] = review["summary"]
    suggestions = review.get("suggestions")
    if isinstance(suggestions, list):
        report["recommendations"] = _dedupe(
            [*report["recommendations"], *(str(s) for s in suggestions)]
        )
    return report
