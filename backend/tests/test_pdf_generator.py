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


def test_render_cv_html_groups_skills_by_category():
    """The skills section reads as labelled lines, not a flat keyword dump."""
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored)

    languages = html.index("<strong>Languages:</strong> python")
    frameworks = html.index("<strong>Frameworks:</strong> fastapi")
    assert languages < frameworks


def test_render_cv_html_ats_template_groups_skills_too():
    """The ATS layout stays plain text but keeps the categories."""
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored, template="ats")

    assert "<strong>Languages:</strong> python" in html
    assert "<strong>Frameworks:</strong> fastapi" in html


def test_render_cv_html_omits_the_skills_section_when_there_are_none():
    tailored = tailor_cv({"summary": "x", "skills": []}, [])
    html = render_cv_html(tailored)

    assert "<h2>Skills</h2>" not in html


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


def test_render_cv_html_contact_is_two_nowrap_lines():
    """Contact info splits into a details line and a links line, never mid-value."""
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored)

    assert (
        '<div class="contact-line"><span class="ci">jane@example.com</span>'
        '<span class="ci">+55 11 91234-5678</span>'
        '<span class="ci">Sao Paulo, Brazil</span></div>'
    ) in html
    assert (
        '<div class="contact-line"><span class="ci">https://github.com/janedoe</span></div>'
    ) in html
    # Values stay whole (the separator rides on the following field's ::before).
    assert ".contact .ci { white-space: nowrap; }" in html
    # The old single-line join is gone: a bullet could be orphaned onto its own line.
    assert "jane@example.com • +55" not in html


def test_render_cv_html_shares_one_type_scale():
    """Summary and Experience used to disagree on leading and margins."""
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored)

    assert "line-height: 1.4; }" in html  # body sets the shared leading
    assert "p { margin: 0 0 6px; }" in html  # and the shared margin
    assert ".summary" not in html  # the mismatched override is gone
    assert "line-height: 1.5" not in html


def test_render_cv_html_prefers_llm_skill_groups():
    """A variant that authored its own categories renders those, not the taxonomy."""
    tailored = tailor_cv(CV, ["python"])
    tailored.skill_groups = [("Backend", ["python", "fastapi"])]
    html = render_cv_html(tailored)

    assert "<strong>Backend:</strong> python, fastapi" in html
    assert "<strong>Languages:</strong>" not in html


def test_render_cv_html_never_labels_a_skill_group_other():
    """Unknown skills land in "Additional"; "Other" reads like a junk drawer."""
    tailored = tailor_cv({**CV, "skills": ["python", "stakeholder management"]}, ["python"])
    html = render_cv_html(tailored)

    assert "<strong>Additional:</strong> stakeholder management" in html
    assert "<strong>Other:</strong>" not in html


def test_render_cv_html_ats_template_is_plain_single_column():
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored, template="ats")
    assert "Jane Doe" in html
    assert "Experience" in html
    # ATS layout must avoid constructs parsers struggle with.
    assert "<table" not in html.lower()
    assert "<img" not in html.lower()
    assert "float:" not in html.lower()
    # Values stay whole even though the contact line is allowed to wrap.
    assert ".contact .ci { white-space: nowrap; }" in html


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
