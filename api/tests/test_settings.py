"""Settings (Phase 8): GET/PATCH /api/settings + audit, against a temp DB."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import main, store
from app.config import settings
from app.db.models import Base


@pytest_asyncio.fixture
async def env(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'settings.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(store, "async_session", sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_defaults_on_first_get(env):
    resp = await env.get("/api/settings")
    assert resp.status_code == 200
    s = resp.json()
    assert s["block_mode"] is False
    assert s["retention_days"] == 90
    assert set(s["blocked_rules"]) <= store.RULE_IDS


@pytest.mark.asyncio
async def test_patch_roundtrip_and_persist(env):
    resp = await env.patch(
        "/api/settings", json={"block_mode": True, "blocked_rules": ["SQG003"], "retention_days": 30}
    )
    assert resp.status_code == 200
    s = resp.json()
    assert s["block_mode"] is True and s["blocked_rules"] == ["SQG003"] and s["retention_days"] == 30

    again = (await env.get("/api/settings")).json()
    assert again["block_mode"] is True and again["retention_days"] == 30


@pytest.mark.asyncio
async def test_sqg007_settable(env):
    """SQG007 (typosquat) is a real analyzer whose category permits block-eligibility;
    the owner must be able to opt it into blocked_rules like any other rule."""
    resp = await env.patch("/api/settings", json={"blocked_rules": ["SQG001", "SQG007"]})
    assert resp.status_code == 200
    assert resp.json()["blocked_rules"] == ["SQG001", "SQG007"]


@pytest.mark.asyncio
async def test_invalid_retention_rejected(env):
    resp = await env.patch("/api/settings", json={"retention_days": 7})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_invalid_rule_rejected(env):
    resp = await env.patch("/api/settings", json={"blocked_rules": ["SQG999"]})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_is_audited(env):
    await env.patch("/api/settings", json={"block_mode": True})
    rows = await store.list_audit()
    assert any(r["action"] == "settings.updated" for r in rows)


@pytest.mark.asyncio
async def test_settings_requires_api_key_when_configured(env, monkeypatch):
    # Unauthenticated settings mutation would let anyone silently disable/alter
    # enforcement config — must be gated exactly like scan creation.
    monkeypatch.setattr(settings, "api_key", "s3cr3t")
    assert (await env.get("/api/settings")).status_code == 401
    assert (await env.patch("/api/settings", json={"block_mode": True})).status_code == 401

    headers = {"X-API-Key": "s3cr3t"}
    assert (await env.get("/api/settings", headers=headers)).status_code == 200
    assert (await env.patch("/api/settings", json={"block_mode": True}, headers=headers)).status_code == 200
