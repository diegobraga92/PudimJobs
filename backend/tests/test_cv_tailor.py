"""Tests for the rule-based CV tailoring engine."""

from app.services.cv_tailor import tailor_cv

CV = {
    "summary": "Backend engineer",
    "experience": [
        {
            "title": "Python Developer",
            "company": "Acme",
            "bullets": ["Built FastAPI services on AWS"],
        },
        {
            "title": "Java Developer",
            "company": "Beta",
            "bullets": ["Maintained Spring applications"],
        },
    ],
    "education": [{"institution": "MIT", "degree": "BSc Computer Science"}],
    "skills": ["python", "java"],
    "projects": [
        {"name": "Job Tracker", "description": "FastAPI + PostgreSQL pipeline"}
    ],
}


def test_tailor_orders_relevant_experience_first():
    tailored = tailor_cv(CV, ["python", "fastapi", "postgresql"])
    assert tailored.experience[0]["title"] == "Python Developer"
    assert tailored.matched_skills == ["python"]
    assert "fastapi" in tailored.missing_skills


def test_tailor_places_matched_skills_first():
    tailored = tailor_cv(CV, ["python"])
    assert tailored.skills[0] == "python"
    assert "java" in tailored.skills  # remaining skill kept


def test_tailor_drops_irrelevant_blocks():
    tailored = tailor_cv(CV, ["python", "fastapi"], drop_irrelevant=True)
    assert len(tailored.experience) == 1
    assert tailored.experience[0]["title"] == "Python Developer"


def test_tailor_keeps_all_when_not_dropping():
    tailored = tailor_cv(CV, ["python", "fastapi"], drop_irrelevant=False)
    assert len(tailored.experience) == 2


def test_tailor_relevance_zero_when_no_match():
    tailored = tailor_cv(CV, ["rust"])
    assert tailored.relevance == 0.0
    assert tailored.missing_skills == ["rust"]


def test_tailor_uses_annotations_to_score():
    annotations = {"experience": [["python"], ["java"]]}
    tailored = tailor_cv(CV, ["java", "spring"], annotations=annotations)
    assert tailored.experience[0]["title"] == "Java Developer"
