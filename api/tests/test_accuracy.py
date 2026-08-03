"""Measured accuracy against known answers — the gate that makes "accurate" checkable.

Runs the REAL engine (`app.scan.run_scan`, the same entry point the worker uses) over the
committed proof corpus and scores it per rule. Only the three network boundaries are
replayed, from responses recorded on a stated date; all detection logic executes for real.

A regression that weakens a rule fails here instead of surfacing later as "your scanner
missed something". A regression that makes a rule noisier fails here too — precision is
scored, not just recall.
"""

from pathlib import Path

import pytest

from app.ingest import walk_dir
from app.scan import run_scan
from tests.proof_ground_truth import (
    EXPECTATIONS,
    REPLAY_OVERRIDES,
    VERIFIED_ON,
    Expectation,
)

_API_ROOT = Path(__file__).resolve().parents[1]
_CORPUS = _API_ROOT / "tests" / "fixtures" / "proof_corpus"


def _fixture_path(name: str) -> str:
    path = _CORPUS / name
    assert path.is_dir(), f"proof fixture missing on disk: {path}"
    return str(path)


async def _scan_fixture(name: str) -> dict:
    files, skipped = walk_dir(_fixture_path(name))
    assert files, f"fixture {name} ingested no files"
    assert skipped == [], f"fixture {name} should be small enough to ingest whole"
    return await run_scan(files, skipped, overrides=REPLAY_OVERRIDES)


def _counts(result: dict) -> dict:
    counts: dict = {}
    for finding in result["findings"]:
        counts[finding["rule_id"]] = counts.get(finding["rule_id"], 0) + 1
    return counts


def _describe(result: dict) -> str:
    """Findings rendered for an assertion message, so a failure is diagnosable."""
    if not result["findings"]:
        return "(no findings)"
    return "; ".join(
        f"{f['rule_id']} {f['confidence']} {f['file_path']}:{f['line_start']} {f['message'][:70]}"
        for f in result["findings"]
    )


@pytest.mark.parametrize("expectation", EXPECTATIONS, ids=lambda e: e.fixture)
@pytest.mark.asyncio
async def test_fixture_matches_ground_truth(expectation: Expectation):
    """Each fixture finds exactly what it should, and nothing it shouldn't."""
    result = await _scan_fixture(expectation.fixture)
    counts = _counts(result)
    detail = _describe(result)

    # Recall: every expected rule fires, the expected number of times.
    for rule_id, expected in expectation.must_find.items():
        actual = counts.get(rule_id, 0)
        assert actual == expected, (
            f"{expectation.fixture}: expected {expected} {rule_id} finding(s), got {actual}.\n"
            f"Why this fixture exists: {expectation.why}\nFindings: {detail}"
        )

    # Precision: nothing else fires. A false positive on a clean fixture is the failure
    # that costs user trust fastest.
    for rule_id in expectation.must_not_find:
        actual = counts.get(rule_id, 0)
        assert actual == 0, (
            f"{expectation.fixture}: FALSE POSITIVE — {rule_id} produced {actual} finding(s) "
            f"where none is correct.\nWhy this fixture exists: {expectation.why}\n"
            f"Findings: {detail}"
        )

    # Confidence tier, where the underlying fact is strong enough to demand one.
    for rule_id, tier in expectation.min_confidence.items():
        tiers = [f["confidence"] for f in result["findings"] if f["rule_id"] == rule_id]
        assert tier in tiers, (
            f"{expectation.fixture}: {rule_id} should reach {tier}, got {tiers}. "
            f"{expectation.why}"
        )

    # A vulnerability finding without its advisory link is not review-grade.
    for rule_id in expectation.expect_advisories:
        for finding in [f for f in result["findings"] if f["rule_id"] == rule_id]:
            assert finding["advisories"], (
                f"{expectation.fixture}: {rule_id} finding carries no advisory reference"
            )
            assert all(a["url"].startswith("https://") for a in finding["advisories"])

    # A patch may only be offered when it is machine-derived from a named fixed version.
    for rule_id in expectation.expect_applicable_patch:
        for finding in [f for f in result["findings"] if f["rule_id"] == rule_id]:
            remediation = finding["remediation"]
            assert remediation and remediation["applicable"], (
                f"{expectation.fixture}: {rule_id} should offer a commitable fix, got "
                f"{remediation}"
            )
            assert finding["fix_versions"], "a patch requires a source-named fixed version"
            assert remediation["basis"], "a patch must state what it is based on"


@pytest.mark.asyncio
async def test_negative_fixtures_produce_no_findings_at_all():
    """The zero-false-positive bar, stated as one number across every clean fixture."""
    negatives = [e for e in EXPECTATIONS if not e.must_find]
    assert negatives, "the corpus must contain negative fixtures"

    false_positives = []
    for expectation in negatives:
        result = await _scan_fixture(expectation.fixture)
        for finding in result["findings"]:
            false_positives.append(
                f"{expectation.fixture}: {finding['rule_id']} at "
                f"{finding['file_path']}:{finding['line_start']} — {finding['message'][:80]}"
            )

    assert not false_positives, (
        "false positives on clean code (precision must be 1.0):\n  "
        + "\n  ".join(false_positives)
    )


@pytest.mark.asyncio
async def test_recall_is_total_on_positive_fixtures():
    """Every fact the corpus asserts is actually detected — recall 1.0, reported as a
    single number so a partial regression cannot hide behind an otherwise green suite."""
    positives = [e for e in EXPECTATIONS if e.must_find]
    expected_total = sum(sum(e.must_find.values()) for e in positives)

    found_total = 0
    misses = []
    for expectation in positives:
        counts = _counts(await _scan_fixture(expectation.fixture))
        for rule_id, expected in expectation.must_find.items():
            actual = min(counts.get(rule_id, 0), expected)
            found_total += actual
            if actual < expected:
                misses.append(f"{expectation.fixture}/{rule_id}: {actual}/{expected}")

    assert found_total == expected_total, (
        f"recall {found_total}/{expected_total}; missed: {', '.join(misses)}"
    )


@pytest.mark.asyncio
async def test_findings_carry_provenance_everywhere():
    """No finding may reach a user without saying what produced it."""
    for expectation in [e for e in EXPECTATIONS if e.must_find]:
        result = await _scan_fixture(expectation.fixture)
        for finding in result["findings"]:
            assert finding["fingerprint"], f"{expectation.fixture}: finding has no fingerprint"
            assert finding["rule_version"], f"{expectation.fixture}: finding has no rule_version"
            assert finding["tool"], f"{expectation.fixture}: finding has no tool"


def test_every_expectation_has_a_directory_on_disk():
    """The corpus is real files, so `prove.ps1` can scan it the same way a user would."""
    for expectation in EXPECTATIONS:
        assert (_CORPUS / expectation.fixture).is_dir(), expectation.fixture


def test_ground_truth_records_when_it_was_verified():
    """A replayed registry fact without a verification date silently rots."""
    assert VERIFIED_ON
    assert len(VERIFIED_ON) == 10 and VERIFIED_ON.count("-") == 2


def test_corpus_has_no_stray_directories():
    """Every fixture directory is declared, so nothing sits unscored."""
    declared = {e.fixture for e in EXPECTATIONS}
    on_disk = {p.name for p in _CORPUS.iterdir() if p.is_dir() and not p.name.startswith(".")}
    assert on_disk == declared, f"undeclared fixtures: {sorted(on_disk - declared)}"
