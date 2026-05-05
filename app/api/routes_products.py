import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import ProductSnapshot, Shop, User
from app.schemas import ProductOut
from app.services import shopify as shopify_service

router = APIRouter(prefix="/products", tags=["products"])


def get_owned_shop(db: Session, user: User, shop_id: str) -> Shop:
    shop = db.get(Shop, shop_id)
    if not shop or shop.user_id != user.id:
        raise HTTPException(status_code=404, detail="Shop not found")
    if not shop.is_active:
        raise HTTPException(status_code=400, detail="Shop is not active")
    return shop


def serialize_product(snapshot: ProductSnapshot) -> ProductOut:
    return ProductOut(
        id=snapshot.id,
        shop_id=snapshot.shop_id,
        shopify_gid=snapshot.shopify_gid,
        title=snapshot.title,
        handle=snapshot.handle,
        vendor=snapshot.vendor,
        product_type=snapshot.product_type,
        status=snapshot.status,
        tags=json.loads(snapshot.tags_json or "[]"),
        seo_title=snapshot.seo_title,
        seo_description=snapshot.seo_description,
        image_url=snapshot.image_url,
        synced_at=snapshot.synced_at,
    )


@router.post("/sync/{shop_id}", response_model=list[ProductOut])
def sync_products(
    shop_id: str,
    first: int = Query(50, ge=1, le=100),
    query_filter: str | None = Query(None, description="Optional Shopify product search query"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    shop = get_owned_shop(db, user, shop_id)
    page = shopify_service.list_products(shop=shop, first=first, query_filter=query_filter)
    snapshots: list[ProductSnapshot] = []
    for edge in page["edges"]:
        product_node = edge["node"]
        existing = db.scalar(
            select(ProductSnapshot).where(
                ProductSnapshot.shop_id == shop.id,
                ProductSnapshot.shopify_gid == product_node["id"],
            )
        )
        incoming = shopify_service.normalize_product_node(shop.id, product_node)
        if existing:
            for attr in [
                "title",
                "handle",
                "vendor",
                "product_type",
                "status",
                "tags_json",
                "description_html",
                "seo_title",
                "seo_description",
                "image_url",
                "raw_json",
                "synced_at",
            ]:
                setattr(existing, attr, getattr(incoming, attr))
            snapshot = existing
        else:
            snapshot = incoming
            db.add(snapshot)
        snapshots.append(snapshot)
    db.commit()
    for snapshot in snapshots:
        db.refresh(snapshot)
    return [serialize_product(snapshot) for snapshot in snapshots]


@router.get("/{shop_id}", response_model=list[ProductOut])
def list_cached_products(
    shop_id: str,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=250),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    get_owned_shop(db, user, shop_id)
    query = select(ProductSnapshot).where(ProductSnapshot.shop_id == shop_id)
    if q:
        query = query.where(ProductSnapshot.title.ilike(f"%{q}%"))
    query = query.order_by(ProductSnapshot.synced_at.desc()).limit(limit)
    return [serialize_product(snapshot) for snapshot in db.scalars(query)]
