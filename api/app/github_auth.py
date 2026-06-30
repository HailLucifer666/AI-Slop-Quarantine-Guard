"""GitHub App JWT → installation token chain + cache (Phase 2).

Mints a short-lived RS256 App-JWT, exchanges it for a 1-hour installation token,
and caches the token per installation until ~5 min before expiry. Installation
tokens allow 15,000 req/hr — minting one per request would be wasteful, so reuse.
"""

import time
from datetime import datetime

import httpx
import jwt

from app.config import settings

GITHUB_API = "https://api.github.com"
_RENEW_SKEW_SECONDS = 300  # renew 5 min before expiry

# installation_id -> (token, expiry_epoch)
_token_cache: dict[int, tuple[str, float]] = {}


def _load_private_key() -> str:
    """Return the App private key from inline setting or .pem file path."""
    if settings.github_app_private_key:
        return settings.github_app_private_key.replace("\\n", "\n")
    if settings.github_app_private_key_path:
        with open(settings.github_app_private_key_path, "r", encoding="utf-8") as fh:
            return fh.read()
    raise RuntimeError("No GitHub App private key configured (set GITHUB_APP_PRIVATE_KEY[_PATH])")


def _mint_app_jwt(app_id: str, private_key: str) -> str:
    """Mint an RS256 App-JWT (iss=App ID, valid ~10 min, iat backdated 60s for clock skew)."""
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 600, "iss": app_id}, private_key, algorithm="RS256")


def _parse_expiry(expires_at: str) -> float:
    """Parse GitHub's ISO expiry (e.g. '2026-06-28T12:00:00Z') to an epoch float."""
    return datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()


async def get_installation_token(installation_id: int, app_id: str = "", private_key: str = "") -> str:
    """Get a cached (or freshly minted) installation token for an installation.

    Args default to values from settings so callers only need the installation_id.
    """
    app_id = app_id or settings.github_app_id
    private_key = private_key or _load_private_key()

    cached = _token_cache.get(installation_id)
    if cached and time.time() < cached[1] - _RENEW_SKEW_SECONDS:
        return cached[0]

    app_jwt = _mint_app_jwt(app_id, private_key)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
        )
    resp.raise_for_status()
    data = resp.json()
    token, expiry = data["token"], _parse_expiry(data["expires_at"])
    _token_cache[installation_id] = (token, expiry)
    return token
