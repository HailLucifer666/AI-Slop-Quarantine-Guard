"""Worker scan path (Stage 2): handle_scan_job ingests → analyzes → persists.

Ingest is faked (no network/disk) so the assertions focus on the worker's
orchestration + persistence: success completes with analytics, failures are recorded
with a reason (never a silent drop), and the source dispatch is gated correctly.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app import store, worker
from app.db.models import Base
from app.ingest import IngestError, IngestResult


@pytest_asyncio.fixture
async def scan_store(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(store, "async_session", factory)
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_scan_job_completes_and_persists_findings(scan_store, monkeypatch):
    scan_id = await store.create_scan("local", "/proj")
    files = {"config.py": 'KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: implement\nx = 1\n'}
    monkeypatch.setattr(worker, "ingest_codebase", lambda s, r: IngestResult(files=files, skipped=[], resolved_sha="a" * 40))

    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/proj"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "completed"
    assert row["files_scanned"] == 1
    assert row["analytics"]["clean"] is False
    rules = {f["rule_id"] for f in row["findings"]}
    assert "SQG002" in rules  # secret
    assert "SQG003" in rules  # placeholder
    assert row["duration_ms"] is not None


@pytest.mark.asyncio
async def test_scan_job_records_shadow_block_without_blocking(scan_store, monkeypatch):
    """A CERTAIN secret (SQG002, in the default blocked set) WOULD block — the scan
    records that in analytics + a scan.shadow_block audit row, but still completes."""
    scan_id = await store.create_scan("local", "/proj")
    files = {"config.py": 'KEY = "AKIAIOSFODNN7REALKEY"\nx = 1\n'}
    monkeypatch.setattr(worker, "ingest_codebase", lambda s, r: IngestResult(files=files, skipped=[], resolved_sha="a" * 40))

    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/proj"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "completed"          # never blocked — shadow only
    assert row["analytics"]["would_block"] == 1  # the SQG002 secret would block

    actions = {a["action"] for a in await store.list_audit()}
    assert "scan.shadow_block" in actions


@pytest.mark.asyncio
async def test_scan_job_no_findings_records_coverage_not_a_clean_claim(scan_store, monkeypatch):
    """A readme-only repo gives most checks nothing to read, so it isn't "clean"."""
    scan_id = await store.create_scan("local", "/clean")
    monkeypatch.setattr(worker, "ingest_codebase", lambda s, r: IngestResult(files={"README.md": "# hi\n"}, skipped=[], resolved_sha=None))

    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/clean"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "completed"
    assert row["findings"] == []
    assert row["analytics"]["clean"] is False
    assert row["coverage"]["rules_incomplete"] > 0


@pytest.mark.asyncio
async def test_scan_job_records_ingest_provenance(scan_store, monkeypatch):
    """What was analyzed is recorded, so a result can be traced to a snapshot."""
    scan_id = await store.create_scan("url", "https://github.com/a/b")
    files = {"a.py": "x = 1\n"}
    monkeypatch.setattr(worker, "ingest_codebase", lambda s, r: IngestResult(files=files, skipped=[], resolved_sha="deadbeef" * 5))

    await worker.handle_scan_job({"scan_id": scan_id, "source": "url", "ref": "https://github.com/a/b"})

    row = await store.get_scan(scan_id)
    assert row["resolved_sha"] == "deadbeef" * 5
    assert row["file_count"] == 1
    assert row["ingested_at"] is not None
    assert row["engine_versions"]["rules_version"] == store.SQG_RULES_VERSION
    # Same content always hashes the same, which is what makes freshness checkable.
    from app.ingest import content_hash
    assert row["content_hash"] == content_hash(files)


@pytest.mark.asyncio
async def test_provenance_survives_a_failure_during_analysis(scan_store, monkeypatch):
    """A scan that dies mid-analysis still proves which snapshot it was looking at."""
    scan_id = await store.create_scan("local", "/proj")
    monkeypatch.setattr(worker, "ingest_codebase", lambda s, r: IngestResult(files={"a.py": "x=1\n"}, skipped=[], resolved_sha="c" * 40))

    async def boom(*_args, **_kwargs):
        raise RuntimeError("analyzer stage exploded")

    monkeypatch.setattr(worker, "run_scan", boom)
    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/proj"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "failed"
    assert row["resolved_sha"] == "c" * 40  # recorded before analysis began
    assert row["file_count"] == 1


@pytest.mark.asyncio
async def test_scan_job_surfaces_skipped(scan_store, monkeypatch):
    scan_id = await store.create_scan("local", "/big")
    monkeypatch.setattr(
        worker, "ingest_codebase", lambda s, r: IngestResult(files={"a.py": "x=1\n"}, skipped=["huge.bin (too large)"], resolved_sha=None)
    )

    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/big"})

    row = await store.get_scan(scan_id)
    assert row["files_skipped"] == 1
    assert row["skipped"] == ["huge.bin (too large)"]


@pytest.mark.asyncio
async def test_scan_job_ingest_failure_recorded(scan_store, monkeypatch):
    scan_id = await store.create_scan("url", "https://github.com/x/y")

    def boom(_s, _r):
        raise IngestError("clone timed out after 60s")

    monkeypatch.setattr(worker, "ingest_codebase", boom)
    await worker.handle_scan_job({"scan_id": scan_id, "source": "url", "ref": "https://github.com/x/y"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "failed"
    assert "clone timed out" in row["error"]


@pytest.mark.asyncio
async def test_scan_job_unexpected_error_recorded(scan_store, monkeypatch):
    scan_id = await store.create_scan("local", "/proj")

    def boom(_s, _r):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(worker, "ingest_codebase", boom)
    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/proj"})

    row = await store.get_scan(scan_id)
    assert row["status"] == "failed"
    assert "kaboom" in row["error"]


@pytest.mark.asyncio
async def test_scan_job_missing_id_is_noop(scan_store):
    # No scan_id → log and return, don't raise.
    await worker.handle_scan_job({"source": "local", "ref": "/x"})


def test_ingest_codebase_local_gated_in_production(monkeypatch):
    monkeypatch.setattr(worker.settings, "environment", "production")
    with pytest.raises(IngestError):
        worker.ingest_codebase("local", "/some/path")


def test_ingest_codebase_unknown_source():
    with pytest.raises(IngestError):
        worker.ingest_codebase("ftp", "ref")


@pytest.mark.asyncio
async def test_scan_job_reports_progress_through_every_phase(scan_store, monkeypatch):
    # Scans 21/22 (qwen-code, free-claude-code) read as hangs: the queued+clone+read
    # window wrote NOTHING while the analyzer loop wrote transiently. The worker must
    # report cloning before ingest, reading with the true file count after it, and the
    # per-analyzer phases — with progress cleared on completion (existing contract).
    # Probe (2026-11-13, run and restored): disabling the cloning/reading emissions
    # reds this test exactly (phases[0] becomes the first analyzer); disabling the
    # store queue_position branch reds both scan-api position tests.
    scan_id = await store.create_scan("local", "/proj")
    files = {"config.py": 'KEY = "AKIAIOSFODNN7REALKEY"\nx = 1\n'}
    monkeypatch.setattr(
        worker, "ingest_codebase",
        lambda s, r: IngestResult(files=files, skipped=[], resolved_sha="a" * 40),
    )
    writes: list[dict] = []

    async def recording(sid, payload):
        writes.append(dict(payload))
        await store.update_progress(sid, payload)

    monkeypatch.setattr(worker, "update_progress", recording)

    await worker.handle_scan_job({"scan_id": scan_id, "source": "local", "ref": "/proj"})

    phases = [w["phase"] for w in writes]
    assert phases[0] == "cloning", phases  # before the longest silent window
    assert "reading" in phases
    reading = next(w for w in writes if w["phase"] == "reading")
    assert reading["files_total"] == len(files)
    assert "dependencies" in phases and "simplify" in phases  # analyzer phases intact
    row = await store.get_scan(scan_id)
    assert row["status"] == "completed"
    assert row["progress"] is None  # completion clears it — finished scans read clean
