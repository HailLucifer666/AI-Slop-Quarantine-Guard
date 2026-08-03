"""Background worker (Phase 2).

Consumes the raw webhook deliveries enqueued by the webhook handler (Phase 1),
runs the GitHub auth chain, fetches the PR diff, and parses it into added lines.
Analyzers (Phase 3) and Check Run output (Phase 4) plug in at analyze_pr later.

Run with: python -m app.worker
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from app.analyzers.dependencies import check_dependencies
from app.analyzers.placeholders import check_placeholders
from app.analyzers.secrets import check_secrets
from app.analyzers.vulns import check_vulnerabilities
from app.analyzers.sast import check_sast
from app.analyzers.licenses import check_licenses
from app.analyzers.typosquat import check_typosquat
from app.analyzers.simplify import check_simplify
from app.cache import cached_existence, cached_license, cached_osv_batch
from app.analyzers.base import finalize
from app.checks import (
    apply_block_eligibility,
    build_annotations,
    build_review_comments,
    dedupe_findings,
    determine_conclusion,
    format_check_run_summary,
    would_block_findings,
)
from app.config import settings
from app.coverage import (
    CAPABILITIES,
    ERRORED,
    NOT_RUN_DISABLED,
    NOT_RUN_UNSUPPORTED,
    TIMED_OUT,
    RuleCoverage,
    plan_rule,
    summarize,
    take_census,
)
from app.diff import parse_diff
from app.github_auth import get_installation_token
from app.github_client import (
    MAX_REVIEW_COMMENTS,
    create_check_run,
    create_review,
    fetch_pr_diff,
    fetch_review_comment_bodies,
    update_check_run,
)
from app.grouping import group_findings
from app.ingest import IngestError, clone_repo, content_hash, head_sha, read_zip, walk_dir
from app.queue import (
    QUEUE_PAIRS,
    SCAN_QUEUE_KEY,
    WEBHOOK_QUEUE_KEY,
    ack_job,
    recover_orphaned_jobs,
    reserve_job,
)
from app.scan import ANALYZER_BUDGET, run_scan
from app.store import (
    complete_scan,
    fail_scan,
    get_settings,
    mark_running,
    reconcile_stale_scans,
    record_event,
    record_ingest_provenance,
    touch_scan_heartbeat,
    touch_worker_heartbeat,
    update_progress,
)

logger = logging.getLogger("worker")

# PR actions worth analyzing (ignore label/assignee/etc. churn).
RELEVANT_ACTIONS = {"opened", "synchronize", "reopened"}

# How often a running scan renews its liveness lease. Well under
# store.STALE_LEASE_SECONDS so a healthy scan is never reconciled away.
HEARTBEAT_INTERVAL_S = 20
# How often the idle worker proves it is alive at all, for /api/health.
WORKER_HEARTBEAT_INTERVAL_S = 10


async def analyze_pr(repo: str, pr_number: int, head_sha: str, installation_id: int) -> dict:
    """Turn a PR reference into a parsed diff in memory (Phase 2 endpoint).

    Phase 3 will run analyzers over the parsed lines; Phase 4 will write a Check Run.

    Any failure past this point is caught below: the Check Run is resolved to a
    visible terminal state (never left stuck "in_progress" forever — that would
    make a required check permanently unmergeable) and the failure is recorded to
    the audit trail before re-raising, mirroring how a whole-repo scan's failure
    is never silently dropped (store.fail_scan).
    """
    token = await get_installation_token(installation_id)

    # Open the Check Run immediately so the gate shows as "running" on the PR
    # while analyzers work. None => the API rejected it; we skip the update.
    check_run_id = await create_check_run(repo, head_sha, token)

    try:
        return await _run_pr_analysis(repo, pr_number, head_sha, token, check_run_id)
    except Exception as exc:
        await record_event("pr_analysis.failed", {
            "repo": repo, "pr_number": pr_number, "head_sha": head_sha,
            "check_run_id": check_run_id, "error": str(exc)[:500],
        })
        if check_run_id is not None:
            try:
                await update_check_run(
                    repo, check_run_id, "action_required",
                    "⚠️ The quality gate hit an internal error and could not finish "
                    "analyzing this PR. This is not a finding about your code — "
                    "re-run the check or contact the repo owner if it persists.",
                    token,
                )
            except Exception:
                logger.exception(
                    "failed to resolve stuck check run %s for %s#%s after an error",
                    check_run_id, repo, pr_number,
                )
        raise


async def _run_pr_analysis(
    repo: str, pr_number: int, head_sha: str, token: str, check_run_id: Optional[int]
) -> dict:
    """The actual analysis body of analyze_pr, split out so its caller can wrap
    it in one try/except covering every failure mode (see analyze_pr)."""
    diff_text = await fetch_pr_diff(repo, pr_number, token)
    if diff_text is None:
        logger.warning("no diff available for %s#%s", repo, pr_number)
        if check_run_id is not None:
            await update_check_run(
                repo, check_run_id, "success",
                "✅ Nothing to analyze in this change.", token,
            )
        return {"repo": repo, "pr_number": pr_number, "files": {}, "added_lines": 0}

    added = parse_diff(diff_text)
    files: dict[str, int] = {}
    for file_path, _line, _content in added:
        files[file_path] = files.get(file_path, 0) + 1

    # check_exists injected so SQG001 uses the Redis-cached registry lookup.
    repo_context = {"repo": repo, "head_sha": head_sha, "token": token, "check_exists": cached_existence}
    disabled = settings.disabled_analyzer_ids
    # (rule id, thunk) — the kill-switch drops any disabled analyzer.
    runners = [
        ("SQG001", lambda: check_dependencies(diff_text, repo_context)),
        ("SQG003", lambda: check_placeholders(diff_text, repo_context)),
        ("SQG002", lambda: check_secrets(diff_text, repo_context)),
        ("SQG004", lambda: check_vulnerabilities(diff_text, repo_context, query_batch=cached_osv_batch)),
        ("SQG006", lambda: check_sast(diff_text, repo_context)),
        ("SQG005", lambda: check_licenses(diff_text, repo_context, fetch_license=cached_license)),
        ("SQG007", lambda: check_typosquat(diff_text, repo_context)),
        ("SQG009", lambda: check_simplify(diff_text, repo_context)),
    ]
    # Coverage over the files this PR touched, so the check run can say which rules
    # actually inspected the change instead of implying all of them did.
    census = take_census({path: "" for path in files})

    findings = []
    coverages: list[RuleCoverage] = []
    for rule_id, run in runners:
        if rule_id in disabled:
            coverages.append(RuleCoverage(
                rule_id, CAPABILITIES[rule_id].title if rule_id in CAPABILITIES else rule_id,
                NOT_RUN_DISABLED, detail="switched off by DISABLED_ANALYZERS",
            ))
            continue

        coverage = plan_rule(rule_id, census)
        if not coverage.covered and coverage.status == NOT_RUN_UNSUPPORTED:
            coverages.append(coverage)
            continue

        try:
            produced = await asyncio.wait_for(run(), timeout=ANALYZER_BUDGET)
            findings += produced
        except asyncio.TimeoutError:
            # One slow analyzer must never hang the PR check — but the check run must
            # report the gap rather than presenting it as a pass.
            coverage.status = TIMED_OUT
            coverage.detail = f"exceeded its {ANALYZER_BUDGET:.0f}s budget and was stopped"
            logger.warning("analyzer %s exceeded %ss budget — skipped for %s#%s",
                           rule_id, ANALYZER_BUDGET, repo, pr_number)
        except Exception as exc:  # noqa: BLE001 — one broken rule must not void the check
            coverage.status = ERRORED
            coverage.detail = f"failed with an internal error: {exc}"[:300]
            logger.exception("analyzer %s failed for %s#%s", rule_id, repo, pr_number)
        coverages.append(coverage)

    # Canonicalize block-eligibility + collapse duplicate (file,line,rule) findings.
    findings = dedupe_findings(apply_block_eligibility(finalize(findings)))

    # Per-rule counts from the FINAL list, so the table can't disagree with the
    # annotations shown on the PR.
    final_by_rule: dict[str, int] = {}
    for f in findings:
        final_by_rule[f.rule_id] = final_by_rule.get(f.rule_id, 0) + 1
    for c in coverages:
        c.findings = final_by_rule.get(c.rule_id, 0)
    coverage_summary = summarize(coverages)

    logger.info(
        "analyzed %s#%s sha=%s files=%d added_lines=%d findings=%d",
        repo, pr_number, head_sha[:7], len(files), len(added), len(findings),
    )
    for file_path, count in files.items():
        logger.info("  %s: +%d", file_path, count)
    for f in findings:
        logger.info("  [%s/%s] %s:%d %s", f.rule_id, f.confidence.value, f.file_path, f.line_start, f.message)

    conclusion = determine_conclusion(findings)

    # Shadow gate (Phase 9 precursor): record what real blocking WOULD do, but never
    # actually block — the gate stays label-only until the <1% FP bar is met.
    settings_row = await get_settings()
    would = would_block_findings(findings, settings_row.get("blocked_rules", []))
    if would:
        logger.info(
            "SHADOW would-block %s#%s: %d finding(s) rules=%s — NOT blocked (label-only)",
            repo, pr_number, len(would), sorted({f.rule_id for f in would}),
        )

    groups = group_findings(findings)

    if check_run_id is not None:
        summary = format_check_run_summary(
            findings,
            dashboard_url=settings.dashboard_url or None,
            coverage=coverage_summary,
            groups=groups,
        )
        ok = await update_check_run(
            repo, check_run_id, conclusion, summary, token,
            annotations=build_annotations(findings),
        )
        if not ok:
            logger.error("failed to complete check run %s for %s#%s", check_run_id, repo, pr_number)

    # Inline review comments, with a one-click suggestion wherever a patch is
    # machine-derived. Anchored only to lines that exist in this diff: GitHub rejects an
    # entire review if one comment lands outside it.
    if findings:
        diff_lines = {(path, line) for path, line, _content in added}
        existing = await fetch_review_comment_bodies(repo, pr_number, token)
        comments = build_review_comments(
            findings, diff_lines=diff_lines, already_posted=existing,
            max_comments=MAX_REVIEW_COMMENTS,
        )
        if comments:
            posted = await create_review(repo, pr_number, head_sha, comments, token)
            if not posted:
                # The Check Run above already carries every finding, so a failed review
                # loses convenience, not information.
                logger.warning(
                    "review comments could not be posted for %s#%s (%d comment(s))",
                    repo, pr_number, len(comments),
                )

    return {
        "repo": repo,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "files": files,
        "added_lines": len(added),
        "findings": findings,
        "coverage": coverage_summary,
        "conclusion": conclusion,
        "check_run_id": check_run_id,
    }


def _extract_pr(payload: dict) -> tuple[str, int, str, int]:
    """Pull (repo, pr_number, head_sha, installation_id) from a pull_request payload."""
    return (
        payload["repository"]["full_name"],
        payload["pull_request"]["number"],
        payload["pull_request"]["head"]["sha"],
        payload["installation"]["id"],
    )


def ingest_codebase(source: str, ref: str) -> tuple[dict[str, str], list[str], Optional[str]]:
    """Turn a scan job's (source, ref) into a {path: content} map, skipped list, and SHA.

    Read-only by construction: clone is shallow and we only parse text — scanned
    code is never executed. The temp zip is deleted after reading.

    The third element is the resolved commit, or None where there genuinely isn't one
    (a zip upload, a folder that isn't a git repo). None means "not applicable", and is
    reported as such rather than filled in with a guess.
    """
    if source == "url":
        return clone_repo(ref)
    if source == "zip":
        try:
            with open(ref, "rb") as fh:
                data = fh.read()
            files, skipped = read_zip(data)
            return files, skipped, None  # an archive has no commit
        finally:
            try:
                os.remove(ref)
            except OSError:
                pass
    if source == "local":
        if settings.environment != "development":
            raise IngestError("local-folder scans are only allowed in development")
        files, skipped = walk_dir(ref)
        return files, skipped, head_sha(ref)  # None when the folder isn't a git repo
    raise IngestError(f"unknown scan source: {source}")


async def _heartbeat_loop(scan_id: int) -> None:
    """Renew a running scan's lease until cancelled.

    Progress advances only between analyzers, so one analyzer sitting near its 90s
    budget would otherwise let the lease lapse and get a perfectly healthy scan
    reconciled to failed. Errors are swallowed: a heartbeat is a liveness signal, and
    losing one must never be what kills a scan that is still working.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_S)
        try:
            await touch_scan_heartbeat(scan_id)
        except Exception:  # noqa: BLE001
            logger.debug("heartbeat dropped for scan %s", scan_id)


async def handle_scan_job(job: dict) -> None:
    """Run a whole-repo scan end-to-end: ingest → 6 analyzers → persist analytics.

    Any failure is recorded on the row with a reason — a scan never silently dies
    (the product's "never lie / fail-safe" promise applies to our own pipeline too).
    """
    scan_id = job.get("scan_id")
    source = job.get("source", "")
    ref = job.get("ref", "")
    if scan_id is None:
        logger.error("scan job missing scan_id: %r", job)
        return

    heartbeat = asyncio.create_task(_heartbeat_loop(scan_id))
    try:
        await mark_running(scan_id)
        files, skipped, resolved_sha = ingest_codebase(source, ref)

        # Record the snapshot before analyzing it, so even a scan that dies mid-analysis
        # still proves which commit and which file set it was looking at.
        await record_ingest_provenance(
            scan_id,
            resolved_sha=resolved_sha,
            content_hash=content_hash(files),
            file_count=len(files),
        )

        async def _progress(payload: dict) -> None:
            # Best-effort: a progress-update failure must never fail the scan.
            try:
                await update_progress(scan_id, payload)
            except Exception:  # noqa: BLE001
                logger.debug("progress update dropped for scan %s", scan_id)

        result = await run_scan(files, skipped, on_progress=_progress)

        # Shadow gate: count findings that WOULD block under the configured rules,
        # so the dashboard + audit show enforcement impact without ever blocking.
        settings_row = await get_settings()
        blocked = set(settings_row.get("blocked_rules", []))
        would = [
            f for f in result["findings"]
            if f.get("block_eligible") and f.get("rule_id") in blocked
        ]
        result["analytics"]["would_block"] = len(would)

        await complete_scan(scan_id, result)
        a = result["analytics"]
        logger.info(
            "scan %s done: %d findings over %d files (%d skipped) in %dms",
            scan_id, a["total_findings"], a["files_scanned"], a["files_skipped"],
            result["duration_ms"],
        )
    except IngestError as exc:
        await fail_scan(scan_id, str(exc))
        logger.warning("scan %s failed to ingest: %s", scan_id, exc)
    except Exception as exc:  # noqa: BLE001 — record, never crash the worker loop
        await fail_scan(scan_id, f"internal error: {exc}")
        logger.exception("scan %s failed", scan_id)
    finally:
        heartbeat.cancel()


async def run_worker() -> None:
    """Consume both queues forever: PR webhooks → analyze_pr, scan jobs → handle_scan_job.

    Reliable-queue pattern (see app.queue): each job is reserved into a processing
    list before it's handled and only acknowledged — removed from Redis — once
    handling finishes, successfully or not. A worker crash mid-job leaves it
    sitting in the processing list, recovered on the next startup, instead of the
    old plain BRPOP which discarded the job from Redis the instant it was popped.
    """
    recovered = await recover_orphaned_jobs()
    if recovered:
        logger.warning("recovered %d orphaned job(s) from a previous crash", recovered)

    # Jobs whose worker died mid-scan are not in the processing list any more, so
    # recover_orphaned_jobs can't see them — their scan rows are simply stuck at
    # "running". Fail them honestly before consuming anything new.
    await reconcile_stale_scans()

    logger.info("worker started, consuming %s + %s", WEBHOOK_QUEUE_KEY, SCAN_QUEUE_KEY)
    last_liveness = 0.0
    while True:
        # Prove the worker is alive even while idle, so /api/health can tell "nothing
        # to do" apart from "process is gone".
        now = time.monotonic()
        if now - last_liveness >= WORKER_HEARTBEAT_INTERVAL_S:
            last_liveness = now
            try:
                await touch_worker_heartbeat()
            except Exception:  # noqa: BLE001 — liveness reporting must not stop work
                logger.debug("worker liveness stamp dropped")

        # Redis has no multi-key BRPOPLPUSH, so poll each source in turn (unlike
        # the old single BRPOP([key1, key2]) call). A brief sleep when both are
        # empty avoids a hot loop; work is still picked up promptly when present.
        raw = None
        key = processing_key = None
        for source_key, proc_key in QUEUE_PAIRS:
            raw = await reserve_job(source_key, proc_key)
            if raw is not None:
                key, processing_key = source_key, proc_key
                break
        if raw is None:
            await asyncio.sleep(1)
            continue

        try:
            try:
                job = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.error("dropping malformed job: %r", raw)
                continue

            if key == SCAN_QUEUE_KEY or job.get("kind") == "scan":
                # Guard the loop: handle_scan_job records its own failures, but a DB error
                # inside fail_scan must not kill the consumer.
                try:
                    await handle_scan_job(job)
                except Exception:
                    logger.exception("handle_scan_job crashed for %r", job.get("scan_id"))
                continue

            if job.get("event") != "pull_request":
                logger.info("skip event=%s delivery=%s", job.get("event"), job.get("delivery_guid"))
                continue

            payload = job.get("payload", {})
            action = payload.get("action")
            if action not in RELEVANT_ACTIONS:
                logger.info("skip pull_request action=%s", action)
                continue

            try:
                repo, pr_number, head_sha, installation_id = _extract_pr(payload)
            except KeyError as exc:
                logger.error("pull_request payload missing field %s", exc)
                continue

            try:
                await analyze_pr(repo, pr_number, head_sha, installation_id)
            except Exception:
                logger.exception("analyze_pr failed for %s#%s", repo, pr_number)
        finally:
            # Ack unconditionally: whatever branch handled (or dropped) the job
            # above, it's fully done now — never left in the processing list.
            await ack_job(processing_key, raw)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
