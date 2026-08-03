"""Reliable-queue pattern: reserve_job moves a job into its processing list
atomically, ack_job removes it once handled, and recover_orphaned_jobs puts
anything left in a processing list (a crash before ack) back on its source
queue — a job is never lost between being popped and being fully handled."""

import pytest

from app import queue as queue_mod
from app.queue import (
    QUEUE_PAIRS,
    SCAN_PROCESSING_KEY,
    SCAN_QUEUE_KEY,
    ack_job,
    reserve_job,
    recover_orphaned_jobs,
)


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
