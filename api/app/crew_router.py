"""The Crew API (Phase 7) — on-demand plain-English explanation for one finding.

POST /api/crew/explain  body = a finding object (as returned in scan detail).
Returns {explanation, why_it_matters, how_to_fix}, or 503 when the explainer is
unavailable (no key / provider down) so the UI can say so without breaking.
Advisory only: this endpoint never mutates a scan or its conclusions.
"""

from fastapi import APIRouter, HTTPException, Request

from app.crew.explainer import explain_finding

router = APIRouter(prefix="/api/crew", tags=["crew"])


@router.post("/explain")
async def explain(request: Request):
    try:
        finding = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="expected a finding JSON body")
    if not isinstance(finding, dict) or not finding.get("rule_id"):
        raise HTTPException(status_code=400, detail="body must be a finding object")

    result = await explain_finding(finding)
    if result is None:
        raise HTTPException(
            status_code=503,
            detail="The AI explainer is unavailable right now. The finding itself stands.",
        )
    return result
