from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import OAuthState, Shop, User
from app.schemas import ShopOut
from app.security import encrypt_secret
from app.services import shopify as shopify_service

router = APIRouter(prefix="/shopify", tags=["shopify"])


@router.get("/install")
def install(
    shop: str = Query(..., description="Shopify domain, e.g. acme.myshopify.com"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    shop_domain = shopify_service.normalize_shop_domain(shop)
    state = shopify_service.new_oauth_state(user.id, shop_domain)
    db.add(state)
    db.commit()
    return {"install_url": shopify_service.build_install_url(shop_domain, state.state)}


@router.get("/callback")
def callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    params = dict(request.query_params)
    if not shopify_service.verify_oauth_hmac(params):
        raise HTTPException(status_code=401, detail="Invalid Shopify OAuth HMAC")

    state_value = params.get("state")
    code = params.get("code")
    shop_param = params.get("shop")
    if not state_value or not code or not shop_param:
        raise HTTPException(status_code=400, detail="Missing OAuth callback parameters")

    shop_domain = shopify_service.normalize_shop_domain(shop_param)
    state = db.get(OAuthState, state_value)
    if not state:
        raise HTTPException(status_code=400, detail="OAuth state is missing or expired")
    expires_at = state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="OAuth state is missing or expired")
    if state.shop_domain != shop_domain:
        raise HTTPException(status_code=400, detail="OAuth state shop mismatch")

    access_token = shopify_service.exchange_code_for_token(shop_domain, code)
    shop = db.scalar(select(Shop).where(Shop.shop_domain == shop_domain))
    if not shop:
        shop = Shop(
            user_id=state.user_id,
            shop_domain=shop_domain,
            access_token_ciphertext=encrypt_secret(access_token),
        )
    else:
        shop.user_id = state.user_id
        shop.access_token_ciphertext = encrypt_secret(access_token)
        shop.is_active = True
        shop.uninstalled_at = None

    db.add(shop)
    db.delete(state)
    db.commit()
    return RedirectResponse(url=f"/static/index.html?shop_connected={shop_domain}", status_code=302)


@router.get("/shops", response_model=list[ShopOut])
def shops(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Shop]:
    return list(db.scalars(select(Shop).where(Shop.user_id == user.id).order_by(Shop.installed_at.desc())))
