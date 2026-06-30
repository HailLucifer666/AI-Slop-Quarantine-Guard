"""SQG006 — lightweight SAST: dangerous-API sink detector (Phase 3, regex MVP).

A curated, high-signal pattern set over added lines — a mini-Bandit, not a full
Semgrep. Each pattern targets a P0/P1 sink that is almost always worth a human
glance: code execution, command injection, insecure deserialization, weak
crypto, DOM-XSS sinks.

Advisory only: SAST findings are HIGH or MEDIUM and never block-eligible. Static
sink detection has irreducible false positives (an ``eval`` on a literal, an
md5 used for a cache key), so we surface and explain — we never gate.

Patterns are language-gated by file extension to cut noise, doc files skipped,
and ``# nosec`` / ``# noqa`` honoured as deliberate suppressions. A real Semgrep
ruleset (subprocess + curated rules) is the backlog upgrade; this ships today
with zero external binaries.
"""

import re
from typing import List

from app.diff import parse_diff

from .base import Confidence, Evidence, Finding
from .textctx import comment_start, inside_string_literal, lang_for

RULE_ID = "SQG006"

_DOC_EXTENSIONS = (".md", ".markdown", ".rst", ".txt")
_ALLOWLIST = ("# nosec", "// nosec", "# noqa", "# type: ignore")

_PY_EXT = (".py",)
_JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

# (label, confidence, compiled pattern). First match per line wins.
_PY_PATTERNS: list[tuple[str, Confidence, re.Pattern]] = [
    # `(?<![.\w])` keeps these to the BUILTINS — `eval(`/`exec(` — and off method
    # calls like `model.eval()` / `df.exec()`, which are not the dangerous sink.
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("use of exec()", Confidence.HIGH, re.compile(r"(?<![.\w])exec\s*\(")),
    ("os.system() call", Confidence.HIGH, re.compile(r"\bos\.system\s*\(")),
    ("subprocess with shell=True", Confidence.HIGH, re.compile(r"shell\s*=\s*True")),
    ("insecure deserialization (pickle)", Confidence.MEDIUM, re.compile(r"\bpickle\.loads?\s*\(")),
    ("unsafe yaml.load()", Confidence.MEDIUM, re.compile(r"\byaml\.load\s*\((?!.*SafeLoader)")),
    ("weak hash (md5/sha1)", Confidence.MEDIUM, re.compile(r"\bhashlib\.(?:md5|sha1)\s*\(")),
]

_JS_PATTERNS: list[tuple[str, Confidence, re.Pattern]] = [
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("child_process exec()", Confidence.HIGH, re.compile(r"child_process\.exec(?:Sync)?\s*\(")),
    ("React dangerouslySetInnerHTML", Confidence.MEDIUM, re.compile(r"dangerouslySetInnerHTML")),
    ("innerHTML assignment", Confidence.MEDIUM, re.compile(r"\.innerHTML\s*=(?!=)")),
    ("document.write()", Confidence.MEDIUM, re.compile(r"document\.write\s*\(")),
]


def _patterns_for(path: str):
    low = path.lower()
    if low.endswith(_DOC_EXTENSIONS):
        return None
    if low.endswith(_PY_EXT):
        return _PY_PATTERNS
    if low.endswith(_JS_EXT):
        return _JS_PATTERNS
    return None


async def check_sast(diff: str, repo_context: dict) -> List[Finding]:
    """Flag dangerous-API sinks on added lines (advisory, language-gated)."""
    findings: List[Finding] = []
    for path, line, content in parse_diff(diff):
        patterns = _patterns_for(path)
        if patterns is None:
            continue
        if any(token in content for token in _ALLOWLIST):
            continue
        # Skip comment lines — a sink mentioned in prose (e.g. "# … without shell=True")
        # is documentation, not a call site. Inline trailing comments on real code lines
        # (which don't start with a marker) still fire.
        if content.lstrip().startswith(("#", "//", "/*", "*")):
            continue
        lang = lang_for(path)
        cstart = comment_start(content, lang)
        for label, confidence, pattern in patterns:
            m = pattern.search(content)
            if not m:
                continue
            # A sink inside a string literal ("...eval()...") or after an inline
            # trailing comment (`x = 1  # eval(y)`) is prose, not a call site — skip.
            if inside_string_literal(content, m.start(), lang) or (
                cstart != -1 and m.start() > cstart
            ):
                continue
            findings.append(
                Finding(
                    category="sast",
                    confidence=confidence,
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
