"""API request/response schemas (Pydantic)."""

from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.schemas.generated_cv import GeneratedCVResponse, TailorRequest
from app.schemas.jd import ParsedJDResponse
from app.schemas.job import JobCreate, JobResponse, JobSummary, JobUpdate
from app.schemas.master_cv import (
    CVStructure,
    EducationItem,
    ExperienceItem,
    MasterCVCreate,
    MasterCVResponse,
    MasterCVUpdate,
    ProjectItem,
)
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate

__all__ = [
    "ApplicationCreate",
    "ApplicationResponse",
    "ApplicationUpdate",
    "CVStructure",
    "EducationItem",
    "ExperienceItem",
    "GeneratedCVResponse",
    "JobCreate",
    "JobResponse",
    "JobSummary",
    "JobUpdate",
    "LoginRequest",
    "MasterCVCreate",
    "MasterCVResponse",
    "MasterCVUpdate",
    "ParsedJDResponse",
    "ProjectItem",
    "SourceCreate",
    "SourceResponse",
    "SourceUpdate",
    "TailorRequest",
    "TokenResponse",
    "UserResponse",
]
