"""Whole-repo scan API (Stage 2).

Three ways to start a scan, all returning ``202 {scan_id}`` and processed async by
the worker:
- ``POST /api/scans`` JSON ``{"source": "url", "url": ...}``  — clone a public repo.
- ``POST /api/scans`` JSON ``{"source": "local", "path": ...}`` — a local dir (dev only).
- ``POST /api/scans`` multipart with a ``file`` field            — upload a zip.

Reads:
- ``GET /api/scans``        — recent scans (summary) for the dashboard list.
- ``GET /api/scans/{id}``   — full detail incl. findings + analytics.

The endpoint validates input at the boundary (URL host, dev-gate, size) so we never
enqueue a job that can't run. The clone/extract re-validates defensively in ``ingest``.
"""

import asyncio
import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.api_security import rate_limit, require_api_key
from app.config import settings
from app.ingest import IngestError, validate_clone_url
from app.queue import enqueue_scan
from app.store import count_scans, create_scan, fail_scan, get_scan, list_scans, summarize_scans

# SSE poll interval + a hard ceiling on stream lifetime — a scan stuck "running"
# (a known worker-reliability gap, see Phase 4) must not hold a connection open
# forever; the client falls back to its own poll once the stream ends.
_SSE_POLL_SECONDS = 1.0
_SSE_MAX_SECONDS = 15 * 60

router = APIRouter(prefix="/api/scans", tags=["scans"])

# Cap the raw upload before buffering it (compressed bytes). The unpacked-size caps
# live in ingest.read_zip; this just stops an oversized request body up front.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("", status_code=202, dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def start_scan(request: Request):
    """Create a scan and enqueue it. Branches on content-type: multipart = zip upload."""
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        return await _start_zip_scan(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected a JSON body or a multipart upload")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    source = body.get("source")
    if source == "url":
        return await _start_url_scan(body)
    if source == "local":
        return await _start_local_scan(body)
    raise HTTPException(
        status_code=400,
        detail="source must be 'url' or 'local' (zip is sent as a multipart upload)",
    )


async def _enqueue_or_fail(scan_id: int, source: str, ref: str) -> None:
    """Enqueue a created scan, or mark it failed so it can't linger as a phantom.

    The row must be committed first — ``enqueue_scan`` needs the DB-assigned id — so a
    Redis outage would otherwise leave a row at "queued" that no worker will ever see
    and nothing will ever fail. That phantom then sits at the top of the scans list
    while the dashboard keeps showing the last *completed* scan as the current result.
    """
    try:
        await enqueue_scan(scan_id, source, ref)
    except Exception as exc:  # noqa: BLE001 — any queue failure, not just Redis errors
        await fail_scan(scan_id, f"could not be queued for scanning: {exc}")
        raise HTTPException(
            status_code=503,
            detail="scan queue is unavailable; the scan was recorded as failed, please retry",
        ) from exc


async def _start_url_scan(body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required for source=url")
    try:
        validate_clone_url(url)  # https + allowed forge host (SSRF guard)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    scan_id = await create_scan("url", url)
    await _enqueue_or_fail(scan_id, "url", url)
    return {"scan_id": scan_id}


async def _start_local_scan(body: dict) -> dict:
    if settings.environment != "development":
        raise HTTPException(status_code=403, detail="local-folder scans are only allowed in development")
    path = (body.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="path must be an existing directory")
    scan_id = await create_scan("local", path)
    await _enqueue_or_fail(scan_id, "local", path)
    return {"scan_id": scan_id}


async def _start_zip_scan(request: Request) -> dict:
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        raise HTTPException(status_code=400, detail="multipart upload requires a 'file' field")
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="uploaded file too large")
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    # Spool the bytes to a temp file and enqueue its path — the worker reads and
    # deletes it. (Shared-disk assumption for now; object storage in Phase 5.)
    fd, tmp_path = tempfile.mkstemp(prefix="slopupload-", suffix=".zip")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)

    filename = getattr(upload, "filename", None) or "upload.zip"
    try:
        scan_id = await create_scan("zip", filename)
        # Marks the row failed on a queue outage, so it can't linger as a phantom.
        await _enqueue_or_fail(scan_id, "zip", tmp_path)
    except Exception:
        # Don't leak the spooled upload if the DB insert or Redis enqueue fails.
        os.unlink(tmp_path)
        raise
    return {"scan_id": scan_id}


@router.get("", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def get_scans(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Recent scans (summary) for the dashboard list, paginated."""
    scans = await list_scans(limit=limit, offset=offset)
    total = await count_scans()
    return {"scans": scans, "total": total, "has_more": offset + len(scans) < total}


_RANGE_RE = re.compile(r"^(\d+)d$")


@router.get("/summary", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def get_scans_summary(range: str = Query("30d")):
    """Cross-scan rollup (clean-pass-rate, totals, by-rule, top-files) for the
    dashboard overview. ``range`` is a window like '7d'/'30d'/'90d'."""
    match = _RANGE_RE.match(range)
    if not match:
        raise HTTPException(status_code=400, detail="range must look like '30d'")
    since = datetime.utcnow() - timedelta(days=int(match.group(1)))
    return await summarize_scans(since=since)


@router.get("/{scan_id}", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def get_scan_detail(scan_id: int):
    """Full scan detail incl. findings + analytics."""
    scan = await get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return scan


async def _scan_event_stream(scan_id: int):
    """Poll the scan row and yield an SSE frame each time status/progress changes.
    Ends the stream on a terminal status, a missing scan, or the lifetime cap —
    never silently: a timed-out stream tells the client to fall back to polling."""
    last_payload = None
    deadline = time.monotonic() + _SSE_MAX_SECONDS
    while True:
        scan = await get_scan(scan_id)
        if scan is None:
            yield f"event: error\ndata: {json.dumps({'detail': 'scan not found'})}\n\n"
            return
        payload = {"status": scan["status"], "progress": scan["progress"]}
        if payload != last_payload:
            yield f"data: {json.dumps(payload)}\n\n"
            last_payload = payload
        if scan["status"] in ("completed", "failed"):
            return
        if time.monotonic() >= deadline:
            yield f"event: timeout\ndata: {json.dumps({'detail': 'stream lifetime exceeded, keep polling'})}\n\n"
            return
        await asyncio.sleep(_SSE_POLL_SECONDS)


@router.get("/{scan_id}/events", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def stream_scan_events(scan_id: int):
    """Live progress via Server-Sent Events while a scan runs — a smoother
    alternative to the dashboard's 2s poll. One-way (SSE, not a WebSocket) is
    enough since only the server ever has new information here."""
    scan = await get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return StreamingResponse(_scan_event_stream(scan_id), media_type="text/event-stream")
