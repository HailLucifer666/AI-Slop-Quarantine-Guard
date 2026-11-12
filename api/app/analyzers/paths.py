"""Shared test/fixture path classifier for the analyzers (SQG001, SQG002).

One vocabulary, one boundary rule, two consumers. A per-detector copy of this
regex is how scan #20 (openai/codex-security, 2026-11-12) happened: SQG002's own
copy matched only whole path segments, so ``tests-ts/`` (dash-suffixed segment),
a ``-fixtures.`` filename (token buried mid-segment) and ``evals/`` (absent from
the vocabulary) all read as production paths, and two fixture tokens came out
CERTAIN / block-eligible — the never-false-block promise broken by a regex.

Deliberately free of analyzer imports: a pure function so the boundary rules
are unit-testable without a diff (see tests/test_paths.py, which pins every
token AND the words the boundary rule must not swallow).
"""

import re

# A test-token must be a DELIMITED word: it starts at a path boundary (segment
# start, or right after / . _ -) and ends at one. That is what keeps
# ``contest.py``, ``latest.md`` and ``testutils/`` out — "test" is only the
# test token when a delimiter or the segment edge says so.
_TEST_TOKEN = re.compile(
    r"(?:^|[/_.-])(?:tests?|testing|testdata|__tests__|__snapshots__|cypress|fixtures?|"
    r"mocks?|__mocks__|specs?|e2e|evals?|examples?|samples?)(?:$|[/_.-])",
    re.IGNORECASE,
)


def in_test_path(path: str) -> bool:
    """True when a path carries a test/fixture token as a delimited word.

    Used to DOWNGRADE, never drop: material under these paths is surfaced as
    advisory, because a real leak does land in test folders — but blocking a PR
    on a fixture violates the never-false-block promise (scan #20).
    """
    return bool(_TEST_TOKEN.search(path.replace("\\", "/")))
