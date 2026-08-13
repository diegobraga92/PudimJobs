import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from scrapers.utils import fetch_html
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.enums import SourceAuthType
from app.models.job import Job
from app.models.source import Source
from app.models.source_auth import SourceAuth
from app.models.user import User
from app.ratelimit import auth_key, limiter
from app.schemas.source import SourceCreate, SourceResponse, SourceUpdate
from app.schemas.source_auth import SourceAuthResponse, SourceAuthUpdate
from app.services.secrets import encrypt_secret
from app.services.source_auth import build_fetch_auth

router = APIRouter(prefix="/api/sources", tags=["sources"])


async def get_owned_source(source_id: uuid.UUID, user: User, db: AsyncSession) -> Source:
    """Fetch a source owned by the current user or raise 404."""
    result = await db.execute(
        select(Source).where(Source.id == source_id, Source.user_id == user.id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return source


async def _job_counts(db: AsyncSession, user: User) -> dict[uuid.UUID, int]:
    """Map source_id → number of jobs scraped by the current user."""
    result = await db.execute(
        select(Job.source_id, func.count(Job.id))
        .where(Job.user_id == user.id, Job.source_id.is_not(None))
        .group_by(Job.source_id)
    )
    return {source_id: count for source_id, count in result.all()}


def _attach_counts(
    sources: list[Source], counts: dict[uuid.UUID, int]
) -> list[SourceResponse]:
    return [
        SourceResponse.model_validate(source).model_copy(
            update={"jobs_count": counts.get(source.id, 0)}
        )
        for source in sources
    ]


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Source).where(Source.user_id == user.id).order_by(Source.created_at.desc())
    )
    sources = result.scalars().all()
    counts = await _job_counts(db, user)
    return _attach_counts(list(sources), counts)


@router.get("/providers")
async def list_providers(
    user: User = Depends(get_current_user),
):
    """Discovery provider metadata, driving the source form's provider dropdown."""
    from scrapers.discovery import DISCOVERY_PROVIDERS

    return [
        {
            "name": cls.provider_name,
            "family": cls.family,
            "requires_key": cls.requires_key,
        }
        for cls in DISCOVERY_PROVIDERS.values()
    ]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = Source(user_id=user.id, **payload.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_owned_source(source_id, user, db)


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    await db.delete(source)
    await db.commit()


async def _get_auth_record(source_id: uuid.UUID, db: AsyncSession) -> SourceAuth | None:
    result = await db.execute(select(SourceAuth).where(SourceAuth.source_id == source_id))
    return result.scalar_one_or_none()


async def _auth_response(record: SourceAuth | None) -> SourceAuthResponse:
    return SourceAuthResponse(
        auth_type=record.auth_type if record else SourceAuthType.none,
        has_auth=bool(record and record.credentials_encrypted),
        updated_at=record.updated_at if record else None,
    )


@router.get("/{source_id}/auth", response_model=SourceAuthResponse)
async def get_source_auth(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return whether a source has auth configured (never the secret itself)."""
    await get_owned_source(source_id, user, db)
    return await _auth_response(await _get_auth_record(source_id, db))


@router.put("/{source_id}/auth", response_model=SourceAuthResponse)
async def update_source_auth(
    source_id: uuid.UUID,
    payload: SourceAuthUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Store encrypted auth credentials (bearer token or API key)."""
    await get_owned_source(source_id, user, db)

    if payload.auth_type in (SourceAuthType.token, SourceAuthType.api_key):
        secret = {
            SourceAuthType.token: payload.token,
            SourceAuthType.api_key: payload.api_key,
        }[payload.auth_type]
        if not secret or not secret.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Provide a value for {payload.auth_type.value} auth",
            )

    record = await _get_auth_record(source_id, db)
    if record is None:
        record = SourceAuth(source_id=source_id)
        db.add(record)

    record.auth_type = payload.auth_type
    if payload.auth_type == SourceAuthType.none:
        record.credentials_encrypted = None
    else:
        secret = {
            SourceAuthType.token: payload.token,
            SourceAuthType.api_key: payload.api_key,
        }[payload.auth_type]
        record.credentials_encrypted = encrypt_secret(secret.strip())

    await db.commit()
    await db.refresh(record)
    await log_audit(
        db,
        user_id=user.id,
        action="updated",
        entity_type="source_auth",
        entity_id=record.id,
        changes={"auth_type": payload.auth_type.value},  # never the secret
    )
    await db.commit()
    return await _auth_response(record)


@router.delete("/{source_id}/auth", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_auth(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove a source's stored credentials."""
    await get_owned_source(source_id, user, db)
    record = await _get_auth_record(source_id, db)
    if record is not None:
        await db.delete(record)
        await log_audit(
            db,
            user_id=user.id,
            action="deleted",
            entity_type="source_auth",
            entity_id=record.id,
        )
        await db.commit()


@router.post("/{source_id}/auth/test")
@limiter.limit(settings.rate_limit_api, key_func=auth_key)
async def test_source_auth(
    request: Request,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch the source URL with the stored credentials to validate them."""
    source = await get_owned_source(source_id, user, db)
    record = await _get_auth_record(source_id, db)
    if record is None or not record.credentials_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authentication configured for this source",
        )
    try:
        page = await fetch_html(source.url, timeout=20, auth=build_fetch_auth(record))
        return {"ok": True, "status_code": page.status_code}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "status_code": exc.response.status_code,
            "error": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return {"ok": False, "status_code": None, "error": str(exc)[:300]}
