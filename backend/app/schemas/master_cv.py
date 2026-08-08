import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExperienceItem(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    institution: str = Field(min_length=1, max_length=255)
    degree: str = Field(min_length=1, max_length=255)
    year: str | None = None


class ProjectItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    link: str | None = None


class CVStructure(BaseModel):
    summary: str = ""
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)


class MasterCVCreate(BaseModel):
    structured_json: CVStructure
    label: str | None = Field(default=None, max_length=255)


class MasterCVUpdate(BaseModel):
    structured_json: CVStructure | None = None
    label: str | None = Field(default=None, max_length=255)


class MasterCVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    version: int
    is_current: bool
    structured_json: dict
    created_at: datetime
    updated_at: datetime
