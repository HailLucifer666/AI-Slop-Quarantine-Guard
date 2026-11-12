"""Short-TTL Redis cache for the external registry / OSV / license lookups.

Wraps the live HTTP checks so the same package isn't re-fetched within a scan or
across recent scans. Keyed by ``ecosystem:name(:version)`` as the plan specifies.

Two hard rules, both inherited from the analyzers' honesty model:
* **Fail-open.** Any Redis error is a transparent cache miss — we just call the
  real function. A cache outage never changes a verdict and never fails a scan.
* **Never cache a non-answer.** Existence ``UNKNOWN`` (registry unreachable) and
  OSV ``None`` (feed unreachable) are transient; caching them would persist an
  outage into a false "couldn't verify". Only definitive results are stored.
"""

import json
import logging
from datetime import datetime
from typing import Optional

import httpx

from app.analyzers.licenses import fetch_license as _fetch_license
from app.analyzers.vulns import query_osv as _query_osv, query_osv_batch as _query_osv_batch
from app.queue import get_redis
from app.registries import (
    Existence,
    check_exists as _check_exists,
    registry_created_at as _registry_created_at,
)

logger = logging.getLogger("cache")

# Registry existence / license / vuln status changes slowly; an hour keeps a busy
# scan fast without serving badly stale data.
_TTL_SECONDS = 3600


async def _get(key: str) -> Optional[str]:
    try:
        return await get_redis().get(key)
    except Exception:  # noqa: BLE001 — Redis down → cache miss, never fatal
        return None


async def _set(key: str, value: str) -> None:
    try:
        await get_redis().set(key, value, ex=_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.debug("cache set dropped for %s", key)


async def cached_existence(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Existence:
    """``registries.check_exists`` with a Redis cache. UNKNOWN is never cached."""
    key = f"sqg:exist:{ecosystem}:{name}"
    hit = await _get(key)
    if hit in (Existence.EXISTS.value, Existence.MISSING.value):
        return Existence(hit)
    result = await _check_exists(ecosystem, name, client)
    if result is not Existence.UNKNOWN:
        await _set(key, result.value)
    return result


async def cached_registry_created(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Optional[datetime]:
    """``registries.registry_created_at`` with a Redis cache. None (outage, unknown
    name, field missing) is NEVER cached — same rule as existence UNKNOWN: caching
    an non-answer would persist a transient gap into a stale "can't verify"."""
    key = f"sqg:created:{ecosystem}:{name}"
    hit = await _get(key)
    if hit is not None:
        try:
            return datetime.fromisoformat(hit)
        except ValueError:
            pass
    result = await _registry_created_at(ecosystem, name, client)
    if result is not None:
        await _set(key, result.isoformat())
    return result


async def cached_osv(
    ecosystem: str, name: str, version: str, client: httpx.AsyncClient
) -> Optional[list]:
    """``vulns.query_osv`` with a Redis cache. None (feed outage) is never cached."""
    key = f"sqg:osv:{ecosystem}:{name}:{version}"
    hit = await _get(key)
    if hit is not None:
        try:
            return json.loads(hit)
        except json.JSONDecodeError:
            pass
    result = await _query_osv(ecosystem, name, version, client)
    if result is not None:  # [] (no vulns) is a real answer worth caching
        await _set(key, json.dumps(result))
    return result


async def cached_osv_batch(pins: list, client: httpx.AsyncClient) -> dict:
    """Batched ``vulns.query_osv_batch`` with a Redis cache, keyed identically to
    ``cached_osv`` (``sqg:osv:{eco}:{name}:{version}``) so the PR and whole-repo
    paths share entries. Cache hits are served locally; only the misses are sent to
    OSV in one batched call. None (feed outage) is never cached. Fail-open: a Redis
    error just means more pins fall through to the (still fail-safe) batch query.
    """
    results: dict = {}
    misses: list = []
    for pin in pins:
        eco, name, version = pin
        hit = await _get(f"sqg:osv:{eco}:{name}:{version}")
        if hit is not None:
            try:
                results[pin] = json.loads(hit)
                continue
            except json.JSONDecodeError:
                pass
        misses.append(pin)

    if misses:
        fetched = await _query_osv_batch(misses, client)
        for pin, vulns in fetched.items():
            results[pin] = vulns
            if vulns is not None:  # [] (clean) is a real answer worth caching; None isn't
                eco, name, version = pin
                await _set(f"sqg:osv:{eco}:{name}:{version}", json.dumps(vulns))
    return results


async def cached_license(
    ecosystem: str, name: str, client: httpx.AsyncClient
) -> Optional[str]:
    """``licenses.fetch_license`` with a Redis cache. None (unreachable) is never cached."""
    key = f"sqg:lic:{ecosystem}:{name}"
    hit = await _get(key)
    if hit is not None:
        return hit
    result = await _fetch_license(ecosystem, name, client)
    if result is not None:
        await _set(key, result)
    return result
