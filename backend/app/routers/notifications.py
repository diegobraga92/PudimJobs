import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationListResponse, NotificationResponse

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    total = await db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == user.id)
    )
    unread = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.read.is_(False)
        )
    )
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return NotificationListResponse(
        total=total.scalar() or 0,
        unread=unread.scalar() or 0,
        items=[NotificationResponse.model_validate(n) for n in result.scalars().all()],
    )


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.read = True
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user.id, Notification.read.is_(False)
        )
    )
    for notification in result.scalars().all():
        notification.read = True
    await db.commit()
    return {"updated": True}
