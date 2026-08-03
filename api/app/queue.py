"""Redis queue: raw webhook delivery + whole-repo scan enqueue + idempotency.

The worker consumes both the webhook queue (PR deliveries) and the scan queue.
"""

import json

import redis.asyncio as aioredis

from app.config import settings

WEBHOOK_QUEUE_KEY = "slopguard:webhook_queue"
SCAN_QUEUE_KEY = "slopguard:scan_queue"
# Reliable-queue pattern: a job moves source -> processing (atomically, via
# RPOPLPUSH) and is only LREM'd out of processing once the worker has fully
# handled it (success or recorded failure) — see reserve_job/ack_job. A worker
# crash between reserve and ack leaves the job sitting safely in `processing`,
# recoverable on the next startup (see recover_orphaned_jobs), instead of a bare
# BRPOP that discards the job from Redis the instant it's popped.
WEBHOOK_PROCESSING_KEY = f"{WEBHOOK_QUEUE_KEY}:processing"
SCAN_PROCESSING_KEY = f"{SCAN_QUEUE_KEY}:processing"
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


# (source queue key, its processing-list key) pairs the worker polls in
# round-robin. Redis has no multi-key BRPOPLPUSH, so — unlike the old single
# BRPOP([key1, key2]) call — the worker tries each source in turn.
QUEUE_PAIRS = (
    (WEBHOOK_QUEUE_KEY, WEBHOOK_PROCESSING_KEY),
    (SCAN_QUEUE_KEY, SCAN_PROCESSING_KEY),
)


async def reserve_job(source_key: str, processing_key: str) -> str | None:
    """Atomically move one job (if any) from `source_key` to `processing_key`,
    returning its raw JSON, or None if the source is empty right now."""
    return await get_redis().rpoplpush(source_key, processing_key)


async def ack_job(processing_key: str, raw: str) -> None:
    """Remove a job from its processing list once it's been fully handled
    (successfully or with its failure recorded) — never before."""
    await get_redis().lrem(processing_key, 1, raw)


async def recover_orphaned_jobs() -> int:
    """Startup recovery: move anything left in a processing list back onto its
    source queue. With this product's single-worker deployment shape, a job
    sitting in `processing` at startup can only be a leftover from a previous
    crash (not a peer worker actively handling it), so it's always safe to
    requeue. Returns the number of jobs recovered."""
    redis = get_redis()
    recovered = 0
    for source_key, processing_key in QUEUE_PAIRS:
        while True:
            raw = await redis.rpoplpush(processing_key, source_key)
            if raw is None:
                break
            recovered += 1
    return recovered
