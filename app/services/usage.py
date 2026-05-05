from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import UsageEvent, User


def month_start_utc(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def monthly_limit(user: User) -> int:
    active_subscription = user.stripe_subscription_status in {"active", "trialing"}
    if user.plan == "business" and active_subscription:
        return settings.BUSINESS_MONTHLY_CREDITS
    if user.plan == "pro" and active_subscription:
        return settings.PRO_MONTHLY_CREDITS
    return settings.FREE_MONTHLY_CREDITS


def used_credits(db: Session, user_id: str) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.credits), 0)).where(
            UsageEvent.user_id == user_id,
            UsageEvent.created_at >= month_start_utc(),
        )
    )
    return int(total or 0)


def assert_has_credits(db: Session, user: User, requested_credits: int = 1) -> None:
    if not settings.ENFORCE_USAGE_LIMITS:
        return
    if used_credits(db, user.id) + requested_credits > monthly_limit(user):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=402,
            detail="Monthly generation credit limit reached. Upgrade your plan or wait for reset.",
        )


def record_usage(
    db: Session,
    *,
    user_id: str,
    shop_id: str | None,
    job_id: str | None,
    credits: int,
    reason: str = "copy_generation",
) -> UsageEvent:
    event = UsageEvent(
        user_id=user_id,
        shop_id=shop_id,
        job_id=job_id,
        credits=credits,
        reason=reason,
    )
    db.add(event)
    return event
