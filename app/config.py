from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: Literal["dev", "test", "prod"] = "dev"
    APP_NAME: str = "AI Commerce Copy Agent"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "sqlite:///./commerce_agent.db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-only-change-me"
    FERNET_KEY: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    CORS_ORIGINS: str = "http://localhost:8000"

    SHOPIFY_API_KEY: str = ""
    SHOPIFY_API_SECRET: str = ""
    SHOPIFY_API_VERSION: str = "2026-04"
    SHOPIFY_SCOPES: str = "read_products,write_products"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.2"
    MOCK_LLM: bool = False

    FREE_MONTHLY_CREDITS: int = 50
    PRO_MONTHLY_CREDITS: int = 5000
    BUSINESS_MONTHLY_CREDITS: int = 50000
    ENFORCE_USAGE_LIMITS: bool = True

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRO_PRICE_ID: str = ""
    STRIPE_BUSINESS_PRICE_ID: str = ""

    CELERY_ALWAYS_EAGER: bool = False

    @field_validator("PUBLIC_BASE_URL")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def shopify_scope_list(self) -> list[str]:
        return [scope.strip() for scope in self.SHOPIFY_SCOPES.split(",") if scope.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
