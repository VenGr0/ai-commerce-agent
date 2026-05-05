import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    shops: Mapped[list["Shop"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_domain: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    access_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="shops")
    products: Mapped[list["ProductSnapshot"]] = relationship(
        back_populates="shop", cascade="all, delete-orphan"
    )


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (UniqueConstraint("shop_id", "shopify_gid", name="uq_shop_product"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    shopify_gid: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    description_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    seo_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    shop: Mapped[Shop] = relationship(back_populates="products")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    shopify_gid: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    shop_id: Mapped[str | None] = mapped_column(ForeignKey("shops.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), default="copy_generation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
