"""Engine availability must be probed, never assumed.

The product's docs claim gitleaks, Trivy, Syft, Semgrep and osv-scanner are in use while
none of them is invoked. The failure that matters is not the missing binary — it is a
report that reads the same whether the engine ran or was never installed.
"""

import shutil

import pytest

from app import engines
from app.coverage import RuleCoverage, note_missing_engines


def test_missing_binary_reports_unavailable_with_a_reason(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    status = engines.probe(engines.ENGINES_BY_NAME["semgrep"])
    assert status.available is False
    assert "not installed" in status.error


def test_probe_reads_a_version_from_a_banner(monkeypatch, tmp_path):
    fake = tmp_path / "trivy"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))

    class Result:
        returncode = 0
        stdout = "Version: 0.50.1\n"
        stderr = ""

    monkeypatch.setattr(engines.subprocess, "run", lambda *a, **k: Result())
    status = engines.probe(engines.ENGINES_BY_NAME["trivy"])
    assert status.available is True
    assert status.version == "0.50.1"


def test_present_binary_with_unparseable_banner_is_still_available(monkeypatch, tmp_path):
    """A weird version string is not a reason to claim the tool is absent."""
    fake = tmp_path / "gitleaks"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))

    class Result:
        returncode = 0
        stdout = "gitleaks (dev build)\n"
        stderr = ""

    monkeypatch.setattr(engines.subprocess, "run", lambda *a, **k: Result())
    status = engines.probe(engines.ENGINES_BY_NAME["gitleaks"])
    assert status.available is True
    assert status.version is None


def test_probe_never_raises_on_a_broken_binary(monkeypatch, tmp_path):
    fake = tmp_path / "syft"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))

    def boom(*_a, **_k):
        raise OSError("Exec format error")

    monkeypatch.setattr(engines.subprocess, "run", boom)
    status = engines.probe(engines.ENGINES_BY_NAME["syft"])
    assert status.available is False
    assert "Exec format error" in status.error


def test_availability_states_the_cost_of_each_missing_engine(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    report = engines.availability()

    assert report["available_count"] == 0
    assert report["total_count"] == len(engines.ENGINES)
    assert set(report["missing"]) == {e.name for e in engines.ENGINES}
    # Not just "missing" — what it means for coverage, in plain language.
    assert any("not being inspected" in c or "uninspected" in c for c in report["consequences"])
    assert all("built-in check only" in c for c in report["consequences"])


def test_rules_missing_an_engine_maps_rules_to_absent_tools(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    by_rule = engines.rules_missing_an_engine()
    assert "semgrep" in by_rule["SQG006"]
    assert "trivy" in by_rule["SQG004"]
    assert "gitleaks" in by_rule["SQG002"]


def test_coverage_records_that_a_result_came_from_the_fallback_only():
    coverages = [RuleCoverage("SQG006", "Dangerous code patterns", "ran")]
    note_missing_engines(coverages, {"SQG006": ["semgrep"]})

    row = coverages[0]
    # Still ran — the built-in check did work — but the report cannot imply Semgrep did.
    assert row.status == "ran"
    assert "semgrep not installed" in row.not_covered
    assert "built-in check only" in row.detail


@pytest.mark.asyncio
async def test_scan_reports_engine_gaps_end_to_end(monkeypatch):
    """A real scan on a machine without the binaries must say so in its coverage."""
    from app.scan import run_scan

    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = await run_scan({"a.py": "x = 1\n"})

    sqg006 = next(r for r in result["coverage"]["rules"] if r["rule_id"] == "SQG006")
    assert "semgrep not installed" in sqg006["not_covered"]
    assert result["engine_versions"] == {}
