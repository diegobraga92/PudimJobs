"""Runtime LLM configuration: DB-backed row with an env-var fallback."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm_config import LLM_CONFIG_ROW_ID, LLMConfig
from app.services.secrets import decrypt_secret


@dataclass
class LlmRuntimeConfig:
    enabled: bool
    api_key: str
    base_url: str
    model: str


async def get_llm_config(db: AsyncSession) -> LlmRuntimeConfig:
    """Load the DB-backed LLM config, falling back to environment defaults."""
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == LLM_CONFIG_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        return LlmRuntimeConfig(
            enabled=settings.tailoring_llm_enabled,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    return LlmRuntimeConfig(
        enabled=row.enabled,
        api_key=decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else "",
        base_url=row.base_url,
        model=row.model,
    )
