"""Test HMAC-SHA256 signature verification (the one real security impl).

Proves verify_github_signature accepts valid signatures, rejects invalid ones.
"""

import pytest
from app.security import verify_github_signature


def test_valid_signature():
    """Valid signature should be accepted."""
    secret = "test_secret"
    raw_body = b"test payload"

    # Compute expected signature
    import hmac
    import hashlib
    computed_hmac = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    )
    signature_header = f"sha256={computed_hmac.hexdigest()}"

    # Verify
    assert verify_github_signature(raw_body, signature_header, secret) is True


def test_invalid_signature():
    """Invalid signature should be rejected."""
    secret = "test_secret"
    raw_body = b"test payload"
    signature_header = "sha256=invalid_signature_hex"

    assert verify_github_signature(raw_body, signature_header, secret) is False


def test_empty_signature():
    """Empty signature should be rejected."""
    secret = "test_secret"
    raw_body = b"test payload"

    assert verify_github_signature(raw_body, "", secret) is False


def test_bad_algorithm():
    """Unsupported algorithm should raise ValueError."""
    secret = "test_secret"
    raw_body = b"test payload"
    signature_header = "sha512=somehash"

    with pytest.raises(ValueError, match="Unsupported algorithm"):
        verify_github_signature(raw_body, signature_header, secret)


def test_malformed_header():
    """Malformed header should raise ValueError."""
    secret = "test_secret"
    raw_body = b"test payload"
    signature_header = "no_equals_sign"

    with pytest.raises(ValueError, match="Invalid signature header format"):
        verify_github_signature(raw_body, signature_header, secret)
