"""Tests for the JD parsing service."""

from app.services.jd_parser import parse_jd, parsed_jd_to_dict

SAMPLE_JD = (
    "We are looking for a Senior Python Engineer with 5+ years of experience. "
    "You will build APIs with FastAPI and PostgreSQL on AWS. "
    "A Bachelor's degree in Computer Science is required."
)


def test_parse_jd_extracts_skills_years_education():
    parsed = parse_jd(SAMPLE_JD)
    assert "python" in parsed.skills
    assert "fastapi" in parsed.skills
    assert "postgresql" in parsed.skills
    assert "aws" in parsed.skills
    assert parsed.years_experience == 5
    assert parsed.education_level == "bachelor"


def test_parse_jd_empty_text():
    parsed = parse_jd(None)
    assert parsed.skills == []
    assert parsed.years_experience is None
    assert parsed.education_level is None
    assert parsed.keywords == []


def test_parse_jd_no_years():
    parsed = parse_jd("Looking for a Go developer who knows Docker.")
    assert parsed.years_experience is None
    assert "go" not in parsed.skills  # short tokens are excluded


def test_parse_jd_master_level():
    parsed = parse_jd("M.S. in Statistics and Python expertise expected.")
    assert parsed.education_level == "master"


def test_parsed_jd_to_dict_roundtrip():
    parsed = parse_jd(SAMPLE_JD)
    data = parsed_jd_to_dict(parsed)
    assert set(data) == {"skills", "years_experience", "education_level", "keywords"}
    assert data["years_experience"] == 5
