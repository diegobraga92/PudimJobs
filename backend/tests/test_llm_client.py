"""Tests for the shared OpenAI-compatible chat client (ADR 016).

Two production defects are pinned here:

* a thinking-mode provider (DeepSeek ``deepseek-flash``) answers ``200 OK`` with
  an empty ``content`` because the chain-of-thought consumed ``max_tokens`` —
  the client must return ``None`` and log *why*, never raise, and it must send
  the provider's "thinking off" toggle for those endpoints only; and
* a provider that does not support ``response_format`` must not take the whole
  feature down — the call is retried once without it.
"""

import json

import httpx
import pytest
from structlog.testing import capture_logs

from app.services import llm_client
from app.services.llm_client import chat_json, chat_text, request_body
from app.services.llm_config import LlmRuntimeConfig


def _config(
    base_url: str = "https://api.deepseek.com/v1", model: str = "deepseek-flash"
) -> LlmRuntimeConfig:
    return LlmRuntimeConfig(enabled=True, api_key="sk-test", base_url=base_url, model=model)


class _FakeResponse:
    def __init__(
        self,
        *,
        content: str | None,
        status_code: int = 200,
        text: str = "",
        reasoning_content: str | None = None,
        finish_reason: str = "stop",
    ):
        self._payload = {
            "choices": [
                {
                    "message": {"content": content, "reasoning_content": reasoning_content},
                    "finish_reason": finish_reason,
                }
            ]
        }
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Scripted stand-in for ``httpx.AsyncClient``; records every request body."""

    def __init__(self, *responses: _FakeResponse):
        self._responses = list(responses)
        self.requests: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append(json)
        return self._responses.pop(0)


def _patch(monkeypatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: fake)


# --- request body (provider quirks) -----------------------------------------


def test_request_body_disables_thinking_for_deepseek():
    """DeepSeek must be told not to spend the budget on a chain-of-thought."""
    body = request_body(
        _config(), system="s", user="u", max_tokens=4000, temperature=0.2, json_mode=True
    )
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 4000


def test_request_body_leaves_other_providers_alone():
    """``thinking`` is not an OpenAI parameter — it must not be sent there."""
    body = request_body(
        _config(base_url="https://api.openai.com/v1", model="gpt-4o-mini"),
        system="s",
        user="u",
        max_tokens=700,
        temperature=0,
    )
    assert "thinking" not in body
    assert "response_format" not in body  # only JSON callers ask for it


# --- happy path -------------------------------------------------------------


async def test_chat_json_parses_a_fenced_reply(monkeypatch):
    fake = _FakeClient(_FakeResponse(content='```json\n{"score": 90}\n```'))
    _patch(monkeypatch, fake)

    assert await chat_json(
        _config(), system="s", user="u", max_tokens=700, temperature=0, label="LLM ATS review"
    ) == {"score": 90}
    assert fake.requests[0]["thinking"] == {"type": "disabled"}


# --- the bug: 200 OK with nothing to parse ----------------------------------


async def test_chat_json_returns_none_when_thinking_ate_the_answer(monkeypatch):
    """A thinking budget overrun is a 200 with empty content — not a success."""
    fake = _FakeClient(
        _FakeResponse(
            content="",
            reasoning_content="Let me think about the job description...",
            finish_reason="length",
        )
    )
    _patch(monkeypatch, fake)

    with capture_logs() as logs:
        result = await chat_json(
            _config(), system="s", user="u", max_tokens=4000, temperature=0.2
        )

    assert result is None
    empty = [entry for entry in logs if entry["event"] == "llm_empty_content"]
    assert len(empty) == 1
    # The one log line has to be enough to identify the cause.
    assert empty[0]["reasoning_content"] is True
    assert empty[0]["finish_reason"] == "length"
    assert empty[0]["max_tokens"] == 4000
    assert empty[0]["model"] == "deepseek-flash"


async def test_chat_json_returns_none_on_a_whitespace_only_reply(monkeypatch):
    _patch(monkeypatch, _FakeClient(_FakeResponse(content="   \n")))

    assert await chat_json(_config(), system="s", user="u", max_tokens=10, temperature=0) is None


# --- never raises -----------------------------------------------------------


class _DownClient:
    """Transport that refuses to connect (the endpoint is unreachable)."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *args, **kwargs):
        raise httpx.ConnectError("connection refused")


async def test_chat_call_returns_none_when_the_endpoint_is_unreachable(monkeypatch):
    """A dead endpoint degrades every caller instead of failing it."""
    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda *a, **k: _DownClient())

    with capture_logs() as logs:
        result = await chat_json(_config(), system="s", user="u", max_tokens=700, temperature=0)

    assert result is None
    failed = [entry for entry in logs if entry["event"] == "llm_request_failed"]
    assert len(failed) == 1
    assert "connection refused" in failed[0]["error"]


@pytest.mark.parametrize(
    ("reply", "event"),
    [("definitely not json", "llm_invalid_json"), ("[1, 2, 3]", "llm_json_not_an_object")],
)
async def test_chat_json_rejects_a_non_usable_reply(monkeypatch, reply, event):
    _patch(monkeypatch, _FakeClient(_FakeResponse(content=reply)))

    with capture_logs() as logs:
        result = await chat_json(_config(), system="s", user="u", max_tokens=10, temperature=0)

    assert result is None
    assert any(entry["event"] == event for entry in logs)


# --- response_format compatibility ------------------------------------------


async def test_chat_json_retries_without_json_mode_when_the_provider_rejects_it(monkeypatch):
    """A provider without ``response_format`` must still work."""
    fake = _FakeClient(
        _FakeResponse(
            content=None,
            status_code=400,
            text='{"error": {"message": "Unrecognized request argument: response_format"}}',
        ),
        _FakeResponse(content=json.dumps({"ok": True})),
    )
    _patch(monkeypatch, fake)

    result = await chat_json(_config(), system="s", user="u", max_tokens=10, temperature=0)

    assert result == {"ok": True}
    assert len(fake.requests) == 2
    assert "response_format" in fake.requests[0]
    assert "response_format" not in fake.requests[1]


async def test_chat_json_does_not_retry_an_unrelated_bad_request(monkeypatch):
    """Only a complaint about ``response_format`` is retried (no double billing)."""
    fake = _FakeClient(
        _FakeResponse(content=None, status_code=400, text='{"error": "bad model name"}')
    )
    _patch(monkeypatch, fake)

    assert await chat_json(_config(), system="s", user="u", max_tokens=10, temperature=0) is None
    assert len(fake.requests) == 1


# --- guards -----------------------------------------------------------------


async def test_chat_text_refuses_to_call_without_an_api_key(monkeypatch):
    fake = _FakeClient(_FakeResponse(content="should never be reached"))
    _patch(monkeypatch, fake)

    config = LlmRuntimeConfig(
        enabled=True, api_key="", base_url="https://api.deepseek.com/v1", model="deepseek-flash"
    )
    assert await chat_text(config, system="s", user="u", max_tokens=10, temperature=0) is None
    assert fake.requests == []
