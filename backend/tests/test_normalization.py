"""Unit tests for the normalization service."""

from app.services.normalization import (
    normalize_company,
    normalize_skill,
    normalize_skills,
    normalize_title,
)


def test_company_map_lookup():
    assert normalize_company("Google LLC") == "Google"
    assert normalize_company("Google Inc.") == "Google"
    assert normalize_company("Acme Corporation") == "Acme"


def test_company_suffix_cleanup_fallback():
    assert normalize_company("Acme Manufacturing Inc.") == "Acme Manufacturing"


def test_company_empty():
    assert normalize_company(None) == ""
    assert normalize_company("") == ""


def test_title_map():
    assert normalize_title("Sr. Software Engineer") == "Senior Software Engineer"
    assert normalize_title("VP of Engineering") == "VP of Engineering"


def test_title_unknown_passthrough():
    assert normalize_title("Cloud Architect") == "Cloud Architect"


def test_skill_alias_mapping():
    assert normalize_skill("react.js") == "react"
    assert normalize_skill("K8s") == "kubernetes"
    assert normalize_skill("NodeJS") == "node.js"
    assert normalize_skill("NLP") == "natural language processing"


def test_skills_list_mapping():
    assert normalize_skills(["react.js", "postgres", "docker"]) == [
        "react",
        "postgresql",
        "docker",
    ]
