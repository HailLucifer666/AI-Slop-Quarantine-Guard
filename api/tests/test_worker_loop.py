"""Worker loop resilience: Redis outages must never kill the consumer.

Three outcomes of _safe_brpop stay distinguishable: job / idle timeout / Redis
unavailable. The unavailable case raises RedisUnavailable (the caller backs off
and retries); idle stays None so a healthy empty queue is never logged as an
outage.
"""

import pytest
import redis

from app import worker


def test_backoff_schedule_caps_at_10():
    assert worker._backoff_seconds(0) == 1.0
    assert worker._backoff_seconds(1) == 2.0
    assert worker._backoff_seconds(2) == 5.0
    assert worker._backoff_seconds(3) == 10.0
    assert worker._backoff_seconds(99) == 10.0


class _BrokenRedis:
    async def brpop(self, keys, timeout=5):
        raise redis.exceptions.ConnectionError("redis down")


class _IdleRedis:
    async def brpop(self, keys, timeout=5):
        return None


class _WorkingRedis:
    async def brpop(self, keys, timeout=5):
        return ("slopguard:scan_queue", '{"kind": "scan", "scan_id": 1}')


@pytest.mark.asyncio
async def test_safe_brpop_raises_unavailable_on_connection_error():
    """Mutation (2026-11-11): delete the except in _safe_brpop -> the raw
    ConnectionError escapes instead of RedisUnavailable; this test fails."""
    with pytest.raises(worker.RedisUnavailable):
        await worker._safe_brpop(_BrokenRedis())


@pytest.mark.asyncio
async def test_safe_brpop_idle_timeout_is_none():
    """An idle BRPOP expiry is normal queue sleep — never an outage."""
    assert await worker._safe_brpop(_IdleRedis()) is None


@pytest.mark.asyncio
async def test_safe_brpop_returns_item_on_success():
    assert await worker._safe_brpop(_WorkingRedis()) == (
        "slopguard:scan_queue",
        '{"kind": "scan", "scan_id": 1}',
    )
