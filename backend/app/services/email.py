"""Email delivery via SMTP (Mailpit for local development)."""

import smtplib
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_notification_email(
    *, job_title: str, job_company: str, job_url: str | None, rule_name: str
) -> str:
    template = _env.get_template("notification_email.html.j2")
    return template.render(
        job_title=job_title,
        job_company=job_company,
        job_url=job_url,
        rule_name=rule_name,
    )


def send_email(to: str, subject: str, html: str) -> None:
    """Send an HTML email through the configured SMTP server."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from
    message["To"] = to
    message.set_content("This is an HTML email; please open it in an HTML client.")
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)
