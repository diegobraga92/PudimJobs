"""Schemas for ATS (Applicant Tracking System) scoring (ADR 013)."""

import uuid

from pydantic import BaseModel, Field

from app.schemas.master_cv import CVStructure


class AtsScoreRequest(BaseModel):
    """Score a CV structure, optionally against a stored job or raw JD text."""

    cv: CVStructure
    job_id: uuid.UUID | None = None
    # Job title: its significant terms join the keyword pool and drive a
    # "mirror the job title" recommendation. When ``job_id`` is set the stored
    # job's title is used as a fallback.
    job_title: str | None = Field(default=None, max_length=255)
    job_description: str | None = None
    # When set, the score is cached on the owned generated CV (see ADR 013).
    generated_cv_id: uuid.UUID | None = None


class AtsFactor(BaseModel):
    """One weighted component of the overall ATS score."""

    key: str
    label: str
    score: float  # 0..1
    weight: float  # contributes score * weight to the final 0..1 total
    detail: str


class AtsScoreResponse(BaseModel):
    # Headline score: the deterministic baseline (ADR 013). Kept as *the*
    # comparable number so artifacts scored at different times line up.
    score: int  # 0..100
    # The deterministic baseline on its own — mirrors ``score``. Explicit so the
    # UI can label both numbers instead of inferring one from the other.
    deterministic_score: int  # 0..100
    # The LLM reviewer's own 0..100 estimate when the overlay ran; ``None`` when
    # it did not (disabled, no key, failed call). Never blended into ``score``.
    llm_score: int | None = None
    method: str  # "heuristic" or "hybrid"
    factors: list[AtsFactor]
    matched_skills: list[str]
    missing_skills: list[str]
    recommendations: list[str]
    warnings: list[str]
    llm_summary: str | None = None
    # The LLM's *own* estimate of the artifact it produced (ADR 016), stored only
    # on the ``llm`` variant. Surfaced as "AI's own estimate" so it is never
    # confused with the comparable deterministic score.
    llm_self_score: int | None = None
