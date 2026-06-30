"""Phase 4 Check Run output: conclusion mapping, plain-English summary, annotations."""

from app.analyzers.base import Confidence, Evidence, Finding
from app.checks import (
    MAX_ANNOTATIONS,
    apply_block_eligibility,
    build_annotations,
    dedupe_findings,
    determine_conclusion,
    format_check_run_summary,
    is_block_eligible,
    would_block_findings,
)


def _finding(rule_id="SQG001", confidence=Confidence.CERTAIN, block=True,
             path="app/x.py", line=10, msg="problem here", fix=None,
             category="dependency") -> Finding:
    return Finding(
        category=category,
        confidence=confidence,
        block_eligible=block,
        file_path=path,
        line_start=line,
        line_end=line,
        message=msg,
        evidence=Evidence(snippet="x"),
        tool="test",
        rule_id=rule_id,
        fix_suggestion=fix,
    )


# --- determine_conclusion: Phase 4 is label-only (never "failure") ----------

def test_conclusion_clean_is_success():
    assert determine_conclusion([]) == "success"


def test_conclusion_with_findings_is_action_required():
    assert determine_conclusion([_finding()]) == "action_required"


def test_conclusion_never_failure_even_with_block_eligible():
    """Blocking is Phase 9 — a block-eligible CERTAIN finding still only flags orange."""
    assert determine_conclusion([_finding(confidence=Confidence.CERTAIN, block=True)]) == "action_required"


# --- format_check_run_summary -----------------------------------------------

def test_summary_clean():
    out = format_check_run_summary([])
    assert "All clear" in out


def test_summary_lists_finding_with_location_and_fix():
    out = format_check_run_summary([
        _finding(path="src/api.py", line=42, msg="fake package 'foo'", fix="remove it"),
    ])
    assert "src/api.py:42" in out
    assert "fake package 'foo'" in out
    assert "remove it" in out
    assert "🟠" in out


def test_summary_singular_vs_plural():
    assert "1 thing" in format_check_run_summary([_finding()])
    assert "2 things" in format_check_run_summary([_finding(), _finding(line=11)])


def test_summary_truncates_with_dashboard_link():
    findings = [_finding(line=i) for i in range(30)]
    out = format_check_run_summary(findings, max_findings=20, dashboard_url="https://dash.example/pr/1")
    assert "10 more" in out
    assert "https://dash.example/pr/1" in out


def test_summary_truncates_without_link():
    findings = [_finding(line=i) for i in range(25)]
    out = format_check_run_summary(findings, max_findings=20)
    assert "5 more" in out


def test_summary_most_severe_first():
    findings = [
        _finding(rule_id="SQG003", confidence=Confidence.MEDIUM, msg="todo", line=1),
        _finding(rule_id="SQG001", confidence=Confidence.CERTAIN, msg="fake pkg", line=2),
    ]
    out = format_check_run_summary(findings)
    assert out.index("fake pkg") < out.index("todo")


# --- build_annotations ------------------------------------------------------

def test_annotation_level_maps_confidence():
    anns = build_annotations([
        _finding(confidence=Confidence.CERTAIN, line=1),
        _finding(confidence=Confidence.HIGH, line=2),
        _finding(confidence=Confidence.MEDIUM, line=3),
    ])
    levels = {a["start_line"]: a["annotation_level"] for a in anns}
    assert levels == {1: "failure", 2: "warning", 3: "notice"}


def test_annotation_anchors_to_line_and_carries_fix():
    anns = build_annotations([_finding(path="a.py", line=7, msg="bad", fix="do this")])
    a = anns[0]
    assert a["path"] == "a.py"
    assert a["start_line"] == 7
    assert a["end_line"] == 7
    assert "bad" in a["message"]
    assert "do this" in a["message"]
    assert "SQG001" in a["title"]


def test_annotations_capped_at_50():
    findings = [_finding(line=i) for i in range(80)]
    anns = build_annotations(findings)
    assert len(anns) == MAX_ANNOTATIONS


# --- block-eligibility invariant (Sprint A) ---------------------------------

def test_is_block_eligible_only_certain_dependency_or_secret():
    assert is_block_eligible("dependency", Confidence.CERTAIN) is True
    assert is_block_eligible("secret", Confidence.CERTAIN) is True
    # Wrong category, even when CERTAIN, never blocks.
    assert is_block_eligible("license", Confidence.CERTAIN) is False
    assert is_block_eligible("sast", Confidence.CERTAIN) is False
    # Right category, lower confidence, never blocks.
    assert is_block_eligible("dependency", Confidence.HIGH) is False
    assert is_block_eligible("secret", Confidence.MEDIUM) is False


def test_apply_block_eligibility_corrects_a_divergent_flag():
    # A future rule wrongly marks an advisory CVE block-eligible; the resolver fixes it.
    bad = _finding(rule_id="SQG004", confidence=Confidence.HIGH, block=True, category="vulnerability")
    # And a dependency 404 that forgot to set the flag gets it set.
    missed = _finding(rule_id="SQG001", confidence=Confidence.CERTAIN, block=False, category="dependency")
    apply_block_eligibility([bad, missed])
    assert bad.block_eligible is False
    assert missed.block_eligible is True


# --- dedupe_findings (Sprint A) ---------------------------------------------

def test_dedupe_collapses_same_file_line_rule_keeping_highest_confidence():
    high = _finding(rule_id="SQG002", confidence=Confidence.HIGH, path="a.py", line=5, category="secret")
    certain = _finding(rule_id="SQG002", confidence=Confidence.CERTAIN, path="a.py", line=5, category="secret")
    other = _finding(rule_id="SQG003", confidence=Confidence.MEDIUM, path="a.py", line=5, category="placeholder")
    out = dedupe_findings([high, certain, other])
    assert len(out) == 2  # the two SQG002 collapse; SQG003 on the same line is distinct
    kept = next(f for f in out if f.rule_id == "SQG002")
    assert kept.confidence is Confidence.CERTAIN  # highest confidence wins


def test_dedupe_preserves_first_seen_order():
    a = _finding(rule_id="SQG001", path="a.py", line=1)
    b = _finding(rule_id="SQG002", path="b.py", line=2, category="secret")
    assert [f.rule_id for f in dedupe_findings([a, b])] == ["SQG001", "SQG002"]


# --- would_block_findings (shadow gate, Sprint A) ---------------------------

def test_would_block_only_block_eligible_and_configured_rules():
    dep = _finding(rule_id="SQG001", confidence=Confidence.CERTAIN, block=True, category="dependency")
    secret = _finding(rule_id="SQG002", confidence=Confidence.CERTAIN, block=True, category="secret", line=2)
    advisory = _finding(rule_id="SQG004", confidence=Confidence.HIGH, block=False, category="vulnerability", line=3)
    would = would_block_findings([dep, secret, advisory], blocked_rules=["SQG001"])
    assert [f.rule_id for f in would] == ["SQG001"]  # SQG002 not configured, advisory not eligible


def test_would_block_empty_when_no_rules_configured():
    dep = _finding(rule_id="SQG001", confidence=Confidence.CERTAIN, block=True, category="dependency")
    assert would_block_findings([dep], blocked_rules=[]) == []
