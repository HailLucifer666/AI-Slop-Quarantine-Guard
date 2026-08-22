"""FastAPI application entry point.

Handles GitHub webhook ingestion: POST /webhooks/github (HMAC verify → dedupe → enqueue → 202)
Health check: GET /healthz
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import init_db
from app.health_router import router as health_router
from app.queue import already_seen, enqueue_webhook_delivery, release_delivery
from app.scans_router import router as scans_router
from app.crew_router import router as crew_router
from app.audit_router import router as audit_router
from app.settings_router import router as settings_router
from app.security import verify_github_signature
from app.store import reconcile_stale_scans

# uvicorn configures only its own loggers, so without this the root level stays at
# WARNING and every logger.info in the app is discarded — including which database
# resolved, the one line that makes an API/worker split diagnosable. Matches the
# format worker.main() already uses so both processes' logs read the same.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

# How often the API re-checks for scans whose worker died. The worker runs the same
# reconciler at startup, but only the API can unwedge the dashboard when the worker
# never comes back at all — which is the case that actually stranded users.
RECONCILE_POLL_SECONDS = 60


async def _reconcile_loop() -> None:
    """Fail scans with a lapsed worker lease, forever, without ever raising."""
    while True:
        await asyncio.sleep(RECONCILE_POLL_SECONDS)
        try:
            await reconcile_stale_scans()
        except Exception:  # noqa: BLE001 — a bad pass must not end the loop
            logger.exception("stale-scan reconciliation pass failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables on startup so the scan API + worker have somewhere to write."""
    await init_db()
    # Clear anything already stranded by a past worker crash before serving traffic,
    # so the dashboard doesn't open on a stuck "running" scan.
    try:
        await reconcile_stale_scans()
    except Exception:  # noqa: BLE001 — never block startup on a reconciliation pass
        logger.exception("startup stale-scan reconciliation failed")
    reconciler = asyncio.create_task(_reconcile_loop())
    try:
        yield
    finally:
        reconciler.cancel()


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
app.include_router(health_router)


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

    # 2. Parse before claiming the GUID — a body we cannot read was never a delivery
    #    we handled, and must not consume the dedupe key.
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="malformed JSON body")

    # 3. Idempotency — GitHub retries on timeout/5xx, so dedupe before enqueue.
    if await already_seen(delivery_guid):
        logger.info("duplicate delivery ignored: %s", delivery_guid)
        return JSONResponse({"status": "duplicate"}, status_code=200)

    # 4. Enqueue, and release the dedupe claim if that fails. already_seen is a SET NX
    #    that marks the GUID handled; if the enqueue then dies, the job exists nowhere
    #    and GitHub's retry of the same delivery would be answered
    #    200 {"status":"duplicate"} — the PR silently never analysed. Releasing the key
    #    turns a lost delivery into a retried one. Worst case on a failed release is a
    #    duplicate scan, which the pipeline already tolerates; a dropped PR it does not.
    try:
        await enqueue_webhook_delivery(delivery_guid, event, payload)
    except Exception:
        await release_delivery(delivery_guid)
        raise
    logger.info("enqueued delivery=%s event=%s", delivery_guid, event)

    return JSONResponse({"status": "accepted"}, status_code=202)
