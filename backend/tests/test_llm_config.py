"""Tests for the runtime LLM rule shared by the tailor API and the worker.

Both sides must agree: the API advertises the variants a run will produce with
``llm_variant_wanted`` and the worker generates them with the same predicate
(ADR 016), so a client can wait for exactly what is coming.
"""

from app.services.llm_config import (
    LlmRuntimeConfig,
    llm_variant_skip_reason,
    llm_variant_wanted,
)


def _config(*, enabled: bool = True, api_key: str = "sk-x") -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=enabled, api_key=api_key, base_url="http://llm", model="gpt-4o-mini"
    )


def test_llm_variant_is_wanted_when_enabled_with_a_key():
    assert llm_variant_wanted(_config()) is True
    assert llm_variant_skip_reason(_config()) == ""


def test_llm_variant_is_skipped_when_disabled():
    assert llm_variant_wanted(_config(enabled=False)) is False
    assert llm_variant_skip_reason(_config(enabled=False)) == "the LLM is disabled in Admin -> LLM"


def test_llm_variant_is_skipped_without_a_key():
    assert llm_variant_wanted(_config(api_key="")) is False
    assert llm_variant_skip_reason(_config(api_key="")) == "no LLM API key is configured"
