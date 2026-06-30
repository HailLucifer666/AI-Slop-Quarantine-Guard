"""Redis queue: raw webhook delivery + whole-repo scan enqueue + idempotency.

The worker consumes both the webhook queue (PR deliveries) and the scan queue.
"""

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

WEBHOOK_QUEUE_KEY = "slopguard:webhook_queue"
SCAN_QUEUE_KEY = "slopguard:scan_queue"
DEDUPE_KEY_PREFIX = "slopguard:delivery:"
DEDUPE_TTL_SECONDS = 86400  # 24h — long enough to cover GitHub's retry window

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Lazily create a module-level async Redis client from settings."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


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
