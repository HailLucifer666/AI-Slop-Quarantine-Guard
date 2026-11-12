"""SQG006 SAST: flags dangerous sinks on added lines, advisory-only, language-gated."""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.sast import check_sast


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


# --- positive: dangerous sinks flagged -------------------------------------

@pytest.mark.asyncio
async def test_python_eval_flagged_high():
    findings = await check_sast(_diff("app.py", ["    result = eval(user_input)"]), {})
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG006"
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "eval" in f.message


@pytest.mark.asyncio
async def test_shell_true_flagged():
    findings = await check_sast(_diff("run.py", ["    subprocess.run(cmd, shell=True)"]), {})
    assert len(findings) == 1
    assert "shell=True" in findings[0].message


@pytest.mark.asyncio
async def test_shell_true_with_nested_call_still_flagged():
    findings = await check_sast(
        _diff("run.py", ["subprocess.run(shlex.split(cmd), shell=True)"]), {}
    )
    assert len(findings) == 1
    assert "shell=True" in findings[0].message


@pytest.mark.asyncio
async def test_custom_shell_kwarg_not_flagged():
    # An unrelated kwarg that happens to end in "shell=True" is not a subprocess call.
    findings = await check_sast(_diff("run.py", ["result = do_thing(custom_shell=True)"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_multiline_safe_yaml_load_not_flagged():
    findings = await check_sast(
        _diff("y.py", ["data = yaml.load(", "    f, Loader=yaml.SafeLoader", ")"]), {}
    )
    assert findings == []


@pytest.mark.asyncio
async def test_destructured_child_process_exec_flagged():
    findings = await check_sast(
        _diff("run.js", ["const { exec } = require('child_process')", "exec(userCmd)"]), {}
    )
    assert len(findings) == 1
    assert findings[0].line_start == 2
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_bare_exec_without_destructured_import_not_flagged():
    # A bare exec() with no child_process destructuring anywhere in the file is not
    # this sink (could be any other function named exec).
    findings = await check_sast(_diff("run.js", ["exec(userCmd)"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_weak_hash_flagged_medium():
    findings = await check_sast(_diff("h.py", ["    d = hashlib.md5(data).hexdigest()"]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.MEDIUM


@pytest.mark.asyncio
async def test_js_child_process_exec_flagged():
    findings = await check_sast(_diff("server.js", ["child_process.exec(userCmd)"]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_react_dangerous_html_flagged():
    findings = await check_sast(_diff("c.tsx", ["  <div dangerouslySetInnerHTML={{__html: x}} />"]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.MEDIUM


# --- low-noise controls ----------------------------------------------------

@pytest.mark.asyncio
async def test_clean_code_silent():
    findings = await check_sast(_diff("math.py", ["def add(a, b):", "    return a + b"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_literal_eval_not_flagged():
    # ast.literal_eval is safe; the \beval boundary must not match "_eval".
    findings = await check_sast(_diff("safe.py", ["    v = ast.literal_eval(s)"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_safe_yaml_load_not_flagged():
    findings = await check_sast(_diff("y.py", ["    cfg = yaml.load(f, Loader=yaml.SafeLoader)"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_nosec_suppressed():
    findings = await check_sast(_diff("app.py", ["    eval(x)  # nosec"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_python_pattern_not_applied_to_markdown():
    findings = await check_sast(_diff("README.md", ["Call eval(x) to run it."]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_one_finding_per_line():
    findings = await check_sast(_diff("a.py", ["    eval(exec(x))"]), {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_innerhtml_assignment_flagged():
    findings = await check_sast(_diff("ui.js", ["  el.innerHTML = userInput"]), {})
    assert len(findings) == 1
    assert "innerHTML" in findings[0].message


@pytest.mark.asyncio
async def test_innerhtml_comparison_not_flagged():
    # `===` is a comparison, not an assignment — the `=(?!=)` guard must not match it.
    findings = await check_sast(_diff("ui.js", ['  if (el.innerHTML === "") return']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_method_eval_not_flagged():
    # `.eval()` is a method call (e.g. PyTorch model.eval()), NOT the builtin eval sink —
    # the `(?<![.\w])` lookbehind must keep it off these.
    findings = await check_sast(_diff("m.py", ["    model.eval()", "    _MODEL.eval()"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_sink_named_in_comment_not_flagged():
    # A sink mentioned in a comment is documentation, not a call site.
    findings = await check_sast(_diff("t.py", [
        "    # rewritten to use shutil.which() without shell=True",
        "    # eval(x) would be dangerous here; we avoid it",
    ]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_sink_inside_string_literal_not_flagged():
    # `eval()` and `shell=True` quoted as string content are prose, not call sites.
    for line in ('tip = "Use eval() carefully"', 'docs = "Set shell=True to enable"'):
        findings = await check_sast(_diff("app.py", [f"    {line}"]), {})
        assert findings == [], line


@pytest.mark.asyncio
async def test_sink_in_inline_trailing_comment_not_flagged():
    # A real code line whose only sink mention sits in its trailing comment must not fire.
    findings = await check_sast(_diff("app.py", ["    x = 1  # eval(user_input) would be unsafe"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_sink_in_code_with_trailing_comment_still_flagged():
    # The inline-comment guard must not blind us to a real sink before the comment.
    findings = await check_sast(_diff("app.py", ["    eval(user_input)  # FIXME: sanitize first"]), {})
    assert len(findings) == 1
    assert "eval" in findings[0].message


@pytest.mark.asyncio
async def test_sink_inside_mid_line_block_comment_not_flagged():
    # A sink named inside a self-contained /* ... */ block comment that sits in
    # the MIDDLE of a line (real code before and after) is documentation, not a
    # call site — the whole-line "starts with /*" guard alone doesn't catch this.
    findings = await check_sast(_diff("run.js", [
        "doSomething(); /* old approach: eval(userInput) — do not use */ doOther();"
    ]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_sink_after_block_comment_on_same_line_still_flagged():
    findings = await check_sast(_diff("run.js", [
        "/* old note */ eval(userInput);"
    ]), {})
    assert len(findings) == 1
    assert "eval" in findings[0].message


@pytest.mark.asyncio
async def test_unterminated_block_comment_opening_line_not_flagged():
    # This line opens a multi-line /* ... */ that continues past it — still
    # treated as comment (unterminated on this line), not a new false positive.
    findings = await check_sast(_diff("run.js", [
        "/* eval(userInput) is dangerous, this whole block is disabled:"
    ]), {})
    assert findings == []


# --- usedforsecurity=False (scan #20 finding 9: git empty-blob hashing) -------
# Probe (2026-11-13, run and restored): disabling the flag guard reded exactly the
# suppress test while both negative controls stayed green.

@pytest.mark.asyncio
async def test_weak_hash_with_usedforsecurity_false_not_flagged():
    # hashlib's own flag says this hash protects nothing (git blob hashing, cache
    # keys). The flag must be on the SAME line as the call to count.
    diff = _diff("scripts/hash.py", ['digest = hashlib.sha1(b"blob 0", usedforsecurity=False).hexdigest()'])
    assert await check_sast(diff, {}) == []


@pytest.mark.asyncio
async def test_weak_hash_without_flag_still_flagged():
    # Negative control: the guard must not switch the weak-hash rule off.
    diff = _diff("scripts/hash.py", ["digest = hashlib.md5(data).hexdigest()"])
    findings = await check_sast(diff, {})
    assert len(findings) == 1
    assert findings[0].rule_id == "SQG006"


@pytest.mark.asyncio
async def test_usedforsecurity_false_on_another_line_still_flagged():
    # A multi-line call with the flag out of sight still surfaces — the same-line
    # rule fails safe toward keep-the-finding.
    diff = _diff("scripts/hash.py", ["digest = hashlib.sha1(", "    data, usedforsecurity=False,"])
    findings = await check_sast(diff, {})
    assert len(findings) == 1


# --- review hardening (2026-11-13): the flag must belong to the matched call --

@pytest.mark.asyncio
async def test_flag_mention_in_trailing_comment_does_not_suppress():
    # A comment explaining the flag is NOT yet passed is the natural way to write
    # about this code — it must not silence a real unflagged call.
    diff = _diff("scripts/hash.py", ["h = hashlib.sha1(secret).hexdigest()  # TODO: pass usedforsecurity=False here"])
    findings = await check_sast(diff, {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_flag_inside_a_string_literal_does_not_suppress():
    diff = _diff("scripts/hash.py", ['cfg = {"flag": "usedforsecurity=False"}; h = hashlib.sha1(secret).hexdigest()'])
    findings = await check_sast(diff, {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_flagged_sibling_call_does_not_suppress_an_unflagged_one():
    # Compound line: the md5 call carries its own flag; the sha1 call does not.
    # Suppressing per-call must still surface the sha1 (one finding per line holds).
    diff = _diff("scripts/hash.py", ["a = hashlib.md5(k, usedforsecurity=False).digest(); b = hashlib.sha1(secret).hexdigest()"])
    findings = await check_sast(diff, {})
    assert len(findings) == 1
    assert "sha1" in findings[0].message
