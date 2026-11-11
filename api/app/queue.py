"""Redis queue: raw webhook delivery + whole-repo scan enqueue + idempotency.

The worker consumes both the webhook queue (PR deliveries) and the scan queue.

Redis is a soft dependency: nothing here may crash the API or the worker when
Redis is down — the API returns 503, the worker backs off and retries (see the
RedisUnavailable contract in worker.py).
"""

import asyncio
import json

import redis.asyncio as aioredis

from app.config import settings

WEBHOOK_QUEUE_KEY = "slopguard:webhook_queue"
SCAN_QUEUE_KEY = "slopguard:scan_queue"
DEDUPE_KEY_PREFIX = "slopguard:delivery:"
DEDUPE_TTL_SECONDS = 86400  # 24h — long enough to cover GitHub's retry window

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Lazily create a module-level async Redis client from settings.

    ``socket_connect_timeout`` keeps a down Redis a fast, typed failure instead
    of a hang; ``health_check_interval`` catches silently dead connections.
    """
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            health_check_interval=30,
        )
    return _redis


def reset_redis_client() -> None:
    """Drop the cached client so the next ``get_redis()`` builds a fresh one.

    Called by the worker after repeated connectivity failures: a stale broken
    connection can keep failing even after Redis comes back. (Probe 2026-11-11:
    without this, a client whose first connect failed is never rebuilt.)
    """
    global _redis
    _redis = None


async def ping_redis(timeout: float = 1.0) -> bool:
    """True iff Redis answers PING within ``timeout`` seconds.

    Health-check helper: never raises, never hangs. A false here means the
    worker is (or will be) backing off in the background, not that the API
    is broken.
    """
    try:
        await asyncio.wait_for(get_redis().ping(), timeout=timeout)
        return True
    except Exception:
        return False


async def already_seen(delivery_guid: str) -> bool:
    """Mark a delivery GUID seen; return True if it was already seen.

    Uses SET NX EX for atomic check-and-set. GitHub retries on timeout/5xx,
    so duplicate deliveries will happen — this is the idempotency guard.
    """
    was_new = await get_redis().set(
        f"{DEDUPE_KEY_PREFIX}{delivery_guid}", "1", nx=True, ex=DEDUPE_TTL_SECONDS
    )
    return not was_new


async def enqueue_webhook_delivery(delivery_guid: str, event: str, payload: dict) -> None:
    """Push a raw webhook delivery onto the Redis queue for the worker (Phase 2)."""
    job = json.dumps({"delivery_guid": delivery_guid, "event": event, "payload": payload})
    await get_redis().lpush(WEBHOOK_QUEUE_KEY, job)


async def enqueue_scan(scan_id: int, source: str, ref: str) -> None:
    """Push a whole-repo scan job onto the scan queue (Stage 2).

    ``ref`` is what the worker ingests from: a clone URL, a local dir path, or a
    temp zip path written by the upload endpoint.
    """
    job = json.dumps({"kind": "scan", "scan_id": scan_id, "source": source, "ref": ref})
    await get_redis().lpush(SCAN_QUEUE_KEY, job)
