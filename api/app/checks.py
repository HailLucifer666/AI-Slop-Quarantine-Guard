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


_STATUS_LABEL = {
    "ran": "ran",
    "partial": "partial",
    "not_run_unsupported": "not run — unsupported",
    "not_run_engine_missing": "not run — engine missing",
    "not_run_disabled": "not run — switched off",
    "errored": "error",
    "timed_out": "timed out",
}


def format_coverage_table(coverage: Optional[dict]) -> str:
    """Markdown table of what each check did, or "" when coverage is unavailable.

    This is the receipt behind the headline. Without it, "no problems found" is
    unfalsifiable — the reader cannot tell which checks actually looked.
    """
    if not coverage or not coverage.get("rules"):
        return ""

    lines = [
        "",
        "<details><summary>What was checked</summary>",
        "",
        "| Check | Status | Covered | Not covered | Findings |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rule in coverage["rules"]:
        status = _STATUS_LABEL.get(rule["status"], rule["status"])
        covered = ", ".join(rule["covered"]) or "—"
        not_covered = ", ".join(rule["not_covered"]) or "—"
        engine = rule.get("engine") or "builtin"
        if rule.get("engine_version"):
            engine = f"{engine} {rule['engine_version']}"
        lines.append(
            f"| `{rule['rule_id']}` {rule['title']} <br/><sub>{engine}</sub> "
            f"| {status} | {covered} | {not_covered} | {rule['findings']} |"
        )
    incomplete = coverage.get("rules_incomplete", 0)
    if incomplete:
        lines += [
            "",
            f"**{incomplete} of {coverage.get('rules_total', 0)} checks did not reach a "
            "conclusive result.** Anything they would have caught is unknown, not absent.",
        ]
    lines += ["", "</details>"]
    return "\n".join(lines)


def _no_findings_summary(coverage: Optional[dict]) -> str:
    """The zero-findings headline, which may only claim "all clear" when earned."""
    if not coverage or not coverage.get("rules"):
        # No coverage record — state what we know (no findings) without asserting
        # that every check ran, which we cannot support.
        return "**No problems found.** (Check coverage was not recorded for this run.)"

    total = coverage.get("rules_total", 0)
    ran = coverage.get("rules_ran", 0)
    if coverage.get("fully_covered"):
        return f"✅ **All {total} checks ran and found nothing.**"
    return (
        f"⚠️ **{ran} of {total} checks ran. No problems found in what was scanned** — "
        f"{total - ran} could not run, so this is not a clean bill of health. See the "
        "table below for what was skipped and why."
    )


def format_check_run_summary(
    findings: List[Finding],
    max_findings: int = 20,
    dashboard_url: Optional[str] = None,
    coverage: Optional[dict] = None,
    groups: Optional[List] = None,
) -> str:
    """Plain-English, truncation-safe Markdown summary of the findings.

    Shows the most-severe findings first, capped at ``max_findings``, with a
    "+N more" deep link so a huge PR never produces a wall of text.

    Args:
        findings: All findings for the PR.
        max_findings: How many to spell out before linking to the dashboard.
        dashboard_url: Optional deep link for the overflow ("see all").
        coverage: Per-rule coverage rollup from ``app.coverage.summarize``. Without it
            the summary cannot claim full coverage, and says so rather than guessing.

    Returns:
        Markdown summary.
    """
    if not findings:
        return _no_findings_summary(coverage) + format_coverage_table(coverage)

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

    # With groups, lead with the clustered view: a flat list of 367 findings buries the
    # three that matter. Without them, fall back to the per-finding list.
    if groups:
        lines.append(format_grouped_summary(groups))

    for f in ordered[:max_findings]:
        detail = f"- **{_TIER_LABEL[f.confidence]}** · `{f.file_path}:{f.line_start}` — {f.message}"
        refs = [f"[{a.id}]({a.url})" for a in f.advisories[:2]] + list(f.cwe[:2])
        if refs:
            detail += f" ({', '.join(refs)})"
        lines.append(detail)
        if f.remediation and f.remediation.is_applicable:
            lines.append(f"  - _Fix available:_ {f.remediation.text}")
        elif f.fix_suggestion:
            lines.append(f"  - _Suggested fix:_ {f.fix_suggestion}")

    remaining = total - max_findings
    if remaining > 0:
        lines.append("")
        if dashboard_url:
            lines.append(f"…and **{remaining} more** — [view all in your dashboard]({dashboard_url}).")
        else:
            lines.append(f"…and **{remaining} more**.")

    return "\n".join(lines) + format_coverage_table(coverage)


# Marker embedded in every review comment so a re-run can recognize its own past
# comments and not repeat them. Kept in an HTML comment: invisible on GitHub, but
# reliably greppable in the raw body.
_FINGERPRINT_MARKER = "<!-- sqg:{fingerprint} -->"


def _fingerprint_marker(finding: Finding) -> str:
    return _FINGERPRINT_MARKER.format(fingerprint=finding.fingerprint or "unknown")


def format_review_comment(finding: Finding) -> str:
    """The body of one inline PR comment.

    A ```suggestion block is emitted ONLY when the finding carries a machine-derived
    replacement (``Remediation.is_applicable``) — GitHub renders those as a one-click
    "Commit suggestion", so an invented patch would be committed to a user's branch on
    our word. Everything else gets prose, and says what it is based on.
    """
    tier = _TIER_LABEL.get(finding.confidence, "Worth a look")
    lines = [f"**{tier} · `{finding.rule_id}`** — {finding.message}"]

    references: List[str] = []
    if finding.cwe:
        references += [f"[{c}](https://cwe.mitre.org/data/definitions/{c.split('-')[-1]}.html)"
                       for c in finding.cwe]
    references += [f"[{a.id}]({a.url})" for a in finding.advisories[:5]]
    if references:
        lines += ["", "References: " + " · ".join(references)]

    remediation = finding.remediation
    if remediation and remediation.is_applicable:
        lines += [
            "",
            remediation.text,
            "",
            "```suggestion",
            (remediation.suggested_replacement or "").rstrip("\n"),
            "```",
        ]
        if remediation.basis:
            lines += ["", f"<sub>Basis: {remediation.basis}.</sub>"]
    elif remediation:
        lines += ["", remediation.text]
        if remediation.basis:
            lines += ["", f"<sub>No automatic fix offered: {remediation.basis}.</sub>"]
    elif finding.fix_suggestion:
        lines += ["", finding.fix_suggestion]

    provenance = finding.tool or "builtin"
    if finding.tool_version:
        provenance = f"{provenance} {finding.tool_version}"
    lines += ["", f"<sub>Detected by {provenance} · rules v{finding.rule_version}</sub>",
              _fingerprint_marker(finding)]
    return "\n".join(lines)


def build_review_comments(
    findings: List[Finding],
    diff_lines: Optional[set] = None,
    already_posted: Optional[List[str]] = None,
    max_comments: int = 25,
) -> List[dict]:
    """Inline review comments for the most severe findings, most severe first.

    Args:
        findings: all findings for the PR.
        diff_lines: ``{(path, line)}`` pairs that exist in the diff. GitHub rejects the
            entire review if any comment anchors outside it, so an unanchorable finding
            is left to the summary instead of being mis-anchored to a nearby line.
        already_posted: bodies of existing review comments; anything whose fingerprint
            appears there is skipped so a re-run doesn't duplicate it.
        max_comments: cap on inline comments (the summary still covers everything).
    """
    seen_bodies = "\n".join(already_posted or [])
    comments: List[dict] = []
    for finding in _sorted(findings):
        if len(comments) >= max_comments:
            break
        if diff_lines is not None and (finding.file_path, finding.line_start) not in diff_lines:
            continue
        if finding.fingerprint and _fingerprint_marker(finding) in seen_bodies:
            continue
        comments.append({
            "path": finding.file_path,
            "line": max(finding.line_end, finding.line_start),
            "side": "RIGHT",
            "body": format_review_comment(finding),
        })
    return comments


def format_grouped_summary(groups: List, max_groups: int = 15) -> str:
    """Markdown for the grouped view: one row per issue, with its true occurrence count.

    Answers the failure this exists for — a flat list of 367 findings where the 3 that
    matter are somewhere in the middle.
    """
    if not groups:
        return ""
    lines = ["", "**Issues found**", ""]
    for group in groups[:max_groups]:
        tier = _TIER_LABEL.get(group.confidence, "Worth a look")
        if group.is_group:
            where = f"{group.count} occurrences across {group.file_count} files"
        else:
            first = group.findings[0]
            where = f"`{first.file_path}:{first.line_start}`"
            if group.count > 1:
                where += f" and {group.count - 1} more"
        lines.append(f"- **{tier}** · `{group.rule_id}` — {group.title} ({where})")
    remaining = len(groups) - max_groups
    if remaining > 0:
        lines.append(f"- …and {remaining} more distinct issue(s).")
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
