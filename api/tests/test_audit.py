"""Audit trail (Phase 8): store.list_audit + GET /api/audit, against a temp DB."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import main, store
from app.db.models import Base

COMPLETE = {
    "duration_ms": 10,
    "analytics": {"files_scanned": 3, "files_skipped": 0, "total_findings": 2, "block_eligible": 1},
    "findings": [],
    "skipped": [],
}


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'audit.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(store, "async_session", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_audit_empty_initially(env):
    assert await store.list_audit() == []


@pytest.mark.asyncio
async def test_audit_records_lifecycle_newest_first(env):
    sid = await store.create_scan("local", "/tmp/x")
    await store.mark_running(sid)
    await store.complete_scan(sid, COMPLETE)

    rows = await store.list_audit()
    assert [r["action"] for r in rows] == ["scan.completed", "scan.running", "scan.created"]

    created = rows[-1]
    assert created["details"]["scan_id"] == sid  # details deserialized to dict, not str
    assert created["details"]["source"] == "local"
    assert rows[0]["details"]["total_findings"] == 2
    assert isinstance(created["created_at"], str) and "T" in created["created_at"]  # isoformat


@pytest.mark.asyncio
async def test_audit_http_route_shape(env):
    sid = await store.create_scan("url", "https://github.com/a/b")
    resp = await env.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert "audit" in body
    entry = next(e for e in body["audit"] if e["action"] == "scan.created")
    assert entry["details"]["scan_id"] == sid
    assert set(entry) == {"id", "action", "details", "created_at"}
