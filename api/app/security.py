"""HMAC-SHA256 webhook signature verification (constant-time, real impl).

This is security-critical and non-stubbed.
"""

import hmac
import hashlib
from typing import Optional


def verify_github_signature(
    raw_body: bytes, signature_header: str, secret: str
) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature (constant-time).

    Args:
        raw_body: Raw request body bytes (before any parsing).
        signature_header: X-Hub-Signature-256 header value (format: "sha256=<hex>").
        secret: GITHUB_WEBHOOK_SECRET from config.

    Returns:
        True if signature is valid, False otherwise.

    Raises:
        ValueError: If signature header format is invalid.
    """
    if not signature_header:
        return False

    # Parse header: format is "sha256=<hex>"
    try:
        algo, expected_sig = signature_header.split("=", 1)
    except ValueError:
        raise ValueError("Invalid signature header format")

    if algo != "sha256":
        raise ValueError(f"Unsupported algorithm: {algo}")

    # Compute HMAC
    computed_hmac = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    )
    computed_sig = computed_hmac.hexdigest()

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_sig, expected_sig)
