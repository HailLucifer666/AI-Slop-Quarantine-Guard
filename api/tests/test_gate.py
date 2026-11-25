"""Phase 1 regression tests: honest verdict gate, lockfile caps, multi-line suggestions,
and semantic-preserving SQG009 rewrites."""

import io
import zipfile

import pytest

from app.analyzers.base import (
    REMEDIATION_PATCH,
    Confidence,
    Evidence,
    Finding,
    Remediation,
    finalize,
)
from app.analyzers.simplify import check_simplify
from app.checks import build_review_comments, format_review_comment
from app.gate import CONCLUSION, GateInput, Verdict, conclusion_for, decide
from app.ingest import MAX_FILE_BYTES, read_zip, walk_dir


def _f(**kw):
    defaults = dict(
        category="dependency",
        confidence=Confidence.CERTAIN,
        block_eligible=True,
        file_path="requirements.txt",
        line_start=1,
        line_end=1,
        message="pkg missing",
        evidence=Evidence(snippet="fake-pkg==1.0"),
        tool="registry:pypi",
        rule_id="SQG001",
    )
    defaults.update(kw)
    return Finding(**defaults)


# --- gate.py ----------------------------------------------------------------------


def test_gate_failed_diff_is_unverified_neutral():
    v = decide(GateInput(diff_available=False))
    assert v is Verdict.UNVERIFIED
    assert CONCLUSION[v] == "neutral"


def test_gate_clean_when_conclusive_and_zero_findings():
    cov = {"rules": [{"rule_id": "SQG001", "status": "ran"}], "unexamined_files": 0}
    assert decide(GateInput(findings=[], coverage=cov)) is Verdict.CLEAN
    assert conclusion_for(GateInput(findings=[], coverage=cov)) == "success"


def test_gate_errored_rule_with_zero_findings_is_unverified():
    cov = {"rules": [{"rule_id": "SQG001", "status": "errored"}], "unexamined_files": 0}
    assert decide(GateInput(findings=[], coverage=cov)) is Verdict.UNVERIFIED
    assert conclusion_for(GateInput(findings=[], coverage=cov)) == "neutral"


def test_gate_proven_finding_beats_unverified():
    cov = {"rules": [{"rule_id": "SQG004", "status": "timed_out"}], "unexamined_files": 0}
    assert decide(GateInput(findings=[_f()], coverage=cov, block_mode=False)) is Verdict.FLAGGED
    assert decide(
        GateInput(findings=[_f()], coverage=cov, block_mode=True, blocked_rules=["SQG001"])
    ) is Verdict.BLOCKED


# --- ingest.py lockfile > 1 MB cap bug (F2) ---------------------------------------


def test_walk_dir_reads_lockfile_larger_than_1mb(tmp_path):
    """Regression for F2: walk_dir previously passed b'' for lockfiles > 1 MB,
    storing an empty string in files['package-lock.json'] and causing 0 CVEs."""
    lock = tmp_path / "package-lock.json"
    body = '{"lockfileVersion": 3, "pad": "' + ("a" * (MAX_FILE_BYTES + 4096)) + '"}'
    lock.write_text(body, encoding="utf-8")

    result = walk_dir(str(tmp_path))
    assert "package-lock.json" in result.files
    assert len(result.files["package-lock.json"]) > MAX_FILE_BYTES


def test_read_zip_reads_lockfile_larger_than_1mb():
    buf = io.BytesIO()
    body = '{"lockfileVersion": 3, "pad": "' + ("b" * (MAX_FILE_BYTES + 4096)) + '"}'
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("repo/package-lock.json", body)

    result = read_zip(buf.getvalue())
    assert "package-lock.json" in result.files
    assert len(result.files["package-lock.json"]) > MAX_FILE_BYTES


# --- checks.py multi-line suggestion anchoring (F3) -------------------------------


def test_multiline_finding_sets_start_line_and_start_side():
    finding = finalize([
        _f(
            rule_id="SQG009",
            category="complexity",
            confidence=Confidence.MEDIUM,
            block_eligible=False,
            file_path="app.py",
            line_start=10,
            line_end=13,
            remediation=Remediation(
                kind=REMEDIATION_PATCH,
                text="Replace with ternary",
                suggested_replacement="x = a if c else b",
                basis="AST",
            ),
        )
    ])[0]
    diff_lines = {("app.py", n) for n in range(10, 14)}
    comments = build_review_comments([finding], diff_lines=diff_lines)
    assert len(comments) == 1
    assert comments[0]["start_line"] == 10
    assert comments[0]["start_side"] == "RIGHT"
    assert comments[0]["line"] == 13
    assert comments[0]["side"] == "RIGHT"


def test_suggestion_fence_escapes_embedded_triple_backticks():
    finding = finalize([
        _f(
            remediation=Remediation(
                kind=REMEDIATION_PATCH,
                text="Replace",
                suggested_replacement='x = "```code```"',
                basis="AST",
            )
        )
    ])[0]
    body = format_review_comment(finding)
    assert "````suggestion" in body


# --- simplify.py semantic preservation (F4) ---------------------------------------


def _diff_for(path: str, src: str) -> str:
    lines = src.splitlines()
    body = "\n".join(f"+{ln}" for ln in lines)
    return f"diff --git a/{path} b/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}\n"


@pytest.mark.asyncio
async def test_simplify_boolop_wraps_in_bool():
    """if a and b: return True else: return False must rewrite to return bool(a and b)."""
    src = "def f(a, b):\n    if a and b:\n        return True\n    else:\n        return False\n"
    async def fetch(_p):
        return src
    findings = await check_simplify(_diff_for("a.py", src), {"fetch_file": fetch})
    assert len(findings) == 1
    assert "return bool(a and b)" in findings[0].remediation.suggested_replacement


@pytest.mark.asyncio
async def test_simplify_skips_eager_call_default_in_dict_get():
    """if k in d: v = d[k] else: v = expensive() must NOT rewrite to d.get(k, expensive())."""
    src = (
        "def f(d, k):\n"
        "    if k in d:\n"
        "        v = d[k]\n"
        "    else:\n"
        "        v = expensive_call()\n"
        "    return v\n"
    )
    async def fetch(_p):
        return src
    findings = await check_simplify(_diff_for("a.py", src), {"fetch_file": fetch})
    # May still match ternary (which IS lazy!), must NEVER emit .get(..., expensive_call())
    for f in findings:
        assert ".get(" not in (f.remediation.text if f.remediation else "")


def test_multiline_comment_skipped_when_start_line_outside_diff():
    """G5 guard: GitHub rejects a multi-line review comment if start_line is outside diff_lines."""
    finding = finalize([
        _f(
            rule_id="SQG009",
            category="complexity",
            confidence=Confidence.MEDIUM,
            block_eligible=False,
            file_path="app.py",
            line_start=5,
            line_end=8,
            remediation=Remediation(
                kind=REMEDIATION_PATCH,
                text="Replace",
                suggested_replacement="x = a if c else b",
                basis="AST",
            ),
        )
    ])[0]
    # Only end_line (8) is in diff_lines; start_line (5) is NOT -> must skip!
    comments = build_review_comments([finding], diff_lines={("app.py", 8)})
    assert comments == []


def test_read_zip_caps_oversized_gitignore_prepass():
    """G4 guard: an oversized .gitignore inside a zip must not OOM the ignore pre-pass."""
    buf = io.BytesIO()
    giant_ignore = ("*.tmp\n" * ((MAX_FILE_BYTES // 6) + 1000))
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("repo/.gitignore", giant_ignore)
        zf.writestr("repo/app.py", "x = 1\n")

    result = read_zip(buf.getvalue())
    assert "app.py" in result.files
    assert any(".gitignore" in s for s in result.skipped)


@pytest.mark.asyncio
async def test_run_scan_returns_unverified_verdict_when_analyzer_errors(monkeypatch):
    """P1 guard: whole-repo scan exposes Verdict.UNVERIFIED when an analyzer crashes."""
    from app import scan as scan_mod

    async def boom(_diff, _ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_mod, "check_sast", boom)
    res = await scan_mod.run_scan({"app.py": "x = 1\n"})
    assert res["verdict"] == "UNVERIFIED"
    assert res["analytics"]["verdict"] == "UNVERIFIED"
