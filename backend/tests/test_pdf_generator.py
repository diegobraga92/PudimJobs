"""Tests for PDF generation."""

from app.services.cv_tailor import tailor_cv
from app.services.pdf_generator import generate_pdf, render_cv_html

CV = {
    "summary": "Backend engineer",
    "experience": [
        {"title": "Python Developer", "company": "Acme", "bullets": ["Built FastAPI services"]}
    ],
    "education": [{"institution": "MIT", "degree": "BSc"}],
    "skills": ["python", "fastapi"],
    "projects": [],
}


def test_render_cv_html_contains_sections():
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored, name="Jane Doe", email="jane@example.com")
    assert "Jane Doe" in html
    assert "jane@example.com" in html
    assert "Experience" in html
    assert "Skills" in html


def test_generate_pdf_returns_valid_pdf():
    tailored = tailor_cv(CV, ["python"])
    pdf = generate_pdf(tailored, name="Jane Doe", email="jane@example.com")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500
