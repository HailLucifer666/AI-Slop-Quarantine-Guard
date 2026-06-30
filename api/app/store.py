"""Scan persistence (Stage 2).

Thin async helpers over the ``scans`` table, shared by the API (create/read/list)
and the worker (mark running, complete, fail). Findings + analytics are stored as
JSON text on the row for the MVP — normalized into real tables in Phase 5.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.db.models import AppSettings, AuditLog, Scan
from app.db.session import async_session

# Settings validation contract, shared with settings_router.
RULE_IDS = {"SQG001", "SQG002", "SQG003", "SQG004", "SQG005", "SQG006"}
RETENTION_CHOICES = {30, 90, 365}
_DEFAULT_BLOCKED = ["SQG001", "SQG002"]  # fake-dep + secret: the safest block defaults

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


async def create_scan(source: str, ref: str) -> int:
    """Insert a queued scan row and return its id."""
    async with async_session() as session:
        scan = Scan(source=source, ref=ref, status="queued")
        session.add(scan)
        await session.flush()  # assigns scan.id without closing the transaction
        _audit(session, "scan.created", {"scan_id": scan.id, "source": source, "ref": ref})
        await session.commit()  # single atomic commit: scan row + audit row together
        return scan.id


async def mark_running(scan_id: int) -> None:
    """Flip a queued scan to running when the worker picks it up."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        if scan is None:
            logger.warning("mark_running: scan_id=%s not found, skipping", scan_id)
            return
        scan.status = "running"
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
        "progress": json.loads(scan.progress) if getattr(scan, "progress", None) else None,
        "skipped": json.loads(scan.skipped_json) if scan.skipped_json else [],
        "created_at": _iso_utc(scan.created_at),
        "completed_at": _iso_utc(scan.completed_at),
    }
    if include_findings:
        data["findings"] = json.loads(scan.findings_json) if scan.findings_json else []
    return data


async def get_scan(scan_id: int) -> Optional[dict]:
    """Full scan detail (incl. findings) for GET /api/scans/{id}; None if missing."""
    async with async_session() as session:
        scan = await session.get(Scan, scan_id)
        return _row_to_dict(scan, include_findings=True) if scan is not None else None


async def list_scans(limit: int = 50) -> list[dict]:
    """Most-recent scans first (summary only, no findings) for the dashboard list."""
    async with async_session() as session:
        rows = (
            await session.execute(select(Scan).order_by(Scan.id.desc()).limit(limit))
        ).scalars().all()
        return [_row_to_dict(row) for row in rows]


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
