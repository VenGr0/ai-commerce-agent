import json
import re
from typing import Any

import bleach
from openai import OpenAI
from pydantic import ValidationError

from app.config import settings
from app.schemas import GenerateCopyRequest, GenerateCopyResult

ALLOWED_TAGS = ["p", "ul", "ol", "li", "strong", "em", "br", "h2", "h3"]
ALLOWED_ATTRS: dict[str, list[str]] = {}


class CopywriterError(RuntimeError):
    pass


def sanitize_description_html(value: str) -> str:
    cleaned = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise CopywriterError("Model did not return JSON") from None
        return json.loads(match.group(0))


def validate_result(data: dict[str, Any]) -> GenerateCopyResult:
    if "description_html" in data and data["description_html"]:
        data["description_html"] = sanitize_description_html(str(data["description_html"]))
    try:
        result = GenerateCopyResult.model_validate(data)
    except ValidationError as exc:
        raise CopywriterError(f"Generated copy failed schema validation: {exc}") from exc

    # Shopify SEO fields are commonly displayed with roughly these practical limits.
    result.meta_title = result.meta_title[:70].strip()
    result.meta_description = result.meta_description[:160].strip()
    result.tags = [tag.strip()[:60] for tag in result.tags if tag.strip()][:20]
    result.bullets = [bullet.strip() for bullet in result.bullets if bullet.strip()][:8]
    result.confidence_notes = [note.strip() for note in result.confidence_notes if note.strip()][:6]
    return result


def fallback_copy(product: dict[str, Any], request: GenerateCopyRequest) -> GenerateCopyResult:
    title = product.get("title") or "Product"
    vendor = product.get("vendor") or "our brand"
    product_type = product.get("productType") or "product"
    keywords = ", ".join(request.primary_keywords[:4]) or product_type
    safe_title = f"{title} | {vendor}"[:120]
    html = sanitize_description_html(
        f"""
        <p><strong>{title}</strong> is a {request.tone} {product_type.lower()} designed for {request.audience}.</p>
        <ul>
          <li>Clear product positioning based on: {keywords}</li>
          <li>Written for the {request.market} market in {request.language}</li>
          <li>Ready to refine with brand-specific benefits and proof points</li>
        </ul>
        <p>Use this description as a safe draft and add verified product specifications before publishing.</p>
        """
    )
    tags = list(dict.fromkeys((product.get("tags") or []) + request.primary_keywords + [product_type]))
    return GenerateCopyResult(
        title=safe_title,
        description_html=html,
        meta_title=safe_title[:70],
        meta_description=f"Shop {title}, a {product_type.lower()} from {vendor}. Clear, practical product information for confident buying."[:160],
        tags=[tag for tag in tags if tag][:20],
        bullets=[
            f"Positioned for {request.audience}",
            f"Optimized around {keywords}",
            "Draft avoids unsupported medical, legal, or absolute claims",
        ],
        confidence_notes=["MOCK_LLM or missing OPENAI_API_KEY: deterministic fallback generated."],
    )


def build_prompt(product: dict[str, Any], request: GenerateCopyRequest) -> str:
    product_payload = {
        "id": product.get("id"),
        "title": product.get("title"),
        "vendor": product.get("vendor"),
        "product_type": product.get("productType"),
        "status": product.get("status"),
        "tags": product.get("tags") or [],
        "current_description_html": product.get("descriptionHtml"),
        "current_seo": product.get("seo"),
    }
    requirements = request.model_dump()
    return json.dumps(
        {
            "task": "Generate Shopify product copy as valid JSON only.",
            "product": product_payload,
            "requirements": requirements,
            "output_schema": {
                "title": "string; customer-facing product title, use original title if unsure",
                "description_html": "string; clean HTML using only p, ul, ol, li, strong, em, br, h2, h3",
                "meta_title": "string; <= 70 chars",
                "meta_description": "string; <= 160 chars",
                "tags": "array of concise Shopify tags",
                "bullets": "array of 3-6 product benefit bullets",
                "confidence_notes": "array listing assumptions and any missing facts",
            },
            "safety_rules": [
                "Do not invent certifications, health claims, legal claims, warranty terms, shipping promises, discounts, or material composition.",
                "Use cautious wording when specs are missing.",
                "Avoid competitor trademarks unless present in source data.",
                "Return JSON only. No markdown fences.",
            ],
        },
        ensure_ascii=False,
    )


def generate_product_copy(product: dict[str, Any], request: GenerateCopyRequest) -> GenerateCopyResult:
    if settings.MOCK_LLM or not settings.OPENAI_API_KEY:
        return fallback_copy(product, request)

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        instructions=(
            "You are an expert e-commerce SEO copywriter. Generate accurate, conversion-oriented "
            "Shopify product copy. You must output JSON only and must not invent unsupported claims."
        ),
        input=build_prompt(product, request),
    )
    raw = response.output_text
    parsed = _extract_json(raw)
    return validate_result(parsed)
