import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.alert_rule import AlertRule
from app.models.user import User
from app.schemas.alert_rule import (
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
)

router = APIRouter(prefix="/api/alert-rules", tags=["alert-rules"])


async def get_owned_rule(rule_id: uuid.UUID, user: User, db: AsyncSession) -> AlertRule:
    result = await db.execute(
        select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user.id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return rule


@router.get("", response_model=list[AlertRuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = AlertRule(user_id=user.id, **payload.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=AlertRuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    payload: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = await get_owned_rule(rule_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = await get_owned_rule(rule_id, user, db)
    await db.delete(rule)
    await db.commit()
