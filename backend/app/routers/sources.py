import asyncio
import inspect
import uuid
from types import SimpleNamespace

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from scrapers.utils import is_allowed_by_robots, redact_sensitive
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_audit
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.enums import SourceAuthType, SourceType
from app.models.job import Job
from app.models.source import Source
from app.models.source_auth import SourceAuth
from app.models.user import User
from app.ratelimit import auth_key, limiter
from app.schemas.source import (
    SourceAvoidRequest,
    SourceCreate,
    SourceImportRequest,
    SourceImportResponse,
    SourceImportResult,
    SourcePreviewJob,
    SourcePreviewRequest,
    SourcePreviewResponse,
    SourceResponse,
    SourceUpdate,
)
from app.schemas.source_auth import SourceAuthResponse, SourceAuthUpdate
from app.services.secrets import encrypt_secret
from app.services.source_auth import build_fetch_auth
from app.services.source_config import (
    adapter_metadata,
    manual_metadata,
    provider_metadata,
    validate_source_config,
)
from app.services.source_schedule import is_scrape_due, next_scrape_at
from app.services.source_watchlist import (
    advance_manual_check,
    is_avoided,
    is_due,
    next_check_at,
    set_avoided,
)

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


def _attach_counts(sources: list[Source], counts: dict[uuid.UUID, int]) -> list[SourceResponse]:
    return [_source_response(source, counts.get(source.id, 0)) for source in sources]


def _source_response(source: Source, jobs_count: int) -> SourceResponse:
    """Serialize a source, filling the derived schedule/watchlist fields."""
    avoided = is_avoided(source)
    return SourceResponse.model_validate(source).model_copy(
        update={
            "jobs_count": jobs_count,
            "next_check_at": next_check_at(source),
            "due": is_due(source),
            "next_scrape_at": next_scrape_at(source),
            "scrape_due": is_scrape_due(source) and not avoided,
            "avoided": avoided,
        }
    )


def _validate_config(source_type, config: dict | None) -> None:
    """Reject a config that cannot drive its scraper, as a 422."""
    try:
        validate_source_config(source_type, config)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


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
    return provider_metadata()


@router.get("/adapters")
async def list_adapters(
    user: User = Depends(get_current_user),
):
    """Aggregator adapter metadata, driving the form's adapter dropdown."""
    return adapter_metadata()


@router.get("/manual-metadata")
async def list_manual_metadata(
    user: User = Depends(get_current_user),
):
    """``manual`` (watchlist) contract: cadence bounds, accepted keys, example.

    Declared before ``/{source_id}`` so the literal path is not parsed as a UUID.
    """
    return manual_metadata()


@router.post("/import", response_model=SourceImportResponse)
async def import_sources(
    payload: SourceImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bulk-create sources from a catalog, idempotently per user."""
    existing = await db.execute(select(Source.url, Source.type).where(Source.user_id == user.id))
    known = {(row.url, row.type) for row in existing.all()}

    results: list[SourceImportResult] = []
    created = skipped = invalid = 0
    for index, item in enumerate(payload.sources):
        try:
            validate_source_config(item.type, item.config)
        except ValueError as exc:
            invalid += 1
            results.append(
                SourceImportResult(
                    index=index,
                    status="invalid",
                    name=item.name,
                    url=item.url,
                    reason=str(exc),
                )
            )
            continue

        key = (item.url, item.type)
        if key in known:
            skipped += 1
            results.append(
                SourceImportResult(
                    index=index,
                    status="skipped",
                    name=item.name,
                    url=item.url,
                    reason="already exists",
                )
            )
            continue

        created += 1
        known.add(key)
        if payload.dry_run:
            results.append(
                SourceImportResult(
                    index=index,
                    status="created",
                    name=item.name,
                    url=item.url,
                    reason="dry run",
                )
            )
            continue

        source = Source(user_id=user.id, **item.model_dump())
        db.add(source)
        await db.flush()
        results.append(
            SourceImportResult(
                index=index,
                status="created",
                name=item.name,
                url=item.url,
                source_id=source.id,
            )
        )

    if not payload.dry_run:
        await db.commit()
    return SourceImportResponse(created=created, skipped=skipped, invalid=invalid, results=results)


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_config(payload.type, payload.config)
    source = Source(user_id=user.id, **payload.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _source_response(source, 0)


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    counts = await _job_counts(db, user)
    return _source_response(source, counts.get(source.id, 0))


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await get_owned_source(source_id, user, db)
    updates = payload.model_dump(exclude_unset=True)
    if "config" in updates or "type" in updates:
        # `config` is replaced wholesale, so validate exactly what will be stored.
        effective_type = updates.get("type") or source.type
        effective_config = updates.get("config", source.config)
        _validate_config(effective_type, effective_config)
    # The avoid flag is not a plain column write: it has semantics (ADR 019).
    avoided = updates.pop("avoided", None)
    avoid_reason_sent = "avoid_reason" in updates
    avoid_reason = updates.pop("avoid_reason", None)
    for field, value in updates.items():
        setattr(source, field, value)
    if avoided is not None:
        set_avoided(source, avoided, avoid_reason)
    elif avoid_reason_sent and is_avoided(source):
        # Editing the reason of an already-avoided source.
        set_avoided(source, True, avoid_reason)
    await db.commit()
    await db.refresh(source)
    counts = await _job_counts(db, user)
    return _source_response(source, counts.get(source.id, 0))


@router.post("/{source_id}/avoid", response_model=SourceResponse)
async def set_source_avoided(
    source_id: uuid.UUID,
    payload: SourceAvoidRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Flag a source as *avoid*, or restore it (ADR 019).

    An avoided source is never fetched and never reminded about, but it stays in
    the list as a visible reminder with the optional reason attached. Works for
    every source type and is idempotent: avoiding twice keeps the original
    ``avoided_at``.
    """
    source = await get_owned_source(source_id, user, db)
    set_avoided(source, payload.avoided, payload.reason)
    await db.commit()
    await db.refresh(source)
    counts = await _job_counts(db, user)
    return _source_response(source, counts.get(source.id, 0))


@router.post("/{source_id}/check", response_model=SourceResponse)
async def check_manual_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a manual (watchlist) source as checked *by hand*.

    Stamps ``last_scraped`` and schedules the next reminder; never fetches the
    board. Only meaningful for ``manual`` sources.
    """
    source = await get_owned_source(source_id, user, db)
    if source.type != SourceType.manual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only manual sources can be marked as checked by hand",
        )
    advance_manual_check(source)
    await db.commit()
    await db.refresh(source)
    counts = await _job_counts(db, user)
    return _source_response(source, counts.get(source.id, 0))


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
    """Fetch the source the way the engine would, to validate the credentials.

    Providers build their own URL/body (and key placement), so testing through
    the scraper is what actually proves the key works for *this* source.
    """
    source = await get_owned_source(source_id, user, db)
    record = await _get_auth_record(source_id, db)
    if record is None or not record.credentials_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No authentication configured for this source",
        )
    from scrapers.registry import get_scraper

    auth = build_fetch_auth(record)
    api_key = auth.api_key if auth else None
    try:
        scraper = get_scraper(
            SimpleNamespace(type=source.type, config=source.config), api_key
        )
        fetch_url = getattr(scraper, "first_fetch_url", lambda value: value)(source.url)
        page = await asyncio.wait_for(scraper.fetch(fetch_url, auth=auth), timeout=20)
        return {"ok": True, "status_code": page.status_code}
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "status_code": exc.response.status_code,
            # Keyed APIs explain themselves in the payload ("invalid api key").
            "error": redact_sensitive(str(exc), api_key)[:300],
        }
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return {
            "ok": False,
            "status_code": None,
            "error": redact_sensitive(str(exc), api_key)[:300],
        }


async def _discover_detail_urls(scraper, page) -> list[str]:
    """Detail URLs for a page, tolerating scrapers without the hook."""
    discover = getattr(scraper, "discover_urls", None)
    if not callable(discover):
        return []
    result = discover(page)
    if inspect.isawaitable(result):
        result = await result
    return list(result or [])


def _robots_target(scraper, fetch_url: str) -> str:
    """The URL whose robots.txt applies to a fetch (see the scrape worker)."""
    hook = getattr(scraper, "robots_url", None)
    return hook(fetch_url) if callable(hook) else fetch_url


async def _run_preview(
    *,
    source_type,
    url: str,
    config: dict,
    api_key: str | None = None,
    auth=None,
    respect_robots: bool = False,
) -> SourcePreviewResponse:
    """Fetch + parse once and return a sample — without persisting anything."""
    from scrapers.registry import get_scraper

    if str(source_type) == SourceType.manual.value:
        # Manual sources are hand-checked: there is nothing to fetch, and the
        # ManualScraper's fetch would raise. Report that clearly instead.
        return SourcePreviewResponse(
            fetched_url=url,
            error=(
                "manual source — the engine never fetches it; "
                "open the board yourself to check it by hand"
            ),
        )

    try:
        scraper = get_scraper(SimpleNamespace(type=source_type, config=config), api_key)
    except ValueError as exc:
        return SourcePreviewResponse(fetched_url=url, error=str(exc))

    fetch_url = url
    max_samples = settings.scraper_preview_max_jobs
    timeout = settings.scraper_preview_timeout_seconds
    try:
        # `first_fetch_url` renders provider templates, so a config mistake
        # (e.g. a missing `tenant`) surfaces here and must be reported, not
        # raised: the preview is how users discover such mistakes.
        fetch_url = getattr(scraper, "first_fetch_url", lambda value: value)(url)
        if respect_robots and not is_allowed_by_robots(_robots_target(scraper, fetch_url)):
            return SourcePreviewResponse(
                fetched_url=fetch_url, error="robots.txt disallows this source"
            )
        page = await asyncio.wait_for(scraper.fetch(fetch_url, auth=auth), timeout=timeout)
        raw_jobs = []
        detail_urls = await _discover_detail_urls(scraper, page)
        if detail_urls:
            for detail_url in detail_urls[:max_samples]:
                if respect_robots and not is_allowed_by_robots(
                    _robots_target(scraper, detail_url)
                ):
                    continue
                detail_page = await asyncio.wait_for(
                    scraper.fetch(detail_url, auth=auth), timeout=timeout
                )
                raw_jobs.extend(scraper.parse(detail_page))
        else:
            raw_jobs.extend(scraper.parse(page))
        normalized = scraper.normalize(raw_jobs)
    except TimeoutError:
        return SourcePreviewResponse(
            fetched_url=fetch_url,
            error=f"timed out after {timeout:g}s — the site may be slow or JS-rendered",
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return SourcePreviewResponse(
            fetched_url=fetch_url,
            status_code=getattr(getattr(exc, "response", None), "status_code", None),
            error=redact_sensitive(str(exc), api_key)[:300],
        )

    sample = [
        SourcePreviewJob(
            title=item.get("title") or "",
            company=item.get("company") or "",
            url=item.get("url"),
            posted_date=item.get("posted_date"),
            tags=item.get("tags") or [],
        )
        for item in normalized[:max_samples]
    ]
    return SourcePreviewResponse(
        fetched_url=fetch_url,
        status_code=page.status_code,
        jobs_found=len(normalized),
        sample_jobs=sample,
        truncated=len(normalized) > len(sample),
    )


@router.post("/preview", response_model=SourcePreviewResponse)
@limiter.limit(settings.rate_limit_preview, key_func=auth_key)
async def preview_source_config(
    request: Request,
    payload: SourcePreviewRequest,
    user: User = Depends(get_current_user),
):
    """Dry-run a URL/type/config so selectors can be tuned before saving."""
    return await _run_preview(
        source_type=payload.type, url=payload.url, config=payload.config or {}
    )


@router.post("/{source_id}/preview", response_model=SourcePreviewResponse)
@limiter.limit(settings.rate_limit_preview, key_func=auth_key)
async def preview_source(
    request: Request,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dry-run a saved source, with its stored config and credentials."""
    source = await get_owned_source(source_id, user, db)
    record = await _get_auth_record(source_id, db)
    auth = None
    api_key = None
    if record is not None and record.credentials_encrypted:
        auth = build_fetch_auth(record)
        api_key = auth.api_key if auth else None
    return await _run_preview(
        source_type=source.type,
        url=source.url,
        config=source.config or {},
        api_key=api_key,
        auth=auth,
        respect_robots=source.respect_robots_txt,
    )
