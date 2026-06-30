"""Audit-trail API.

Read-only view of the immutable log of Guard actions (scan lifecycle events).
Separate prefix from /api/scans so the path never collides with /api/scans/{id}.
"""

from fastapi import APIRouter

from app.store import list_audit

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def get_audit():
    """Recent audit entries (newest first)."""
    return {"audit": await list_audit()}
