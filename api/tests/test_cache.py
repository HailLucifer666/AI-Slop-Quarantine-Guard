"""Registry/OSV/license Redis cache (Sprint A): identical lookups hit the cache;
transient non-answers (UNKNOWN / None) are never cached; Redis errors fail open."""

import pytest

from app import cache
from app.registries import Existence


class FakeRedis:
    """Minimal in-memory stand-in for the async Redis client used by app.cache."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: r)
    return r


@pytest.mark.asyncio
async def test_existence_second_identical_lookup_hits_cache(fake_redis, monkeypatch):
    calls = []

    async def fake_check(ecosystem, name, client):
        calls.append(name)
        return Existence.MISSING

    monkeypatch.setattr(cache, "_check_exists", fake_check)

    assert await cache.cached_existence("pypi", "leftpad", None) is Existence.MISSING
    assert await cache.cached_existence("pypi", "leftpad", None) is Existence.MISSING
    assert calls == ["leftpad"]  # underlying registry hit exactly once


@pytest.mark.asyncio
async def test_existence_unknown_is_not_cached(fake_redis, monkeypatch):
    calls = []

    async def fake_check(ecosystem, name, client):
        calls.append(name)
        return Existence.UNKNOWN

    monkeypatch.setattr(cache, "_check_exists", fake_check)

    await cache.cached_existence("pypi", "flaky", None)
    await cache.cached_existence("pypi", "flaky", None)
    assert calls == ["flaky", "flaky"]  # outage re-checked every time, never persisted


@pytest.mark.asyncio
async def test_osv_empty_list_is_cached_but_none_is_not(fake_redis, monkeypatch):
    results = [None, []]  # first an outage, then a real "no vulns" answer
    calls = []

    async def fake_osv(ecosystem, name, version, client):
        calls.append(name)
        return results[min(len(calls) - 1, len(results) - 1)]

    monkeypatch.setattr(cache, "_query_osv", fake_osv)

    assert await cache.cached_osv("npm", "x", "1.0.0", None) is None      # not cached
    assert await cache.cached_osv("npm", "x", "1.0.0", None) == []        # cached now
    assert await cache.cached_osv("npm", "x", "1.0.0", None) == []        # served from cache
    assert calls == ["x", "x"]  # third call is a cache hit, no third lookup


@pytest.mark.asyncio
async def test_cache_fails_open_when_redis_unavailable(monkeypatch):
    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache, "get_redis", boom)

    async def fake_check(ecosystem, name, client):
        return Existence.EXISTS

    monkeypatch.setattr(cache, "_check_exists", fake_check)
    # No Redis → transparent miss, real function still answers.
    assert await cache.cached_existence("pypi", "requests", None) is Existence.EXISTS


# --- batched OSV cache (hang fix) -------------------------------------------

@pytest.mark.asyncio
async def test_osv_batch_caches_misses_then_serves_hits(fake_redis, monkeypatch):
    calls = []

    async def fake_batch(pins, client):
        calls.append(list(pins))
        return {p: ([] if p[1] == "clean" else [{"id": "X"}]) for p in pins}

    monkeypatch.setattr(cache, "_query_osv_batch", fake_batch)
    pins = [("npm", "clean", "1.0.0"), ("npm", "bad", "2.0.0")]

    first = await cache.cached_osv_batch(pins, None)
    assert first[("npm", "bad", "2.0.0")] == [{"id": "X"}]
    assert first[("npm", "clean", "1.0.0")] == []  # [] (no vulns) is a real answer

    calls.clear()
    second = await cache.cached_osv_batch(pins, None)
    assert second[("npm", "bad", "2.0.0")] == [{"id": "X"}]
    assert calls == []  # both served from cache — no second network batch


@pytest.mark.asyncio
async def test_osv_batch_none_is_never_cached(fake_redis, monkeypatch):
    calls = []

    async def fake_batch(pins, client):
        calls.append(list(pins))
        return {p: None for p in pins}  # outage

    monkeypatch.setattr(cache, "_query_osv_batch", fake_batch)
    pins = [("npm", "x", "1.0.0")]
    await cache.cached_osv_batch(pins, None)
    await cache.cached_osv_batch(pins, None)
    assert len(calls) == 2  # outage re-queried every time, never persisted


@pytest.mark.asyncio
async def test_created_cache_roundtrip_and_never_cache_none(fake_redis, monkeypatch):
    from datetime import datetime, timezone

    calls = []

    async def fake_created(ecosystem, name, client):
        calls.append(name)
        if name == "bleak":
            return datetime(2018, 4, 27, 9, 43, 2, tzinfo=timezone.utc)
        return None  # outage shape

    monkeypatch.setattr(cache, "_registry_created_at", fake_created)
    first = await cache.cached_registry_created("pypi", "bleak", None)
    assert first is not None and first.year == 2018
    # second identical lookup is served from the cache without hitting the producer
    second = await cache.cached_registry_created("pypi", "bleak", None)
    assert second == first and calls.count("bleak") == 1
    # None is never cached: an outage re-fetches on every call
    await cache.cached_registry_created("pypi", "downpkg", None)
    await cache.cached_registry_created("pypi", "downpkg", None)
    assert calls.count("downpkg") == 2


@pytest.mark.asyncio
async def test_created_cache_key_normalizes_pypi_names(fake_redis, monkeypatch):
    # 'Bleak' and 'bleak' alias one registry body; they must alias one cache entry
    # (review NIT, 2026-11-13) — the producer must fire exactly once.
    calls = []

    async def fake_created(ecosystem, name, client):
        calls.append(name)
        from datetime import datetime, timezone
        return datetime(2018, 4, 27, 9, 43, 2, tzinfo=timezone.utc)

    monkeypatch.setattr(cache, "_registry_created_at", fake_created)
    await cache.cached_registry_created("pypi", "Bleak", None)
    await cache.cached_registry_created("pypi", "bleak", None)
    # One producer call total: the first lookup's key is the NORMALIZED name, so the
    # second spelling hits the same entry (the producer seeing 'bleak' rather than
    # 'Bleak' is the normalization itself doing its job).
    assert calls == ["bleak"]
