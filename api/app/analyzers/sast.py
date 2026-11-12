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
from .textctx import comment_start, inside_block_comment, inside_string_literal, lang_for

RULE_ID = "SQG006"

_DOC_EXTENSIONS = (".md", ".markdown", ".rst", ".txt")
_ALLOWLIST = ("# nosec", "// nosec", "# noqa", "# type: ignore")

_PY_EXT = (".py",)
_JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

# Weakness class per pattern label. These are statements of fact about what the pattern
# detects — a `shell=True` subprocess call *is* CWE-78 by definition — not a guess about
# exploitability, which is why the finding stays advisory while the CWE is asserted.
# Each id links to cwe.mitre.org so a reader can check the classification themselves.
_CWE_BY_LABEL = {
    "use of eval()": ["CWE-95"],            # eval injection
    "use of exec()": ["CWE-95"],
    "os.system() call": ["CWE-78"],         # OS command injection
    "subprocess with shell=True": ["CWE-78"],
    "child_process exec()": ["CWE-78"],
    "insecure deserialization (pickle)": ["CWE-502"],
    "unsafe yaml.load()": ["CWE-502"],
    "weak hash (md5/sha1)": ["CWE-327", "CWE-328"],
    "React dangerouslySetInnerHTML": ["CWE-79"],   # cross-site scripting
    "innerHTML assignment": ["CWE-79"],
    "document.write()": ["CWE-79"],
}


def _cwe_for(label: str) -> list:
    return list(_CWE_BY_LABEL.get(label, []))

# (label, confidence, compiled pattern). First match per line wins.
_PY_PATTERNS: list[tuple[str, Confidence, re.Pattern]] = [
    # `(?<![.\w])` keeps these to the BUILTINS — `eval(`/`exec(` — and off method
    # calls like `model.eval()` / `df.exec()`, which are not the dangerous sink.
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("use of exec()", Confidence.HIGH, re.compile(r"(?<![.\w])exec\s*\(")),
    ("os.system() call", Confidence.HIGH, re.compile(r"\bos\.system\s*\(")),
    (
        "subprocess with shell=True",
        Confidence.HIGH,
        # Anchored to an actual subprocess.*( call, not any kwarg ending in
        # "shell=True" (e.g. custom_shell=True). Non-greedy so a nested call as
        # an argument (subprocess.run(shlex.split(cmd), shell=True)) still matches.
        re.compile(r"\bsubprocess\.\w+\(.*?\bshell\s*=\s*True\b"),
    ),
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

# `const { exec } = require('child_process')` — after this, a bare `exec(cmd)` call
# is the same sink as `child_process.exec(cmd)`, just not qualified. Detected as a
# supplementary per-file pattern (see _destructured_exec_pattern) once this import
# is seen anywhere in the file's added lines.
_JS_DESTRUCTURED_IMPORT = re.compile(
    r"""\{\s*[^}]*\b(exec|execSync)\b[^}]*\}\s*=\s*require\(\s*['"]child_process['"]\s*\)"""
)


def _destructured_exec_names(added: list[tuple[int, str]]) -> set[str]:
    """Names (exec/execSync) destructured from require('child_process') anywhere
    in this file's added lines."""
    names: set[str] = set()
    for _, content in added:
        m = _JS_DESTRUCTURED_IMPORT.search(content)
        if m:
            names.add(m.group(1))
    return names


def _patterns_for(path: str):
    low = path.lower()
    if low.endswith(_DOC_EXTENSIONS):
        return None
    if low.endswith(_PY_EXT):
        return _PY_PATTERNS
    if low.endswith(_JS_EXT):
        return _JS_PATTERNS
    return None


# How many subsequent added lines a yaml.load() call may look ahead for
# `Loader=yaml.SafeLoader` before being treated as unsafe — covers the common
# multi-line call style (`yaml.load(\n    f, Loader=yaml.SafeLoader\n)`).
_SAFELOADER_LOOKAHEAD = 3


def _safeloader_follows(added: list[tuple[int, str]], idx: int) -> bool:
    for _, content in added[idx + 1:idx + 1 + _SAFELOADER_LOOKAHEAD]:
        if "SafeLoader" in content:
            return True
    return False


async def check_sast(diff: str, repo_context: dict) -> List[Finding]:
    """Flag dangerous-API sinks on added lines (advisory, language-gated)."""
    findings: List[Finding] = []

    by_file: dict[str, List[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        by_file.setdefault(path, []).append((line, content))

    for path, added in by_file.items():
        patterns = _patterns_for(path)
        if patterns is None:
            continue
        lang = lang_for(path)
        destructured = _destructured_exec_names(added) if patterns is _JS_PATTERNS else set()

        for idx, (line, content) in enumerate(added):
            if any(token in content for token in _ALLOWLIST):
                continue
            # Skip comment lines — a sink mentioned in prose (e.g. "# … without shell=True")
            # is documentation, not a call site. Inline trailing comments on real code lines
            # (which don't start with a marker) still fire.
            stripped = content.lstrip()
            if stripped.startswith(("#", "//", "*")):
                continue  # "*" = a JSDoc-style continuation line of an assumed-open block comment
            if stripped.startswith("/*"):
                end = content.find("*/")
                # No closing marker on this line (comment continues past it), or
                # nothing but whitespace after the closing marker → the whole
                # line is comment. If real code follows the close, fall through
                # to full matching — inside_block_comment protects just the span.
                if end == -1 or not content[end + 2:].strip():
                    continue
            cstart = comment_start(content, lang)

            matched_line = False
            for label, confidence, pattern in patterns:
                m = pattern.search(content)
                if not m:
                    continue
                # A sink inside a string literal ("...eval()..."), after an inline
                # trailing comment (`x = 1  # eval(y)`), or inside a self-contained
                # one-line /* ... */ block comment is prose, not a call site — skip.
                if (
                    inside_string_literal(content, m.start(), lang)
                    or (cstart != -1 and m.start() > cstart)
                    or inside_block_comment(content, m.start(), lang)
                ):
                    continue
                if label == "unsafe yaml.load()" and _safeloader_follows(added, idx):
                    continue  # SafeLoader arrives a couple lines later — a safe multi-line call
                if label == "weak hash (md5/sha1)" and "usedforsecurity=False" in content:
                    # hashlib's own flag says this hash protects nothing (git blob
                    # hashing, cache keys) — scan #20 finding 9 flagged exactly that
                    # shape. Same line only: a multi-line call with the flag out of
                    # sight still surfaces (fails safe toward keep-the-finding).
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
                        cwe=_cwe_for(label),
                    )
                )
                matched_line = True
                break  # one finding per line

            if matched_line or not destructured:
                continue

            # A bare exec(...)/execSync(...) call after `const { exec } =
            # require('child_process')` is the same sink as the qualified form.
            bare = re.search(
                r"(?<![.\w])(" + "|".join(re.escape(n) for n in destructured) + r")\s*\(",
                content,
            )
            if not bare:
                continue
            if (
                inside_string_literal(content, bare.start(), lang)
                or (cstart != -1 and bare.start() > cstart)
                or inside_block_comment(content, bare.start(), lang)
            ):
                continue
            findings.append(
                Finding(
                    category="sast",
                    confidence=Confidence.HIGH,
                    block_eligible=False,
                    file_path=path,
                    line_start=line,
                    line_end=line,
                    message=f"child_process exec() (destructured import) at line {line}: '{content.strip()[:80]}'",
                    evidence=Evidence(snippet=content.strip()),
                    tool="regex",
                    rule_id=RULE_ID,
                )
            )
    return findings
