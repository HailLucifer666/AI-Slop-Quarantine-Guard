"""Worker loop resilience: Redis outages must never kill the consumer.

Three outcomes of _poll_for_job stay distinguishable: job / idle / Redis
unavailable. The unavailable case raises RedisUnavailable (the caller backs off
and retries); idle returns the (None, None, None) triple so a healthy empty
queue is never logged as an outage.
"""

import pytest
import redis

from app import worker
from app.queue import SCAN_QUEUE_KEY


def test_backoff_schedule_caps_at_10():
    assert worker._backoff_seconds(0) == 1.0
    assert worker._backoff_seconds(1) == 2.0
    assert worker._backoff_seconds(2) == 5.0
    assert worker._backoff_seconds(3) == 10.0
    assert worker._backoff_seconds(99) == 10.0


@pytest.mark.asyncio
async def test_poll_for_job_raises_unavailable_on_connection_error(monkeypatch):
    """Mutation (2026-11-11): delete the except in _poll_for_job -> the raw
    ConnectionError escapes instead of RedisUnavailable; this test fails."""
    async def boom(source_key, proc_key):
        raise redis.exceptions.ConnectionError("redis down")

    monkeypatch.setattr(worker, "reserve_job", boom)
    with pytest.raises(worker.RedisUnavailable):
        await worker._poll_for_job()


@pytest.mark.asyncio
async def test_poll_for_job_idle_returns_none_triple(monkeypatch):
    """An idle pass (all queues empty) is normal sleep — never an outage."""
    async def idle(source_key, proc_key):
        return None

    monkeypatch.setattr(worker, "reserve_job", idle)
    assert await worker._poll_for_job() == (None, None, None)


@pytest.mark.asyncio
async def test_poll_for_job_returns_first_available_job(monkeypatch):
    seen = []

    async def first_nonempty(source_key, proc_key):
        seen.append(source_key)
        if source_key == SCAN_QUEUE_KEY:
            return '{"kind": "scan", "scan_id": 1}'
        return None

    monkeypatch.setattr(worker, "reserve_job", first_nonempty)
    key, proc_key, raw = await worker._poll_for_job()

    assert key == SCAN_QUEUE_KEY
    assert raw == '{"kind": "scan", "scan_id": 1}'
    assert proc_key is not None  # the processing key paired with the source
    assert SCAN_QUEUE_KEY in seen  # the scan source was polled


@pytest.mark.asyncio
async def test_refresh_redis_state_logs_restore_once(monkeypatch):
    """Mutation (2026-11-11): remove the ping_redis() check in
    _refresh_redis_state -> was_down never flips and this test fails."""
    calls = {"n": 0}

    async def fake_ping():
        calls["n"] += 1
        return calls["n"] >= 2  # first: still down; second: restored

    monkeypatch.setattr(worker, "ping_redis", fake_ping)

    # Still down -> was_down stays True, no flip.
    assert await worker._refresh_redis_state(True) is True
    # Redis back -> was_down flips False.
    assert await worker._refresh_redis_state(True) is False
    # Healthy path (was_down=False) -> never pings, stays False.
    assert await worker._refresh_redis_state(False) is False
    assert calls["n"] == 2
