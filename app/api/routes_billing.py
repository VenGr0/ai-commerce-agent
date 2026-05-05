from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import User
from app.schemas import CheckoutOut, CheckoutRequest
from app.services.billing import create_checkout_session, handle_webhook

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout", response_model=CheckoutOut)
def checkout(
    payload: CheckoutRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> CheckoutOut:
    return CheckoutOut(checkout_url=create_checkout_session(db, user, payload.plan))


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    return await handle_webhook(request, db)
