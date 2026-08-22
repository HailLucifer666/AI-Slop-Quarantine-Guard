"""Whole-repo scan orchestrator.

Runs the same 7 analyzers the PR gate uses, but over an entire codebase instead of a PR
diff. The trick: a synthetic all-added diff (every line counts as added) plus locally-injected
file readers, so the analyzers run unchanged. Returns findings, per-rule coverage, and
aggregated analytics for the dashboard.

Coverage is not decoration. A check that was skipped, timed out, or cannot read this
repository's languages produces zero findings, which is indistinguishable from a clean
pass unless it is recorded separately — see app.coverage.
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, List, Optional

from app.analyzers.base import Confidence, Finding, finalize
from app.analyzers.dependencies import check_dependencies
from app.analyzers.licenses import check_licenses
from app.analyzers.placeholders import check_placeholders
from app.analyzers.sast import check_sast
from app.analyzers.secrets import check_secrets
from app.analyzers.simplify import check_simplify
from app.analyzers.typosquat import check_typosquat
from app.analyzers.vulns import check_vulnerabilities
from app.cache import cached_existence, cached_license, cached_osv_batch
from app.checks import apply_block_eligibility, dedupe_findings
from app.config import settings
from app.coverage import (
    CAPABILITIES,
    ERRORED,
    NOT_RUN_DISABLED,
    NOT_RUN_UNSUPPORTED,
    TIMED_OUT,
    RuleCoverage,
    note_missing_engines,
    plan_rule,
    summarize,
    take_census,
)
from app.engines import probe_all, rules_missing_an_engine
from app.grouping import group_findings, summarize_groups
from app.synthetic_diff import build_synthetic_diff

logger = logging.getLogger("scan")

TOP_FILES = 10
# A single analyzer may never hang a whole scan: cap each at this wall-clock budget.
# On timeout it contributes no findings and the scan continues (fail-safe).
ANALYZER_BUDGET = 90.0


def _local_fetch_one(files: Dict[str, str]):
    """fetch_file(path) -> content  — the contract dependencies.py expects via repo_context."""
    async def fetch(path: str) -> Optional[str]:
        return files.get(path)
    return fetch


def _local_fetch_four(files: Dict[str, str]):
    """fetch_file(repo, path, ref, token) -> content — the kwarg vulns/licenses expect."""
    async def fetch(_repo: str, path: str, _ref: str, _token: str) -> Optional[str]:
        return files.get(path)
    return fetch


def finding_to_dict(f: Finding) -> dict:
    """Serialize a Finding for JSON (API + persistence).

    Provenance (which analyzer version, which tool version, the evidence hash) is part
    of the payload: a finding a user cannot trace back to the thing that produced it is
    a claim, not a result. These fields exist on the dataclass and were previously
    dropped here, so they never reached the dashboard or the PR.
    """
    return {
        "rule_id": f.rule_id,
        "category": f.category,
        "confidence": f.confidence.value,
        "block_eligible": f.block_eligible,
        "file_path": f.file_path,
        "line_start": f.line_start,
        "line_end": f.line_end,
        "message": f.message,
        "tool": f.tool,
        "fix_suggestion": f.fix_suggestion,
        "analyzer_version": f.analyzer_version,
        "rule_version": f.rule_version,
        "tool_version": f.tool_version,
        "evidence_hash": f.evidence_hash,
        "fingerprint": f.fingerprint,
        # Review-grade detail. Empty/None means "no source stated this", which is why
        # these are never defaulted to a plausible-looking value.
        "cwe": list(f.cwe),
        "advisories": [{"id": a.id, "url": a.url} for a in f.advisories],
        "severity": f.severity,
        "cvss_score": f.cvss_score,
        "cvss_vector": f.cvss_vector,
        "fix_versions": list(f.fix_versions),
        "rule_url": f.rule_url,
        "remediation": (
            {
                "kind": f.remediation.kind,
                "text": f.remediation.text,
                "suggested_replacement": f.remediation.suggested_replacement,
                "basis": f.remediation.basis,
                "applicable": f.remediation.is_applicable,
            }
            if f.remediation else None
        ),
        "evidence": {
            "snippet": f.evidence.snippet,
            "context_before": f.evidence.context_before,
            "context_after": f.evidence.context_after,
        },
    }


def aggregate(
    findings: List[Finding],
    files_scanned: int,
    skipped: List[str],
    coverage: Optional[dict] = None,
) -> dict:
    """Roll findings up into the analytics the dashboard renders.

    ``clean`` comes from the coverage rollup, not from ``len(findings) == 0``: a scan
    where three of seven checks never ran has not established that anything is clean.
    """
    by_confidence = {c.value: 0 for c in Confidence}
    by_rule: Dict[str, int] = {}
    by_file: Dict[str, int] = {}
    block_eligible = 0
    for f in findings:
        by_confidence[f.confidence.value] = by_confidence.get(f.confidence.value, 0) + 1
        by_rule[f.rule_id] = by_rule.get(f.rule_id, 0) + 1
        by_file[f.file_path] = by_file.get(f.file_path, 0) + 1
        if f.block_eligible:
            block_eligible += 1
    top_files = sorted(by_file.items(), key=lambda kv: kv[1], reverse=True)[:TOP_FILES]
    coverage = coverage or {}
    return {
        "total_findings": len(findings),
        "by_confidence": by_confidence,
        "by_rule": by_rule,
        "block_eligible": block_eligible,
        "top_files": [{"file_path": p, "count": n} for p, n in top_files],
        "files_scanned": files_scanned,
        "files_skipped": len(skipped),
        # True only when every check reached a conclusive result and found nothing.
        # Absent coverage means we cannot claim cleanliness, so we don't.
        "clean": bool(coverage.get("clean", False)),
        "fully_covered": bool(coverage.get("fully_covered", False)),
        "rules_ran": coverage.get("rules_ran", 0),
        "rules_total": coverage.get("rules_total", 0),
        "rules_incomplete": coverage.get("rules_incomplete", 0),
    }


ProgressCb = Callable[[dict], Awaitable[None]]


async def run_scan(
    files: Dict[str, str],
    skipped: Optional[List[str]] = None,
    on_progress: Optional[ProgressCb] = None,
    overrides: Optional[Dict[str, Callable]] = None,
    suppressed: Optional[List[str]] = None,
) -> dict:
    """Run all 7 analyzers over a whole codebase and aggregate the results.

    Args:
        files: {repo-relative path: full content} map (from app.ingest).
        skipped: paths skipped during ingest (size/count caps), surfaced to the user.
        suppressed: paths excluded by the scanned repository's OWN ignore rules. Kept
            separate from ``skipped`` because the cause — and therefore the wording the
            user needs — is different. Both count as unexamined.
        on_progress: optional async callback invoked before each analyzer and once
            before reporting, with a real {phase, index, total, findings_so_far,
            files_total} payload — honest phase progress, no invented %/ETA.
        overrides: replacements for the three network boundaries — ``check_exists``,
            ``query_batch``, ``fetch_license``. Same injection the analyzers already
            accept individually, hoisted here so an offline accuracy test can exercise
            the real detection logic against known answers instead of mocking it away.

    Returns:
        {findings: [...], analytics: {...}, coverage: {...}, skipped: [...],
         duration_ms: int}
    """
    skipped = skipped or []
    suppressed = suppressed or []
    overrides = overrides or {}
    started = time.monotonic()

    diff = build_synthetic_diff(files)
    # Cached registry/OSV/license lookups so a big repo doesn't re-hit the network
    # for the same package (fail-open — see app.cache).
    check_exists = overrides.get("check_exists", cached_existence)
    query_batch = overrides.get("query_batch", cached_osv_batch)
    fetch_license = overrides.get("fetch_license", cached_license)
    repo_context = {
        "repo": "", "head_sha": "", "token": "",
        "fetch_file": _local_fetch_one(files), "check_exists": check_exists,
    }
    fetch4 = _local_fetch_four(files)

    # (phase label, rule id, thunk) — keep the analyzer order stable; the index is
    # the progress. ``rule_id`` lets the kill-switch drop a disabled analyzer.
    analyzers: List[tuple] = [
        ("dependencies", "SQG001", lambda: check_dependencies(diff, repo_context)),
        ("placeholders", "SQG003", lambda: check_placeholders(diff, repo_context)),
        ("secrets", "SQG002", lambda: check_secrets(diff, repo_context)),
        ("vulnerabilities", "SQG004", lambda: check_vulnerabilities(diff, repo_context, fetch_file=fetch4, query_batch=query_batch)),
        ("sast", "SQG006", lambda: check_sast(diff, repo_context)),
        ("licenses", "SQG005", lambda: check_licenses(diff, repo_context, fetch_file=fetch4, fetch_license=fetch_license)),
        ("typosquat", "SQG007", lambda: check_typosquat(diff, repo_context)),
        ("simplify", "SQG009", lambda: check_simplify(diff, repo_context)),
    ]
    disabled = settings.disabled_analyzer_ids
    total = len(analyzers)
    files_total = len(files)

    # What the repository actually contains, so each rule can be judged against what
    # it was able to read rather than against silence.
    census = take_census(files)

    findings: List[Finding] = []
    coverages: List[RuleCoverage] = []
    for idx, (phase, rule_id, run) in enumerate(analyzers):
        if on_progress:
            await on_progress({
                "phase": phase, "index": idx, "total": total,
                "findings_so_far": len(findings), "files_total": files_total,
            })

        # An operator-disabled rule is reported as disabled, never as a pass.
        if rule_id in disabled:
            coverages.append(RuleCoverage(
                rule_id, CAPABILITIES[rule_id].title if rule_id in CAPABILITIES else rule_id,
                NOT_RUN_DISABLED, detail="switched off by DISABLED_ANALYZERS",
            ))
            continue

        coverage = plan_rule(rule_id, census)
        if not coverage.covered and coverage.status == NOT_RUN_UNSUPPORTED:
            # Nothing this rule can read — don't spend the budget, and say why.
            coverages.append(coverage)
            continue

        rule_started = time.monotonic()
        try:
            produced = await asyncio.wait_for(run(), timeout=ANALYZER_BUDGET)
            findings += produced
            coverage.findings = len(produced)
        except asyncio.TimeoutError:
            # Never let one slow analyzer hang the scan — but a skipped analyzer is a
            # gap in the result, not a clean pass, so it is recorded as such.
            coverage.status = TIMED_OUT
            coverage.detail = f"exceeded its {ANALYZER_BUDGET:.0f}s budget and was stopped"
            logger.warning("analyzer %s (%s) exceeded %ss budget — skipped", phase, rule_id, ANALYZER_BUDGET)
        except Exception as exc:  # noqa: BLE001 — one broken rule must not void the scan
            coverage.status = ERRORED
            coverage.detail = f"failed with an internal error: {exc}"[:300]
            logger.exception("analyzer %s (%s) failed", phase, rule_id)
        coverage.duration_ms = int((time.monotonic() - rule_started) * 1000)
        coverages.append(coverage)

    if on_progress:
        await on_progress({
            "phase": "reporting", "index": total, "total": total,
            "findings_so_far": len(findings), "files_total": files_total,
        })

    # Canonicalize the block-eligibility invariant, then collapse duplicates a
    # cross-analyzer overlap could produce — before aggregating the analytics.
    findings = dedupe_findings(apply_block_eligibility(finalize(findings)))

    # Re-derive per-rule counts from the FINAL list. Counting what each analyzer
    # returned would overstate any rule whose findings were deduped away, and the
    # coverage table must never disagree with the findings the user is shown.
    final_by_rule: Dict[str, int] = {}
    for f in findings:
        final_by_rule[f.rule_id] = final_by_rule.get(f.rule_id, 0) + 1
    for c in coverages:
        c.findings = final_by_rule.get(c.rule_id, 0)

    # Say which advertised engine was absent, so no rule's result is attributed to a
    # scanner that never ran here.
    engine_status = probe_all()
    note_missing_engines(coverages, rules_missing_an_engine())

    coverage_summary = summarize(coverages)
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "findings": [finding_to_dict(f) for f in findings],
        "analytics": aggregate(findings, len(files), skipped, coverage_summary),
        "coverage": coverage_summary,
        # Clustered view, so 318 real TODOs cannot bury 3 real secrets. Every finding
        # still appears above; this is structure, not filtering.
        "groups": summarize_groups(group_findings(findings)),
        "engine_versions": {
            name: status.version for name, status in engine_status.items() if status.available
        },
        "skipped": skipped,
        "suppressed": suppressed,
        "duration_ms": duration_ms,
    }
