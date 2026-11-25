"""Honest PR Gate verdict decision (CLEAN / FLAGGED / BLOCKED / UNVERIFIED).

Separates four outcomes that a boolean findings-or-not check previously collapsed:
- CLEAN: every applicable check ran conclusively and found nothing -> GitHub `success`.
- FLAGGED: at least one finding (advisory or label-only) -> GitHub `action_required`.
- BLOCKED: opt-in blocking enabled AND at least one block-eligible finding on a
  configured blocked rule -> GitHub `failure`.
- UNVERIFIED: the diff could not be fetched, or checks errored/timed out with zero
  findings -> GitHub `neutral` (never green `success` on an unverified change).

A proven finding always beats UNVERIFIED: if SQG002 caught a real secret while SQG004
timed out, the PR is FLAGGED (or BLOCKED), never downgraded to neutral.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional

from app.analyzers.base import Finding
from app.checks import would_block_findings


class Verdict(str, Enum):
    CLEAN = "CLEAN"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


CONCLUSION: dict[Verdict, str] = {
    Verdict.CLEAN: "success",
    Verdict.FLAGGED: "action_required",
    Verdict.BLOCKED: "failure",
    Verdict.UNVERIFIED: "neutral",
}

UNVERIFIED_DIFF_SUMMARY = (
    "⚠️ Slop Guard could not examine this change (diff unavailable), so it makes no claim."
)


@dataclass(frozen=True)
class GateInput:
    findings: List[Finding] = field(default_factory=list)
    diff_available: bool = True
    coverage: Optional[dict] = None
    block_mode: bool = False
    blocked_rules: Iterable[str] = field(default_factory=tuple)


def _has_incomplete_failure(coverage: Optional[dict]) -> bool:
    """True if any rule errored or timed out, or files were left unexamined."""
    if not coverage:
        return False
    if coverage.get("unexamined_files", 0) > 0:
        return True
    for rule in coverage.get("rules") or []:
        if rule.get("status") in ("errored", "timed_out"):
            return True
    return False


def decide(inp: GateInput) -> Verdict:
    """Pure verdict function — maps GateInput to one of four honest Verdicts."""
    if not inp.diff_available:
        return Verdict.UNVERIFIED
    if inp.findings:
        if inp.block_mode and would_block_findings(inp.findings, inp.blocked_rules):
            return Verdict.BLOCKED
        return Verdict.FLAGGED
    if _has_incomplete_failure(inp.coverage):
        return Verdict.UNVERIFIED
    return Verdict.CLEAN


def conclusion_for(inp: GateInput) -> str:
    """Map GateInput directly to the GitHub Check Run conclusion string."""
    return CONCLUSION[decide(inp)]
