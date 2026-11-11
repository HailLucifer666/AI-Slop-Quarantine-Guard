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

import os
import tempfile

import redis
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api_security import rate_limit, require_api_key
from app.config import settings
from app.ingest import IngestError, validate_clone_url
from app.queue import enqueue_scan
from app.store import create_scan, fail_scan, get_scan, list_scans

router = APIRouter(prefix="/api/scans", tags=["scans"])

# Cap the raw upload before buffering it (compressed bytes). The unpacked-size caps
# live in ingest.read_zip; this just stops an oversized request body up front.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


async def _safe_enqueue_scan(scan_id: int, source: str, ref: str) -> None:
    """Enqueue a scan, or fail loudly when Redis is down.

    A scan that cannot be queued must not linger as "queued" forever — mark it
    failed and 503 so the dashboard never shows a phantom pending scan. Redis
    being down is a service condition, not an internal error (500).
    """
    try:
        await enqueue_scan(scan_id, source, ref)
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError, OSError):
        await fail_scan(scan_id, "queue unavailable: redis unreachable")
        raise HTTPException(
            status_code=503,
            detail="Scan queue unavailable (Redis not reachable).",
        )


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


async def _start_url_scan(body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url is required for source=url")
    try:
        validate_clone_url(url)  # https + allowed forge host (SSRF guard)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    scan_id = await create_scan("url", url)
    await _safe_enqueue_scan(scan_id, "url", url)
    return {"scan_id": scan_id}


async def _start_local_scan(body: dict) -> dict:
    if settings.environment != "development":
        raise HTTPException(status_code=403, detail="local-folder scans are only allowed in development")
    path = (body.get("path") or "").strip()
    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="path must be an existing directory")
    scan_id = await create_scan("local", path)
    await _safe_enqueue_scan(scan_id, "local", path)
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
        await _safe_enqueue_scan(scan_id, "zip", tmp_path)
    except Exception:
        # Don't leak the spooled upload if the DB insert or Redis enqueue fails.
        os.unlink(tmp_path)
        raise
    return {"scan_id": scan_id}


@router.get("", dependencies=[Depends(rate_limit)])
async def get_scans():
    """Recent scans (summary) for the dashboard list."""
    return {"scans": await list_scans()}


@router.get("/{scan_id}", dependencies=[Depends(rate_limit)])
async def get_scan_detail(scan_id: int):
    """Full scan detail incl. findings + analytics."""
    scan = await get_scan(scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return scan
