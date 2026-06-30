"""Trust Score: turn a list of analyzer findings into a 0–100 reproducible score.

Neutral by construction — it uses the engine's OWN confidence tiers as the penalty
basis, so every tool is judged by the exact same measure the product applies to a
real scan. Pure function, no I/O: same findings in → same score out, every time.
"""

from typing import Dict, List

# Penalty per finding, keyed by the analyzer's confidence tier. CERTAIN findings
# are reproducible facts (a hallucinated dep, a live secret) and cost the most;
# advisory tiers cost progressively less. Published + adjustable (see METHODOLOGY).
WEIGHTS: Dict[str, int] = {"CERTAIN": 25, "HIGH": 8, "MEDIUM": 3}
MAX_SCORE = 100


def score_findings(findings: List[dict]) -> dict:
    """Score one code sample's findings.

    Returns trust_score (0–100), the total penalty, and a per-confidence breakdown
    so the score is fully explainable from the published raw findings.
    """
    by_confidence: Dict[str, int] = {tier: 0 for tier in WEIGHTS}
    penalty = 0
    for f in findings:
        tier = f.get("confidence", "MEDIUM")
        by_confidence[tier] = by_confidence.get(tier, 0) + 1
        penalty += WEIGHTS.get(tier, 0)
    return {
        "trust_score": max(0, MAX_SCORE - penalty),
        "penalty": penalty,
        "by_confidence": by_confidence,
        "findings_total": len(findings),
    }
