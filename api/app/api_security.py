"""Scan-API protection (Sprint A): API-key auth + per-IP rate limiting.

Both are FastAPI dependencies reusing the existing Redis. They close the
"anyone can trigger unlimited repo clones via POST /api/scans" hole.

* ``require_api_key`` — if ``settings.api_key`` is set, require a matching
  ``X-API-Key`` header (constant-time compare). Empty key = open mode so the
  local dashboard works out of the box (mirrors the demo-mode AuthGate).
* ``rate_limit`` — a fixed-window per-minute counter keyed by client IP, applied
  even in open mode so an unauthenticated instance still can't be abused.
  Fail-open: if Redis is down we allow the request (availability over a hard
  lockout — the same fail-safe stance the analyzers take).
"""

import hmac
import time

from fastapi import Header, HTTPException, Request

from app.config import settings
from app.queue import get_redis


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Reject the request unless a configured API key matches (open if unset)."""
    expected = settings.api_key
    if not expected:
        return  # no key configured → open mode (dev / demo)
    if not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


# Forwarded-client headers, most specific first. Trusted ONLY because the platform
# proxy is the sole ingress and overwrites them on every inbound request — never trust
# these when the app is reachable directly, since a client can set any header it likes.
_CLIENT_IP_HEADERS = ("fly-client-ip", "cf-connecting-ip", "x-real-ip")


def _client_ip(request: Request) -> str:
    """The end client's address, not the proxy's.

    ``request.client.host`` is the peer of the TCP connection. Behind fly.io that is the
    proxy for EVERY caller, so a "per-IP" window silently became one global bucket: all
    users shared a single 60/min allowance and any one caller could exhaust it for
    everybody. Falls back to the peer address when no forwarded header is present, which
    is the correct answer for a direct local connection.
    """
    for header in _CLIENT_IP_HEADERS:
        value = request.headers.get(header, "").strip()
        if value:
            # x-real-ip is single-valued, but be tolerant of a comma list.
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    """Allow at most ``settings.rate_limit_per_minute`` requests per client IP per
    minute. <=0 disables; a Redis error fails open (request allowed)."""
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    window = int(time.time() // 60)
    key = f"sqg:rl:{_client_ip(request)}:{window}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        over_limit = count > limit
    except Exception:  # noqa: BLE001 — Redis down → don't lock users out
        return
    # Inside the same try/except as the counter: reading `count` after the handler meant
    # an expire() failure skipped the check entirely for that request.
    if over_limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded; try again shortly")
