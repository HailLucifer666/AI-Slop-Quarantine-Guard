"""SQG006 — AST-backed SAST: dangerous-API sink detector.

Uses Tree-sitter syntax trees (via ``ast_ctx``) for Python, JavaScript, TypeScript, and
TSX when full file source is available — and falls back cleanly to lexically-guarded
line scanning for diff-only fragments or when Tree-sitter is unavailable.

Why AST-backed:
* Eliminates entire classes of regex false positives: interface method signatures
  (``interface Redis { eval(...): Promise }``), method definitions
  (``async eval(script, numKeys) {``), Python ``def eval(self):``, multi-line block
  comments, docstrings, and multi-line template literals.
* Tracks both CommonJS ``require('child_process')`` AND ESM
  ``import { exec, execSync } from 'child_process' | 'node:child_process'`` (including
  aliased imports), always attaching ``CWE-78``.
* Skips test/fixture paths (``in_test_path``) for test-harness ``eval()``/``exec()`` and
  weak-hash noise so intentional compatibility/unit tests don't flood the report.

Advisory only: SAST findings are HIGH or MEDIUM and never block-eligible.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from app.diff import parse_diff

from .ast_ctx import HAS_TREE_SITTER, FileAst, parse_file_ast, ts_lang_for
from .base import Confidence, Evidence, Finding
from .paths import in_test_path
from .textctx import comment_start, inside_block_comment, inside_string_literal, lang_for

RULE_ID = "SQG006"

_DOC_EXTENSIONS = (".md", ".markdown", ".rst", ".txt")
_ALLOWLIST = ("# nosec", "// nosec", "# noqa", "# type: ignore")

_PY_EXT = (".py",)
_JS_EXT = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")

_WEAK_HASH_LABEL = "weak hash (md5/sha1)"

_CWE_BY_LABEL = {
    "use of eval()": ["CWE-95"],
    "use of exec()": ["CWE-95"],
    "os.system() call": ["CWE-78"],
    "subprocess with shell=True": ["CWE-78"],
    "child_process exec()": ["CWE-78"],
    "child_process exec() (destructured import)": ["CWE-78"],
    "insecure deserialization (pickle)": ["CWE-502"],
    "unsafe yaml.load()": ["CWE-502"],
    _WEAK_HASH_LABEL: ["CWE-327", "CWE-328"],
    "React dangerouslySetInnerHTML": ["CWE-79"],
    "innerHTML assignment": ["CWE-79"],
    "document.write()": ["CWE-79"],
}

# Labels skipped inside test/fixture/eval paths (intentional dynamic eval tests,
# test-harness shell helpers, hash fixtures).
_TEST_SKIP_LABELS = frozenset({
    "use of eval()",
    "use of exec()",
    "child_process exec()",
    "child_process exec() (destructured import)",
    _WEAK_HASH_LABEL,
})


def _cwe_for(label: str) -> list:
    return list(_CWE_BY_LABEL.get(label, []))


# Fallback regex patterns (used only when full source / Tree-sitter is unavailable).
_PY_PATTERNS: list[tuple[str, Confidence, re.Pattern]] = [
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("use of exec()", Confidence.HIGH, re.compile(r"(?<![.\w])exec\s*\(")),
    ("os.system() call", Confidence.HIGH, re.compile(r"\bos\.system\s*\(")),
    ("subprocess with shell=True", Confidence.HIGH, re.compile(r"\bsubprocess\.\w+\(.*?\bshell\s*=\s*True\b")),
    ("insecure deserialization (pickle)", Confidence.MEDIUM, re.compile(r"\bpickle\.loads?\s*\(")),
    ("unsafe yaml.load()", Confidence.MEDIUM, re.compile(r"\byaml\.load\s*\((?!.*SafeLoader)")),
    (_WEAK_HASH_LABEL, Confidence.MEDIUM, re.compile(r"\bhashlib\.(?:md5|sha1)\s*\(")),
]

_JS_PATTERNS: list[tuple[str, Confidence, re.Pattern]] = [
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("child_process exec()", Confidence.HIGH, re.compile(r"child_process\.exec(?:Sync)?\s*\(")),
    ("React dangerouslySetInnerHTML", Confidence.MEDIUM, re.compile(r"dangerouslySetInnerHTML")),
    ("innerHTML assignment", Confidence.MEDIUM, re.compile(r"\.innerHTML\s*=(?!=)")),
    ("document.write()", Confidence.MEDIUM, re.compile(r"document\.write\s*\(")),
]

# CJS require OR ESM import of exec/execSync from child_process / node:child_process.
_JS_DESTRUCTURED_IMPORT = re.compile(
    r"""(?:\{\s*[^}]*\b(exec|execSync)\b[^}]*\}\s*=\s*require\(\s*['"](?:node:)?child_process['"]\s*\))"""
    r"""|(?:import\s*\{[^}]*\b(exec|execSync)\b[^}]*\}\s*from\s*['"](?:node:)?child_process['"])"""
)

# Guard for regex fallback: method definitions like `async eval(...) {` or `def eval(...):`.
_METHOD_DEF_PREFIX = re.compile(r"^\s*(?:async\s+|public\s+|private\s+|protected\s+|static\s+|def\s+)+(?:eval|exec)\s*\(")

_SAFELOADER_LOOKAHEAD = 3


def _flag_suppresses(content: str, m: re.Match, cstart: int, lang: str) -> bool:
    code_end = cstart if cstart != -1 else len(content)
    idx = content.find("usedforsecurity=False", 0, code_end)
    while idx != -1:
        if idx >= m.start() and not inside_string_literal(content, idx, lang):
            return True
        idx = content.find("usedforsecurity=False", idx + 1)
    return False


def _destructured_exec_names(added: list[tuple[int, str]]) -> set[str]:
    names: set[str] = set()
    for _, content in added:
        for m in _JS_DESTRUCTURED_IMPORT.finditer(content):
            name = m.group(1) or m.group(2)
            if name:
                names.add(name)
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


def _safeloader_follows(added: list[tuple[int, str]], idx: int) -> bool:
    for _, content in added[idx + 1 : idx + 1 + _SAFELOADER_LOOKAHEAD]:
        if "SafeLoader" in content:
            return True
    return False


def _make_finding(
    label: str, confidence: Confidence, path: str, line: int, content: str, tool: str
) -> Finding:
    return Finding(
        category="sast",
        confidence=confidence,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{label} at line {line}: '{content.strip()[:80]}'",
        evidence=Evidence(snippet=content.strip()),
        tool=tool,
        rule_id=RULE_ID,
        cwe=_cwe_for(label),
    )


def _scan_with_ast(
    path: str,
    file_ast: FileAst,
    added_map: Dict[int, str],
    in_test: bool,
) -> List[Finding]:
    """AST-based sink detection over added lines (one finding per line, highest priority first)."""
    findings: List[Finding] = []
    emitted_lines: Set[int] = set()
    is_py = file_ast.lang == "python"
    cp_execs = set() if is_py else file_ast.imported_child_process_execs()

    # 1. Call-expression sinks (eval, exec, os.system, subprocess, pickle, yaml, hashlib,
    #    child_process.exec*, destructured exec*, document.write).
    for call in file_ast.call_sites():
        line = call.line
        if line not in added_map or line in emitted_lines:
            continue
        content = added_map[line]
        if any(token in content for token in _ALLOWLIST):
            continue
        if len(content) > 500 and (sum(1 for ch in content if ch.isspace()) / len(content)) < 0.10:
            continue

        label: Optional[str] = None
        confidence = Confidence.HIGH

        if is_py:
            if call.qualifier is None and call.callee == "eval":
                label = "use of eval()"
            elif call.qualifier is None and call.callee == "exec":
                label = "use of exec()"
            elif call.qualifier == "os" and call.callee == "system":
                label = "os.system() call"
            elif call.qualifier == "subprocess" and call.has_kwarg_shell_true:
                label = "subprocess with shell=True"
            elif call.qualifier == "pickle" and call.callee in ("load", "loads"):
                label, confidence = "insecure deserialization (pickle)", Confidence.MEDIUM
            elif call.qualifier == "yaml" and call.callee == "load" and not call.has_kwarg_safeloader:
                label, confidence = "unsafe yaml.load()", Confidence.MEDIUM
            elif (
                call.qualifier == "hashlib"
                and call.callee in ("md5", "sha1")
                and not call.has_kwarg_usedforsecurity_false
            ):
                label, confidence = _WEAK_HASH_LABEL, Confidence.MEDIUM
        else:
            if call.qualifier is None and call.callee == "eval":
                label = "use of eval()"
            elif call.qualifier == "child_process" and call.callee in ("exec", "execSync"):
                # A constant string literal command (`execSync('git add .', opts)`) has
                # zero dynamic input, so OS command injection (CWE-78) is impossible.
                if not call.first_arg_is_static_string:
                    label = "child_process exec()"
            elif call.qualifier is None and call.callee in cp_execs:
                if not call.first_arg_is_static_string:
                    label = "child_process exec() (destructured import)"
            elif call.qualifier == "document" and call.callee == "write":
                label, confidence = "document.write()", Confidence.MEDIUM

        if label is None:
            continue
        if in_test and label in _TEST_SKIP_LABELS:
            continue
        findings.append(_make_finding(label, confidence, path, line, content, tool="ast"))
        emitted_lines.add(line)

    # 2. DOM-XSS sinks (JSX dangerouslySetInnerHTML, .innerHTML = ...).
    if not is_py:
        for site in file_ast.dom_xss_sites():
            line = site.line
            if line not in added_map or line in emitted_lines:
                continue
            content = added_map[line]
            if any(token in content for token in _ALLOWLIST):
                continue
            findings.append(_make_finding(site.label, Confidence.MEDIUM, path, line, content, tool="ast"))
            emitted_lines.add(line)

    return findings


def _innerhtml_rhs_is_static(line: str, after: int) -> bool:
    """True when everything after ``=`` is string literals and ``+`` (line-local).

    The regex fallback has no syntax tree, so this is a token-level approximation with
    a deliberate bias: a trailing operator means the literal continues on the next line
    — scan #37's constant banner (obra/superpowers) is exactly that shape — so it is
    treated as static. Anything that is not a quoted literal or an operator makes the
    line dynamic and it stays flagged. Quote-aware tokenisation matters: ``'<b>' + x``
    must not read ``x`` as part of a literal.
    """
    rest = line[after:].strip()
    if not rest:
        return False
    tokens = re.findall(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`|\S+", rest)
    for tok in tokens:
        if tok in ("+", "(", ")", ";"):
            continue
        if tok[0] in "'\"":
            continue
        if tok.startswith("`") and "${" not in tok:
            continue
        return False
    return True


def _scan_with_regex(
    path: str,
    added: List[Tuple[int, str]],
    patterns: list[tuple[str, Confidence, re.Pattern]],
    in_test: bool,
) -> List[Finding]:
    """Fallback single-line regex scanner when full file source is not available."""
    findings: List[Finding] = []
    lang = lang_for(path)
    destructured = _destructured_exec_names(added) if patterns is _JS_PATTERNS else set()

    for idx, (line, content) in enumerate(added):
        if any(token in content for token in _ALLOWLIST):
            continue
        stripped = content.lstrip()
        if stripped.startswith(("#", "//", "*")):
            continue
        if stripped.startswith("/*"):
            end = content.find("*/")
            if end == -1 or not content[end + 2 :].strip():
                continue
        cstart = comment_start(content, lang)

        matched_line = False
        for label, confidence, pattern in patterns:
            m = pattern.search(content)
            if not m:
                continue
            if label in ("use of eval()", "use of exec()") and _METHOD_DEF_PREFIX.match(content):
                continue
            if in_test and label in _TEST_SKIP_LABELS:
                continue
            if label == "innerHTML assignment" and _innerhtml_rhs_is_static(content, m.end()):
                continue  # literal markup cannot carry untrusted input
            if (
                inside_string_literal(content, m.start(), lang)
                or (cstart != -1 and m.start() > cstart)
                or inside_block_comment(content, m.start(), lang)
            ):
                continue
            if label == "unsafe yaml.load()" and _safeloader_follows(added, idx):
                continue
            if label == _WEAK_HASH_LABEL:
                emitted = False
                search_from = 0
                while True:
                    wm = pattern.search(content, search_from)
                    if wm is None:
                        break
                    search_from = wm.end()
                    if _flag_suppresses(content, wm, cstart, lang):
                        continue
                    findings.append(_make_finding(label, confidence, path, line, content, tool="regex"))
                    emitted = True
                    break
                if emitted:
                    matched_line = True
                continue
            findings.append(_make_finding(label, confidence, path, line, content, tool="regex"))
            matched_line = True
            break

        if matched_line or not destructured:
            continue

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
            _make_finding(
                "child_process exec() (destructured import)",
                Confidence.HIGH,
                path,
                line,
                content,
                tool="regex",
            )
        )
    return findings


async def check_sast(diff: str, repo_context: dict) -> List[Finding]:
    """Flag dangerous-API sinks on added lines (advisory, AST-backed when source is available)."""
    findings: List[Finding] = []
    files_map: Optional[Dict[str, str]] = repo_context.get("files")
    ast_cache = repo_context.get("ast_cache")

    by_file: Optional[Dict[str, List[Tuple[int, str]]]] = repo_context.get("added_by_file")
    if by_file is None:
        by_file = {}
        for path, line, content in parse_diff(diff):
            by_file.setdefault(path, []).append((line, content))

    for path, added in by_file.items():
        patterns = _patterns_for(path)
        if patterns is None:
            continue
        in_test = in_test_path(path)
        source = files_map.get(path) if isinstance(files_map, dict) else None

        if source is not None and HAS_TREE_SITTER and ts_lang_for(path) is not None:
            file_ast = parse_file_ast(path, source, ast_cache=ast_cache)
            if file_ast is not None:
                added_map = {line: content for line, content in added}
                findings.extend(_scan_with_ast(path, file_ast, added_map, in_test))
                continue

        findings.extend(_scan_with_regex(path, added, patterns, in_test))
    return findings
