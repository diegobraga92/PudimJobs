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


def test_parse_jd_years_range_uses_upper_bound():
    assert parse_jd("We need 3-5 years of experience.").years_experience == 5


def test_parse_jd_years_without_experience_keyword():
    assert parse_jd("Minimum 5 years building distributed systems.").years_experience == 5
    assert parse_jd("At least 4 years in data engineering.").years_experience == 4


def test_parse_jd_seniority_fallback():
    assert parse_jd("Senior backend engineer role.").years_experience == 5
    assert parse_jd("Mid-level frontend developer.").years_experience == 3
    assert parse_jd("Junior developer.").years_experience == 1
    assert parse_jd("We need help with a project.").years_experience is None


def test_parse_jd_extracts_skill_aliases():
    parsed = parse_jd("Kubernetes (k8s) with React.js and C++ experience.")
    assert "kubernetes" in parsed.skills
    assert "react" in parsed.skills
    assert "c++" in parsed.skills
