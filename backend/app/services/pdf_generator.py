"""PDF generation: renders a tailored CV via a Jinja2 template + weasyprint.

Two templates ship: ``classic`` (the styled default) and ``ats`` (a plain,
single-column layout designed to be parsed cleanly by applicant tracking
systems — see ADR 013).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.services.cv_tailor import TailoredCV
from app.services.skill_matcher import group_skills

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
    """Render a tailored CV to HTML using the named template.

    Contact values embedded in the CV itself take precedence over the
    ``name``/``email`` fallbacks (which are derived from the user account).
    """
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
        # The flat list stays available; the templates render this grouped view
        # so the Skills section reads as categories instead of a keyword dump.
        skill_groups=group_skills(tailored.skills),
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
