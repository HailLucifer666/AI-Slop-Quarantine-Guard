"""Audit-trail API.

Read-only view of the immutable log of Guard actions (scan lifecycle events).
Separate prefix from /api/scans so the path never collides with /api/scans/{id}.
"""

from fastapi import APIRouter, Depends

from app.api_security import rate_limit, require_api_key
from app.store import list_audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def get_audit():
    """Recent audit entries (newest first)."""
    return {"audit": await list_audit()}
