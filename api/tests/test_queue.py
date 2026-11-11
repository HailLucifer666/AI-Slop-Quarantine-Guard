"""Queue resilience: ping_redis never raises, reset_redis_client rebuilds.

Redis is a soft dependency — these pin the helpers the API and worker use to
tell "Redis is down" apart from "everything is fine".
"""

import pytest
import redis

from app import queue


class _RaisingRedis:
    async def ping(self):
        raise redis.exceptions.ConnectionError("redis down")


class _OkRedis:
    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_ping_redis_false_when_client_raises(monkeypatch):
    """Mutation (2026-11-11): drop the `except Exception` in ping_redis -> the
    ConnectionError escapes to the caller. With it, we get a clean False."""
    monkeypatch.setattr(queue, "get_redis", lambda: _RaisingRedis())
    assert await queue.ping_redis() is False


@pytest.mark.asyncio
async def test_ping_redis_true_when_client_responds(monkeypatch):
    monkeypatch.setattr(queue, "get_redis", lambda: _OkRedis())
    assert await queue.ping_redis() is True


def test_reset_redis_client_drops_cached_client():
    """Mutation (2026-11-11): make reset_redis_client a no-op -> the stale cached
    client survives and this test fails."""
    saved = queue._redis
    queue._redis = object()
    try:
        queue.reset_redis_client()
        assert queue._redis is None
    finally:
        queue._redis = saved
