"""Run code samples through the engine and roll them up into a leaderboard.

The harness reuses ``app.scan.run_scan`` — the exact whole-repo engine the product
ships — so a benchmark score is the same measure a user sees, never a parallel
re-implementation that could drift.
"""

from statistics import mean
from typing import Dict, List

from app.scan import run_scan

from .corpus import METHODOLOGY_VERSION
from .scoring import WEIGHTS, score_findings


async def score_sample(files: Dict[str, str]) -> dict:
    """Score one (tool, task) code sample. ``files`` is a {path: content} map."""
    result = await run_scan(files)
    scored = score_findings(result["findings"])
    scored["analytics"] = result["analytics"]
    return scored


async def run_benchmark(samples: Dict[str, Dict[str, Dict[str, str]]], *, data_source: str) -> dict:
    """Score every tool's samples and return a ranked leaderboard.

    Args:
        samples: {tool_name: {task_id: {path: content}}}.
        data_source: honest provenance label baked into the output — e.g.
            "live:2026-06-30" for real tool runs, or "sample-fixtures" for demo
            data. The leaderboard is NEVER published as real unless this says so.

    Returns a JSON-serializable dict: methodology version, weights, provenance, and
    tools sorted by Trust Score (descending), each with its per-task breakdown.
    """
    tools: List[dict] = []
    for tool, tasks in samples.items():
        per_task: List[dict] = []
        for task_id, files in tasks.items():
            scored = await score_sample(files)
            per_task.append({
                "task_id": task_id,
                "trust_score": scored["trust_score"],
                "by_confidence": scored["by_confidence"],
                "findings_total": scored["findings_total"],
            })
        scores = [t["trust_score"] for t in per_task]
        tools.append({
            "tool": tool,
            "trust_score": round(mean(scores), 1) if scores else None,
            "samples_scored": len(per_task),
            "per_task": per_task,
        })

    # Rank by score; tools with no samples sink to the bottom (None < any number).
    tools.sort(key=lambda t: (t["trust_score"] is None, -(t["trust_score"] or 0)))
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "weights": WEIGHTS,
        "data_source": data_source,
        "tools": tools,
    }
