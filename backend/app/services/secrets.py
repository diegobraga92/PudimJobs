"""Encryption helpers for secret values (API keys, source credentials).

Uses Fernet (AES-128-CBC + HMAC) from the ``cryptography`` package. The key
comes from ``settings.fernet_key``; in development a key is derived
deterministically from ``settings.secret_key`` so no extra setup is needed,
but production MUST set ``FERNET_KEY`` to a real key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest).decode("ascii")
    return Fernet(key.encode("utf-8"))


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext secret and return the Fernet token string."""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token produced by :func:`encrypt_secret`."""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")


def mask_secret(value: str | None) -> str | None:
    """Return a masked preview of a secret (first 4 + last 4 chars)."""
    if not value:
        return None
    if len(value) <= 8:
        return "•" * 8
    return f"{value[:4]}…{value[-4:]}"
