"""GitHub Check Run output formatting (Phase 4).

Turns the analyzers' findings into what a non-coder sees on their PR:
- a Check Run conclusion (green `success` / orange `action_required`),
- a plain-English, truncation-safe summary,
- inline annotations anchored to the exact added lines.

Phase 4 is label-only: a finding makes the check orange, never red. Real
blocking (`conclusion: failure` on CERTAIN + block-eligible findings) is
opt-in and arrives in Phase 9 — the `block_eligible` flag is carried through
now so that gate is a config change, not a rewrite.
"""

from typing import List, Optional

from .analyzers.base import Confidence, Finding

# Most-severe first, so the summary and the 50-annotation cap keep the
# findings that matter most.
_CONFIDENCE_ORDER = {Confidence.CERTAIN: 0, Confidence.HIGH: 1, Confidence.MEDIUM: 2}

# GitHub Checks API: annotation_level ∈ notice | warning | failure.
_ANNOTATION_LEVEL = {
    Confidence.CERTAIN: "failure",
    Confidence.HIGH: "warning",
    Confidence.MEDIUM: "notice",
}

# GitHub accepts at most 50 annotations per request.
MAX_ANNOTATIONS = 50

# Plain-English label per confidence tier, for the summary.
_TIER_LABEL = {
    Confidence.CERTAIN: "Definitely a problem",
    Confidence.HIGH: "Likely a problem",
    Confidence.MEDIUM: "Worth a look",
}


def _sorted(findings: List[Finding]) -> List[Finding]:
    """Most-severe first, then by file/line for stable, readable output."""
    return sorted(
        findings,
        key=lambda f: (_CONFIDENCE_ORDER.get(f.confidence, 9), f.file_path, f.line_start),
    )


def determine_conclusion(findings: List[Finding]) -> str:
    """Map findings to a Check Run conclusion (Phase 4: label-only).

    Returns "success" when nothing was found, otherwise "action_required"
    (orange — highly visible, never a green `neutral`). Blocking is Phase 9.
    """
    return "action_required" if findings else "success"


# The ONLY categories that may ever block a merge: SQG001 hallucinated dependency
# and SQG002 leaked secret. A finding is block-eligible iff it is CERTAIN *and* in
# this set — the single source of truth, so no analyzer can quietly diverge.
BLOCKABLE_CATEGORIES = frozenset({"dependency", "secret"})


def is_block_eligible(category: str, confidence: Confidence) -> bool:
    """The canonical block-eligibility invariant (see BLOCKABLE_CATEGORIES)."""
    return confidence is Confidence.CERTAIN and category in BLOCKABLE_CATEGORIES


def apply_block_eligibility(findings: List[Finding]) -> List[Finding]:
    """Force every finding's ``block_eligible`` to the canonical invariant.

    Analyzers set the flag themselves today and agree with this; running it as a
    final pass guards against a future rule mis-setting the flag (e.g. marking an
    advisory CVE block-eligible). Mutates in place and returns the same list.
    """
    for f in findings:
        f.block_eligible = is_block_eligible(f.category, f.confidence)
    return findings


def dedupe_findings(findings: List[Finding]) -> List[Finding]:
    """Collapse findings that share ``(file_path, line_start, rule_id)``.

    Two analyzer passes (or a PR diff overlapping a manifest) can surface the same
    rule on the same line twice; keep the highest-confidence copy. First-seen order
    is preserved so the summary stays stable.
    """
    best: dict[tuple, Finding] = {}
    order: list[tuple] = []
    for f in findings:
        key = (f.file_path, f.line_start, f.rule_id)
        current = best.get(key)
        if current is None:
            best[key] = f
            order.append(key)
        elif _CONFIDENCE_ORDER.get(f.confidence, 9) < _CONFIDENCE_ORDER.get(current.confidence, 9):
            best[key] = f
    return [best[key] for key in order]


def would_block_findings(findings: List[Finding], blocked_rules) -> List[Finding]:
    """Shadow gate: findings that WOULD block if enforcement were on — block-eligible
    *and* whose rule the owner configured to block. Pure computation; it never blocks
    anything (honors the <1% FP / never-false-block promise — real blocking is Phase 9)."""
    blocked = set(blocked_rules or [])
    return [f for f in findings if f.block_eligible and f.rule_id in blocked]


def format_check_run_summary(
    findings: List[Finding],
    max_findings: int = 20,
    dashboard_url: Optional[str] = None,
) -> str:
    """Plain-English, truncation-safe Markdown summary of the findings.

    Shows the most-severe findings first, capped at ``max_findings``, with a
    "+N more" deep link so a huge PR never produces a wall of text.

    Args:
        findings: All findings for the PR.
        max_findings: How many to spell out before linking to the dashboard.
        dashboard_url: Optional deep link for the overflow ("see all").

    Returns:
        Markdown summary.
    """
    if not findings:
        return "✅ **All clear.** Every check passed — no problems found in this change."

    ordered = _sorted(findings)
    counts: dict[Confidence, int] = {}
    for f in ordered:
        counts[f.confidence] = counts.get(f.confidence, 0) + 1

    headline_bits = [
        f"{counts[c]} {_TIER_LABEL[c].lower()}"
        for c in (Confidence.CERTAIN, Confidence.HIGH, Confidence.MEDIUM)
        if counts.get(c)
    ]
    total = len(ordered)
    noun = "thing" if total == 1 else "things"
    lines = [
        f"🟠 **Found {total} {noun} to look at** ({', '.join(headline_bits)}).",
        "",
        "Nothing here blocks your merge — these are flagged for your attention.",
        "",
    ]

    for f in ordered[:max_findings]:
        lines.append(f"- **{_TIER_LABEL[f.confidence]}** · `{f.file_path}:{f.line_start}` — {f.message}")
        if f.fix_suggestion:
            lines.append(f"  - _Suggested fix:_ {f.fix_suggestion}")

    remaining = total - max_findings
    if remaining > 0:
        lines.append("")
        if dashboard_url:
            lines.append(f"…and **{remaining} more** — [view all in your dashboard]({dashboard_url}).")
        else:
            lines.append(f"…and **{remaining} more**.")

    return "\n".join(lines)


def build_annotations(findings: List[Finding]) -> List[dict]:
    """Build GitHub Check Run annotations (inline line markers), capped at 50.

    The most-severe findings win the limited slots. Each annotation anchors to
    the finding's added line(s) and carries a short title + the message.
    """
    annotations: List[dict] = []
    for f in _sorted(findings)[:MAX_ANNOTATIONS]:
        message = f.message
        if f.fix_suggestion:
            message = f"{f.message}\n\nSuggested fix: {f.fix_suggestion}"
        annotations.append(
            {
                "path": f.file_path,
                "start_line": f.line_start,
                "end_line": max(f.line_end, f.line_start),
                "annotation_level": _ANNOTATION_LEVEL.get(f.confidence, "warning"),
                "title": f"{f.rule_id}: {f.category}",
                "message": message,
            }
        )
    return annotations
