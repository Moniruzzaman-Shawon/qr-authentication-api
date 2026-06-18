"""Signed QR payload helpers.

Each QR encodes the customer verify URL plus a short HMAC signature derived from
the product id and ``QR_SIGNING_KEY``. The verify/check endpoints reject requests
with a missing or invalid signature, so an attacker cannot probe or fabricate
verification URLs for arbitrary UUIDs even if a UUID is leaked.
"""
import hashlib
import hmac

from django.conf import settings


def make_signature(product_id):
    """Return a URL-safe HMAC signature for a product id."""
    key = settings.QR_SIGNING_KEY.encode('utf-8')
    msg = str(product_id).encode('utf-8')
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    # 16 hex chars (64 bits) is ample for a tamper check on an already-unguessable UUID.
    return digest[:16]


def verify_signature(product_id, signature):
    if not signature:
        return False
    return hmac.compare_digest(make_signature(product_id), str(signature))


def build_verify_url(product_id):
    base = settings.FRONTEND_URL.rstrip('/')
    return f"{base}/verify/{product_id}?sig={make_signature(product_id)}"
