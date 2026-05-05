from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    plan: str
    stripe_subscription_status: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ShopOut(BaseModel):
    id: str
    shop_domain: str
    is_active: bool
    installed_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: str
    shop_id: str
    shopify_gid: str
    title: str
    handle: str | None = None
    vendor: str | None = None
    product_type: str | None = None
    status: str | None = None
    tags: list[str] = []
    seo_title: str | None = None
    seo_description: str | None = None
    image_url: str | None = None
    synced_at: datetime


class GenerateCopyRequest(BaseModel):
    shop_id: str
    shopify_gid: str
    publish: bool = False
    language: str = "English"
    market: str = "United States"
    tone: Literal[
        "premium",
        "friendly",
        "technical",
        "minimalist",
        "playful",
        "luxury",
        "eco",
        "neutral",
    ] = "neutral"
    audience: str = "online shoppers"
    primary_keywords: list[str] = Field(default_factory=list, max_length=12)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=20)
    include_title: bool = True
    include_tags: bool = True
    description_word_target: int = Field(default=180, ge=80, le=500)


class GenerateCopyResult(BaseModel):
    title: str
    description_html: str
    meta_title: str
    meta_description: str
    tags: list[str]
    bullets: list[str]
    confidence_notes: list[str]


class GenerationJobOut(BaseModel):
    id: str
    user_id: str
    shop_id: str
    shopify_gid: str
    status: str
    publish: bool
    input: dict
    output: dict | None = None
    error: str | None = None
    credits_charged: int
    created_at: datetime
    updated_at: datetime


class CheckoutRequest(BaseModel):
    plan: Literal["pro", "business"]


class CheckoutOut(BaseModel):
    checkout_url: str


class UsageOut(BaseModel):
    plan: str
    used_credits: int
    monthly_limit: int
    remaining_credits: int
