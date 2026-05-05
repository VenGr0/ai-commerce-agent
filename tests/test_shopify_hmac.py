import hashlib
import hmac
from urllib.parse import urlencode

from app.config import settings
from app.services.shopify import verify_oauth_hmac


def test_verify_oauth_hmac(monkeypatch):
    monkeypatch.setattr(settings, "SHOPIFY_API_SECRET", "shpss_test_secret")
    params = {
        "code": "abc",
        "shop": "demo.myshopify.com",
        "state": "state123",
        "timestamp": "1700000000",
    }
    msg = urlencode(sorted(params.items()))
    params["hmac"] = hmac.new(b"shpss_test_secret", msg.encode(), hashlib.sha256).hexdigest()
    assert verify_oauth_hmac(params) is True
