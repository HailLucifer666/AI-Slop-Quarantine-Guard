"""FastAPI application entry point.

Handles GitHub webhook ingestion: POST /webhooks/github (HMAC verify → dedupe → enqueue → 202)
Health check: GET /healthz
"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import init_db
from app.queue import already_seen, enqueue_webhook_delivery
from app.scans_router import router as scans_router
from app.crew_router import router as crew_router
from app.audit_router import router as audit_router
from app.settings_router import router as settings_router
from app.security import verify_github_signature

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables on startup so the scan API + worker have somewhere to write."""
    await init_db()
    yield


app = FastAPI(title="AI Slop Quarantine Guard", lifespan=lifespan)

# The Next.js dashboard calls these endpoints from the browser.
_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scans_router)
app.include_router(crew_router)
app.include_router(audit_router)
app.include_router(settings_router)


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    """GitHub webhook handler.

    HMAC-SHA256 verify (raw body) → dedupe by X-GitHub-Delivery → enqueue → 202.
    No analysis happens here — that's the worker's job (Phase 2). The point is
    to ACK in well under 10s so GitHub never times out and retries.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    delivery_guid = request.headers.get("X-GitHub-Delivery", "")
    event = request.headers.get("X-GitHub-Event", "")

    # 1. Verify HMAC on the RAW bytes, before parsing anything.
    try:
        valid = verify_github_signature(raw_body, signature, settings.github_webhook_secret)
    except ValueError:
        raise HTTPException(status_code=401, detail="malformed signature header")
    if not valid:
        raise HTTPException(status_code=401, detail="signature verification failed")

    if not delivery_guid:
        raise HTTPException(status_code=400, detail="missing X-GitHub-Delivery header")

    # 2. Idempotency — GitHub retries on timeout/5xx, so dedupe before enqueue.
    if await already_seen(delivery_guid):
        logger.info("duplicate delivery ignored: %s", delivery_guid)
        return JSONResponse({"status": "duplicate"}, status_code=200)

    # 3. Enqueue the raw delivery and return immediately. Zero analysis here.
    payload = json.loads(raw_body)
    await enqueue_webhook_delivery(delivery_guid, event, payload)
    logger.info("enqueued delivery=%s event=%s", delivery_guid, event)

    return JSONResponse({"status": "accepted"}, status_code=202)
