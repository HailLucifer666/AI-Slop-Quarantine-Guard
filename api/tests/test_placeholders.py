"""SQG003 placeholder scanner: catches stubs on added lines, advisory-only, low noise."""

import pytest

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
