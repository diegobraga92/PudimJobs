"""Tests for API rate limiting (slowapi)."""

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


async def test_rate_limit_returns_429_after_limit():
    limiter = Limiter(key_func=get_remote_address, default_limits=["2/minute"])
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/ping")
    @limiter.limit("2/minute")
    async def ping(request: Request):
        return {"ok": True}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/ping")).status_code == 200
        assert (await client.get("/ping")).status_code == 200
        assert (await client.get("/ping")).status_code == 429
