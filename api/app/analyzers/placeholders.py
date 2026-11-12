"""SQG003 — placeholder / incomplete code detector (Phase 3, regex MVP).

Scans newly added lines for the tells of unfinished or stubbed-out code: TODO markers,
NotImplementedError, ellipsis-only bodies, and "your code here" prose.

Advisory only: every finding is MEDIUM confidence and never block-eligible — a
TODO can be perfectly intentional. The job is to surface, not to gate. AST-aware
detection (empty function bodies) is deferred to a later phase; this is regex.
"""

import re
from typing import List

from app.diff import parse_diff

from .base import Confidence, Evidence, Finding
from .textctx import inside_string_literal, lang_for

RULE_ID = "SQG003"

# Files where these patterns are noise rather than signal.
_DOC_EXTENSIONS = (".md", ".markdown", ".rst", ".txt")

# Ignore/attribute files hold glob patterns, not code — `*TODO*` in .gitignore is a
# file pattern, not a TODO marker. Skip them by basename.
_IGNORE_FILES = (
    ".gitignore", ".dockerignore", ".npmignore", ".eslintignore",
    ".prettierignore", ".gitattributes", ".npmrc",
)

# A line carrying one of these is a deliberate annotation, not a placeholder.
_ALLOWLIST = ("# noqa", "# type: ignore", "# pragma: no cover")

# (label, pattern). First match per line wins; order = priority.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "TODO/FIXME marker",
        # TODO flags only in its marker forms — colon, dash, paren-attributed,
        # @-prefixed, or bare at end of line — so prose that merely mentions the
        # word ("there is still todo work") is not a stub. The other two marker
        # arms keep their bare-word behavior: lowercase "fixme later" is pinned as
        # a real signal. XXX excludes a following "-<digit-or-X>" — that shape is
        # a ticket-ID prefix (XXX-1234) or a masked value (XXX-XX-XXXX), not a
        # placeholder marker.
        re.compile(
            r"@TODO\b|\bTODO\b\s*(?:\([^)]*\)\s*)?(?:[:\-]|$)"
            r"|\b(?:FIXME|HACK)\b|\bXXX\b(?!-[\dXx])",
            re.IGNORECASE,
        ),
    ),
    (
        "not-implemented stub",
        # Only a genuine empty stub / explicit admission — NOT every NotImplementedError.
        # A class def, or `throw new NotImplementedError(msg)` signalling an unsupported
        # operation, is complete, intentional code, so the bare symbol is no longer matched.
        re.compile(
            r"^\s*raise\s+NotImplementedError\s*(?:\(\s*\))?\s*$"  # bare Python stub, no message
            r"|throw new Error\(\s*['\"][^'\"]*not implemented"     # JS 'not implemented' error literal
            r"|#\s*not implemented",                               # explicit comment admission
            re.IGNORECASE,
        ),
    ),
    ("ellipsis-only body", re.compile(r"^\s*\.\.\.\s*$")),
    (
        "placeholder prose",
        re.compile(
            r"\b(your code here|rest of (?:the )?code(?: here)?|"
            r"implement (?:this|here)|fill in (?:the )?(?:rest|implementation)|"
            r"add your .+ here)\b",
            re.IGNORECASE,
        ),
    ),
]


def _is_code_file(path: str) -> bool:
    low = path.lower()
    base = low.replace("\\", "/").rsplit("/", 1)[-1]
    if base in _IGNORE_FILES:
        return False
    return not low.endswith(_DOC_EXTENSIONS)


async def check_placeholders(diff: str, repo_context: dict) -> List[Finding]:
    """Flag placeholder/incomplete-code tells on added lines (advisory)."""
    findings: List[Finding] = []
    for path, line, content in parse_diff(diff):
        if not _is_code_file(path):
            continue
        if any(token in content for token in _ALLOWLIST):
            continue
        lang = lang_for(path)
        for label, pattern in _PATTERNS:
            m = pattern.search(content)
            # Skip a marker that lives inside a string literal — it's data, not a
            # stub (e.g. `msg = "TODO: ..."`). Comments stay flagged: a TODO comment
            # is the intended SQG003 signal, so we guard on strings only.
            if m and not inside_string_literal(content, m.start(), lang):
                findings.append(
                    Finding(
                        category="placeholder",
                        confidence=Confidence.MEDIUM,
                        block_eligible=False,
                        file_path=path,
                        line_start=line,
                        line_end=line,
                        message=f"{label} at line {line}: '{content.strip()[:80]}'",
                        evidence=Evidence(snippet=content.strip()),
                        tool="regex",
                        rule_id=RULE_ID,
                    )
                )
                break  # one finding per line
    return findings
