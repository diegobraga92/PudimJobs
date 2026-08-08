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


def render_cv_html(tailored: TailoredCV, *, name: str = "", email: str = "") -> str:
    template = _env.get_template("cv_template.html.j2")
    return template.render(
        name=name,
        email=email,
        summary=tailored.summary,
        experience=tailored.experience,
        skills=tailored.skills,
        projects=tailored.projects,
        education=tailored.education,
    )


def generate_pdf(tailored: TailoredCV, *, name: str = "", email: str = "") -> bytes:
    html = render_cv_html(tailored, name=name, email=email)
    return HTML(string=html).write_pdf()
