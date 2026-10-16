"""Tests for PDF generation (classic + ATS templates)."""

import pytest
from weasyprint import HTML
from weasyprint.formatting_structure import boxes

from app.services.cv_labels import labels_for
from app.services.cv_tailor import TailoredCV, tailor_cv
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

# The header that exposed the wrap (ADR 021): five fields, 109 characters, which
# DejaVu Sans fits on one row at 8pt (472.9pt of the 493.2pt text block) but not
# at the 9.5pt the template used.
REPORTED_HEADER = {
    "full_name": "Diego Braga",
    "email": "diego.braga92@gmail.com",
    "phone": "+55 12 98801-8904",
    "location": "Brazil",
    "links": ["github.com/diegobraga92", "linkedin.com/in/diegobraga92"],
    "skills": [],
}


def _boxes(box):
    """Depth-first walk of WeasyPrint's box tree."""
    yield box
    for child in getattr(box, "children", None) or []:
        yield from _boxes(child)


def _is_contact_block(box) -> bool:
    element = getattr(box, "element", None)
    if getattr(box, "element_tag", None) != "div" or element is None:
        return False
    return "contact" in (element.get("class") or "").split()


def _text_of(box) -> str:
    """Every character box under ``box``, in visual order."""
    if isinstance(box, boxes.TextBox):
        return box.text
    return "".join(_text_of(child) for child in getattr(box, "children", None) or [])


def _contact_lines(html: str) -> list[str]:
    """The contact block as the renderer laid it out: one string per rendered line.

    WeasyPrint exposes no public box API, so this walks the private ``_page_box``:
    the coupling is deliberate, because "does the header wrap, and where" is a
    property of the *rendered* page. The old two-line header passed every
    string-level test in this module, which is what let the wrap ship.
    """
    page_box = getattr(HTML(string=html).render().pages[0], "_page_box", None)
    if page_box is None:  # pragma: no cover - guards a WeasyPrint upgrade
        pytest.skip("WeasyPrint no longer exposes a page box tree to walk")

    contact = next((box for box in _boxes(page_box) if _is_contact_block(box)), None)
    assert contact is not None, "contact block not found in the rendered page"
    return [_text_of(box) for box in _boxes(contact) if isinstance(box, boxes.LineBox)]


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


def test_render_cv_html_contact_is_one_flowing_line():
    """Every field shares one line — no forced details-then-links split (ADR 021)."""
    tailored = tailor_cv(CV, ["python"])
    html = render_cv_html(tailored)

    assert html.count('<div class="contact">') == 1
    # The pre-split shape is gone: it was only there to stop the block
    # overflowing the page edge, which the breakable separator now handles.
    assert '<div class="contact-line">' not in html
    for bit in (
        "jane@example.com",
        "+55 11 91234-5678",
        "Sao Paulo, Brazil",
        "https://github.com/janedoe",
    ):
        assert f'<span class="ci">{bit}</span>' in html
    # Fields stay whole: the break opportunity lives in the separator, not in a value.
    assert '<span class="sep"> • </span>' in html
    assert ".contact .ci { white-space: nowrap; }" in html
    # 8pt is what makes five fields fit in 17.4cm of DejaVu Sans (ADR 021).
    assert ".contact { color: #555; font-size: 8pt; margin-bottom: 14px; }" in html
    # So the content box is the width the @page margin promises, not 8px less.
    assert "body { margin: 0;" in html


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
    # Values stay whole even though the contact line is allowed to wrap, and the
    # line renders at the 8pt that keeps five fields on one row (ADR 021).
    assert ".contact .ci { white-space: nowrap; }" in html
    assert ".contact { margin: 0 0 14px; font-size: 8pt; }" in html


def test_render_cv_html_rejects_unknown_template():
    tailored = tailor_cv(CV, ["python"])
    with pytest.raises(ValueError):
        render_cv_html(tailored, template="fancy")


@pytest.mark.parametrize("template", ["classic", "ats"])
def test_contact_header_renders_as_a_single_line(template):
    """The reported five-field header fits on one line in both templates (ADR 021)."""
    html = render_cv_html(tailor_cv(REPORTED_HEADER, []), template=template)

    separator = " | " if template == "ats" else " • "
    assert _contact_lines(html) == [
        separator.join(
            [
                "diego.braga92@gmail.com",
                "+55 12 98801-8904",
                "Brazil",
                "github.com/diegobraga92",
                "linkedin.com/in/diegobraga92",
            ]
        )
    ]


@pytest.mark.parametrize("template", ["classic", "ats"])
def test_contact_header_keeps_every_field_when_it_has_to_wrap(template):
    """A header too long for one line wraps *between* fields, never mid-token (ADR 021)."""
    padded = {**REPORTED_HEADER, "location": "Sao Paulo, Brazil (open to relocation)"}
    html = render_cv_html(tailor_cv(padded, []), template=template)

    lines = _contact_lines(html)
    assert len(lines) == 2
    # A mid-token split would leave the value on neither line; a clean break
    # leaves it whole on exactly one.
    for field in (
        "diego.braga92@gmail.com",
        "+55 12 98801-8904",
        "Sao Paulo, Brazil (open to relocation)",
        "github.com/diegobraga92",
        "linkedin.com/in/diegobraga92",
    ):
        assert sum(field in line for line in lines) == 1, field


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


# --- Localised headings (ADR 024) -------------------------------------------


def test_render_cv_html_localises_every_heading():
    """The headings are chrome: they must match the translated content."""
    tailored = TailoredCV.from_structure(
        {
            "full_name": "Jane Doe",
            "summary": "Engenheira backend",
            "experience": [
                {"company": "Acme", "title": "Dev", "start_date": "2020-01", "bullets": ["x"]}
            ],
            "education": [{"institution": "MIT", "degree": "BSc"}],
            "skills": ["python"],
            "projects": [{"name": "PudimJobs", "description": "Job tracker"}],
            "certifications": ["AWS Solutions Architect"],
            "languages": ["Inglês (fluente)"],
        }
    )
    html = render_cv_html(tailored, labels=labels_for("pt-BR"))

    assert '<html lang="pt-BR">' in html
    for heading in (
        "Resumo",
        "Experiência",
        "Competências",
        "Projetos",
        "Formação",
        "Certificações",
        "Idiomas",
    ):
        assert f"<h2>{heading}</h2>" in html, heading
    for english in ("Summary", "Experience", "Education", "Certifications"):
        assert f"<h2>{english}</h2>" not in html, english


def test_render_cv_html_localises_the_open_ended_date():
    """A current role dates to "Atual" under PT-BR, not "Present"."""
    tailored = TailoredCV.from_structure(
        {
            "summary": "x",
            "experience": [
                {"company": "Acme", "title": "Dev", "start_date": "2020-01", "bullets": []}
            ],
        }
    )
    html = render_cv_html(tailored, labels=labels_for("pt-BR"))

    assert "2020-01 \u2013 Atual" in html
    assert "Present" not in html


def test_render_cv_html_localises_the_skill_group_labels():
    """The group labels travel inside the translated structure: a PT-BR export of
    a CV that groups by taxonomy shows `Linguagens`, not `Languages`."""
    tailored = TailoredCV.from_structure(
        {
            "summary": "x",
            "skills": ["python", "Docker"],
            "skill_groups": [
                {"label": "Linguagens", "items": ["python"]},
                {"label": "Ferramentas", "items": ["Docker"]},
            ],
        }
    )
    html = render_cv_html(tailored, labels=labels_for("pt-BR"))

    assert "<strong>Linguagens:</strong> python" in html
    assert "<strong>Ferramentas:</strong> Docker" in html
    assert "<strong>Languages:</strong>" not in html


def test_render_cv_html_ats_template_is_localised_too():
    html = render_cv_html(
        tailor_cv(CV, ["python"]), template="ats", labels=labels_for("pt-BR")
    )

    assert "<h2>Resumo</h2>" in html
    assert "<h2>Formação</h2>" in html


def test_generate_pdf_with_localised_labels_returns_a_valid_pdf():
    pdf = generate_pdf(tailor_cv(CV, ["python"]), labels=labels_for("pt-BR"))

    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 500

