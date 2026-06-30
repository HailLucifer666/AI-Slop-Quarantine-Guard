"""Whole-repo scan orchestrator.

Runs the same 6 analyzers the PR gate uses, but over an entire codebase instead of a PR
diff. The trick: a synthetic all-added diff (every line counts as added) plus locally-injected
file readers, so the analyzers run unchanged. Returns findings + aggregated analytics for the
dashboard.
"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, Dict, List, Optional

from app.analyzers.base import Confidence, Finding
from app.analyzers.dependencies import check_dependencies
from app.analyzers.licenses import check_licenses
from app.analyzers.placeholders import check_placeholders
from app.analyzers.sast import check_sast
from app.analyzers.secrets import check_secrets
from app.analyzers.typosquat import check_typosquat
from app.analyzers.vulns import check_vulnerabilities
from app.cache import cached_existence, cached_license, cached_osv_batch
from app.checks import apply_block_eligibility, dedupe_findings
from app.config import settings
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
    """Serialize a Finding for JSON (API + persistence)."""
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
        "evidence": {
            "snippet": f.evidence.snippet,
            "context_before": f.evidence.context_before,
            "context_after": f.evidence.context_after,
        },
    }


def aggregate(findings: List[Finding], files_scanned: int, skipped: List[str]) -> dict:
    """Roll findings up into the analytics the dashboard renders."""
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
    return {
        "total_findings": len(findings),
        "by_confidence": by_confidence,
        "by_rule": by_rule,
        "block_eligible": block_eligible,
        "top_files": [{"file_path": p, "count": n} for p, n in top_files],
        "files_scanned": files_scanned,
        "files_skipped": len(skipped),
        "clean": len(findings) == 0,
    }


ProgressCb = Callable[[dict], Awaitable[None]]


async def run_scan(
    files: Dict[str, str],
    skipped: Optional[List[str]] = None,
    on_progress: Optional[ProgressCb] = None,
) -> dict:
    """Run all 6 analyzers over a whole codebase and aggregate the results.

    Args:
        files: {repo-relative path: full content} map (from app.ingest).
        skipped: paths skipped during ingest (size/count caps), surfaced to the user.
        on_progress: optional async callback invoked before each analyzer and once
            before reporting, with a real {phase, index, total, findings_so_far,
            files_total} payload — honest phase progress, no invented %/ETA.

    Returns:
        {findings: [...], analytics: {...}, skipped: [...], duration_ms: int}
    """
    skipped = skipped or []
    started = time.monotonic()

    diff = build_synthetic_diff(files)
    # Cached registry/OSV/license lookups so a big repo doesn't re-hit the network
    # for the same package (fail-open — see app.cache).
    repo_context = {
        "repo": "", "head_sha": "", "token": "",
        "fetch_file": _local_fetch_one(files), "check_exists": cached_existence,
    }
    fetch4 = _local_fetch_four(files)

    # (phase label, rule id, thunk) — keep the analyzer order stable; the index is
    # the progress. ``rule_id`` lets the kill-switch drop a disabled analyzer.
    analyzers: List[tuple] = [
        ("dependencies", "SQG001", lambda: check_dependencies(diff, repo_context)),
        ("placeholders", "SQG003", lambda: check_placeholders(diff, repo_context)),
        ("secrets", "SQG002", lambda: check_secrets(diff, repo_context)),
        ("vulnerabilities", "SQG004", lambda: check_vulnerabilities(diff, repo_context, fetch_file=fetch4, query_batch=cached_osv_batch)),
        ("sast", "SQG006", lambda: check_sast(diff, repo_context)),
        ("licenses", "SQG005", lambda: check_licenses(diff, repo_context, fetch_file=fetch4, fetch_license=cached_license)),
        ("typosquat", "SQG007", lambda: check_typosquat(diff, repo_context)),
    ]
    disabled = settings.disabled_analyzer_ids
    analyzers = [a for a in analyzers if a[1] not in disabled]
    total = len(analyzers)
    files_total = len(files)

    findings: List[Finding] = []
    for idx, (phase, _rule_id, run) in enumerate(analyzers):
        if on_progress:
            await on_progress({
                "phase": phase, "index": idx, "total": total,
                "findings_so_far": len(findings), "files_total": files_total,
            })
        try:
            findings += await asyncio.wait_for(run(), timeout=ANALYZER_BUDGET)
        except asyncio.TimeoutError:
            # Never let one slow analyzer hang the scan — skip it, keep going.
            logger.warning("analyzer %s (%s) exceeded %ss budget — skipped", phase, _rule_id, ANALYZER_BUDGET)
    if on_progress:
        await on_progress({
            "phase": "reporting", "index": total, "total": total,
            "findings_so_far": len(findings), "files_total": files_total,
        })

    # Canonicalize the block-eligibility invariant, then collapse duplicates a
    # cross-analyzer overlap could produce — before aggregating the analytics.
    findings = dedupe_findings(apply_block_eligibility(findings))

    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "findings": [finding_to_dict(f) for f in findings],
        "analytics": aggregate(findings, len(files), skipped),
        "skipped": skipped,
        "duration_ms": duration_ms,
    }
