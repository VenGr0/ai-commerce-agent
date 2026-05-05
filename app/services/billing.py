import stripe
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User


def configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def price_id_for_plan(plan: str) -> str:
    if plan == "pro":
        return settings.STRIPE_PRO_PRICE_ID
    if plan == "business":
        return settings.STRIPE_BUSINESS_PRICE_ID
    raise HTTPException(status_code=400, detail="Unsupported billing plan")


def create_checkout_session(db: Session, user: User, plan: str) -> str:
    if not configured():
        raise HTTPException(status_code=501, detail="Stripe is not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_id = price_id_for_plan(plan)
    if not price_id:
        raise HTTPException(status_code=500, detail=f"Stripe price ID for {plan} is missing")

    if not user.stripe_customer_id:
        customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
        user.stripe_customer_id = customer["id"]
        db.add(user)
        db.commit()
        db.refresh(user)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.PUBLIC_BASE_URL}/static/index.html?billing=success",
        cancel_url=f"{settings.PUBLIC_BASE_URL}/static/index.html?billing=cancelled",
        metadata={"user_id": user.id, "plan": plan},
        subscription_data={"metadata": {"user_id": user.id, "plan": plan}},
        allow_promotion_codes=True,
    )
    return session["url"]


async def handle_webhook(request: Request, db: Session) -> dict[str, str]:
    if not configured() or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=501, detail="Stripe webhook is not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as exc:  # Stripe throws several concrete exception classes.
        raise HTTPException(status_code=400, detail=f"Invalid Stripe webhook: {exc}") from exc

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = obj.get("metadata", {}).get("user_id")
        plan = obj.get("metadata", {}).get("plan")
        user = db.get(User, user_id) if user_id else None
        if user:
            user.plan = plan or user.plan
            user.stripe_subscription_id = obj.get("subscription")
            user.stripe_subscription_status = "active"
            db.add(user)
            db.commit()

    if event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription = obj
        user_id = subscription.get("metadata", {}).get("user_id")
        plan = subscription.get("metadata", {}).get("plan")
        user = db.get(User, user_id) if user_id else None
        if not user and subscription.get("customer"):
            user = db.scalar(select(User).where(User.stripe_customer_id == subscription["customer"]))
        if user:
            user.stripe_subscription_id = subscription.get("id")
            user.stripe_subscription_status = subscription.get("status")
            if plan:
                user.plan = plan
            if subscription.get("status") in {"canceled", "unpaid", "incomplete_expired"}:
                user.plan = "free"
            db.add(user)
            db.commit()

    return {"status": "ok"}
