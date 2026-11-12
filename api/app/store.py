"""Scan persistence (Stage 2).

Thin async helpers over the ``scans`` table, shared by the API (create/read/list)
and the worker (mark running, complete, fail). Findings + analytics are stored as
JSON text on the row for the MVP — normalized into real tables in Phase 5.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select

from app.analyzers.base import RULE_VERSION
from app.db.models import AppSettings, AuditLog, Scan, WorkerHeartbeat
from app.db.session import async_session

# Settings validation contract, shared with settings_router.
# SQG008 is absent on purpose: it is specified (AI-scratchpad detection) but not built,
# so accepting it in blocked_rules would let a user configure a check that never runs.
RULE_IDS = {"SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006", "SQG007", "SQG009"}
RETENTION_CHOICES = {30, 90, 365}
# Stamped onto every completed scan so a stored result records which revision of the
# rule set produced it. Imported from analyzers.base so the two can never drift — the
# hand-copied literal here stopped half-way once (RULE_VERSION went 1.1 while this kept
# stamping 1.0), caught in the 2026-11-12 audit and locked by test_stored_scan_rule_version_matches_engine.
SQG_RULES_VERSION = RULE_VERSION
_DEFAULT_BLOCKED = ["SQG001", "SQG002"]  # fake-dep + secret: the safest block defaults

# How stale a running scan's heartbeat may get before we declare its worker dead.
# 5 minutes matches the watchdog docs/ARCHITECTURE.md already promises for Check Runs
# ("no orphaned spinners") and is comfortably above the worker's 20s stamp interval,
# so a slow analyzer or a GC pause can never be mistaken for a crash.
STALE_LEASE_SECONDS = 300

logger = logging.getLogger("store")


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """Serialize a stored (naive-UTC) timestamp as a tz-aware ISO string.

    Timestamps are written with ``datetime.utcnow()`` — correct UTC, but naive. A
    naive ``.isoformat()`` ("2026-06-29T11:21:00") is parsed by the browser as LOCAL
    time, skewing relative times by the viewer's offset. Tagging it UTC ("…+00:00")
    makes ``new Date(...)`` parse it correctly everywhere.
    """
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _audit(session, action: str, details: dict) -> None:
    """Stage an immutable audit-trail row inside the caller's transaction.

    Every scan lifecycle transition is recorded so a non-technical owner (and any
    future compliance review) can answer "what did the Guard do, and when" without
    trusting the mutable scan row. Best-effort detail payload, never secrets.
    """
    session.add(AuditLog(action=action, details=json.dumps(details, default=str)))


async def record_event(action: str, details: dict) -> None:
    """Record a standalone audit-trail event not tied to a scan row — e.g. a PR
    analysis failure. PR analysis has no persisted DB row the way a whole-repo
    scan does (the Check Run on GitHub is its own user-facing record), so this is
    the only durable trail of "the gate hit an internal error and didn't finish"
    for operational visibility."""
    async with async_session() as session:
        _audit(session, action, details)
        await session.commit()


async def create_scan(source: str, ref: str) -> int:
    """Insert a queued scan row and return its id."""
    async with async_session() as session:
        scan = Scan(source=source, ref=ref, status="queued")
        session.add(scan)
        await session.flush()  # assigns scan.id without closing the transaction
        _audit(session, "scan.created", {"scan_id": scan.id, "source": source, "ref": ref})
        await session.commit()  # single atomic commit: scan row + audit row together
        assert scan.id is not None  # flushed above; mypy needs the narrowing
        return scan.id


async def mark_running(scan_id: int) -> None:
    """Flip a queued scan to running when the worker picks it up."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("mark_running: scan_id=%s not found, skipping", scan_id)
            return
        scan.status = "running"
        scan.heartbeat_at = datetime.utcnow()  # open the liveness lease
        _audit(session, "scan.running", {"scan_id": scan_id})
        await session.commit()


async def update_progress(scan_id: int, payload: dict) -> None:
    """Record live scan progress (phase/index while running). Best-effort: a failure
    here must never fail the scan, so callers swallow exceptions."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            return
        scan.progress = json.dumps(payload, default=str)
        scan.heartbeat_at = datetime.utcnow()  # same UPDATE — no extra round trip
        await session.commit()


async def touch_scan_heartbeat(scan_id: int) -> None:
    """Renew a running scan's liveness lease. Best-effort, like update_progress.

    Progress only advances between analyzers, so a single analyzer running near its
    90s budget could otherwise let the lease lapse mid-scan and get a healthy scan
    reconciled out from under itself.
    """
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            return
        scan.heartbeat_at = datetime.utcnow()
        await session.commit()


async def reconcile_stale_scans() -> list[int]:
    """Fail every running scan whose worker lease has lapsed; return their ids.

    A worker that dies mid-scan leaves the row at "running" forever. Because the
    dashboard's headline numbers come only from *completed* scans, that stuck row
    silently leaves the previous scan on screen as if it were the current result —
    the "stale results" symptom. Failing it honestly makes the gap visible instead.

    ``fail_scan`` overwrites unconditionally, so a double-reconcile (worker startup
    racing the API's periodic pass) is harmless — no lock needed for a single-instance
    deployment.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_LEASE_SECONDS)
    async with async_session() as session:
        stale_ids = (
            await session.execute(
                select(Scan.id).where(
                    Scan.status == "running",
                    or_(
                        Scan.heartbeat_at < cutoff,
                        # Pre-upgrade rows (and any scan that died before its first
                        # stamp) have no heartbeat — fall back to when it was created.
                        Scan.heartbeat_at.is_(None) & (Scan.created_at < cutoff),
                    ),
                )
            )
        ).scalars().all()

    stale_ids_clean = [sid for sid in stale_ids if sid is not None]

    for scan_id in stale_ids_clean:
        await fail_scan(
            scan_id,
            f"worker heartbeat lease expired (no update for over {STALE_LEASE_SECONDS}s) — "
            "the worker process most likely stopped mid-scan. No results were produced; "
            "re-run the scan.",
        )
    if stale_ids_clean:
        logger.warning("reconciled %d stale running scan(s): %s", len(stale_ids_clean), stale_ids_clean)
    return stale_ids_clean


async def touch_worker_heartbeat() -> None:
    """Stamp the global worker-liveness row, whether or not a scan is in flight."""
    async with async_session() as session:
        row = await session.get(WorkerHeartbeat, 1)
        if row is None:
            session.add(WorkerHeartbeat(id=1, updated_at=datetime.utcnow()))
        else:
            row.updated_at = datetime.utcnow()
        await session.commit()


async def get_worker_heartbeat() -> Optional[datetime]:
    """When a worker last reported in, or None if one never has."""
    async with async_session() as session:
        row = await session.get(WorkerHeartbeat, 1)
        return row.updated_at if row is not None else None


async def record_ingest_provenance(
    scan_id: int,
    *,
    resolved_sha: Optional[str],
    content_hash: str,
    file_count: int,
) -> None:
    """Record exactly what was ingested, before analysis begins.

    Written up front deliberately: a scan that dies during analysis still proves which
    snapshot it was looking at. It also answers the question behind "is this stale?" —
    a re-scan of unchanged code yields a NEW scan id with a MATCHING content hash,
    which is evidence of a fresh run, not of a cached one.
    """
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("record_ingest_provenance: scan_id=%s not found", scan_id)
            return
        scan.resolved_sha = resolved_sha
        scan.content_hash = content_hash
        scan.file_count = file_count
        scan.ingested_at = datetime.utcnow()
        await session.commit()


async def complete_scan(scan_id: int, result: dict) -> None:
    """Persist a finished scan's analytics + findings and mark it completed.

    ``result`` is the dict returned by ``app.scan.run_scan``.
    """
    analytics = result.get("analytics", {})
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("complete_scan: scan_id=%s not found, result dropped", scan_id)
            return
        scan.status = "completed"
        scan.files_scanned = analytics.get("files_scanned", 0)
        scan.files_skipped = analytics.get("files_skipped", 0)
        scan.duration_ms = result.get("duration_ms")
        scan.analytics_json = json.dumps(analytics)
        scan.findings_json = json.dumps(result.get("findings", []))
        scan.skipped_json = json.dumps(result.get("skipped", []))
        scan.suppressed_json = json.dumps(result.get("suppressed", []))
        coverage = result.get("coverage")
        scan.coverage_json = json.dumps(coverage) if coverage else None
        groups = result.get("groups")
        scan.groups_json = json.dumps(groups) if groups else None
        scan.engine_versions_json = json.dumps({
            "rules_version": SQG_RULES_VERSION,
            "engines": result.get("engine_versions", {}),
        })
        scan.progress = None  # finished — clear live progress
        scan.completed_at = datetime.utcnow()
        would_block = analytics.get("would_block", 0)
        _audit(session, "scan.completed", {
            "scan_id": scan_id,
            "total_findings": analytics.get("total_findings", 0),
            "block_eligible": analytics.get("block_eligible", 0),
            "would_block": would_block,
            "files_scanned": scan.files_scanned,
        })
        # Shadow gate: a separate, explicit trail row when enforcement WOULD have
        # blocked — recorded only; no merge is ever blocked (real blocking is Phase 9).
        if would_block:
            _audit(session, "scan.shadow_block", {
                "scan_id": scan_id,
                "would_block": would_block,
                "note": "shadow only — no block was applied",
            })
        await session.commit()


async def fail_scan(scan_id: int, reason: str) -> None:
    """Mark a scan failed with a human-readable reason (never a silent drop)."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("fail_scan: scan_id=%s not found, failure reason dropped: %s", scan_id, reason[:200])
            return
        scan.status = "failed"
        scan.error = reason[:2000]
        scan.progress = None  # finished — clear live progress
        scan.completed_at = datetime.utcnow()
        _audit(session, "scan.failed", {"scan_id": scan_id, "reason": reason[:500]})
        await session.commit()


def _row_to_dict(scan: Scan, *, include_findings: bool = False) -> dict:
    # Narrow before loads(): these columns are nullable, and getattr(...) does not
    # narrow the attribute for mypy.
    coverage_json = getattr(scan, "coverage_json", None)
    groups_json = getattr(scan, "groups_json", None)
    progress_json = getattr(scan, "progress", None)
    engine_versions_json = getattr(scan, "engine_versions_json", None)
    data = {
        "id": scan.id,
        "source": scan.source,
        "ref": scan.ref,
        "status": scan.status,
        "files_scanned": scan.files_scanned,
        "files_skipped": scan.files_skipped,
        "duration_ms": scan.duration_ms,
        "error": scan.error,
        "analytics": json.loads(scan.analytics_json) if scan.analytics_json else None,
        "coverage": json.loads(coverage_json) if coverage_json else None,
        "groups": json.loads(groups_json) if groups_json else None,
        "progress": json.loads(progress_json) if progress_json else None,
        # Provenance — what was analyzed, so the result can be re-derived and checked.
        "resolved_sha": getattr(scan, "resolved_sha", None),
        "content_hash": getattr(scan, "content_hash", None),
        "file_count": getattr(scan, "file_count", None),
        "ingested_at": _iso_utc(getattr(scan, "ingested_at", None)),
        "engine_versions": (
            json.loads(engine_versions_json)
            if engine_versions_json else None
        ),
        "skipped": json.loads(scan.skipped_json) if scan.skipped_json else [],
        "suppressed": json.loads(scan.suppressed_json) if scan.suppressed_json else [],
        "created_at": _iso_utc(scan.created_at),
        "completed_at": _iso_utc(scan.completed_at),
        "heartbeat_at": _iso_utc(getattr(scan, "heartbeat_at", None)),
    }
    if include_findings:
        data["findings"] = json.loads(scan.findings_json) if scan.findings_json else []
    return data


async def get_scan(scan_id: int) -> Optional[dict]:
    """Full scan detail (incl. findings) for GET /api/scans/{id}; None if missing."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            return None
        data = _row_to_dict(scan, include_findings=True)
        if scan.status == "queued":
            # Queue context for the dashboard: how many queued scans precede this one.
            # 0 = next up. A RUNNING scan is not queued and counts for nobody.
            data["queue_position"] = await _queued_ahead(session, scan_id)
        return data


async def _queued_ahead(session, scan_id: int) -> int:
    """Count queued scans with a smaller id — FIFO, because enqueue follows
    create_scan and ids are assigned at creation. The count self-corrects on every
    poll; if orphan-requeue ever returns jobs out of id order, the position is
    advisory UI information, not a guarantee (the Redis LPOS order is the truth the
    worker consumes — this number is what a human reads)."""
    result = await session.execute(
        select(func.count())
        .select_from(Scan)
        .where(Scan.status == "queued", Scan.id < scan_id)
    )
    return int(result.scalar_one())



async def list_scans(limit: int = 50, offset: int = 0) -> list[dict]:
    """Most-recent scans first (summary only, no findings) for the dashboard list."""
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Scan).order_by(Scan.id.desc()).limit(limit).offset(offset)
            )
        ).scalars().all()
        return [_row_to_dict(row) for row in rows]


async def count_scans() -> int:
    """Total scan count (all statuses) — pagination metadata for the scans list."""
    async with async_session() as session:
        result = await session.execute(select(func.count()).select_from(Scan))
        return result.scalar_one()


# Cap how many completed scans a summary rolls up over. Analytics are stored as a
# JSON blob per row (see module docstring), so the rollup happens in Python, not
# SQL — an unbounded history would mean loading everything into memory. Capped,
# never silently: `scanned_in_range` always reports exactly how many were rolled up.
SUMMARY_SCAN_CAP = 2000


async def summarize_scans(since: Optional[datetime] = None) -> dict:
    """Cross-scan rollup for the dashboard overview: clean-pass-rate, totals,
    by-rule, top-files — computed server-side instead of the client re-deriving
    it from a capped scan list on every poll."""
    async with async_session() as session:
        query = select(Scan).where(Scan.status == "completed")
        if since is not None:
            query = query.where(Scan.created_at >= since)
        query = query.order_by(Scan.id.desc()).limit(SUMMARY_SCAN_CAP)
        rows = (await session.execute(query)).scalars().all()

    total_findings = 0
    certain_total = 0
    clean_count = 0
    incomplete_count = 0
    by_rule: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for row in rows:
        a = json.loads(row.analytics_json) if row.analytics_json else None
        if not a:
            continue
        total_findings += a.get("total_findings", 0)
        certain_total += a.get("by_confidence", {}).get("CERTAIN", 0)
        # "clean" now means every check ran and found nothing (app.coverage.summarize).
        # Scans stored before coverage existed have clean=False, which understates the
        # pass rate — preferable to counting an unverified scan as a pass.
        if a.get("clean"):
            clean_count += 1
        if a.get("rules_incomplete"):
            incomplete_count += 1
        for rule_id, n in a.get("by_rule", {}).items():
            by_rule[rule_id] = by_rule.get(rule_id, 0) + n
        for f in a.get("top_files", []):
            by_file[f["file_path"]] = by_file.get(f["file_path"], 0) + f["count"]

    completed = len(rows)
    top_files = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:10]
    return {
        "scanned_in_range": completed,
        "clean_pass_rate": round(clean_count / completed * 100) if completed else 100,
        # How many of those scans had at least one check that couldn't finish — the
        # caveat that belongs next to any pass rate.
        "scans_with_incomplete_coverage": incomplete_count,
        "certain_total": certain_total,
        "findings_total": total_findings,
        "by_rule": by_rule,
        "top_files": [{"file_path": p, "count": n} for p, n in top_files],
    }


async def list_audit(limit: int = 100) -> list[dict]:
    """Most-recent audit entries first — the tamper-evident trail of Guard actions."""
    async with async_session() as session:
        rows = (
            await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
        ).scalars().all()
        return [
            {
                "id": row.id,
                "action": row.action,
                "details": json.loads(row.details) if row.details else None,
                "created_at": _iso_utc(row.created_at),
            }
            for row in rows
        ]


def _settings_to_dict(s: AppSettings) -> dict:
    return {
        "block_mode": s.block_mode,
        "blocked_rules": json.loads(s.blocked_rules) if s.blocked_rules else [],
        "retention_days": s.retention_days,
        "updated_at": _iso_utc(s.updated_at),
    }


def _new_settings_row() -> AppSettings:
    return AppSettings(
        id=1, block_mode=False, blocked_rules=json.dumps(_DEFAULT_BLOCKED), retention_days=90
    )


async def get_settings() -> dict:
    """Global gate settings (the single id=1 row), seeding defaults on first read."""
    async with async_session() as session:
        row = await session.get(AppSettings, 1)
        if row is None:
            row = _new_settings_row()
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return _settings_to_dict(row)


async def update_settings(patch: dict) -> dict:
    """Partial-update the settings row and audit it. Caller validates the payload."""
    async with async_session() as session:
        row = await session.get(AppSettings, 1)
        if row is None:
            row = _new_settings_row()
            session.add(row)
            await session.flush()
        if "block_mode" in patch:
            row.block_mode = bool(patch["block_mode"])
        if "blocked_rules" in patch:
            row.blocked_rules = json.dumps([r for r in patch["blocked_rules"] if r in RULE_IDS])
        if "retention_days" in patch:
            row.retention_days = int(patch["retention_days"])
        row.updated_at = datetime.utcnow()
        _audit(session, "settings.updated", _settings_to_dict(row))
        await session.commit()
        await session.refresh(row)
        return _settings_to_dict(row)
