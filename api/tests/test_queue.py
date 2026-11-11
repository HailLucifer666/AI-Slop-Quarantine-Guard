"""Queue tests: soft-dependency helpers (ping/reset) + the reliable-queue pattern.

Redis is a soft dependency — ping_redis never raises and reset_redis_client
rebuilds a stale client. The reliable-queue half pins reserve_job/ack_job/
recover_orphaned_jobs: a job is never lost between being popped and being fully
handled.
"""

import pytest
import redis

from app import queue
from app import queue as queue_mod
from app.queue import (
    QUEUE_PAIRS,
    SCAN_PROCESSING_KEY,
    SCAN_QUEUE_KEY,
    ack_job,
    reserve_job,
    recover_orphaned_jobs,
)


class _RaisingRedis:
    async def ping(self):
        raise redis.exceptions.ConnectionError("redis down")


class _OkRedis:
    async def ping(self):
        return True


class _FakeAwaitable:
    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _finish():
            return self._value
        return _finish().__await__()


@pytest.mark.asyncio
async def test_await_result_unwraps_awaitable_and_passthrough():
    """Mutation (2026-11-11): drop the isinstance branch -> an already-awaited
    plain value (redis stubs union Awaitable[T] | T) is returned but a real
    awaitable would be returned unawaited and this test fails."""
    assert await queue._await_result(_FakeAwaitable(7)) == 7
    assert await queue._await_result("plain") == "plain"
    assert await queue._await_result(None) is None


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


class _FakeListRedis:
    """Minimal in-memory stand-in supporting the list ops the queue module uses."""

    def __init__(self):
        self.lists: dict[str, list[str]] = {}

    def _l(self, key):
        return self.lists.setdefault(key, [])

    async def lpush(self, key, value):
        self._l(key).insert(0, value)

    async def rpoplpush(self, src, dst):
        lst = self._l(src)
        if not lst:
            return None
        val = lst.pop()
        self._l(dst).insert(0, val)
        return val

    async def lrem(self, key, count, value):
        lst = self._l(key)
        for i, v in enumerate(lst):
            if v == value:
                del lst[i]
                return 1
        return 0


@pytest.fixture
def fake_redis(monkeypatch):
    r = _FakeListRedis()
    monkeypatch.setattr(queue_mod, "get_redis", lambda: r)
    return r


@pytest.mark.asyncio
async def test_reserve_job_moves_from_source_to_processing(fake_redis):
    await fake_redis.lpush(SCAN_QUEUE_KEY, '{"scan_id": 1}')

    raw = await reserve_job(SCAN_QUEUE_KEY, SCAN_PROCESSING_KEY)

    assert raw == '{"scan_id": 1}'
    assert fake_redis.lists[SCAN_QUEUE_KEY] == []
    assert fake_redis.lists[SCAN_PROCESSING_KEY] == ['{"scan_id": 1}']


@pytest.mark.asyncio
async def test_reserve_job_returns_none_when_source_empty(fake_redis):
    assert await reserve_job(SCAN_QUEUE_KEY, SCAN_PROCESSING_KEY) is None


@pytest.mark.asyncio
async def test_ack_job_removes_from_processing(fake_redis):
    await fake_redis.lpush(SCAN_QUEUE_KEY, '{"scan_id": 1}')
    raw = await reserve_job(SCAN_QUEUE_KEY, SCAN_PROCESSING_KEY)

    await ack_job(SCAN_PROCESSING_KEY, raw)

    assert fake_redis.lists[SCAN_PROCESSING_KEY] == []


@pytest.mark.asyncio
async def test_job_survives_crash_before_ack(fake_redis):
    """The core crash-safety property: reserve without ack (simulating a worker
    crash mid-job) must not lose the job — it must still be recoverable."""
    await fake_redis.lpush(SCAN_QUEUE_KEY, '{"scan_id": 1}')
    raw = await reserve_job(SCAN_QUEUE_KEY, SCAN_PROCESSING_KEY)
    assert raw is not None
    # Simulate a crash here — no ack_job call.

    recovered = await recover_orphaned_jobs()

    assert recovered == 1
    assert fake_redis.lists[SCAN_QUEUE_KEY] == ['{"scan_id": 1}']  # back on the source queue
    assert fake_redis.lists[SCAN_PROCESSING_KEY] == []


@pytest.mark.asyncio
async def test_recover_orphaned_jobs_across_both_queues(fake_redis):
    for source_key, processing_key in QUEUE_PAIRS:
        await fake_redis.lpush(source_key, f"job-for-{source_key}")
        await reserve_job(source_key, processing_key)  # reserve, never ack

    recovered = await recover_orphaned_jobs()

    assert recovered == len(QUEUE_PAIRS)
    for source_key, processing_key in QUEUE_PAIRS:
        assert fake_redis.lists[source_key] == [f"job-for-{source_key}"]
        assert fake_redis.lists[processing_key] == []


@pytest.mark.asyncio
async def test_recover_orphaned_jobs_is_noop_when_nothing_pending(fake_redis):
    assert await recover_orphaned_jobs() == 0
