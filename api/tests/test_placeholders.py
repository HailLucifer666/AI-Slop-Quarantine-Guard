"""SQG003 placeholder scanner: catches stubs on added lines, advisory-only, low noise."""

from pathlib import Path

import pytest

import app.analyzers.placeholders as _placeholders_module
from app.analyzers.base import Confidence
from app.analyzers.placeholders import check_placeholders


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


@pytest.mark.asyncio
async def test_todo_flagged():
    findings = await check_placeholders(_diff("app/auth.py", ["    # TODO: implement hashing"]), {})
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG003"
    assert f.confidence is Confidence.MEDIUM
    assert f.block_eligible is False
    assert f.line_start == 1


@pytest.mark.asyncio
async def test_lowercase_todo_flagged():
    # Lowercase is just as real a marker as uppercase — must not be silently missed.
    findings = await check_placeholders(_diff("app/auth.py", ["    # todo: implement hashing"]), {})
    assert len(findings) == 1
    assert findings[0].rule_id == "SQG003"


@pytest.mark.asyncio
async def test_prose_todo_without_colon_not_flagged():
    # The word "todo" inside a normal sentence ("there is still todo work") is prose,
    # not a stub marker. Only the marker forms flag — bare-word mention does not.
    # The other marker arms keep their bare-word behavior (pinned by the tests below).
    findings = await check_placeholders(_diff("app/auth.py", ["    # there is still todo work before launch"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_real_marker_forms_besides_colon_still_flagged():
    """KEEPER against recall loss (preflight REV finding): the colon tightening must
    not lose the dash form, the attributed form, or the @-prefixed form — all were
    flagged before the tightening and are real slop markers."""
    forms = [
        "    # TODO - implement rate limiting",
        "    // TODO(marco): fix this",
        "    # @todo refactor this",
        "    # TODO",
    ]
    for form in forms:
        findings = await check_placeholders(_diff("app/auth.py", [form]), {})
        assert len(findings) == 1, form


@pytest.mark.asyncio
async def test_lowercase_fixme_flagged():
    findings = await check_placeholders(_diff("app/auth.py", ["    // fixme later"]), {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_xxx_ticket_id_not_flagged():
    # "XXX-1234" is a ticket-ID prefix (Jira-style), not a placeholder marker.
    findings = await check_placeholders(_diff("app/auth.py", ["    // see XXX-1234 for context"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_xxx_masked_value_not_flagged():
    # Outside a string literal too (the doc's mask format), not just the marker itself.
    findings = await check_placeholders(_diff("app/auth.py", ["    # expected format: XXX-XX-XXXX"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_bare_xxx_marker_still_flagged():
    findings = await check_placeholders(_diff("app/auth.py", ["    # XXX: this is fragile"]), {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_not_implemented_flagged():
    findings = await check_placeholders(_diff("svc.py", ["    raise NotImplementedError"]), {})
    assert len(findings) == 1
    assert "not-implemented" in findings[0].message


@pytest.mark.asyncio
async def test_ellipsis_body_flagged():
    findings = await check_placeholders(_diff("stub.py", ["def f():", "    ..."]), {})
    assert any("ellipsis" in f.message for f in findings)


@pytest.mark.asyncio
async def test_prose_placeholder_flagged():
    findings = await check_placeholders(_diff("x.js", ["// rest of the code here"]), {})
    assert len(findings) == 1


# --- low-noise controls ---------------------------------------------------

@pytest.mark.asyncio
async def test_clean_code_silent():
    findings = await check_placeholders(
        _diff("app/math.py", ["def add(a, b):", "    return a + b"]), {}
    )
    assert findings == []


@pytest.mark.asyncio
async def test_todo_in_markdown_skipped():
    findings = await check_placeholders(_diff("README.md", ["- TODO: write the docs"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_allowlisted_annotations_skipped():
    findings = await check_placeholders(
        _diff("app/x.py", ["import os  # noqa", "x: int = 1  # type: ignore"]), {}
    )
    assert findings == []


@pytest.mark.asyncio
async def test_one_finding_per_line():
    # A line with both a marker and prose yields a single finding, not two.
    findings = await check_placeholders(_diff("x.py", ["# TODO: implement this here"]), {})
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_gitignore_glob_not_flagged():
    # Cat G: `*TODO*` in .gitignore is a file glob, not a TODO marker.
    findings = await check_placeholders(_diff(".gitignore", ["*TODO*", "node_modules/"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_notimplementederror_class_and_signalled_throw_not_flagged():
    # Cat H: a class definition and an intentional `throw new NotImplementedError(msg)`
    # signalling an unsupported operation are complete code, not stubs.
    findings = await check_placeholders(_diff("composio.ts", [
        "class NotImplementedError extends Error {",
        '  throw new NotImplementedError("Composio does not support this adapter")',
    ]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_bare_raise_notimplementederror_still_flagged():
    # A genuine empty stub (no message) is still a real placeholder signal.
    findings = await check_placeholders(_diff("svc.py", ["    raise NotImplementedError"]), {})
    assert len(findings) == 1
    assert "not-implemented" in findings[0].message


@pytest.mark.asyncio
async def test_todo_inside_string_literal_not_flagged():
    # A TODO living inside a string literal is data, not a stub — comments still flag,
    # but string contents must not (the lexical-context guard).
    findings = await check_placeholders(_diff("app/x.py", ['    msg = "TODO: check this later"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_fixme_inside_js_string_not_flagged():
    findings = await check_placeholders(_diff("ui.js", ["  const msg = 'FIXME: handle edge';"]), {})
    assert findings == []


# --- pinned known self-reference advisory ------------------------------------

# The detector's own source names its patterns in prose. Bare XXX in that prose
# cannot be separated from slop XXX by any sound pattern (a prose sentence and
# a stub note have the same shape), and repo-side ignore markers are forbidden
# by the scanner-adapts principle (DECISIONS.md ADR, 2026-11-12). So the self-scan
# of this repo keeps exactly ONE advisory self-reference hit: the regex comment
# that documents what the triple-X lookahead excludes. The scanner flagging its
# own documentation is the scanner proving it works.

def _real_xxx_doc_line() -> str:
    """Read the XXX-lookahead documentation line from the COMMITTED detector file.
    The pin derives from the real artifact, not a copied string — a hand-copied
    string survives comment moves and becomes a false green (preflight REV finding:
    the comment moved twice in this very PR while the copy-pinned test stayed green)."""
    source = Path(_placeholders_module.__file__).read_text(encoding="utf-8")
    hits = [ln for ln in source.splitlines() if "XXX excludes" in ln]
    assert len(hits) == 1, "the triple-X documentation line moved or split — re-derive this pin"
    return hits[0]


@pytest.mark.asyncio
async def test_known_self_reference_advisory_is_pinned():
    """Pins the ONE accepted self-scan advisory: bare XXX in the regex's own
    explanatory comment, read from the real committed file. If this test fails,
    the rule changed or the line split: re-derive the expected count from a real
    rescan and update this pin with its reason — never delete it to make a scan
    look clean."""
    findings = await check_placeholders(_diff("app/analyzers/placeholders.py", [
        _real_xxx_doc_line(),
    ]), {})
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG003"
    assert f.confidence is Confidence.MEDIUM
    assert f.block_eligible is False


@pytest.mark.asyncio
async def test_detector_prose_lines_stay_silent():
    # The detector's other prose lines that name the patterns produce NO findings —
    # quoted words are skipped by the string-literal guard, the docstring's marker
    # word is followed by a noun (not a marker form), and only the triple-X
    # documentation line (pinned above) is a self-reference hit.
    findings = await check_placeholders(_diff("app/analyzers/placeholders.py", [
        '# Case-insensitive: lowercase "todo"/"fixme" comments are just as real a',
        'Scans newly added lines for the tells of unfinished or stubbed-out code: TODO markers,',
        '# file pattern, not a TODO marker. Skip them by basename.',
        'a TODO can be perfectly intentional. The job is to surface, not to gate. AST-aware',
    ]), {})
    assert findings == []
