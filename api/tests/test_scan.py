"""Whole-repo scan: offline analyzers fire over full files; analytics aggregate correctly.

Kept network-free on purpose: no manifest files are planted, so the registry/OSV/license
analyzers find nothing to look up. The offline analyzers (secrets, placeholders) carry the
assertions.
"""

import asyncio

import pytest

from app import scan as scanmod
from app.config import settings
from app.scan import aggregate, run_scan
from app.analyzers.base import Confidence, Evidence, Finding


@pytest.mark.asyncio
async def test_scan_flags_secret_and_placeholder_across_full_file():
    files = {
        "app/config.py": 'AWS_KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: implement auth\nx = 1\n',
    }
    result = await run_scan(files)

    rules = {f["rule_id"] for f in result["findings"]}
    assert "SQG002" in rules  # secret (CERTAIN, full-file scan, not just a diff)
    assert "SQG003" in rules  # placeholder TODO
    assert result["analytics"]["clean"] is False
    assert result["analytics"]["files_scanned"] == 1


@pytest.mark.asyncio
async def test_kill_switch_drops_a_disabled_analyzer(monkeypatch):
    """DISABLED_ANALYZERS=SQG002 → the secret analyzer is skipped; others still run."""
    monkeypatch.setattr(settings, "disabled_analyzers", "SQG002")
    files = {"app/config.py": 'AWS_KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: implement auth\n'}

    calls: list[dict] = []

    async def cb(payload: dict) -> None:
        calls.append(payload)

    result = await run_scan(files, on_progress=cb)

    rules = {f["rule_id"] for f in result["findings"]}
    assert "SQG002" not in rules  # disabled — the secret is not flagged
    assert "SQG003" in rules      # placeholder analyzer still runs
    assert calls[0]["total"] == 6  # one analyzer dropped from the 7-analyzer total


@pytest.mark.asyncio
async def test_slow_analyzer_times_out_without_hanging_scan(monkeypatch):
    """A single analyzer that never returns must not hang the scan — it's skipped
    after ANALYZER_BUDGET and the others still report (the hang-fix safety net)."""
    monkeypatch.setattr(scanmod, "ANALYZER_BUDGET", 0.05)

    async def slow(_diff, _ctx):
        await asyncio.sleep(5)
        return []

    monkeypatch.setattr(scanmod, "check_sast", slow)  # SQG006 will hang → must be skipped

    files = {"app/config.py": 'AWS_KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: x\n'}
    result = await run_scan(files)

    rules = {f["rule_id"] for f in result["findings"]}
    assert "SQG002" in rules       # other analyzers still ran to completion
    assert "SQG006" not in rules   # the hung analyzer was skipped, scan still finished
    assert result["analytics"]["files_scanned"] == 1


@pytest.mark.asyncio
async def test_scan_clean_repo_has_no_findings():
    files = {"README.md": "# My Project\n\nThis is a normal readme.\n"}
    result = await run_scan(files)

    assert result["findings"] == []
    assert result["analytics"]["clean"] is True
    assert result["analytics"]["total_findings"] == 0


@pytest.mark.asyncio
async def test_scan_reports_skipped_files():
    result = await run_scan({"a.py": "x = 1\n"}, skipped=["big.bin (too large)"])
    assert result["analytics"]["files_skipped"] == 1
    assert result["skipped"] == ["big.bin (too large)"]


@pytest.mark.asyncio
async def test_run_scan_emits_honest_phase_progress():
    """on_progress fires once per analyzer (rising index) plus a final 'reporting' —
    real phase data, no invented %/ETA."""
    calls: list[dict] = []

    async def cb(payload: dict) -> None:
        calls.append(payload)

    await run_scan({"a.py": "x = 1\n"}, on_progress=cb)

    assert len(calls) == 8  # 7 analyzers + reporting
    assert [c["index"] for c in calls] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert all(c["total"] == 7 for c in calls)
    assert calls[0]["phase"] == "dependencies"
    assert calls[-1]["phase"] == "reporting"
    assert all(c["files_total"] == 1 for c in calls)
    # findings_so_far is monotonic non-decreasing
    counts = [c["findings_so_far"] for c in calls]
    assert counts == sorted(counts)


def _f(rule_id, confidence=Confidence.HIGH, block=False, path="a.py"):
    return Finding(
        category="x", confidence=confidence, block_eligible=block, file_path=path,
        line_start=1, line_end=1, message="m", evidence=Evidence(snippet="s"),
        tool="t", rule_id=rule_id,
    )


def test_aggregate_counts_by_rule_confidence_and_file():
    findings = [
        _f("SQG002", Confidence.CERTAIN, block=True, path="a.py"),
        _f("SQG003", Confidence.MEDIUM, path="a.py"),
        _f("SQG003", Confidence.MEDIUM, path="b.py"),
    ]
    a = aggregate(findings, files_scanned=5, skipped=[])
    assert a["total_findings"] == 3
    assert a["by_rule"] == {"SQG002": 1, "SQG003": 2}
    assert a["by_confidence"]["CERTAIN"] == 1
    assert a["by_confidence"]["MEDIUM"] == 2
    assert a["block_eligible"] == 1
    assert a["top_files"][0] == {"file_path": "a.py", "count": 2}
    assert a["clean"] is False
