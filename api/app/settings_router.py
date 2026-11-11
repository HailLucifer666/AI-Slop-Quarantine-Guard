"""Gate settings API (Phase 8).

A single global settings row (repo defaults) read/written by the dashboard
Settings page. Saving persists intent only — enforcement (blocking) is Phase 9.
Validation lives here at the boundary; store.update_settings filters defensively too.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api_security import rate_limit, require_api_key
from app.store import RETENTION_CHOICES, RULE_IDS, get_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def read_settings():
    """Current global gate settings (seeds defaults on first read)."""
    return await get_settings()


@router.patch("", dependencies=[Depends(require_api_key), Depends(rate_limit)])
async def patch_settings(request: Request):
    """Partial-update the settings. Validates each provided field at the boundary."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected a JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    if "block_mode" in body and not isinstance(body["block_mode"], bool):
        raise HTTPException(status_code=400, detail="block_mode must be a boolean")

    if "blocked_rules" in body:
        rules = body["blocked_rules"]
        if not isinstance(rules, list) or any(r not in RULE_IDS for r in rules):
            raise HTTPException(
                status_code=400, detail="blocked_rules must be a subset of SQG001..SQG007"
            )

    if "retention_days" in body:
        try:
            rd = int(body["retention_days"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="retention_days must be a number")
        if rd not in RETENTION_CHOICES:
            raise HTTPException(status_code=400, detail="retention_days must be 30, 90, or 365")
        body["retention_days"] = rd

    return await update_settings(body)
