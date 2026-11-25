"""SQG003 — placeholder / incomplete code detector.

Scans newly added lines for the tells of unfinished or stubbed-out code: TODO markers,
NotImplementedError, ellipsis-only bodies, and "your code here" prose.

Precision controls (calibrated against real-world Scan #24):
* Test/fixture paths (``in_test_path``) are skipped: test runtimes and mocks
  intentionally contain ``throw new Error('... not implemented in test runtime')``.
* Kebab-case identifiers and file paths (``todo-dock``, ``todo-progress-reminder.ts``,
  ``followup-todo-nudge.ts``) are excluded by requiring non-identifier/non-hyphen
  boundaries around ``TODO`` and whitespace around a trailing dash (``TODO - fix``).
* JSDoc API-documentation prose (``* Implement this interface to create...``) is
  excluded from ``placeholder prose``.
* When full file source + Tree-sitter are available, comment-based markers are matched
  against actual comment AST nodes (immune to multi-line strings/template literals).
* Mode awareness (``repo_context["mode"] == "repo"``): in whole-repo scans, attributed
  backlog TODOs (``TODO(owner): ...``) are skipped as normal engineering backlog, while
  PR diffs continue to flag every newly added TODO marker.

Advisory only: every finding is MEDIUM confidence and never block-eligible.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from app.diff import parse_diff

from .ast_ctx import HAS_TREE_SITTER, parse_file_ast, ts_lang_for
from .base import Confidence, Evidence, Finding
from .paths import in_test_path
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

# Attributed backlog TODO, e.g. `// TODO(James): Reenable when...` — normal engineering
# backlog in a mature repository, skipped in whole-repo mode (still flagged in PR diffs).
_ATTRIBUTED_TODO = re.compile(r"(?<![\w/\-.])TODO\s*\([^)]+\)", re.IGNORECASE)

# JSDoc/docstring API documentation describing how callers should implement an
# interface/class/method — documentation, not an unfinished stub.
_JSDOC_IMPLEMENT_DOC = re.compile(
    r"^\s*(?:/\*\*|\*)\s*implement\s+this\s+"
    r"(?:interface|class|method|function|trait|protocol|type|abstract|hook|handler|renderer|plugin|provider|adapter)\b",
    re.IGNORECASE,
)

# (label, pattern). First match per line wins; order = priority.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "TODO/FIXME marker",
        # TODO flags only in its marker forms — colon (`TODO:`), spaced dash (`TODO - fix`),
        # paren-attributed (`TODO(owner):`), @-prefixed (`@todo`), or bare at end of line.
        # Strict left/right boundaries `(?<![\w/\-.])` and `(?![\w/\-.])` prevent matching
        # kebab-case identifiers or filenames like `todo-dock`, `todo-progress-reminder.ts`,
        # or `followup-todo-nudge.ts`.
        # XXX excludes a following "-<digit-or-X>" — that shape is a ticket-ID prefix
        # (XXX-1234) or a masked value (XXX-XX-XXXX), not a placeholder marker.
        re.compile(
            r"@TODO\b"
            r"|(?<![\w/\-.])TODO(?![\w/\-.])(?:\s*\([^)]*\))?(?:\s*:|\s+-\s+|\s*$)"
            r"|\b(?:FIXME|HACK)\b"
            r"|(?<![\w./-])XXX(?![\w./-])",
            re.IGNORECASE,
        ),
    ),
    (
        "not-implemented stub",
        # Only a genuine empty stub / explicit admission — NOT every NotImplementedError.
        re.compile(
            r"^\s*raise\s+NotImplementedError\s*(?:\(\s*\))?\s*$"
            r"|throw new Error\(\s*['\"][^'\"]*not implemented"
            r"|#\s*not implemented",
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


def _comment_lines_from_ast(path: str, source: str, ast_cache) -> Optional[Tuple[Set[int], Set[int]]]:
    """Return (all_comment_lines, jsdoc_lines) from Tree-sitter, or None if unavailable."""
    if not HAS_TREE_SITTER or ts_lang_for(path) is None:
        return None
    file_ast = parse_file_ast(path, source, ast_cache=ast_cache)
    if file_ast is None:
        return None
    comment_lines: Set[int] = set()
    jsdoc_lines: Set[int] = set()
    for c in file_ast.comment_nodes():
        for ln in range(c.line_start, c.line_end + 1):
            comment_lines.add(ln)
            if c.is_jsdoc:
                jsdoc_lines.add(ln)
    return comment_lines, jsdoc_lines


async def check_placeholders(diff: str, repo_context: dict) -> List[Finding]:
    """Flag placeholder/incomplete-code tells on added lines (advisory)."""
    findings: List[Finding] = []
    repo_mode = repo_context.get("mode") == "repo"
    files_map: Optional[Dict[str, str]] = repo_context.get("files")
    ast_cache = repo_context.get("ast_cache")

    by_file: Optional[Dict[str, List[Tuple[int, str]]]] = repo_context.get("added_by_file")
    if by_file is None:
        by_file = {}
        for path, line, content in parse_diff(diff):
            by_file.setdefault(path, []).append((line, content))

    for path, added in by_file.items():
        if not _is_code_file(path) or in_test_path(path):
            continue
        lang = lang_for(path)
        source = files_map.get(path) if isinstance(files_map, dict) else None
        ast_comments = _comment_lines_from_ast(path, source, ast_cache) if source is not None else None
        comment_lines = ast_comments[0] if ast_comments is not None else None
        jsdoc_lines = ast_comments[1] if ast_comments is not None else set()

        for line, content in added:
            if any(token in content for token in _ALLOWLIST):
                continue
            if len(content) > 500 and (sum(1 for ch in content if ch.isspace()) / len(content)) < 0.10:
                continue  # minified/bundled line (e.g. installHook.js) — not user source
            for label, pattern in _PATTERNS:
                m = pattern.search(content)
                if not m:
                    continue
                if inside_string_literal(content, m.start(), lang):
                    continue
                # Comment-only patterns: when AST comment spans are known, require the
                # match to live on an actual comment line (eliminates multi-line string
                # and template-literal false positives).
                if label in ("TODO/FIXME marker", "placeholder prose") and comment_lines is not None:
                    if line not in comment_lines:
                        continue
                # Skip JSDoc API-doc prose (`* Implement this interface...`).
                if label == "placeholder prose" and (
                    line in jsdoc_lines or _JSDOC_IMPLEMENT_DOC.match(content)
                ):
                    continue
                # Whole-repo mode: attributed `TODO(owner):` is normal engineering backlog,
                # not an unreviewed AI stub. PR diffs still flag newly added TODO(owner):.
                if repo_mode and label == "TODO/FIXME marker" and _ATTRIBUTED_TODO.search(content):
                    continue
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
                        tool="ast" if comment_lines is not None else "regex",
                        rule_id=RULE_ID,
                    )
                )
                break  # one finding per line
    return findings
