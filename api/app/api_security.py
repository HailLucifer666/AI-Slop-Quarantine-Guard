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


async def rate_limit(request: Request) -> None:
    """Allow at most ``settings.rate_limit_per_minute`` requests per client IP per
    minute. <=0 disables; a Redis error fails open (request allowed)."""
    limit = settings.rate_limit_per_minute
    if limit <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    key = f"sqg:rl:{ip}:{window}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
    except Exception:  # noqa: BLE001 — Redis down → don't lock users out
        return
    if count > limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded; try again shortly")
