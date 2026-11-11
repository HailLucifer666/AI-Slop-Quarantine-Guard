"""Phase 1 reliability: one database, no stuck scans, no phantom queue rows.

These three defects together produced the "stale results" symptom: the dashboard's
headline numbers come only from COMPLETED scans, so any new scan that gets stranded —
by a worker that died, by a queue that was down, or by the API and worker writing to
two different sqlite files — leaves the PREVIOUS scan on screen looking current.

Real persistence against a throwaway SQLite file (no DB mocking), matching
test_scans_api.py; only Redis is faked, since there's no live Redis in CI.
"""

import sys
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import main, scans_router, store
from app.config import _resolve_sqlite_path
from app.db.models import Base, Scan
from app.db.diagnostics import find_stray_databases


# --- one database, whatever the working directory ---------------------------------


def test_relative_sqlite_path_is_anchored_to_api_dir():
    """The bug that split the database in two: ./app.db resolved against the CWD."""
    resolved = _resolve_sqlite_path("sqlite:///./app.db")
    assert resolved != "sqlite:///./app.db"
    assert resolved.endswith("app.db")
    # Anchored to api/, so a process launched from the repo root resolves the same file.
    assert "api" in resolved.replace("\\", "/").split("/")


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows drive-letter path semantics are not meaningful on POSIX (CI is Linux)",
)
def test_absolute_sqlite_path_is_left_alone():
    """An absolute Windows path has three slashes too — must not be re-anchored."""
    url = "sqlite:///C:/data/app.db"
    assert _resolve_sqlite_path(url) == url


def test_memory_and_non_sqlite_urls_are_left_alone():
    assert _resolve_sqlite_path("sqlite:///:memory:") == "sqlite:///:memory:"
    pg = "postgresql+asyncpg://app:password@postgres:5432/app"
    assert _resolve_sqlite_path(pg) == pg


def test_live_database_is_never_reported_as_stray(tmp_path):
    live = tmp_path / "app.db"
    live.write_bytes(b"")
    assert all(path != live for path, _size in find_stray_databases(str(live)))


# --- stuck scans get reconciled ---------------------------------------------------


@pytest_asyncio.fixture
async def db(tmp_path, monkeypatch):
    """Throwaway SQLite file wired into store, like the scans-API fixture does."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reliability.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(store, "async_session", factory)
    yield factory
    await engine.dispose()


async def _set_heartbeat(factory, scan_id: int, age_seconds: float) -> None:
    async with factory() as session:
        scan = await session.get(Scan, scan_id)
        scan.heartbeat_at = datetime.utcnow() - timedelta(seconds=age_seconds)
        await session.commit()


@pytest.mark.asyncio
async def test_running_scan_with_lapsed_lease_is_failed(db):
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    await _set_heartbeat(db, scan_id, store.STALE_LEASE_SECONDS + 60)

    assert await store.reconcile_stale_scans() == [scan_id]

    scan = await store.get_scan(scan_id)
    assert scan["status"] == "failed"
    assert "heartbeat lease expired" in scan["error"]
    # The user is told what to do, not just that something broke.
    assert "re-run the scan" in scan["error"]


@pytest.mark.asyncio
async def test_running_scan_with_fresh_heartbeat_is_left_alone(db):
    """A slow analyzer must never get its own healthy scan reconciled away."""
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    await _set_heartbeat(db, scan_id, 30)

    assert await store.reconcile_stale_scans() == []
    assert (await store.get_scan(scan_id))["status"] == "running"


@pytest.mark.asyncio
async def test_pre_upgrade_running_scan_falls_back_to_created_at(db):
    """Rows written before heartbeat_at existed still get reconciled, via created_at."""
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    async with db() as session:
        scan = await session.get(Scan, scan_id)
        scan.heartbeat_at = None
        scan.created_at = datetime.utcnow() - timedelta(seconds=store.STALE_LEASE_SECONDS + 60)
        await session.commit()

    assert await store.reconcile_stale_scans() == [scan_id]
    assert (await store.get_scan(scan_id))["status"] == "failed"


@pytest.mark.asyncio
async def test_queued_and_completed_scans_are_not_touched(db):
    """Only *running* scans hold a lease; a queued scan hasn't been picked up yet."""
    queued = await store.create_scan("local", "/tmp/queued")
    done = await store.create_scan("local", "/tmp/done")
    await store.complete_scan(done, {"analytics": {}, "findings": [], "skipped": [], "duration_ms": 1})
    async with db() as session:
        for scan_id in (queued, done):
            scan = await session.get(Scan, scan_id)
            scan.created_at = datetime.utcnow() - timedelta(days=1)
        await session.commit()

    assert await store.reconcile_stale_scans() == []
    assert (await store.get_scan(queued))["status"] == "queued"
    assert (await store.get_scan(done))["status"] == "completed"


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(db):
    """Worker startup and the API's periodic pass can race; a double pass is harmless."""
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    await _set_heartbeat(db, scan_id, store.STALE_LEASE_SECONDS + 60)

    assert await store.reconcile_stale_scans() == [scan_id]
    assert await store.reconcile_stale_scans() == []  # no longer running
    assert (await store.get_scan(scan_id))["status"] == "failed"


@pytest.mark.asyncio
async def test_heartbeat_renewal_keeps_a_scan_alive(db):
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    await _set_heartbeat(db, scan_id, store.STALE_LEASE_SECONDS + 60)

    await store.touch_scan_heartbeat(scan_id)

    assert await store.reconcile_stale_scans() == []
    assert (await store.get_scan(scan_id))["status"] == "running"


@pytest.mark.asyncio
async def test_progress_update_also_renews_the_lease(db):
    """Progress and liveness share one UPDATE, so an advancing scan can't be reaped."""
    scan_id = await store.create_scan("local", "/tmp/x")
    await store.mark_running(scan_id)
    await _set_heartbeat(db, scan_id, store.STALE_LEASE_SECONDS + 60)

    await store.update_progress(scan_id, {"phase": "sast", "index": 4})

    assert await store.reconcile_stale_scans() == []


@pytest.mark.asyncio
async def test_worker_heartbeat_roundtrip(db):
    assert await store.get_worker_heartbeat() is None  # nothing has ever reported in
    await store.touch_worker_heartbeat()
    first = await store.get_worker_heartbeat()
    assert first is not None
    await store.touch_worker_heartbeat()  # upsert, not a second row
    assert await store.get_worker_heartbeat() >= first


# --- a queue outage can't leave a phantom row ------------------------------------


@pytest_asyncio.fixture
async def api(tmp_path, monkeypatch):
    """App client whose enqueue always fails, simulating a Redis outage."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'phantom.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(store, "async_session", factory)

    async def broken_enqueue(scan_id: int, source: str, ref: str) -> None:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr(scans_router, "enqueue_scan", broken_enqueue)
    monkeypatch.setattr(main.settings, "environment", "development")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_failure_fails_the_scan_and_returns_503(api):
    resp = await api.post("/api/scans", json={"source": "url", "url": "https://github.com/psf/requests"})

    assert resp.status_code == 503
    # The row must not be left at "queued" for a worker that will never see it.
    listing = await api.get("/api/scans")
    scans = listing.json()["scans"]
    assert len(scans) == 1
    assert scans[0]["status"] == "failed"
    assert "could not be queued" in scans[0]["error"]
