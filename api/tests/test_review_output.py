"""Review-grade output: grouping, first-class references, and honest suggestions.

The load-bearing rule tested here is that a ```suggestion block — which GitHub renders as
a one-click "Commit suggestion" straight onto the author's branch — may only ever appear
when the replacement was derived mechanically from an authoritative source. A fabricated
patch is worse than no patch, because it gets committed on our word.
"""

import pytest

from app.analyzers.base import (
    REMEDIATION_GUIDANCE,
    REMEDIATION_PATCH,
    Advisory,
    Confidence,
    Evidence,
    Finding,
    Remediation,
    compute_fingerprint,
    finalize,
)
from app.checks import (
    build_review_comments,
    format_check_run_summary,
    format_grouped_summary,
    format_review_comment,
)
from app.grouping import GROUPABLE_RULES, group_findings, issue_key, summarize_groups


def _f(rule_id="SQG006", path="a.py", line=1, msg="use of eval() at line 1: 'eval(x)'",
       confidence=Confidence.HIGH, snippet="eval(x)", tool="regex", **kwargs):
    return Finding(
        category="sast", confidence=confidence, block_eligible=False, file_path=path,
        line_start=line, line_end=line, message=msg, evidence=Evidence(snippet=snippet),
        tool=tool, rule_id=rule_id, **kwargs,
    )


# --- fingerprints are content-derived, not positional ------------------------------


def test_fingerprint_survives_a_line_move():
    """Inserting an import above a finding must not make it a "new" finding, or every
    unrelated edit would re-post the same comment."""
    assert compute_fingerprint(_f(line=10)) == compute_fingerprint(_f(line=99))


def test_fingerprint_survives_reindentation():
    assert compute_fingerprint(_f(snippet="eval(x)")) == compute_fingerprint(_f(snippet="  eval(x)  "))


def test_fingerprint_differs_by_file_and_content():
    assert compute_fingerprint(_f(path="a.py")) != compute_fingerprint(_f(path="b.py"))
    assert compute_fingerprint(_f(snippet="eval(x)")) != compute_fingerprint(_f(snippet="eval(y)"))


def test_finalize_fills_fingerprint_and_evidence_hash():
    findings = finalize([_f()])
    assert findings[0].fingerprint
    assert findings[0].evidence_hash


# --- grouping structures without discarding ----------------------------------------


def test_repeated_todos_collapse_into_one_group():
    """The simplex-chat case: 318 real TODOs must not bury 3 real secrets."""
    todos = [
        _f(rule_id="SQG003", path=f"src/f{i}.hs", line=i,
           msg=f"TODO/FIXME marker at line {i}: '-- TODO fix later'",
           confidence=Confidence.MEDIUM, snippet="-- TODO fix later")
        for i in range(40)
    ]
    secret = _f(rule_id="SQG002", path="config.py", msg="AWS key", confidence=Confidence.CERTAIN,
                snippet="AKIA...")

    groups = group_findings(todos + [secret])

    # The secret sorts first despite being outnumbered 40 to 1.
    assert groups[0].rule_id == "SQG002"
    todo_group = next(g for g in groups if g.rule_id == "SQG003")
    assert todo_group.count == 40
    assert todo_group.file_count == 40
    assert todo_group.is_group
    # Nothing is dropped: group counts sum back to the input total.
    assert sum(g.count for g in groups) == 41


def test_a_secret_is_never_collapsed_into_a_group():
    """Secrets and hallucinated dependencies are discrete incidents, however many."""
    secrets = [_f(rule_id="SQG002", path=f"f{i}.py", msg="AWS key", snippet=f"AKIA{i}")
               for i in range(10)]
    groups = group_findings(secrets)
    assert all(not g.is_group for g in groups)
    assert "SQG002" not in GROUPABLE_RULES


def test_same_advisory_across_manifests_is_one_issue():
    a = _f(rule_id="SQG004", path="requirements.txt", msg="x==1.0 has 1 advisory",
           advisories=[Advisory("GHSA-abc", "https://osv.dev/vulnerability/GHSA-abc")])
    b = _f(rule_id="SQG004", path="api/requirements.txt", msg="x==1.0 has 1 advisory(ies): GHSA-abc",
           advisories=[Advisory("GHSA-abc", "https://osv.dev/vulnerability/GHSA-abc")])
    assert issue_key(a) == issue_key(b)
    assert len(group_findings([a, b])) == 1


def test_group_serialization_reports_the_true_total_when_capped():
    findings = [_f(rule_id="SQG003", path=f"f{i}.py", line=i, snippet="# TODO",
                   msg=f"TODO/FIXME marker at line {i}: '# TODO'") for i in range(120)]
    payload = summarize_groups(group_findings(findings))
    group = payload["groups"][0]
    assert group["count"] == 120          # the truth
    assert group["occurrences_shown"] == 50  # what the payload carries
    assert len(group["occurrences"]) == 50


def test_grouped_summary_names_occurrence_counts():
    findings = [_f(rule_id="SQG003", path=f"f{i}.py", line=i, snippet="# TODO",
                   msg=f"TODO/FIXME marker at line {i}: '# TODO'",
                   confidence=Confidence.MEDIUM) for i in range(5)]
    out = format_grouped_summary(group_findings(findings))
    assert "5 occurrences across 5 files" in out


# --- suggestions may never be invented --------------------------------------------


def test_machine_derived_patch_becomes_a_commitable_suggestion():
    finding = _f(
        rule_id="SQG004", path="requirements.txt", msg="requests==2.19.0 has 1 advisory(ies)",
        snippet="requests==2.19.0",
        advisories=[Advisory("GHSA-x", "https://osv.dev/vulnerability/GHSA-x")],
        fix_versions=["2.31.0"],
        remediation=Remediation(
            kind=REMEDIATION_PATCH, text="Upgrade requests to 2.31.0.",
            suggested_replacement="requests==2.31.0",
            basis="OSV lists 2.31.0 as a patched release for GHSA-x",
        ),
    )
    body = format_review_comment(finalize([finding])[0])

    assert "```suggestion" in body
    assert "requests==2.31.0" in body
    # The claim is checkable, not just asserted.
    assert "Basis: OSV lists 2.31.0" in body
    assert "https://osv.dev/vulnerability/GHSA-x" in body


def test_guidance_only_remediation_emits_no_suggestion_block():
    finding = _f(
        rule_id="SQG004", msg="pkg==1.0 has 1 advisory(ies)",
        remediation=Remediation(
            kind=REMEDIATION_GUIDANCE, text="Check the advisory for a patched release.",
            basis="OSV does not name a fixed version for this advisory",
        ),
    )
    body = format_review_comment(finalize([finding])[0])

    assert "```suggestion" not in body
    assert "No automatic fix offered" in body


def test_a_secret_never_gets_an_auto_patch():
    """Rewriting a leaked key in place would look fixed while the key stays compromised."""
    finding = _f(rule_id="SQG002", msg="AWS key", snippet='KEY = "AKIAIOSFODNN7EXAMPLE"',
                 confidence=Confidence.CERTAIN,
                 fix_suggestion="Rotate this credential and load it from an environment variable.")
    body = format_review_comment(finalize([finding])[0])

    assert "```suggestion" not in body
    assert "Rotate this credential" in body


def test_cwe_is_rendered_as_a_checkable_reference():
    body = format_review_comment(finalize([_f(cwe=["CWE-95"])])[0])
    assert "cwe.mitre.org/data/definitions/95.html" in body


def test_comment_carries_provenance():
    body = format_review_comment(finalize([_f(tool="osv", tool_version="1.2")])[0])
    assert "Detected by osv 1.2" in body
    assert "rules v" in body


# --- anchoring and idempotency ----------------------------------------------------


def test_comments_are_only_anchored_to_lines_present_in_the_diff():
    """An unanchorable comment makes GitHub reject the entire review with a 422."""
    inside = _f(path="a.py", line=5)
    outside = _f(path="a.py", line=900)

    comments = build_review_comments([inside, outside], diff_lines={("a.py", 5)})

    assert len(comments) == 1
    assert comments[0]["line"] == 5
    assert comments[0]["side"] == "RIGHT"


def test_a_rerun_does_not_repost_the_same_comment():
    finding = finalize([_f()])[0]
    first = build_review_comments([finding], diff_lines={("a.py", 1)})
    assert len(first) == 1

    again = build_review_comments(
        [finding], diff_lines={("a.py", 1)}, already_posted=[first[0]["body"]]
    )
    assert again == []


def test_comment_count_is_capped_but_summary_still_covers_everything():
    findings = finalize([_f(path="a.py", line=i, snippet=f"eval(x{i})") for i in range(1, 60)])
    diff_lines = {("a.py", i) for i in range(1, 60)}

    comments = build_review_comments(findings, diff_lines=diff_lines, max_comments=25)
    assert len(comments) == 25

    summary = format_check_run_summary(findings, groups=group_findings(findings))
    assert "Found 59 things to look at" in summary


def test_most_severe_findings_win_the_limited_comment_slots():
    medium = [_f(path="a.py", line=i, confidence=Confidence.MEDIUM, snippet=f"m{i}")
              for i in range(1, 30)]
    certain = _f(path="a.py", line=99, confidence=Confidence.CERTAIN, rule_id="SQG002",
                 msg="AWS key", snippet="AKIA")
    diff_lines = {("a.py", i) for i in list(range(1, 30)) + [99]}

    comments = build_review_comments(finalize(medium + [certain]), diff_lines=diff_lines,
                                     max_comments=5)
    assert comments[0]["line"] == 99


@pytest.mark.asyncio
async def test_scan_result_exposes_groups_and_fingerprints():
    from app.scan import run_scan

    files = {"config.py": 'KEY = "AKIAIOSFODNN7REALKEY"\n# TODO: implement\nx = 1\n'}
    result = await run_scan(files)

    assert result["groups"]["findings_total"] == len(result["findings"])
    assert all(f["fingerprint"] for f in result["findings"])
    sast_or_secret = [f for f in result["findings"] if f["rule_id"] in ("SQG002", "SQG003")]
    assert sast_or_secret, "expected the offline analyzers to fire"
