"""app.strix.parser: the honesty invariants (never block-eligible, never
CERTAIN, always category="pentest"/rule_id="STRIX") must hold for ANY input
shape — Strix's real output schema is unverified, so the parser must degrade
gracefully rather than crash or (worse) accidentally produce a Guard-looking
finding on unexpected input."""

from app.analyzers.base import Confidence
from app.strix.parser import to_findings


def test_empty_input_yields_nothing():
    assert to_findings([]) == []


def test_basic_record_mapped_advisory_only():
    records = [{"title": "Reflected XSS on /search", "location": "app/views.py", "line": 42}]
    findings = to_findings(records)
    assert len(findings) == 1
    f = findings[0]
    assert f.category == "pentest"
    assert f.rule_id == "STRIX"
    assert f.block_eligible is False
    assert f.confidence in (Confidence.HIGH, Confidence.MEDIUM)
    assert f.confidence is not Confidence.CERTAIN
    assert "Reflected XSS" in f.message
    assert "advisory" in f.message.lower()


def test_record_with_poc_is_high_not_certain():
    records = [{"title": "SQLi", "proof_of_concept": "' OR 1=1 --"}]
    f = to_findings(records)[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False  # even with a working PoC, never block-eligible


def test_record_without_poc_is_medium():
    records = [{"title": "Weak session cookie flags"}]
    f = to_findings(records)[0]
    assert f.confidence is Confidence.MEDIUM
    assert f.block_eligible is False


def test_a_record_claiming_certain_or_block_eligible_is_ignored():
    # Even if a malformed/adversarial record claims Guard-level certainty, the
    # parser must never honor it — these fields aren't read from the record at all.
    records = [{
        "title": "spoofed",
        "confidence": "CERTAIN",
        "block_eligible": True,
        "rule_id": "SQG001",
        "category": "dependency",
    }]
    f = to_findings(records)[0]
    assert f.category == "pentest"
    assert f.rule_id == "STRIX"
    assert f.block_eligible is False
    assert f.confidence is not Confidence.CERTAIN


def test_missing_fields_degrade_gracefully_not_a_crash():
    # A completely empty record must not raise — unknown/absent fields default safely.
    findings = to_findings([{}])
    assert len(findings) == 1
    f = findings[0]
    assert f.block_eligible is False
    assert f.line_start == 0
    assert f.file_path == "(dynamic)"


def test_malformed_line_field_does_not_crash():
    records = [{"title": "x", "line": "not-a-number"}]
    f = to_findings(records)[0]
    assert f.line_start == 0


def test_multiple_records_all_carry_the_invariants():
    records = [{"title": f"finding {i}"} for i in range(5)]
    findings = to_findings(records)
    assert len(findings) == 5
    assert all(f.block_eligible is False for f in findings)
    assert all(f.category == "pentest" for f in findings)
    assert all(f.rule_id == "STRIX" for f in findings)
    assert all(f.confidence is not Confidence.CERTAIN for f in findings)
