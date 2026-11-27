"""Tree-sitter AST context for Python, JavaScript, and TypeScript analyzers.

Replaces fragile single-line regex guessing with real syntax trees (powered by
``tree-sitter`` + ``tree-sitter-language-pack`` pure wheels — zero external binaries).

Key guarantees:
* Thread-safe: each thread holds its own lazily-created ``Parser`` instance per
  language via ``threading.local()`` (Tree-sitter parsers are not thread-safe when
  shared across threads).
* Parse-once cacheable: ``get_file_ast()`` caches the parsed ``FileAst`` in
  ``repo_context["ast_cache"]`` when provided, so SQG002/SQG003/SQG006 share one
  parse per file instead of re-parsing.
* Graceful degradation: if ``tree-sitter-language-pack`` is unavailable or a file's
  extension has no grammar here, returns ``None`` so callers fall back cleanly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

_ts_get_parser: Any = None
try:
    from tree_sitter_language_pack import get_parser as _imported_get_parser

    _ts_get_parser = _imported_get_parser
    HAS_TREE_SITTER = True
except Exception:  # noqa: BLE001 — optional/degraded fallback if native wheel missing
    HAS_TREE_SITTER = False

_THREAD_LOCAL = threading.local()

_EXT_TO_TS_LANG: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}


def ts_lang_for(path: str) -> Optional[str]:
    """Map a file path to its Tree-sitter language name, or None if unsupported."""
    low = path.lower().replace("\\", "/")
    base = low.rsplit("/", 1)[-1]
    dot = base.rfind(".")
    if dot <= 0:
        return None
    return _EXT_TO_TS_LANG.get(base[dot:])


def _parser_for(lang: str) -> Any:
    if not HAS_TREE_SITTER or _ts_get_parser is None:
        return None
    cache: Dict[str, Any] = getattr(_THREAD_LOCAL, "parsers", None)  # type: ignore[assignment]
    if cache is None:
        cache = {}
        _THREAD_LOCAL.parsers = cache
    parser = cache.get(lang)
    if parser is None:
        parser = _ts_get_parser(lang)
        cache[lang] = parser
    return parser


def _text(node: Any, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


@dataclass(frozen=True)
class CallSite:
    """A real function/method call expression in the AST (never a declaration/signature)."""

    line: int                    # 1-based line number of the call
    callee: str                  # function or method name, e.g. "eval", "execSync", "md5"
    qualifier: Optional[str]     # receiver object if dotted, e.g. "os", "subprocess", "redis"
    args_text: str               # raw text of arguments node
    all_args_static_strings: bool
    first_arg_is_static_string: bool
    has_kwarg_shell_true: bool
    has_kwarg_safeloader: bool
    has_kwarg_usedforsecurity_false: bool


@dataclass(frozen=True)
class DomXssSite:
    """A JSX dangerouslySetInnerHTML, .innerHTML assignment, or document.write() call."""

    line: int
    label: str


def _is_static_string_expr(node) -> bool:
    """True when an expression is built only from string literals.

    Scan #37 (obra/superpowers, 2026-11-27): a constant banner assigned as
    ``el.innerHTML = '<div…>' + '<h2…>' + '<p…>'`` was reported as a DOM-XSS sink.
    A sink is only a sink when something can reach it; a concatenation of literals
    carries no input. Template literals with ``${…}`` are dynamic and stay flagged.
    """
    if node.type in ("string", "template_string"):
        return not any(child.type == "template_substitution" for child in _iter_nodes(node))
    if node.type == "parenthesized_expression":
        inner = node.named_children[0] if node.named_children else None
        return inner is not None and _is_static_string_expr(inner)
    if node.type == "binary_expression":
        return bool(node.named_children) and all(
            _is_static_string_expr(child) for child in node.named_children
        )
    return False


@dataclass(frozen=True)
class CommentNode:
    """An actual comment node from the syntax tree."""

    line_start: int  # 1-based
    line_end: int    # 1-based
    text: str
    is_jsdoc: bool


def _is_static_string_node(node: Any, lang: str) -> bool:
    """True when an AST argument node is a plain constant string literal with no interpolation."""
    t = node.type
    if lang == "python":
        if t == "string":
            return not any(c.type == "interpolation" for c in node.children)
        return False
    # JS / TS / TSX
    if t == "string":
        return True
    if t == "template_string":
        return not any(c.type == "template_substitution" for c in node.children)
    return False


def _iter_nodes(root: Any):
    """Iterative pre-order traversal (avoids Python recursion limits on deep ASTs)."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        children = node.children
        if children:
            stack.extend(reversed(children))


class FileAst:
    """Parsed syntax tree for one source file with lazy query extractors."""

    def __init__(self, source: str, lang: str, tree: Any) -> None:
        self.source = source
        self.source_bytes = source.encode("utf-8", errors="replace")
        self.lang = lang
        self.tree = tree
        self._calls: Optional[List[CallSite]] = None
        self._dom_xss: Optional[List[DomXssSite]] = None
        self._cp_execs: Optional[Set[str]] = None
        self._comments: Optional[List[CommentNode]] = None
        self._string_lines: Optional[Set[int]] = None

    def call_sites(self) -> List[CallSite]:
        if self._calls is not None:
            return self._calls
        out: List[CallSite] = []
        src = self.source_bytes
        is_py = self.lang == "python"
        target_type = "call" if is_py else "call_expression"

        for node in _iter_nodes(self.tree.root_node):
            if node.type != target_type:
                continue
            func = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if func is None:
                continue

            callee = ""
            qualifier: Optional[str] = None
            if func.type == "identifier":
                callee = _text(func, src)
            elif is_py and func.type == "attribute":
                obj = func.child_by_field_name("object")
                attr = func.child_by_field_name("attribute")
                if obj is not None and attr is not None:
                    qualifier = _text(obj, src)
                    callee = _text(attr, src)
            elif not is_py and func.type == "member_expression":
                obj = func.child_by_field_name("object")
                prop = func.child_by_field_name("property")
                if obj is not None and prop is not None:
                    qualifier = _text(obj, src)
                    callee = _text(prop, src)
            else:
                continue

            args_text = _text(args, src) if args is not None else ""
            arg_nodes = [
                c for c in (args.named_children if args is not None else [])
                if c.type != "comment"
            ]
            all_static = bool(arg_nodes) and all(
                _is_static_string_node(a, self.lang) for a in arg_nodes
            )
            first_static = bool(arg_nodes) and _is_static_string_node(arg_nodes[0], self.lang)

            shell_true = False
            safeloader = False
            usedforsecurity_false = False
            if is_py and args is not None:
                for arg in arg_nodes:
                    if arg.type == "keyword_argument":
                        k = arg.child_by_field_name("name")
                        v = arg.child_by_field_name("value")
                        if k is not None and v is not None:
                            kn = _text(k, src)
                            vt = _text(v, src).strip()
                            if kn == "shell" and vt == "True":
                                shell_true = True
                            elif kn == "Loader" and "SafeLoader" in vt:
                                safeloader = True
                            elif kn == "usedforsecurity" and vt == "False":
                                usedforsecurity_false = True
                    elif "SafeLoader" in _text(arg, src):
                        safeloader = True

            out.append(
                CallSite(
                    line=node.start_point.row + 1,
                    callee=callee,
                    qualifier=qualifier,
                    args_text=args_text,
                    all_args_static_strings=all_static,
                    first_arg_is_static_string=first_static,
                    has_kwarg_shell_true=shell_true,
                    has_kwarg_safeloader=safeloader,
                    has_kwarg_usedforsecurity_false=usedforsecurity_false,
                )
            )
        self._calls = out
        return out

    def imported_child_process_execs(self) -> Set[str]:
        """Local names bound to child_process.exec / execSync via CJS require or ESM import."""
        if self._cp_execs is not None:
            return self._cp_execs
        names: Set[str] = set()
        if self.lang == "python":
            self._cp_execs = names
            return names

        src = self.source_bytes
        for node in _iter_nodes(self.tree.root_node):
            # ESM: import { exec, execSync as run } from 'child_process' / 'node:child_process'
            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node is None:
                    continue
                mod = _text(source_node, src).strip("'\"")
                if mod not in ("child_process", "node:child_process"):
                    continue
                for sub in _iter_nodes(node):
                    if sub.type == "import_specifier":
                        orig = sub.child_by_field_name("name")
                        alias = sub.child_by_field_name("alias")
                        if orig is not None and _text(orig, src) in ("exec", "execSync"):
                            bound = _text(alias, src) if alias is not None else _text(orig, src)
                            names.add(bound)
            # CJS: const { exec, execSync: run } = require('child_process' | 'node:child_process')
            elif node.type == "variable_declarator":
                val = node.child_by_field_name("value")
                pat = node.child_by_field_name("name")
                if val is None or pat is None or val.type != "call_expression":
                    continue
                fn = val.child_by_field_name("function")
                args = val.child_by_field_name("arguments")
                if fn is None or _text(fn, src) != "require" or args is None:
                    continue
                if not any(
                    _text(c, src).strip("'\"") in ("child_process", "node:child_process")
                    for c in args.named_children
                ):
                    continue
                if pat.type == "object_pattern":
                    for sub in pat.named_children:
                        if sub.type == "shorthand_property_identifier_pattern":
                            ident = _text(sub, src)
                            if ident in ("exec", "execSync"):
                                names.add(ident)
                        elif sub.type == "pair_pattern":
                            key = sub.child_by_field_name("key")
                            value = sub.child_by_field_name("value")
                            if key is not None and value is not None and _text(key, src) in ("exec", "execSync"):
                                names.add(_text(value, src))
        self._cp_execs = names
        return names

    def dom_xss_sites(self) -> List[DomXssSite]:
        if self._dom_xss is not None:
            return self._dom_xss
        out: List[DomXssSite] = []
        if self.lang == "python":
            self._dom_xss = out
            return out

        src = self.source_bytes
        for node in _iter_nodes(self.tree.root_node):
            if node.type == "jsx_attribute":
                first = node.named_children[0] if node.named_children else None
                if first is not None and _text(first, src) == "dangerouslySetInnerHTML":
                    out.append(DomXssSite(node.start_point.row + 1, "React dangerouslySetInnerHTML"))
            elif node.type == "assignment_expression":
                left = node.child_by_field_name("left")
                if left is not None and left.type == "member_expression":
                    prop = left.child_by_field_name("property")
                    if prop is not None and _text(prop, src) == "innerHTML":
                        right = node.child_by_field_name("right")
                        if right is not None and _is_static_string_expr(right):
                            continue  # literal markup cannot carry untrusted input
                        out.append(DomXssSite(node.start_point.row + 1, "innerHTML assignment"))
        self._dom_xss = out
        return out

    def string_lines(self) -> Set[int]:
        """1-based lines that are string DATA, not code: inside a multi-line literal.

        Scan #38 (firecrawl, 2026-11-27): `ellipsis-only body at line 20: '...'` in
        research_docs.py was a `...` prose line inside a module docstring. The
        text-level string guard is line-local by construction, so a literal spanning
        several lines was read as code. Interpolations (`${…}` in a template,
        `{…}` in an f-string) ARE expressions, so their lines are removed from the
        span — real code inside a template keeps being scanned.
        """
        if self._string_lines is not None:
            return self._string_lines
        skip: Set[int] = set()
        for node in _iter_nodes(self.tree.root_node):
            # Select on the node FAMILY, not one literal name: the grammar shipped with
            # tree-sitter-language-pack 1.25 calls a Python docstring a `string`, while
            # 1.28 calls it a `docstring` (verified against both parsers, 2026-11-27).
            # CI runs 1.28 and local dev 1.25, so a literal match passed locally and
            # failed only in CI — the same "cannot see its own input" class this change
            # exists to remove. `string_content` children also match and add nothing:
            # their span is inside the parent's.
            if "string" not in node.type and node.type != "docstring":
                continue
            if node.start_point.row == node.end_point.row:
                continue  # single-line: inside_string_literal already covers it
            span = set(range(node.start_point.row + 1, node.end_point.row + 2))
            for inner in _iter_nodes(node):
                if inner.type in ("interpolation", "template_substitution"):
                    span.difference_update(
                        range(inner.start_point.row + 1, inner.end_point.row + 2)
                    )
            skip |= span
        self._string_lines = skip
        return skip

    def comment_nodes(self) -> List[CommentNode]:
        if self._comments is not None:
            return self._comments
        out: List[CommentNode] = []
        src = self.source_bytes
        for node in _iter_nodes(self.tree.root_node):
            if node.type == "comment":
                txt = _text(node, src)
                out.append(
                    CommentNode(
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        text=txt,
                        is_jsdoc=txt.lstrip().startswith("/**"),
                    )
                )
        self._comments = out
        return out


def parse_file_ast(
    path: str,
    source: str,
    ast_cache: Optional[Dict[str, Optional[FileAst]]] = None,
) -> Optional[FileAst]:
    """Parse ``source`` for ``path`` via Tree-sitter, using ``ast_cache`` if provided."""
    if ast_cache is not None and path in ast_cache:
        return ast_cache[path]

    lang = ts_lang_for(path)
    if lang is None:
        if ast_cache is not None:
            ast_cache[path] = None
        return None

    parser = _parser_for(lang)
    if parser is None:
        return None

    try:
        tree = parser.parse(source.encode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 — never abort a scan on a grammar error
        return None

    result = FileAst(source, lang, tree)
    if ast_cache is not None:
        ast_cache[path] = result
    return result
