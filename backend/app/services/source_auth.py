"""Build an authenticated fetch context from a stored ``SourceAuth`` row."""

from scrapers.types import FetchAuth

from app.models.enums import SourceAuthType
from app.models.source_auth import SourceAuth
from app.services.secrets import decrypt_secret


def build_fetch_auth(record: SourceAuth | None) -> FetchAuth | None:
    """Return the ``FetchAuth`` for a source, or ``None`` when no auth is set."""
    if record is None or not record.credentials_encrypted:
        return None
    raw = decrypt_secret(record.credentials_encrypted)
    if record.auth_type == SourceAuthType.cookies:
        return FetchAuth(cookies=raw)
    if record.auth_type == SourceAuthType.token:
        return FetchAuth(headers={"Authorization": f"Bearer {raw}"})
    return None
