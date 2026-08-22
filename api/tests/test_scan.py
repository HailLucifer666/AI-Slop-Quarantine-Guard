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
    assert calls[0]["total"] == 8  # every rule is accounted for, disabled ones included

    # A disabled check must be reported as switched off, never as a silent pass —
    # otherwise turning off the secret scanner would make a repo look secret-free.
    by_rule = {r["rule_id"]: r for r in result["coverage"]["rules"]}
    assert by_rule["SQG002"]["status"] == "not_run_disabled"
    assert result["coverage"]["clean"] is False
    assert result["analytics"]["clean"] is False


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
async def test_no_findings_is_not_reported_as_clean_when_checks_could_not_run():
    """A readme-only repo has nothing for 6 of the 8 checks to read.

    The old behaviour called this "clean" because zero findings came back. It isn't:
    the dependency, vulnerability, license, typosquat, SAST and complexity checks never
    looked at anything, so the correct answer is "no problems found in what was scanned".
    """
    files = {"README.md": "# My Project\n\nThis is a normal readme.\n"}
    result = await run_scan(files)

    assert result["findings"] == []
    assert result["analytics"]["total_findings"] == 0
    assert result["analytics"]["clean"] is False
    assert result["analytics"]["fully_covered"] is False

    statuses = {r["rule_id"]: r["status"] for r in result["coverage"]["rules"]}
    # Language-independent checks genuinely ran over the file.
    assert statuses["SQG002"] == "ran"
    assert statuses["SQG003"] == "ran"
    # These had nothing they can read, and say so instead of implying a pass.
    assert statuses["SQG001"] == "not_run_unsupported"
    assert statuses["SQG006"] == "not_run_unsupported"
    assert statuses["SQG009"] == "not_run_unsupported"  # no Python to build a tree from
    assert result["coverage"]["rules_incomplete"] == 6


@pytest.mark.asyncio
async def test_fully_covered_scan_reports_clean():
    """When every check has something to read and finds nothing, clean is earned."""
    # Exactly pinned, so the installed version is knowable without a lockfile.
    files = {
        "requirements.txt": "requests==2.32.3\n",
        "app/main.py": "import requests\n\n\ndef go():\n    return requests.get('https://x')\n",
    }

    async def no_missing_packages(_ecosystem, _name, _client=None):
        from app.registries import Existence
        return Existence.EXISTS

    async def no_vulns(pins, _client=None):
        return {p: [] for p in pins}

    async def permissive_license(_ecosystem, _name, _client=None):
        return "MIT"

    result = await run_scan(
        files,
        overrides={
            "check_exists": no_missing_packages,
            "query_batch": no_vulns,
            "fetch_license": permissive_license,
        },
    )

    assert result["findings"] == []
    assert result["coverage"]["rules_incomplete"] == 0
    assert result["analytics"]["fully_covered"] is True
    assert result["analytics"]["clean"] is True


@pytest.mark.asyncio
async def test_range_specs_without_a_lockfile_are_reported_as_partial():
    """npm's default `^1.2.3` cannot be resolved to an installed version without a
    lockfile, so the vulnerability check must not present itself as complete."""
    files = {"package.json": '{"dependencies": {"lodash": "^4.17.21"}}\n'}

    async def unknown(_ecosystem, _name, _client=None):
        from app.registries import Existence
        return Existence.EXISTS

    async def no_vulns(pins, _client=None):
        return {p: [] for p in pins}

    result = await run_scan(files, overrides={"check_exists": unknown, "query_batch": no_vulns})

    sqg004 = next(r for r in result["coverage"]["rules"] if r["rule_id"] == "SQG004")
    assert sqg004["status"] == "partial"
    assert any("no lockfile" in nc for nc in sqg004["not_covered"])
    assert result["analytics"]["clean"] is False


@pytest.mark.asyncio
async def test_a_lockfile_resolves_the_ranges_and_restores_full_coverage():
    files = {
        "package.json": '{"dependencies": {"lodash": "^4.17.21"}}\n',
        "package-lock.json": '{"lockfileVersion": 3, "packages": {}}\n',
    }

    async def exists(_ecosystem, _name, _client=None):
        from app.registries import Existence
        return Existence.EXISTS

    async def no_vulns(pins, _client=None):
        return {p: [] for p in pins}

    async def mit(_ecosystem, _name, _client=None):
        return "MIT"

    result = await run_scan(
        files,
        overrides={"check_exists": exists, "query_batch": no_vulns, "fetch_license": mit},
    )

    sqg004 = next(r for r in result["coverage"]["rules"] if r["rule_id"] == "SQG004")
    assert sqg004["status"] == "ran"


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

    assert len(calls) == 9  # 8 analyzers + reporting
    assert [c["index"] for c in calls] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
    assert all(c["total"] == 8 for c in calls)
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


# --- a scanned repo must not be able to edit its own report -----------------------


@pytest.mark.asyncio
async def test_secret_behind_a_repo_gitignore_is_still_reported(tmp_path):
    """The F1 end-to-end proof, and the tightest statement of the product promise.

    Before the fix, adding one line to the scanned repository's own .gitignore took a
    committed, format-valid AWS access key id from SQG002=1 to SQG002=0 — with
    files_skipped still reporting 0, so nothing told the user anything had been withheld.
    """
    from app.ingest import walk_dir

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "credentials.py").write_text(
        'AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7REALKEY"\n', encoding="utf-8"
    )
    (tmp_path / ".gitignore").write_text("credentials.py\n", encoding="utf-8")

    ingested = walk_dir(str(tmp_path))
    result = await run_scan(
        ingested.files, ingested.skipped, suppressed=ingested.suppressed,
    )

    assert result["analytics"]["by_rule"].get("SQG002") == 1


@pytest.mark.asyncio
async def test_unexamined_files_disqualify_a_clean_verdict():
    """The class fix, not just the F1 instance.

    A file we did not read is a gap whatever the reason — the repo's ignore rules, or
    our own size/count caps. `clean` previously derived from rule statuses alone, so a
    cap-skipped file sat happily beside "All clear".
    """
    files = {"app/util.py": "def add(a, b):\n    return a + b\n"}

    baseline = await run_scan(files)
    with_skip = await run_scan(files, ["huge.bin (exceeds 1024KB file cap)"])
    with_suppression = await run_scan(files, suppressed=["build/ (repo .gitignore)"])

    # Whatever the baseline concludes, an unexamined file must remove the clean claim.
    assert with_skip["analytics"]["clean"] is False
    assert with_suppression["analytics"]["clean"] is False
    assert with_skip["analytics"]["fully_covered"] is False
    assert with_suppression["analytics"]["fully_covered"] is False
    assert with_suppression["analytics"]["files_suppressed"] == 1
    assert baseline["analytics"]["files_suppressed"] == 0
