from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes_auth import router as auth_router
from app.api.routes_billing import router as billing_router
from app.api.routes_generation import router as generation_router
from app.api.routes_products import router as products_router
from app.api.routes_shopify import router as shopify_router
from app.config import settings
from app.db import init_db

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(shopify_router)
app.include_router(products_router)
app.include_router(generation_router)
app.include_router(billing_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.ENV}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": settings.APP_NAME,
        "docs": "/docs",
        "demo_ui": "/static/index.html",
        "health": "/health",
    }
