"""Scan API (Stage 2): create → 202 {scan_id}, persisted row, enqueued job; reads.

Runs against a throwaway SQLite file (real persistence, no mocking of the DB) via an
in-loop httpx AsyncClient so the app and the async engine share one event loop. The
Redis enqueue is faked so no live Redis is needed — we assert the job that *would* be
pushed.
"""

import io
import json
import os
import zipfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import api_security, main, scans_router, store
from app.config import settings
from app.db.models import Base


@pytest_asyncio.fixture
async def api(tmp_path, monkeypatch):
    """Temp-DB-backed AsyncClient + a capture list of enqueued scan jobs."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scans.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(store, "async_session", factory)

    enqueued: list[dict] = []

    async def fake_enqueue(scan_id: int, source: str, ref: str) -> None:
        enqueued.append({"scan_id": scan_id, "source": source, "ref": ref})

    monkeypatch.setattr(scans_router, "enqueue_scan", fake_enqueue)
    monkeypatch.setattr(settings, "environment", "development")

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, enqueued
    await engine.dispose()


@pytest.mark.asyncio
async def test_url_scan_creates_row_and_enqueues(api):
    client, enqueued = api
    url = "https://github.com/psf/requests"
    resp = await client.post("/api/scans", json={"source": "url", "url": url})

    assert resp.status_code == 202
    scan_id = resp.json()["scan_id"]
    assert isinstance(scan_id, int)
    assert enqueued == [{"scan_id": scan_id, "source": "url", "ref": url}]

    detail = await client.get(f"/api/scans/{scan_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "queued"
    assert body["source"] == "url"
    assert body["ref"] == url
    assert body["findings"] == []
    assert body["analytics"] is None


@pytest.mark.asyncio
async def test_non_https_url_rejected(api):
    client, enqueued = api
    resp = await client.post("/api/scans", json={"source": "url", "url": "http://github.com/x/y"})
    assert resp.status_code == 400
    assert enqueued == []


@pytest.mark.asyncio
async def test_disallowed_host_rejected(api):
    client, enqueued = api
    resp = await client.post("/api/scans", json={"source": "url", "url": "https://evil.internal/r"})
    assert resp.status_code == 400
    assert enqueued == []


@pytest.mark.asyncio
async def test_missing_url_400(api):
    client, _ = api
    resp = await client.post("/api/scans", json={"source": "url"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_local_scan_allowed_in_dev(api, tmp_path):
    client, enqueued = api
    proj = tmp_path / "proj"
    proj.mkdir()
    resp = await client.post("/api/scans", json={"source": "local", "path": str(proj)})
    assert resp.status_code == 202
    assert enqueued[0]["source"] == "local"
    assert enqueued[0]["ref"] == str(proj)


@pytest.mark.asyncio
async def test_local_scan_rejected_in_production(api, monkeypatch, tmp_path):
    client, enqueued = api
    monkeypatch.setattr(settings, "environment", "production")
    proj = tmp_path / "proj2"
    proj.mkdir()
    resp = await client.post("/api/scans", json={"source": "local", "path": str(proj)})
    assert resp.status_code == 403
    assert enqueued == []


@pytest.mark.asyncio
async def test_local_scan_nonexistent_path_400(api):
    client, _ = api
    resp = await client.post("/api/scans", json={"source": "local", "path": "/no/such/dir/xyz"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zip_upload_spools_to_disk_and_enqueues(api):
    client, enqueued = api
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.py", "x = 1\n")

    resp = await client.post(
        "/api/scans",
        files={"file": ("code.zip", buf.getvalue(), "application/zip")},
    )
    assert resp.status_code == 202
    job = enqueued[0]
    assert job["source"] == "zip"
    # ref is a temp path the worker will read + delete; it exists right now.
    assert os.path.exists(job["ref"])
    os.remove(job["ref"])  # the fake enqueue skips the worker, so clean up here

    detail = await client.get(f"/api/scans/{job['scan_id']}")
    assert detail.json()["ref"] == "code.zip"  # user-facing ref = filename


@pytest.mark.asyncio
async def test_unknown_source_400(api):
    client, _ = api
    resp = await client.post("/api/scans", json={"source": "ftp"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_missing_scan_404(api):
    client, _ = api
    resp = await client.get("/api/scans/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_scan_events_stream_closes_on_terminal_status(api):
    client, _ = api
    scan_id = (
        await client.post("/api/scans", json={"source": "url", "url": "https://github.com/a/b"})
    ).json()["scan_id"]
    await store.complete_scan(scan_id, {
        "findings": [], "analytics": {"total_findings": 0, "clean": True}, "duration_ms": 5,
    })

    lines = []
    async with client.stream("GET", f"/api/scans/{scan_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        async for line in resp.aiter_lines():
            if line:
                lines.append(line)

    assert len(lines) == 1
    assert lines[0].startswith("data: ")
    payload = json.loads(lines[0][len("data: "):])
    assert payload["status"] == "completed"


@pytest.mark.asyncio
async def test_scan_events_404_for_missing_scan(api):
    client, _ = api
    resp = await client.get("/api/scans/999999/events")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_scans_most_recent_first(api):
    client, _ = api
    await client.post("/api/scans", json={"source": "url", "url": "https://github.com/a/b"})
    await client.post("/api/scans", json={"source": "url", "url": "https://github.com/c/d"})

    resp = await client.get("/api/scans")
    assert resp.status_code == 200
    body = resp.json()
    scans = body["scans"]
    assert len(scans) == 2
    assert scans[0]["id"] > scans[1]["id"]
    assert "findings" not in scans[0]  # list view is summary-only
    assert body["total"] == 2
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_list_scans_pagination(api):
    client, _ = api
    for i in range(5):
        await client.post("/api/scans", json={"source": "url", "url": f"https://github.com/a/{i}"})

    page1 = (await client.get("/api/scans", params={"limit": 2, "offset": 0})).json()
    assert len(page1["scans"]) == 2
    assert page1["total"] == 5
    assert page1["has_more"] is True

    page3 = (await client.get("/api/scans", params={"limit": 2, "offset": 4})).json()
    assert len(page3["scans"]) == 1
    assert page3["has_more"] is False

    # limit is capped, not silently ignored
    assert (await client.get("/api/scans", params={"limit": 500})).status_code == 422


@pytest.mark.asyncio
async def test_scans_summary_range_rollup(api):
    client, _ = api
    resp = await client.get("/api/scans/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "scanned_in_range": 0,
        "clean_pass_rate": 100,
        "scans_with_incomplete_coverage": 0,
        "certain_total": 0,
        "findings_total": 0,
        "by_rule": {},
        "top_files": [],
    }
    assert (await client.get("/api/scans/summary", params={"range": "bogus"})).status_code == 400


@pytest.mark.asyncio
async def test_scans_summary_rolls_up_completed_scans(api):
    client, _ = api
    scan_id = (
        await client.post("/api/scans", json={"source": "url", "url": "https://github.com/a/b"})
    ).json()["scan_id"]
    await store.complete_scan(scan_id, {
        "findings": [],
        "analytics": {
            "total_findings": 3, "by_confidence": {"CERTAIN": 1, "HIGH": 2, "MEDIUM": 0},
            "by_rule": {"SQG002": 1, "SQG004": 2}, "block_eligible": 1,
            "top_files": [{"file_path": "a.py", "count": 2}],
            "files_scanned": 5, "files_skipped": 0, "clean": False,
        },
        "duration_ms": 10,
    })
    # A second, still-queued scan must NOT count toward the rollup (only completed).
    await client.post("/api/scans", json={"source": "url", "url": "https://github.com/c/d"})

    body = (await client.get("/api/scans/summary")).json()
    assert body["scanned_in_range"] == 1
    assert body["clean_pass_rate"] == 0
    assert body["certain_total"] == 1
    assert body["findings_total"] == 3
    assert body["by_rule"] == {"SQG002": 1, "SQG004": 2}
    assert body["top_files"] == [{"file_path": "a.py", "count": 2}]


# --- API-key auth on POST /api/scans (Sprint A) -----------------------------

@pytest.mark.asyncio
async def test_post_scan_requires_api_key_when_configured(api, monkeypatch):
    client, enqueued = api
    monkeypatch.setattr(settings, "api_key", "s3cr3t")

    # Missing/wrong key → 401, no clone enqueued.
    resp = await client.post("/api/scans", json={"source": "url", "url": "https://github.com/x/y"})
    assert resp.status_code == 401
    assert enqueued == []

    # Correct key → accepted.
    resp = await client.post(
        "/api/scans",
        json={"source": "url", "url": "https://github.com/x/y"},
        headers={"X-API-Key": "s3cr3t"},
    )
    assert resp.status_code == 202
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_post_scan_open_when_no_api_key_configured(api):
    client, enqueued = api  # settings.api_key defaults to "" (demo/dev)
    resp = await client.post("/api/scans", json={"source": "url", "url": "https://github.com/x/y"})
    assert resp.status_code == 202
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_reads_require_api_key_when_configured(api, monkeypatch):
    """GET /api/scans and GET /api/scans/{id} must honor the same key as POST —
    otherwise setting API_KEY only protects creation while findings/snippets stay
    readable by anyone."""
    client, enqueued = api
    resp = await client.post("/api/scans", json={"source": "url", "url": "https://github.com/x/y"})
    scan_id = resp.json()["scan_id"]

    monkeypatch.setattr(settings, "api_key", "s3cr3t")

    assert (await client.get("/api/scans")).status_code == 401
    assert (await client.get(f"/api/scans/{scan_id}")).status_code == 401

    headers = {"X-API-Key": "s3cr3t"}
    assert (await client.get("/api/scans", headers=headers)).status_code == 200
    assert (await client.get(f"/api/scans/{scan_id}", headers=headers)).status_code == 200


# --- per-IP rate limiting (Sprint A) ----------------------------------------

class _CountingRedis:
    """Fake Redis exposing just incr/expire for the fixed-window limiter."""

    def __init__(self):
        self.counts: dict[str, int] = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold(api, monkeypatch):
    client, _ = api
    shared = _CountingRedis()
    monkeypatch.setattr(api_security, "get_redis", lambda: shared)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)

    assert (await client.get("/api/scans")).status_code == 200
    assert (await client.get("/api/scans")).status_code == 200
    assert (await client.get("/api/scans")).status_code == 429  # 3rd in the window


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_down(api, monkeypatch):
    client, _ = api

    def boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr(api_security, "get_redis", boom)
    monkeypatch.setattr(settings, "rate_limit_per_minute", 1)
    # Redis unavailable → requests still served (availability over hard lockout).
    assert (await client.get("/api/scans")).status_code == 200
    assert (await client.get("/api/scans")).status_code == 200
