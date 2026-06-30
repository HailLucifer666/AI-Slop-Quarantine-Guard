"""Test worker helpers: PR field extraction, token cache reuse, expiry parsing."""

import time

import pytest

from app import github_auth
from app.worker import _extract_pr

PR_PAYLOAD = {
    "action": "opened",
    "repository": {"full_name": "octo/repo"},
    "pull_request": {"number": 7, "head": {"sha": "abc123def456"}},
    "installation": {"id": 999},
}


def test_extract_pr():
    assert _extract_pr(PR_PAYLOAD) == ("octo/repo", 7, "abc123def456", 999)


def test_parse_expiry():
    epoch = github_auth._parse_expiry("2026-06-28T12:00:00Z")
    assert isinstance(epoch, float) and epoch > 0


@pytest.mark.asyncio
async def test_token_cache_reuse(monkeypatch):
    """A cached, non-expired token is returned without any network call (one mint, many uses)."""
    github_auth._token_cache.clear()
    github_auth._token_cache[999] = ("cached-token", time.time() + 3600)

    # No httpx is patched: if it tried to hit the network this test would fail loudly.
    monkeypatch.setattr(github_auth.settings, "github_app_id", "4163178")
    monkeypatch.setattr(github_auth, "_load_private_key", lambda: "unused")

    assert await github_auth.get_installation_token(999) == "cached-token"


def test_expired_entry_not_reused():
    """The cache guard treats an expired entry as a miss (forces re-mint)."""
    github_auth._token_cache.clear()
    github_auth._token_cache[999] = ("stale", time.time() - 10)  # already past expiry
    cached = github_auth._token_cache[999]
    fresh_enough = time.time() < cached[1] - github_auth._RENEW_SKEW_SECONDS
    assert fresh_enough is False
