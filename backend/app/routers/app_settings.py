"""Admin settings API (currently: LLM configuration)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import LLMConfig, User
from app.models.llm_config import LLM_CONFIG_ROW_ID
from app.ratelimit import limiter
from app.schemas.llm_config import LLMConfigResponse, LLMConfigUpdate
from app.services.secrets import decrypt_secret, encrypt_secret, mask_secret

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])


async def _get_or_create_row(db: AsyncSession) -> LLMConfig:
    result = await db.execute(select(LLMConfig).where(LLMConfig.id == LLM_CONFIG_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        row = LLMConfig(id=LLM_CONFIG_ROW_ID)
        db.add(row)
        await db.flush()
    return row


def _current_plain_key(row: LLMConfig) -> str:
    if row.api_key_encrypted:
        return decrypt_secret(row.api_key_encrypted)
    return settings.openai_api_key


def _to_response(row: LLMConfig) -> LLMConfigResponse:
    return LLMConfigResponse(
        id=row.id,
        enabled=row.enabled,
        base_url=row.base_url,
        model=row.model,
        api_key_masked=mask_secret(_current_plain_key(row)),
        updated_at=row.updated_at,
    )


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> LLMConfigResponse:
    """Return the global LLM config (the API key is masked)."""
    return _to_response(await _get_or_create_row(db))


@router.put("/llm", response_model=LLMConfigResponse)
async def update_llm(
    payload: LLMConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> LLMConfigResponse:
    """Upsert the global LLM config; a provided ``api_key`` is encrypted."""
    row = await _get_or_create_row(db)

    changes: dict = {}
    for field in ("enabled", "base_url", "model"):
        current = getattr(row, field)
        new_value = getattr(payload, field)
        if new_value != current:
            changes[field] = {"before": current, "after": new_value}
            setattr(row, field, new_value)

    if payload.api_key is not None and payload.api_key.strip():
        encrypted = encrypt_secret(payload.api_key.strip())
        if encrypted != row.api_key_encrypted:
            changes["api_key"] = "updated"  # never store the secret in audit
            row.api_key_encrypted = encrypted

    await db.commit()
    await db.refresh(row)

    if changes:
        await log_audit(
            db,
            user_id=admin.id,
            action="updated",
            entity_type="llm_config",
            entity_id=row.id,
            changes=changes,
        )
        await db.commit()

    return _to_response(row)


@router.post("/llm/test")
@limiter.limit("10/minute")
async def test_llm(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Validate the configured LLM endpoint/model/key with a tiny request."""
    row = await _get_or_create_row(db)
    key = _current_plain_key(row)
    if not row.enabled or not key:
        raise HTTPException(
            status_code=400,
            detail="LLM is not enabled or no API key is configured",
        )
    url = f"{row.base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": row.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
        return {
            "ok": response.status_code == 200,
            "status_code": response.status_code,
            "model": row.model,
        }
    except Exception as exc:  # noqa: BLE001 - connection errors are reported to the UI
        return {"ok": False, "status_code": None, "error": str(exc)[:300]}
