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
    score: int  # 0..100
    method: str  # "heuristic" or "hybrid"
    factors: list[AtsFactor]
    matched_skills: list[str]
    missing_skills: list[str]
    recommendations: list[str]
    warnings: list[str]
    llm_summary: str | None = None
