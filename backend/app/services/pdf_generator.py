"""PDF generation: renders a tailored CV via a Jinja2 template + weasyprint."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.services.cv_tailor import TailoredCV

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

# Logical template name -> Jinja2 file. "classic" stays the default so existing
# exports are unchanged; "ats" is opt-in per request.
TEMPLATES: dict[str, str] = {
    "classic": "cv_template.html.j2",
    "ats": "cv_template_ats.html.j2",
}
DEFAULT_TEMPLATE = "classic"


def render_cv_html(
    tailored: TailoredCV,
    *,
    name: str = "",
    email: str = "",
    template: str = DEFAULT_TEMPLATE,
) -> str:
    """Render a tailored CV to HTML using the named template."""
    try:
        filename = TEMPLATES[template]
    except KeyError as exc:
        raise ValueError(f"Unknown CV template: {template!r}") from exc

    jinja_template = _env.get_template(filename)
    return jinja_template.render(
        name=tailored.full_name or name,
        email=tailored.email or email,
        phone=tailored.phone,
        location=tailored.location,
        links=tailored.links,
        summary=tailored.summary,
        experience=tailored.experience,
        skills=tailored.skills,
        # The LLM variant authors its own labelled categories; the deterministic
        # variant leaves them empty and falls back to the taxonomy grouping. The
        # rule lives on `TailoredCV` so every renderer (PDF, DOCX) agrees.
        skill_groups=tailored.resolved_skill_groups(),
        projects=tailored.projects,
        education=tailored.education,
        certifications=tailored.certifications,
        languages=tailored.languages,
    )


def generate_pdf(
    tailored: TailoredCV,
    *,
    name: str = "",
    email: str = "",
    template: str = DEFAULT_TEMPLATE,
) -> bytes:
    html = render_cv_html(tailored, name=name, email=email, template=template)
    return HTML(string=html).write_pdf()
