"""API rate limiting (slowapi, Redis-backed).

The limiter key defaults to the client's remote address. Authenticated
endpoints can use ``auth_key`` to scope by IP + token hash.
"""

import hashlib

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=[],
    headers_enabled=False,
)


def auth_key(request: Request) -> str:
    """Rate-limit key scoped by client IP + a hash of the bearer token."""
    token = request.headers.get("authorization", "")
    digest = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"{get_remote_address(request)}:{digest}"
