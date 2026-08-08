from pydantic import BaseModel


class ParsedJDResponse(BaseModel):
    skills: list[str]
    years_experience: int | None
    education_level: str | None
    keywords: list[str]
