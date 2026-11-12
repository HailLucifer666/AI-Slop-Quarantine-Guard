"""Shared test/fixture path classifier — one constant serving SQG001 and SQG002.

Pinned because scan #20 (openai/codex-security, 2026-11-12) produced two CERTAIN
block-eligible findings on fixture paths the old segment-exact regex could not see:
``tests-ts/`` (dash-suffixed segment), ``cli-fixtures.ts`` (token buried mid-segment),
and ``evals/`` (absent from the vocabulary). Every token below is pinned; the attack
cases at the bottom are the words the boundary rule must NOT swallow (contest,
latest, testutils, prospects, evaluation, testflight) — a path classifier that
downgrades real source files would hide real leaks.

Mutation probes (2026-11-12, run and restored): ``in_test_path`` → ``return False``
turned 25 tests red across all three consumers (the 17 match-cases here, the three
SQG002 path-downgrades plus the tests-dir pin, and the SQG001 fixture-path
downgrade); disabling the ``evals?`` token reded exactly the two evals cases.
The classifier is load-bearing everywhere it is consumed.
"""

import pytest

from app.analyzers.paths import in_test_path


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_auth.py",
        "test/conftest.py",
        "tests-ts/cli-fixtures.ts",  # scan #20 finding 2 — dash-suffixed segment
        "sdk/typescript/tests-ts/support/x.ts",  # scan #20 — nested under tests-ts
        "evals/secret-discovery/test_runtime.mts",  # scan #20 finding 3 — evals vocabulary
        "evals/triage-finding/fixtures/repo/package.json",
        "tools/cli-fixtures.ts",  # token delimited mid-segment by '-'
        "src/module.test.ts",
        "src/module.spec.tsx",
        "src/__tests__/auth.ts",
        "packages/a/__mocks__/b.ts",
        "e2e/login.spec.ts",
        "test-data/cases.json",
        "testdata/cases.json",
        "my-tests/only.py",  # '-tests' suffix inside one segment
        "test-utils/helper.ts",
        "tests\\unit\\win.py",  # windows separators normalize to forward slashes
        "TESTS/Auth.py",  # case-insensitive
    ],
)
def test_test_paths_match(path):
    assert in_test_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "contest/submit.py",  # 'test' with no left delimiter
        "latest.md",  # 'test' with no left delimiter
        "src/testutils/load.py",  # 'test' with no right delimiter
        "attest/verify.py",  # 'test' with no left delimiter
        "prospectus/index.ts",  # 'spec' with no left delimiter
        "evaluation/run.py",  # 'eval' with no right delimiter
        "testflight/build.py",  # 'test' with no right delimiter
        "dataset/load.py",
        "app/config.py",
        "lib/math.ts",
        "",  # empty path is nothing at all
    ],
)
def test_non_test_paths_do_not_match(path):
    assert in_test_path(path) is False
