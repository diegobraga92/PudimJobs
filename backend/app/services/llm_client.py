"""The one place an OpenAI-compatible chat completion is called (ADR 016).

Every LLM feature in PudimJobs — CV structuring (``cv_parser``), bullet
rephrasing and the full-CV rewrite (``cv_tailor``) and the ATS review overlay
(``ats_scorer``) — goes through this transport, so the provider quirks and the
failure diagnostics live in exactly one place:

* **Thinking-mode models.** Some providers (DeepSeek's ``deepseek-flash`` /
  ``deepseek-reasoner``) emit a chain-of-thought *before* the answer and share
  ``max_tokens`` with it. With a tight budget the API still answers ``200 OK``
  while ``content`` comes back empty, which used to drop every feature onto its
  rule-based path with no visible reason. The toggle is provider-specific
  (``thinking`` is not an OpenAI parameter), so it is only sent to DeepSeek
  endpoints — where ``temperature`` is ignored as long as thinking is on.
* **JSON mode.** ``response_format`` asks for a bare JSON object, so a
  prose-wrapped or explained reply cannot break parsing. A provider that does
  not know the parameter is retried once without it.
* **Never raises.** A failed call, or a reply with no usable content, returns
  ``None`` after logging *why* — the callers all degrade gracefully, and that
  reason used to be invisible ("it only ever kept the deterministic CV").
"""

import json

import httpx
import structlog

from app.services.cv_schema import strip_code_fence
from app.services.llm_config import LlmRuntimeConfig

logger = structlog.get_logger(__name__)

# Endpoint marker for the providers that need the thinking toggle below.
_DEEPSEEK_MARKER = "deepseek"
# A chain-of-thought is pure overhead for the output shapes we ask for.
_THINKING_OFF = {"type": "disabled"}
# Ask for a bare JSON object rather than prose that may wrap or precede it.
_JSON_OBJECT = {"type": "json_object"}
# Status codes a provider uses to reject an unknown request parameter.
_UNSUPPORTED_PARAMETER = (400, 422)


def request_body(
    config: LlmRuntimeConfig,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> dict:
    """The exact payload posted to ``{base_url}/chat/completions``.

    Public so the admin "Test connection" probe can exercise the same request
    (including the provider-specific thinking toggle) as the real features.
    """
    body: dict = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if _DEEPSEEK_MARKER in config.base_url.lower():
        body["thinking"] = _THINKING_OFF
    if json_mode:
        body["response_format"] = _JSON_OBJECT
    return body


def _rejects_json_mode(response: httpx.Response) -> bool:
    """True when the provider does not recognise ``response_format``."""
    return (
        response.status_code in _UNSUPPORTED_PARAMETER
        and "response_format" in response.text.lower()
    )


async def _post(
    config: LlmRuntimeConfig, body: dict, *, label: str, timeout: float
) -> httpx.Response | None:
    """POST ``body``; drop ``response_format`` and retry if it is unsupported."""
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            if _rejects_json_mode(response):
                logger.info("llm_json_mode_unsupported", call=label, base_url=config.base_url)
                response = await client.post(
                    url,
                    headers=headers,
                    json={key: value for key, value in body.items() if key != "response_format"},
                )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            "llm_request_failed",
            call=label,
            model=config.model,
            error=str(exc)[:300],
            exc_info=True,
        )
        return None
    return response


def _content(
    response: httpx.Response, *, config: LlmRuntimeConfig, max_tokens: int, label: str
) -> str | None:
    """The assistant's text, or ``None`` (logged) when there is nothing to use."""
    try:
        choice = response.json()["choices"][0]
        message = choice.get("message") or {}
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
        logger.warning("llm_unexpected_response", call=label, model=config.model, error=str(exc))
        return None
    content = (message.get("content") or "").strip()
    if not content:
        # 200 OK with nothing to parse: typically a thinking-mode model that spent
        # the whole `max_tokens` budget on `reasoning_content` (see module doc).
        # Naming every input here is what makes this single log line enough.
        logger.warning(
            "llm_empty_content",
            call=label,
            model=config.model,
            finish_reason=choice.get("finish_reason"),
            reasoning_content=bool(message.get("reasoning_content")),
            max_tokens=max_tokens,
        )
        return None
    return content


async def _fetch(
    config: LlmRuntimeConfig,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
    timeout: float,
    label: str,
) -> str | None:
    """Send one request and return the assistant's text (``None`` on failure)."""
    if not config.api_key:
        logger.warning("llm_call_without_api_key", call=label, model=config.model)
        return None
    body = request_body(
        config,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
    )
    response = await _post(config, body, label=label, timeout=timeout)
    if response is None:
        return None
    return _content(response, config=config, max_tokens=max_tokens, label=label)


async def chat_text(
    config: LlmRuntimeConfig,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    timeout: float = 60.0,
    label: str = "LLM request",
) -> str | None:
    """Ask for free-form text; ``None`` on any failure (already logged)."""
    return await _fetch(
        config,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=False,
        timeout=timeout,
        label=label,
    )


async def chat_json(
    config: LlmRuntimeConfig,
    *,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    timeout: float = 60.0,
    label: str = "LLM request",
) -> dict | None:
    """Ask for a JSON object; ``None`` on any failure (already logged).

    Markdown fences are tolerated (``strip_code_fence``), anything that is not a
    JSON *object* is rejected, and no exception ever reaches the caller.
    """
    content = await _fetch(
        config,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
        timeout=timeout,
        label=label,
    )
    if content is None:
        return None
    try:
        parsed = json.loads(strip_code_fence(content))
    except json.JSONDecodeError as exc:
        logger.warning(
            "llm_invalid_json",
            call=label,
            model=config.model,
            error=str(exc),
            reply=content[:200],
        )
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            "llm_json_not_an_object", call=label, model=config.model, reply=content[:200]
        )
        return None
    return parsed
