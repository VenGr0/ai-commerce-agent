from app.schemas import GenerateCopyRequest
from app.services.copywriter import fallback_copy, sanitize_description_html


def test_sanitize_description_html_strips_script():
    html = sanitize_description_html('<p>Hello</p><script>alert("x")</script>')
    assert "<script>" not in html
    assert "Hello" in html


def test_fallback_copy_returns_valid_result():
    product = {"title": "Bamboo Bottle", "vendor": "Acme", "productType": "Bottle", "tags": ["eco"]}
    req = GenerateCopyRequest(shop_id="s", shopify_gid="gid://shopify/Product/1", primary_keywords=["reusable"])
    result = fallback_copy(product, req)
    assert result.title
    assert "Bamboo Bottle" in result.description_html
    assert "reusable" in result.tags
