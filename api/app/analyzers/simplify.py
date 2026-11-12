"""SQG009 — avoidable complexity: code that a shorter, equivalent form replaces.

The product is named for AI slop, and verbosity is its most common form: an assistant
writes eight lines building a list that a comprehension does in one, or a four-line
if/else that returns the condition it just tested. No existing check looks at shape.

WHY THIS IS A GUARD RULE AND NOT AN OPINION
"This could be shorter" is a judgement, and the Guard does not ship judgement — that is
the Crew's job (PRD §3). So this rule is deliberately narrow: it only fires when the
shorter form can be **derived from the syntax tree**, and it reports that form verbatim.
Every finding therefore comes with a replacement a reviewer can read, diff and commit;
if the rewrite is not derivable, there is no finding. That keeps a style preference from
masquerading as a fact.

Consequences of that rule, all deliberate:

* Python only. The rewrite is produced by ``ast.unparse``, so a language without a
  parser here gets `not_run_unsupported` rather than a regex guess. JavaScript and
  TypeScript need tree-sitter — the same dependency SQG003 wants — and are reported as
  not covered until it lands.
* Patterns that do not actually save lines are excluded, because the ask is line count.
  ``len(x) == 0`` → ``not x`` is one line either way, and on a NumPy array the "shorter"
  form raises where the original worked. Rewrites that could change behaviour are worse
  than no rewrite, so they are simply not offered.
* A comment inside the region being collapsed downgrades the finding to guidance. The
  one-liner is still correct, but applying it would delete a human's note, and silently
  discarding a comment is not a safe automatic edit.

Advisory only: MEDIUM confidence, never block-eligible. Verbose code is not dangerous
code, and shape is exactly where context wins most often.
"""

import ast
from typing import Awaitable, Callable, List, Optional, Tuple

from app import github_client
from app.diff import parse_diff

from .base import (
    REMEDIATION_GUIDANCE,
    REMEDIATION_PATCH,
    Confidence,
    Evidence,
    Finding,
    Remediation,
)

RULE_ID = "SQG009"
CATEGORY = "complexity"

_PY_EXT = (".py",)
_ALLOWLIST = ("# noqa", "# nosec", "# keep")

# A rewrite is only worth reporting if it removes at least this many lines. One line
# becoming one line is a style opinion, which this rule does not trade in.
MIN_LINES_SAVED = 1

# Both limits came from running this rule over its own source, which proposed folding a
# seven-line if/else into one 150-character ternary — fewer lines of worse code, and a
# lint failure at this project's own 100-column limit.
#
# Past the first limit the rewrite is still a real simplification, but it needs wrapping
# to fit, so it is reported as guidance rather than offered as a one-click commit. A
# first attempt simply dropped these, which also threw away a correct four-line-to-one
# `any()` rewrite for being seven characters over — losing true signal to enforce
# formatting. Past the second limit the one-liner is not a simplification in any useful
# sense and is not reported at all.
MAX_PATCH_WIDTH = 100
MAX_REWRITE_WIDTH = 200

# A proposed rewrite: (label, what the shorter form is, the replacement source).
Rewrite = Tuple[str, str, str]


def _is_const(node: ast.AST, value: object) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


def _shape(node: ast.AST) -> str:
    """A node's structure with load/store context erased.

    A loop target (``for p in prices``) is a Store and its use in the body is a Load, so
    a raw ``ast.dump`` reports the two ``p``s as different nodes. Round-tripping through
    source normalises the context away, which is what lets ``total += p`` be recognised
    as summing the iterable itself rather than a generator over it.
    """
    try:
        return ast.dump(ast.parse(ast.unparse(node), mode="eval").body, annotate_fields=False)
    except (SyntaxError, ValueError):
        return ast.dump(node, annotate_fields=False)


def _same(a: Optional[ast.AST], b: Optional[ast.AST]) -> bool:
    """Structural equality of two expressions, ignoring position and load/store context."""
    if a is None or b is None:
        return False
    return _shape(a) == _shape(b)


def _name(node: ast.AST) -> Optional[str]:
    return node.id if isinstance(node, ast.Name) else None


def _single_assign(stmt: ast.AST) -> Optional[Tuple[str, ast.AST]]:
    """(target name, value) for a plain single-target assignment, else None."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return None
    target = _name(stmt.targets[0])
    return (target, stmt.value) if target else None


def _negate(test: ast.expr) -> ast.expr:
    """`not test`, collapsing a double negation rather than emitting one."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return test.operand
    return ast.UnaryOp(op=ast.Not(), operand=test)


# --- individual patterns ----------------------------------------------------------
# Each returns a Rewrite or None. They receive already-narrowed nodes and are free to
# assume nothing else; a None means "this shape does not apply", never "probably fine".


def _if_returning_booleans(node: ast.If) -> Optional[Rewrite]:
    """``if c: return True`` / ``else: return False`` → ``return bool(c)``."""
    if len(node.body) != 1 or len(node.orelse) != 1:
        return None
    then, other = node.body[0], node.orelse[0]
    if not isinstance(then, ast.Return) or not isinstance(other, ast.Return):
        return None
    if then.value is None or other.value is None:
        return None
    if _is_const(then.value, True) and _is_const(other.value, False):
        test: ast.expr = node.test
    elif _is_const(then.value, False) and _is_const(other.value, True):
        test = _negate(node.test)
    else:
        return None
    # bool() rather than a bare return: the original returned the literal True/False,
    # so returning the truthiness — not the operand — is the equivalent rewrite.
    body = ast.unparse(test) if _is_boolean_valued(test) else f"bool({ast.unparse(test)})"
    return ("if/else returning True and False", "the condition itself", f"return {body}")


def _is_boolean_valued(node: ast.expr) -> bool:
    """True when the expression already evaluates to a bool, so bool() adds nothing."""
    return isinstance(node, (ast.Compare, ast.BoolOp)) or (
        isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)
    )


def _if_else_to_ternary(node: ast.If) -> Optional[Rewrite]:
    """``if c: x = a`` / ``else: x = b`` → ``x = a if c else b``."""
    if len(node.body) != 1 or len(node.orelse) != 1:
        return None
    then, other = _single_assign(node.body[0]), _single_assign(node.orelse[0])
    if not then or not other or then[0] != other[0]:
        return None
    name, when_true = then
    _n, when_false = other
    replacement = (
        f"{name} = {ast.unparse(when_true)} if {ast.unparse(node.test)} "
        f"else {ast.unparse(when_false)}"
    )
    return ("if/else assigning the same variable", "a conditional expression", replacement)


def _membership_to_get(node: ast.If) -> Optional[Rewrite]:
    """``if k in d: v = d[k]`` / ``else: v = default`` → ``v = d.get(k, default)``."""
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    if not isinstance(test.ops[0], ast.In) or len(node.body) != 1 or len(node.orelse) != 1:
        return None
    key, container = test.left, test.comparators[0]

    then, other = _single_assign(node.body[0]), _single_assign(node.orelse[0])
    if not then or not other or then[0] != other[0]:
        return None
    name, lookup = then
    if not isinstance(lookup, ast.Subscript):
        return None
    if not _same(lookup.value, container) or not _same(lookup.slice, key):
        return None
    default_expr = other[1]
    if not isinstance(default_expr, ast.expr):
        return None
    return (
        "membership test guarding a dict lookup",
        "dict.get() with a default",
        f"{name} = {_get_call(container, key, default_expr)}",
    )


def _get_call(container: ast.expr, key: ast.expr, default: ast.expr) -> str:
    """``d.get(k)`` when the default is None, else ``d.get(k, default)``."""
    base = f"{ast.unparse(container)}.get({ast.unparse(key)}"
    if _is_const(default, None):
        return base + ")"
    return f"{base}, {ast.unparse(default)})"


def _try_keyerror_to_get(node: ast.Try) -> Optional[Rewrite]:
    """``try: v = d[k]`` / ``except KeyError: v = default`` → ``v = d.get(k, default)``."""
    if node.orelse or node.finalbody or len(node.handlers) != 1 or len(node.body) != 1:
        return None
    handler = node.handlers[0]
    if not isinstance(handler.type, ast.expr):
        return None
    if _name(handler.type) != "KeyError" or handler.name or len(handler.body) != 1:
        return None

    tried, fallback = node.body[0], handler.body[0]
    if isinstance(tried, ast.Return) and isinstance(fallback, ast.Return):
        lookup: ast.expr | None = tried.value
        default: ast.expr | None = fallback.value
        prefix = "return "
    else:
        first = _single_assign(tried)
        second = _single_assign(fallback)
        if not first or not second or first[0] != second[0]:
            return None
        if not isinstance(first[1], ast.expr) or not isinstance(second[1], ast.expr):
            return None
        lookup = first[1]
        default = second[1]
        prefix = f"{first[0]} = "
    if not isinstance(lookup, ast.Subscript) or default is None:
        return None
    return (
        "try/except KeyError around a dict lookup",
        "dict.get() with a default",
        prefix + _get_call(lookup.value, lookup.slice, default),
    )


def _append_loop_to_comprehension(prev: ast.AST, node: ast.For) -> Optional[Rewrite]:
    """``out = []`` + a loop whose only job is ``out.append(x)`` → a comprehension."""
    assigned = _single_assign(prev)
    if not assigned or not isinstance(assigned[1], ast.List) or assigned[1].elts:
        return None
    out = assigned[0]
    if node.orelse or len(node.body) != 1:
        return None

    stmt, condition = node.body[0], None
    if isinstance(stmt, ast.If):
        if len(stmt.body) != 1 or stmt.orelse:
            return None
        condition, stmt = stmt.test, stmt.body[0]

    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return None
    call = stmt.value
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "append":
        return None
    if _name(func.value) != out or len(call.args) != 1 or call.keywords:
        return None

    clause = f"for {ast.unparse(node.target)} in {ast.unparse(node.iter)}"
    if condition is not None:
        clause += f" if {ast.unparse(condition)}"
    return (
        "loop that only appends to a list",
        "a list comprehension",
        f"{out} = [{ast.unparse(call.args[0])} {clause}]",
    )


def _accumulator_loop_to_sum(prev: ast.AST, node: ast.For) -> Optional[Rewrite]:
    """``total = 0`` + a loop whose only job is ``total += x`` → ``sum(...)``."""
    assigned = _single_assign(prev)
    if not assigned or not _is_const(assigned[1], 0):
        return None
    total = assigned[0]
    if node.orelse or len(node.body) != 1:
        return None
    stmt = node.body[0]
    if not isinstance(stmt, ast.AugAssign) or not isinstance(stmt.op, ast.Add):
        return None
    if _name(stmt.target) != total:
        return None

    # `for x in items: total += x` sums the iterable itself; anything else needs the
    # expression carried into a generator.
    if _same(stmt.value, node.target):
        inner = ast.unparse(node.iter)
    else:
        inner = (
            f"{ast.unparse(stmt.value)} for {ast.unparse(node.target)} "
            f"in {ast.unparse(node.iter)}"
        )
    return ("loop accumulating a total", "sum()", f"{total} = sum({inner})")


def _search_loop_to_any(node: ast.For, following: Optional[ast.AST]) -> Optional[Rewrite]:
    """``for x in xs: if c: return True`` + ``return False`` → ``return any(...)``."""
    if not isinstance(following, ast.Return) or node.orelse or len(node.body) != 1:
        return None
    inner = node.body[0]
    if not isinstance(inner, ast.If) or len(inner.body) != 1 or inner.orelse:
        return None
    returned = inner.body[0]
    if not isinstance(returned, ast.Return):
        return None
    if returned.value is None or following.value is None:
        return None

    if _is_const(returned.value, True) and _is_const(following.value, False):
        builtin, test = "any", inner.test
    elif _is_const(returned.value, False) and _is_const(following.value, True):
        builtin, test = "all", _negate(inner.test)
    else:
        return None
    clause = f"for {ast.unparse(node.target)} in {ast.unparse(node.iter)}"
    return (
        f"loop searching for a match, then returning {'True' if builtin == 'any' else 'False'}",
        f"{builtin}()",
        f"return {builtin}({ast.unparse(test)} {clause})",
    )


# --- driver -----------------------------------------------------------------------


def _statement_blocks(tree: ast.AST):
    """Every list of statements in the tree, so adjacent statements can be compared."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block


def _find_rewrites(tree: ast.AST) -> List[Tuple[int, int, Rewrite]]:
    """(start line, end line, rewrite) for every collapsible region in a module.

    elif-tail If nodes — the ``orelse[0]`` of another If — are skipped for the
    if/else rules, covering two shapes. For an ``elif`` tail the "N lines can be 1"
    claim is factually false AND the one-liner is destructive: it lands at the
    elif's indentation and unconditionally overwrites the variable, dropping the
    chain's earlier arms (scan #20 findings #19/#22/#23 on openai/codex-security
    proposed exactly such rewrites; three of six SQG009 suggestions were broken
    this way). For an ``else:`` + nested ``if/else`` assigning the same variable
    the one-liner WOULD be safe — it lands inside the else block — but the two
    shapes are AST-identical, so both are suppressed conservatively; that
    deliberate loss of a safe rewrite is accepted because the destructive half is
    indistinguishable at parse time (a ``col_offset`` distinguisher exists if the
    safe half is ever wanted). A chain's HEAD still matches when it is a genuine
    2-arm if/else.
    """
    found: List[Tuple[int, int, Rewrite]] = []
    chain_tails: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.orelse and isinstance(node.orelse[0], ast.If):
            chain_tails.add(id(node.orelse[0]))
    for block in _statement_blocks(tree):
        for index, stmt in enumerate(block):
            prev = block[index - 1] if index else None
            following = block[index + 1] if index + 1 < len(block) else None

            if isinstance(stmt, ast.If) and id(stmt) not in chain_tails:
                # Order matters: an `if k in d` guard also fits the generic ternary
                # shape, and `d.get(k, default)` is the better rewrite of the two, so
                # it must be offered first.
                for rule in (_if_returning_booleans, _membership_to_get, _if_else_to_ternary):
                    rewrite = rule(stmt)
                    if rewrite:
                        found.append((stmt.lineno, stmt.end_lineno or stmt.lineno, rewrite))
                        break
            elif isinstance(stmt, ast.Try):
                rewrite = _try_keyerror_to_get(stmt)
                if rewrite:
                    found.append((stmt.lineno, stmt.end_lineno or stmt.lineno, rewrite))
            elif isinstance(stmt, ast.For):
                # The two accumulator shapes start at the initialiser above the loop,
                # because collapsing the loop without removing `out = []` leaves a bug.
                if prev is not None:
                    rewrite = _append_loop_to_comprehension(prev, stmt) or \
                        _accumulator_loop_to_sum(prev, stmt)
                    if rewrite:
                        found.append((prev.lineno, stmt.end_lineno or stmt.lineno, rewrite))
                        continue
                rewrite = _search_loop_to_any(stmt, following)
                if rewrite:
                    end = following.end_lineno or following.lineno  # type: ignore[union-attr]
                    found.append((stmt.lineno, end, rewrite))
    return found


def _default_fetch(repo: str, path: str, ref: str, token: str):
    return github_client.fetch_file_content(repo, path, ref, token)


async def check_simplify(diff: str, repo_context: dict) -> List[Finding]:
    """Flag multi-line Python that a derivable one-liner replaces (advisory).

    Needs whole files, not just added lines: a syntax tree cannot be built from a diff
    fragment. So the full content is fetched (same boundary the dependency and CVE
    checks already use) and only findings whose region *starts* on an added line are
    reported — a PR is judged on what it introduced, never on the code it inherited.
    """
    repo = repo_context.get("repo", "")
    head_sha = repo_context.get("head_sha", "")
    token = repo_context.get("token", "")
    one_arg: Optional[Callable[[str], Awaitable[Optional[str]]]] = repo_context.get("fetch_file")

    added_by_file: dict[str, dict[int, str]] = {}
    for path, line, content in parse_diff(diff):
        added_by_file.setdefault(path, {})[line] = content

    findings: List[Finding] = []
    for path, added in added_by_file.items():
        if not path.lower().endswith(_PY_EXT):
            continue
        if one_arg is not None:
            src = await one_arg(path)
        else:
            src = await _default_fetch(repo, path, head_sha, token)
        if not src:
            continue  # unfetchable → silent, same fail-safe as the other analyzers

        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError, RecursionError):
            continue  # unparseable file → no claim about it

        lines = src.splitlines()
        for start, end, (label, shorter, replacement) in _find_rewrites(tree):
            if start not in added:
                continue  # region is pre-existing code, not this change
            span = lines[start - 1:end]
            if not span:
                continue
            saved = len(span) - 1
            if saved < MIN_LINES_SAVED:
                continue
            if any(token_ in line for line in span for token_ in _ALLOWLIST):
                continue  # deliberate, and marked as such

            indent = span[0][: len(span[0]) - len(span[0].lstrip())]
            width = len(indent) + len(replacement)
            if width > MAX_REWRITE_WIDTH:
                continue  # fewer lines, unreadable code — not a simplification

            # Two things make a rewrite unsafe to apply blind, though still worth
            # reporting: a comment inside the region would be deleted by the collapse,
            # and an over-long line needs wrapping before it fits the codebase.
            has_comment = any("#" in line for line in span)
            too_wide = width > MAX_PATCH_WIDTH
            if has_comment:
                basis = (
                    "derived from the file's syntax tree; a comment inside these lines "
                    "would be lost, so apply it by hand"
                )
            elif too_wide:
                basis = (
                    f"derived from the file's syntax tree; at {width} characters it needs "
                    "wrapping to fit, so it is not offered as a one-click commit"
                )
            else:
                basis = "derived from the file's syntax tree — the shorter form is equivalent"
            offer_patch = not has_comment and not too_wide
            remediation = Remediation(
                kind=REMEDIATION_PATCH if offer_patch else REMEDIATION_GUIDANCE,
                text=f"Replace with {shorter}: {replacement}",
                suggested_replacement=indent + replacement if offer_patch else None,
                basis=basis,
            )
            findings.append(
                Finding(
                    category=CATEGORY,
                    confidence=Confidence.MEDIUM,
                    block_eligible=False,
                    file_path=path,
                    line_start=start,
                    line_end=end,
                    message=(
                        f"{len(span)} lines can be 1: {label} is {shorter}"
                    ),
                    evidence=Evidence(snippet=span[0].strip()),
                    tool="ast",
                    rule_id=RULE_ID,
                    remediation=remediation,
                    fix_suggestion=remediation.text,
                )
            )
    return findings
