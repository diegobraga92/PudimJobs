"""Tests for PDF generation (classic + ATS templates)."""

import pytest

from app.services.cv_tailor import tailor_cv
from app.services.pdf_generator import generate_pdf, render_cv_html

CV = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+55 11 91234-5678",
    "location": "Sao Paulo, Brazil",
    "links": ["https://github.com/janedoe"],
    "summary": "Backend engineer",
    "experience": [
        {"title": "Python Developer", "company": "Acme", "bullets": ["Built FastAPI services"]}
    ],
    "education": [{"institution": "MIT", "degree": "BSc"}],
    "skills": ["python", "fastapi"],
    "projects": [],
    "certifications": ["AWS Solutions Architect"],
    "languages": ["English (fluent)"],
}


def test_render_cv_html_contains_sections():
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored, name="Fallback", email="fallback@example.com")
    # Contact from the CV wins over the account-derived fallbacks.
    assert "Jane Doe" in html
    assert "jane@example.com" in html
    assert "fallback@example.com" not in html
    assert "Experience" in html
    assert "Skills" in html


def test_render_cv_html_includes_contact_certifications_and_languages():
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored)
    assert "+55 11 91234-5678" in html
    assert "Sao Paulo, Brazil" in html
    assert "https://github.com/janedoe" in html
    assert "Certifications" in html
    assert "AWS Solutions Architect" in html
    assert "Languages" in html
    assert "English (fluent)" in html


def test_render_cv_html_falls_back_to_account_name():
    tailored = tailor_cv({"summary": "x", "skills": []}, [])
    html = render_cv_html(tailored, name="Jane Doe", email="jane@example.com")
    assert "Jane Doe" in html
    assert "jane@example.com" in html


def test_render_cv_html_ats_template_is_plain_single_column():
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored, template="ats")
    assert "Jane Doe" in html
    assert "Experience" in html
    # ATS layout must avoid constructs parsers struggle with.
    assert "<table" not in html.lower()
    assert "<img" not in html.lower()
    assert "float:" not in html.lower()


def test_render_cv_html_rejects_unknown_template():
    tailored = tailor_cv(CV, ["python"])
    with pytest.raises(ValueError):
        render_cv_html(tailored, template="fancy")


def test_generate_pdf_returns_valid_pdf():
    tailored = tailor_cv(CV, ["python"])
    pdf = generate_pdf(tailored, name="Jane Doe", email="jane@example.com")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500


def test_generate_pdf_with_ats_template():
    tailored = tailor_cv(CV, ["python"])
    pdf = generate_pdf(tailored, template="ats")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500
