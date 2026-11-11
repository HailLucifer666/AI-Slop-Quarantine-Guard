"""Scan a folder from the command line and print what was actually checked.

    python -m app.cli_scan <path> [--json] [--fail-on-certain] [--offline]

Bypasses Redis, the worker and the database entirely: ingest → analyzers → report, in
one process. That makes it the fastest honest answer to "is this accurate?", because
the coverage table shows which checks ran, which could not, and why — the thing a bare
finding count cannot tell you.

Exit codes: 0 nothing conclusive to report · 1 findings present · 2 bad usage ·
3 CERTAIN findings present (with --fail-on-certain).
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Callable, Dict, Optional

from app.coverage import take_census
from app.ingest import IngestError, content_hash, head_sha, walk_dir
from app.scan import run_scan

_STATUS_MARK = {
    "ran": "ok",
    "partial": "PARTIAL",
    "not_run_unsupported": "NOT RUN",
    "not_run_engine_missing": "NOT RUN",
    "not_run_disabled": "OFF",
    "errored": "ERROR",
    "timed_out": "TIMEOUT",
}


async def _offline_overrides() -> Dict[str, Callable[..., Any]]:
    """Boundaries stubbed so a run works with no network.

    Returns UNKNOWN/empty rather than "fine": an offline run must not be able to
    manufacture a clean answer for checks that genuinely need a registry.
    """
    from app.registries import Existence

    async def unknown_existence(_ecosystem, _name, _client=None):
        return Existence.UNKNOWN

    async def no_vuln_data(pins, _client=None):
        return {p: None for p in pins}

    async def no_license_data(_ecosystem, _name, _client=None):
        return None

    return {
        "check_exists": unknown_existence,
        "query_batch": no_vuln_data,
        "fetch_license": no_license_data,
    }


def _print_report(path: str, result: dict, sha: Optional[str], digest: str) -> None:
    analytics = result["analytics"]
    coverage = result["coverage"]

    print()
    print("=" * 78)
    print(f"SCANNED  {path}")
    print(f"commit   {sha or '(not a git repository)'}")
    print(f"content  sha256:{digest[:16]}…   files={analytics['files_scanned']} "
          f"skipped={analytics['files_skipped']}   {result['duration_ms']}ms")
    print("=" * 78)

    print()
    print(f"{'CHECK':<10} {'STATUS':<8} {'FOUND':>5}  COVERED / NOT COVERED")
    print("-" * 78)
    for rule in coverage["rules"]:
        mark = _STATUS_MARK.get(rule["status"], rule["status"])
        covered = ", ".join(rule["covered"]) or "—"
        print(f"{rule['rule_id']:<10} {mark:<8} {rule['findings']:>5}  {covered}")
        if rule["not_covered"]:
            print(f"{'':<25}  not covered: {', '.join(rule['not_covered'])}")
        if rule["detail"]:
            print(f"{'':<25}  {rule['detail']}")

    print()
    if coverage["fully_covered"]:
        print(f"All {coverage['rules_total']} checks ran.")
    else:
        print(
            f"{coverage['rules_ran']} of {coverage['rules_total']} checks ran. "
            f"{coverage['rules_incomplete']} did not — whatever those would catch is "
            "UNKNOWN here, not absent."
        )

    findings = result["findings"]
    if not findings:
        print("No findings in what was scanned.")
        return

    print()
    print(f"FINDINGS ({len(findings)})")
    print("-" * 78)
    order = {"CERTAIN": 0, "HIGH": 1, "MEDIUM": 2}
    for f in sorted(findings, key=lambda x: (order.get(x["confidence"], 9), x["file_path"])):
        print(f"[{f['confidence']:<7}] {f['rule_id']}  {f['file_path']}:{f['line_start']}")
        print(f"           {f['message']}")
        if f.get("fix_suggestion"):
            print(f"           fix: {f['fix_suggestion']}")
        provenance = f.get("tool") or "builtin"
        if f.get("tool_version"):
            provenance = f"{provenance} {f['tool_version']}"
        print(f"           via {provenance} (rules v{f.get('rule_version', '?')})")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli_scan")
    parser.add_argument("path", help="folder to scan")
    parser.add_argument("--json", action="store_true", help="emit the raw result as JSON")
    parser.add_argument("--offline", action="store_true",
                        help="stub network lookups; registry-backed checks report as inconclusive")
    parser.add_argument("--fail-on-certain", action="store_true",
                        help="exit 3 when any CERTAIN finding is present")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.path):
        print(f"not a directory: {args.path}", file=sys.stderr)
        return 2

    try:
        ingested = walk_dir(args.path)
    except IngestError as exc:
        print(f"could not read {args.path}: {exc}", file=sys.stderr)
        return 2

    files = ingested.files
    overrides = asyncio.run(_offline_overrides()) if args.offline else None
    result = asyncio.run(run_scan(
        files, ingested.skipped, overrides=overrides, suppressed=ingested.suppressed,
    ))

    if args.json:
        result["census"] = take_census(files).language_files
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_report(args.path, result, head_sha(args.path), content_hash(files))

    if args.fail_on_certain and result["analytics"]["by_confidence"].get("CERTAIN"):
        return 3
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
