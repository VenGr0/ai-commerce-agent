import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import HTTPException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.models import OAuthState, ProductSnapshot, Shop
from app.security import decrypt_secret, encrypt_secret

SHOP_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$")


class ShopifyApiError(RuntimeError):
    pass


def normalize_shop_domain(shop: str) -> str:
    candidate = shop.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
    if "." not in candidate:
        candidate = f"{candidate}.myshopify.com"
    if not SHOP_RE.match(candidate):
        raise HTTPException(status_code=400, detail="Invalid Shopify shop domain")
    return candidate


def verify_oauth_hmac(query_params: dict[str, str]) -> bool:
    received_hmac = query_params.get("hmac")
    if not received_hmac or not settings.SHOPIFY_API_SECRET:
        return False
    message_pairs = []
    for key in sorted(query_params):
        if key in {"hmac", "signature"}:
            continue
        message_pairs.append((key, query_params[key]))
    message = urlencode(message_pairs)
    digest = hmac.new(
        settings.SHOPIFY_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, received_hmac)


def build_install_url(shop_domain: str, state: str) -> str:
    params = {
        "client_id": settings.SHOPIFY_API_KEY,
        "scope": ",".join(settings.shopify_scope_list),
        "redirect_uri": f"{settings.PUBLIC_BASE_URL}/shopify/callback",
        "state": state,
    }
    return f"https://{shop_domain}/admin/oauth/authorize?{urlencode(params)}"


def new_oauth_state(user_id: str, shop_domain: str) -> OAuthState:
    return OAuthState(
        state=secrets.token_urlsafe(32),
        user_id=user_id,
        shop_domain=shop_domain,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )


def exchange_code_for_token(shop_domain: str, code: str) -> str:
    if not settings.SHOPIFY_API_KEY or not settings.SHOPIFY_API_SECRET:
        raise HTTPException(status_code=500, detail="Shopify credentials are not configured")
    response = requests.post(
        f"https://{shop_domain}/admin/oauth/access_token",
        json={
            "client_id": settings.SHOPIFY_API_KEY,
            "client_secret": settings.SHOPIFY_API_SECRET,
            "code": code,
        },
        timeout=20,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Shopify OAuth failed: {response.text}")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="Shopify OAuth response did not include access_token")
    return token


def shop_access_token(shop: Shop) -> str:
    return decrypt_secret(shop.access_token_ciphertext)


def set_shop_access_token(shop: Shop, access_token: str) -> None:
    shop.access_token_ciphertext = encrypt_secret(access_token)


@retry(
    retry=retry_if_exception_type(ShopifyApiError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
def graphql(shop_domain: str, access_token: str, query: str, variables: dict[str, Any] | None = None) -> dict:
    endpoint = f"https://{shop_domain}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
    response = requests.post(
        endpoint,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        },
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    if response.status_code in {429, 500, 502, 503, 504}:
        raise ShopifyApiError(f"Transient Shopify error: {response.status_code} {response.text}")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Shopify API error: {response.text}")
    payload = response.json()
    if payload.get("errors"):
        raise HTTPException(status_code=502, detail={"shopify_errors": payload["errors"]})
    return payload["data"]


PRODUCT_FIELDS = """
id
legacyResourceId
title
handle
vendor
productType
status
tags
descriptionHtml
seo { title description }
featuredMedia { preview { image { url altText } } }
"""


PRODUCTS_QUERY = f"""
query Products($first: Int!, $after: String, $query: String) {{
  products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT, reverse: true) {{
    pageInfo {{ hasNextPage endCursor }}
    edges {{ node {{ {PRODUCT_FIELDS} }} }}
  }}
}}
"""


PRODUCT_QUERY = f"""
query Product($id: ID!) {{
  product(id: $id) {{ {PRODUCT_FIELDS} }}
}}
"""


PRODUCT_UPDATE_MUTATION = """
mutation UpdateProduct($product: ProductUpdateInput!) {
  productUpdate(product: $product) {
    product {
      id
      title
      handle
      tags
      descriptionHtml
      seo { title description }
    }
    userErrors { field message }
  }
}
"""


def extract_image_url(product: dict[str, Any]) -> str | None:
    return (
        product.get("featuredMedia", {})
        .get("preview", {})
        .get("image", {})
        .get("url")
    )


def normalize_product_node(shop_id: str, product: dict[str, Any]) -> ProductSnapshot:
    seo = product.get("seo") or {}
    return ProductSnapshot(
        shop_id=shop_id,
        shopify_gid=product["id"],
        title=product.get("title") or "Untitled product",
        handle=product.get("handle"),
        vendor=product.get("vendor"),
        product_type=product.get("productType"),
        status=product.get("status"),
        tags_json=json.dumps(product.get("tags") or [], ensure_ascii=False),
        description_html=product.get("descriptionHtml"),
        seo_title=seo.get("title"),
        seo_description=seo.get("description"),
        image_url=extract_image_url(product),
        raw_json=json.dumps(product, ensure_ascii=False),
    )


def list_products(
    *, shop: Shop, first: int = 50, after: str | None = None, query_filter: str | None = None
) -> dict[str, Any]:
    data = graphql(
        shop.shop_domain,
        shop_access_token(shop),
        PRODUCTS_QUERY,
        {"first": first, "after": after, "query": query_filter},
    )
    return data["products"]


def get_product(*, shop: Shop, product_gid: str) -> dict[str, Any]:
    data = graphql(shop.shop_domain, shop_access_token(shop), PRODUCT_QUERY, {"id": product_gid})
    product = data.get("product")
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in Shopify")
    return product


def update_product_copy(
    *,
    shop: Shop,
    product_gid: str,
    title: str | None,
    description_html: str,
    meta_title: str,
    meta_description: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    product_input: dict[str, Any] = {
        "id": product_gid,
        "descriptionHtml": description_html,
        "seo": {"title": meta_title, "description": meta_description},
    }
    if title:
        product_input["title"] = title
    if tags:
        product_input["tags"] = tags[:250]

    data = graphql(
        shop.shop_domain,
        shop_access_token(shop),
        PRODUCT_UPDATE_MUTATION,
        {"product": product_input},
    )
    result = data["productUpdate"]
    if result.get("userErrors"):
        raise HTTPException(status_code=422, detail={"shopify_user_errors": result["userErrors"]})
    return result["product"]
