"""Readiness endpoint: GET /api/health.

``/healthz`` stays trivial and dependency-free for container liveness probes. This is
the different question — "can this deployment actually finish a scan right now?" — and
it exists because the previous answer required reading logs on two machines.

Every field here maps to a real failure that produced apparently-stale results:
- ``database.path``  — the API and worker each resolving a *different* sqlite file.
- ``redis``          — scans accepted but never queued.
- ``worker``         — no consumer alive, so scans sit at "queued"/"running" while the
                       dashboard keeps rendering the last completed scan.

Unknown is reported as unknown. A probe that cannot answer returns ``null`` with the
error text, never a cheerful default.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db.models import Scan
from app.db.session import async_session, engine
from app.engines import availability
from app.queue import SCAN_QUEUE_KEY, get_redis
from app.store import STALE_LEASE_SECONDS, get_worker_heartbeat

logger = logging.getLogger("health")

router = APIRouter(prefix="/api/health", tags=["health"])

# A worker stamps liveness every 10s (worker.WORKER_HEARTBEAT_INTERVAL_S). Allow a
# generous multiple before calling it dead so a long DB write or a GC pause doesn't
# read as an outage.
WORKER_ALIVE_WINDOW_S = 60


async def _database_status() -> dict:
    status: dict = {
        "path": engine.url.database,
        "dialect": engine.dialect.name,
        "reachable": False,
        "scans_row_count": None,
        "error": None,
    }
    try:
        async with async_session() as session:
            result = await session.execute(select(func.count()).select_from(Scan))
            status["scans_row_count"] = result.scalar_one()
        status["reachable"] = True
    except Exception as exc:  # noqa: BLE001 — report the failure, don't raise it
        status["error"] = str(exc)[:300]
    return status


async def _redis_status() -> dict:
    status: dict = {"reachable": False, "latency_ms": None, "scan_queue_depth": None, "error": None}
    started = time.monotonic()
    try:
        client = get_redis()
        await client.ping()
        status["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
        status["scan_queue_depth"] = await client.llen(SCAN_QUEUE_KEY)
        status["reachable"] = True
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)[:300]
    return status


async def _worker_status() -> dict:
    status: dict = {
        "last_heartbeat_at": None,
        "seconds_since_heartbeat": None,
        "considered_alive": False,
        "error": None,
    }
    try:
        last: Optional[datetime] = await get_worker_heartbeat()
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)[:300]
        return status
    if last is None:
        # No worker has ever reported in against this database.
        return status
    age = (datetime.utcnow() - last).total_seconds()
    status["last_heartbeat_at"] = last.replace(microsecond=0).isoformat() + "+00:00"
    status["seconds_since_heartbeat"] = round(age, 1)
    status["considered_alive"] = age <= WORKER_ALIVE_WINDOW_S
    return status


@router.get("")
async def health():
    """Readiness detail for operators and the dashboard's system panel."""
    database = await _database_status()
    redis = await _redis_status()
    worker = await _worker_status()

    degraded = not (database["reachable"] and redis["reachable"] and worker["considered_alive"])
    return {
        "status": "degraded" if degraded else "ok",
        "database": database,
        "redis": redis,
        "worker": worker,
        "stale_scan_lease_seconds": STALE_LEASE_SECONDS,
        # Which external scanners this deployment can actually run, and what each
        # missing one costs in coverage. Probed live rather than assumed.
        "engines": availability(),
    }
