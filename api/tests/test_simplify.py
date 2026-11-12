"""SQG009: multi-line Python a derivable one-liner replaces.

Two things are asserted throughout. First, the rewrite is *exact* — the test states the
one-liner it expects, because a suggestion a reviewer can commit is the whole basis for
this being a Guard rule rather than a style opinion. Second, the rule stays silent on
code that is already minimal: the negative cases matter more than the positive ones,
since a noisy complexity check trains people to ignore the report.
"""

import ast
import asyncio

import pytest

from app.analyzers.base import REMEDIATION_GUIDANCE, REMEDIATION_PATCH, Confidence
from app.analyzers.simplify import RULE_ID, check_simplify


def _run(source: str, path: str = "mod.py", added_lines: list[int] | None = None):
    """Analyze `source` as a fully-added file (or only the given added line numbers)."""
    lines = source.splitlines()
    numbers = added_lines if added_lines is not None else list(range(1, len(lines) + 1))
    body = "".join(f"+{lines[n - 1]}\n" for n in numbers)
    # The hunk header has to declare the real starting line, or parse_diff numbers the
    # added lines from 1 and a partial-change test silently becomes a whole-file one.
    diff = (
        f"--- a/{path}\n+++ b/{path}\n"
        f"@@ -0,0 +{numbers[0]},{len(numbers)} @@\n{body}"
    )

    async def fetch_file(p):
        return source if p == path else None

    return asyncio.run(check_simplify(diff, {"fetch_file": fetch_file}))


def _only(source: str):
    findings = _run(source)
    assert len(findings) == 1, [f.message for f in findings]
    return findings[0]


def _replacement(source: str) -> str:
    return _only(source).remediation.suggested_replacement.strip()


# --- the seven collapsible shapes -------------------------------------------------


def test_if_else_returning_booleans_becomes_the_condition():
    source = """def is_adult(age):
    if age >= 18:
        return True
    else:
        return False
"""
    finding = _only(source)
    assert finding.remediation.suggested_replacement.strip() == "return age >= 18"
    assert finding.line_start == 2 and finding.line_end == 5
    assert "4 lines can be 1" in finding.message


def test_inverted_boolean_return_negates_rather_than_reordering():
    source = """def blocked(user):
    if user.banned:
        return False
    else:
        return True
"""
    assert _replacement(source) == "return not user.banned"


def test_non_boolean_condition_is_wrapped_in_bool():
    """The original returned a literal True/False, so the rewrite must return
    truthiness — not the operand, which would change the return type."""
    source = """def has_items(cart):
    if cart.items:
        return True
    else:
        return False
"""
    assert _replacement(source) == "return bool(cart.items)"


def test_double_negative_is_collapsed_not_stacked():
    """`not (not x)` must never be emitted. bool() stays, because the original
    returned the literal True/False and dropping it would change the return type."""
    source = """def present(x):
    if not x:
        return False
    else:
        return True
"""
    assert _replacement(source) == "return bool(x)"


def test_if_else_assigning_one_variable_becomes_a_ternary():
    source = """def label(n):
    if n > 0:
        sign = "positive"
    else:
        sign = "negative"
    return sign
"""
    assert _replacement(source) == "sign = 'positive' if n > 0 else 'negative'"


def test_append_loop_becomes_a_comprehension():
    source = """def double_all(numbers):
    out = []
    for n in numbers:
        out.append(n * 2)
    return out
"""
    finding = _only(source)
    assert finding.remediation.suggested_replacement.strip() == "out = [n * 2 for n in numbers]"
    # The region starts at the initialiser: collapsing the loop alone would leave
    # `out = []` behind and silently break the code.
    assert finding.line_start == 2 and finding.line_end == 4


def test_filtered_append_loop_keeps_the_condition():
    source = """def evens(numbers):
    out = []
    for n in numbers:
        if n % 2 == 0:
            out.append(n)
    return out
"""
    assert _replacement(source) == "out = [n for n in numbers if n % 2 == 0]"


def test_accumulator_loop_over_the_iterable_becomes_sum_of_it():
    source = """def total(prices):
    running = 0
    for p in prices:
        running += p
    return running
"""
    assert _replacement(source) == "running = sum(prices)"


def test_accumulator_over_an_expression_becomes_a_generator():
    source = """def total(items):
    running = 0
    for item in items:
        running += item.price
    return running
"""
    assert _replacement(source) == "running = sum(item.price for item in items)"


def test_search_loop_becomes_any():
    source = """def has_admin(users):
    for u in users:
        if u.is_admin:
            return True
    return False
"""
    finding = _only(source)
    assert finding.remediation.suggested_replacement.strip() == "return any(u.is_admin for u in users)"
    assert finding.line_end == 5  # the trailing `return False` is part of the region


def test_inverted_search_loop_becomes_all():
    source = """def all_verified(users):
    for u in users:
        if not u.verified:
            return False
    return True
"""
    assert _replacement(source) == "return all(u.verified for u in users)"


def test_membership_guarded_lookup_becomes_dict_get():
    source = """def setting(config, key):
    if key in config:
        value = config[key]
    else:
        value = "default"
    return value
"""
    assert _replacement(source) == "value = config.get(key, 'default')"


def test_try_keyerror_becomes_dict_get():
    source = """def setting(config, key):
    try:
        value = config[key]
    except KeyError:
        value = 0
    return value
"""
    assert _replacement(source) == "value = config.get(key, 0)"


def test_try_keyerror_with_returns_becomes_a_returned_get():
    source = """def setting(config, key):
    try:
        return config[key]
    except KeyError:
        return None
"""
    # A None default is what .get already returns, so the argument is dropped.
    assert _replacement(source) == "return config.get(key)"


# --- silence on code that is already minimal --------------------------------------


@pytest.mark.parametrize("source", [
    # Already the one-liner this rule would suggest.
    "def is_adult(age):\n    return age >= 18\n",
    "def double_all(ns):\n    return [n * 2 for n in ns]\n",
    "def total(ps):\n    return sum(ps)\n",
    "def has_admin(us):\n    return any(u.is_admin for u in us)\n",
    "def setting(c, k):\n    return c.get(k, 0)\n",
    # An if/else whose branches do different things is not collapsible.
    "def f(n):\n    if n > 0:\n        a = 1\n    else:\n        b = 2\n    return a, b\n",
    # More than one statement per branch — a ternary cannot express it.
    "def f(n):\n    if n:\n        x = 1\n        log(x)\n    else:\n        x = 2\n    return x\n",
    # elif chains are not two-branch.
    "def f(n):\n    if n > 0:\n        return True\n    elif n == 0:\n        return None\n    else:\n        return False\n",
    # The loop does more than append.
    "def f(ns):\n    out = []\n    for n in ns:\n        log(n)\n        out.append(n)\n    return out\n",
    # `out` starts non-empty, so a comprehension would drop the seed values.
    "def f(ns):\n    out = [0]\n    for n in ns:\n        out.append(n)\n    return out\n",
    # The accumulator does not start at zero.
    "def f(ns):\n    total = 100\n    for n in ns:\n        total += n\n    return total\n",
    # A different exception, and a lookup that is not a subscript.
    "def f(c, k):\n    try:\n        return c[k]\n    except ValueError:\n        return None\n",
    "def f(c, k):\n    try:\n        return compute(k)\n    except KeyError:\n        return None\n",
    # A loop searching but returning a value, not a bool.
    "def f(us):\n    for u in us:\n        if u.is_admin:\n            return u\n    return None\n",
])
def test_minimal_code_produces_no_finding(source):
    assert _run(source) == []


def test_non_python_files_are_not_inspected():
    source = "if (x) {\n  return true;\n} else {\n  return false;\n}\n"
    assert _run(source, path="app.ts") == []


def test_unparseable_python_makes_no_claim():
    assert _run("def broken(:\n    pass\n") == []


def test_suppression_marker_is_honoured():
    source = """def is_adult(age):
    if age >= 18:  # noqa
        return True
    else:
        return False
"""
    assert _run(source) == []


def test_mismatched_key_falls_back_to_the_ternary_not_a_wrong_get():
    """`c[j]` guarded by `k in c` is NOT `c.get(k, ...)` — that rewrite would look up
    the wrong key. The generic two-line collapse is still correct and is offered."""
    source = """def f(c, k, j):
    if k in c:
        v = c[j]
    else:
        v = None
    return v
"""
    assert _replacement(source) == "v = c[j] if k in c else None"


def test_two_line_if_else_is_still_worth_collapsing():
    """Written inline it is 2 lines, so folding it to 1 still removes a line."""
    source = "def f(x):\n    if x: return True\n    else: return False\n"
    finding = _only(source)
    assert "2 lines can be 1" in finding.message
    assert finding.remediation.suggested_replacement.strip() == "return bool(x)"


# --- honesty invariants ------------------------------------------------------------


def test_findings_are_advisory_and_never_block():
    source = """def is_adult(age):
    if age >= 18:
        return True
    else:
        return False
"""
    finding = _only(source)
    assert finding.rule_id == RULE_ID
    assert finding.category == "complexity"
    assert finding.confidence is Confidence.MEDIUM
    assert finding.block_eligible is False


def test_every_suggested_replacement_is_valid_python():
    """A suggestion offered as a one-click commit must at minimum parse."""
    sources = [
        "def f(a):\n    if a > 1:\n        return True\n    else:\n        return False\n",
        "def f(ns):\n    out = []\n    for n in ns:\n        out.append(n * 2)\n    return out\n",
        "def f(c, k):\n    try:\n        value = c[k]\n    except KeyError:\n        value = 0\n    return value\n",
        "def f(us):\n    for u in us:\n        if u.ok:\n            return True\n    return False\n",
    ]
    for source in sources:
        replacement = _replacement(source)
        ast.parse(replacement)  # raises SyntaxError if we emitted nonsense


def test_a_comment_inside_the_region_blocks_the_auto_patch():
    """Collapsing these lines would delete the note, so the fix is not offered as
    a one-click suggestion — it is reported as guidance instead."""
    source = """def is_adult(age):
    if age >= 18:
        # adulthood threshold per policy
        return True
    else:
        return False
"""
    finding = _only(source)
    assert finding.remediation.kind == REMEDIATION_GUIDANCE
    assert finding.remediation.suggested_replacement is None
    assert "by hand" in finding.remediation.basis


def test_clean_regions_offer_a_committable_patch():
    source = """def is_adult(age):
    if age >= 18:
        return True
    else:
        return False
"""
    assert _only(source).remediation.kind == REMEDIATION_PATCH
    assert _only(source).remediation.is_applicable is True


def test_replacement_preserves_the_original_indentation():
    source = """class C:
    def m(self, age):
        if age >= 18:
            return True
        else:
            return False
"""
    finding = _only(source)
    assert finding.remediation.suggested_replacement == "        return age >= 18"


def test_only_regions_the_change_introduced_are_reported():
    """A PR is judged on what it added. The collapsible block here is pre-existing;
    only line 7 was touched, so the block must not be attributed to this change."""
    source = """def is_adult(age):
    if age >= 18:
        return True
    else:
        return False


def added_helper(x):
    return x
"""
    assert _run(source, added_lines=[8, 9]) == []


def test_the_rule_reports_a_python_repo_as_covered():
    from app.coverage import RAN, plan_rule, take_census

    coverage = plan_rule("SQG009", take_census({"mod.py": "x = 1\n"}))
    assert coverage.status == RAN
    assert coverage.covered == ["Python (1 files)"]


def test_a_javascript_repo_is_reported_unsupported_not_clean():
    from app.coverage import NOT_RUN_UNSUPPORTED, plan_rule, take_census

    coverage = plan_rule("SQG009", take_census({"app.ts": "const x = 1\n"}))
    assert coverage.status == NOT_RUN_UNSUPPORTED
    assert coverage.is_conclusive is False


def test_repeated_shapes_group_despite_differing_line_counts():
    """Grouping keys off the pattern, not the saved-line count, or the same issue
    would fragment into one group per length."""
    from app.analyzers.base import Finding
    from app.grouping import issue_key

    def finding(count: int) -> Finding:
        return Finding(
            category="complexity", confidence=Confidence.MEDIUM, block_eligible=False,
            file_path="a.py", line_start=1, line_end=count,
            message=f"{count} lines can be 1: if/else returning True and False is the condition itself",
            evidence=None, tool="ast", rule_id=RULE_ID,
        )

    assert issue_key(finding(4)) == issue_key(finding(6))


def test_an_over_long_rewrite_is_reported_but_not_auto_applied():
    """Still a real simplification, but it needs wrapping before it fits.

    Found by running this rule over its own source: it proposed folding a seven-line
    if/else into a 150-character ternary, which would fail this project's own lint. An
    earlier version dropped these outright and lost a correct four-line `any()` rewrite
    to the same rule, so the finding stays and only the one-click patch is withheld.
    """
    source = """def pick(flag, alpha_configuration_value, beta_configuration_value):
    if flag and alpha_configuration_value is not None:
        chosen_configuration_result = alpha_configuration_value.resolve(strict=True)
    else:
        chosen_configuration_result = beta_configuration_value.resolve(strict=False)
    return chosen_configuration_result
"""
    finding = _only(source)
    assert finding.remediation.kind == REMEDIATION_GUIDANCE
    assert finding.remediation.suggested_replacement is None
    assert "needs wrapping" in finding.remediation.basis
    # The shorter form is still named, so the reader can act on it.
    assert "if flag and" in finding.remediation.text


def test_an_absurdly_long_rewrite_is_dropped_entirely():
    """Past a point, one line is not a simplification in any useful sense."""
    long_call = ".resolve(" + ", ".join(f"option_{i}=True" for i in range(14)) + ")"
    source = (
        "def pick(flag, alpha, beta):\n"
        "    if flag:\n"
        f"        result = alpha{long_call}\n"
        "    else:\n"
        f"        result = beta{long_call}\n"
        "    return result\n"
    )
    assert _run(source) == []


def test_a_rewrite_at_the_width_limit_is_still_offered():
    """The guard drops what is too long, not everything near the boundary."""
    source = """def pick(flag, a, b):
    if flag:
        value = a
    else:
        value = b
    return value
"""
    assert _replacement(source) == "value = a if flag else b"


# --- elif-chain fragments: "N lines can be 1" is false, the one-liner is a bug --
# Probe (2026-11-13, run and restored): emptying the skip-set construction reded
# exactly the two chain tests (the tail refired) while all 47 others stayed green.
# Two earlier probe attempts were discarded as no-ops - one was syntactically
# beside the loop line instead of replacing it, one disabled ALL if/else rules
# and made the no-finding assertions vacuously green. Both are the
# silently-failed-mutation class; the diff was verified before trusting red.

def test_three_arm_assign_chain_gets_no_finding():
    # scan #20 finding #22's exact shape (workbench_target.py): the suggested
    # one-liner lands at the elif's indentation and unconditionally overwrites the
    # variable, silently dropping the chain's first arm. No finding is honest;
    # "can be 1" never is for a chain fragment.
    source = (
        "def f(kind, scan):\n"
        "    if kind == 'working_tree':\n"
        "        digest = scan['diff']\n"
        "    elif kind in {'commit', 'range'}:\n"
        "        digest = clean()\n"
        "    else:\n"
        "        digest = scan['snapshot']\n"
        "    return digest\n"
    )
    assert _run(source) == []


def test_three_arm_return_chain_gets_no_finding():
    # The boolean-return rule has the same elif-tail exposure (scan #20 finding #19
    # quoted an elif inside a three-arm normalization chain).
    source = (
        "def f(x):\n"
        "    if x == 1:\n"
        "        return True\n"
        "    elif x == 2:\n"
        "        return False\n"
        "    else:\n"
        "        return True\n"
    )
    assert _run(source) == []


def test_else_with_single_nested_if_gets_no_finding():
    # `else:` followed by one nested `if` is the same AST shape as an elif tail
    # (orelse[0] is an If) — the skip must cover it too.
    source = (
        "def f(x, y):\n"
        "    if x:\n"
        "        v = 1\n"
        "    else:\n"
        "        if y:\n"
        "            v = 2\n"
        "    return v\n"
    )
    assert _run(source) == []


def test_plain_two_arm_if_else_still_suggested():
    # Negative control: the genuine 2-arm shape keeps its suggestion — the skip
    # must never switch the rule off.
    source = (
        "def f(kind, scan):\n"
        "    if kind == 'working_tree':\n"
        "        digest = scan['diff']\n"
        "    else:\n"
        "        digest = scan['snapshot']\n"
        "    return digest\n"
    )
    findings = _run(source)
    assert len(findings) == 1
    assert "conditional expression" in findings[0].message
