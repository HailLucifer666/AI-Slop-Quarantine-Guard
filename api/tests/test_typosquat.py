"""SQG007 typosquat advisory: near-miss of a popular package flagged HIGH/never-block;
real packages, short names, and unrelated names never flagged (zero-FP bar)."""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.typosquat import (
    _closest_popular,
    _edit_distance_within,
    check_typosquat,
)


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


def _ctx(files: dict[str, str]):
    async def fake_fetch(path):
        return files.get(path)

    return {"repo": "o/r", "head_sha": "abc", "token": "t", "fetch_file": fake_fetch}


# --- unit: distance + closest-popular guards --------------------------------

def test_edit_distance_within_bound():
    assert _edit_distance_within("reqests", "requests", 2) == 1
    assert _edit_distance_within("requests", "requests", 2) == 0
    assert _edit_distance_within("totally-different", "requests", 2) is None


def test_closest_popular_guards():
    assert _closest_popular("pypi", "reqests") == "requests"   # 1 edit away
    assert _closest_popular("pypi", "requests") is None        # it IS the real one
    assert _closest_popular("pypi", "flsk") is None            # too short (< MIN_LEN)
    assert _closest_popular("pypi", "my-internal-helper") is None  # nowhere near
    assert _closest_popular("crates", "reqests") is None       # no list for ecosystem


# --- end-to-end through the analyzer ----------------------------------------

@pytest.mark.asyncio
async def test_pypi_typo_flagged_advisory():
    diff = _diff("requirements.txt", ["reqests==1.0.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": "reqests==1.0.0\n"}))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG007"
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False          # suspicion, never a block
    assert "requests" in f.message            # names the look-alike target


@pytest.mark.asyncio
async def test_npm_typo_flagged():
    content = '{"dependencies": {"expres": "^4.0.0"}}'
    diff = _diff("package.json", ['    "expres": "^4.0.0",'])
    findings = await check_typosquat(diff, _ctx({"package.json": content}))
    assert len(findings) == 1
    assert "express" in findings[0].message


@pytest.mark.asyncio
async def test_real_popular_package_not_flagged():
    diff = _diff("requirements.txt", ["requests==2.31.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": "requests==2.31.0\n"}))
    assert findings == []


@pytest.mark.asyncio
async def test_short_and_unrelated_names_not_flagged():
    content = "flsk==1.0.0\nmy-internal-helper==0.1.0\n"
    diff = _diff("requirements.txt", ["flsk==1.0.0", "my-internal-helper==0.1.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": content}))
    assert findings == []  # short name + unrelated name both safe


@pytest.mark.asyncio
async def test_preexisting_dep_not_on_added_line_skipped():
    # 'reqests' is in the manifest but only 'flask' was added in this PR.
    content = "reqests==1.0.0\nflask==3.0.0\n"
    diff = _diff("requirements.txt", ["flask==3.0.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": content}))
    assert findings == []


@pytest.mark.asyncio
async def test_unfetchable_manifest_silent():
    diff = _diff("requirements.txt", ["reqests==1.0.0"])
    findings = await check_typosquat(diff, _ctx({}))  # fetch returns None
    assert findings == []


@pytest.mark.asyncio
async def test_non_manifest_file_ignored():
    diff = _diff("app/main.py", ["reqests = 1  # not a manifest"])
    findings = await check_typosquat(diff, _ctx({"app/main.py": "x"}))
    assert findings == []
