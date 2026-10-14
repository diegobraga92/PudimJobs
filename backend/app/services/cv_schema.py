"""The JSON shape of a structured CV, shared by the LLM prompts (ADR 016)."""

import re

# Mirrors ``app.schemas.master_cv.CVStructure`` field for field.
CV_JSON_SCHEMA = (
    '{"full_name": "string", "email": "string", "phone": "string", '
    '"location": "string", "links": ["string"], '
    '"summary": "string", "experience": [{"company": "string", "title": "string", '
    '"start_date": "YYYY-MM or null", "end_date": "YYYY-MM or null", '
    '"bullets": ["string"]}], "education": [{"institution": "string", "degree": "string", '
    '"year": "string or null"}], "skills": ["string"], '
    '"skill_groups": [{"label": "string", "items": ["string"]}], '
    '"projects": [{"name": "string", "description": "string or null", '
    '"link": "string or null"}], "certifications": ["string"], "languages": ["string"]}'
)


def strip_code_fence(content: str) -> str:
    """Return ``content`` without a surrounding Markdown ``` fence, if any."""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()
