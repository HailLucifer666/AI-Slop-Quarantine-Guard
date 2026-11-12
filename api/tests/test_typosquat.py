"""SQG007 typosquat advisory: near-miss of a popular package flagged HIGH/never-block;
real packages, short names, and unrelated names never flagged (zero-FP bar)."""

from datetime import datetime, timedelta, timezone

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
    assert _closest_popular("pypi", "flsk") == "flask"         # short squat, still caught
    assert _closest_popular("pypi", "yz") is None               # below MIN_LEN entirely
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
async def test_unrelated_name_not_flagged():
    content = "my-internal-helper==0.1.0\n"
    diff = _diff("requirements.txt", ["my-internal-helper==0.1.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": content}))
    assert findings == []


@pytest.mark.asyncio
async def test_short_squat_now_flagged():
    # A short squat ("flsk" vs "flask") must not evade detection just by staying
    # under the old flat length floor — an attacker who knows that rule could
    # trivially bypass it by keeping the name short.
    content = "flsk==1.0.0\n"
    diff = _diff("requirements.txt", ["flsk==1.0.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": content}))
    assert len(findings) == 1
    assert "flask" in findings[0].message
    assert findings[0].block_eligible is False


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


# --- registry-age legitimacy gate (scan #18: bleak vs black) -----------------
# bleak is THE standard cross-platform BLE library (hbldh/bleak, MIT, first PyPI
# release 2018-04-27, verified live 2026-11-13) — two edits from popular 'black',
# so the distance heuristic alone flags a legitimate choice. The gate: when the
# caller supplies a created_fn (scan.py/worker.py inject the cached registry
# lookup), a look-alike whose first release is older than the ADR-025 threshold is
# an established package, not a fresh typosquat. Fail-safe in both directions the
# gate can fail: no created_fn wired → old behaviour (finding stays); created_fn
# returns None (outage, unknown name, PyPI `releases` deprecation) → finding stays.

_ESTABLISHED = datetime(2018, 4, 27, tzinfo=timezone.utc)  # bleak's real first release


@pytest.mark.asyncio
async def test_established_lookalike_not_flagged():
    # The scan-#18 false positive itself: bleak@0.22.0 is a real, 8.5-year-old
    # package. With registry age supplied, the finding must not exist.
    async def bleak_age(ecosystem, name, client):
        assert (ecosystem, name) == ("pypi", "bleak")
        return _ESTABLISHED

    diff = _diff("requirements.txt", ["bleak==0.22.0"])
    ctx = _ctx({"requirements.txt": "bleak==0.22.0\n"})
    ctx["created_fn"] = bleak_age
    assert await check_typosquat(diff, ctx) == []


@pytest.mark.asyncio
async def test_unknown_age_keeps_finding():
    # Negative control: created_fn returning None (registry unreachable, name
    # unknown, or the PyPI `releases` field gone) must NOT turn suppression on.
    async def no_age(ecosystem, name, client):
        return None

    diff = _diff("requirements.txt", ["reqests==1.0.0"])
    ctx = _ctx({"requirements.txt": "reqests==1.0.0\n"})
    ctx["created_fn"] = no_age
    findings = await check_typosquat(diff, ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_young_lookalike_still_flagged():
    # Negative control for the threshold itself: a package days old is exactly the
    # typosquat shape, age data or not. (2026-11-13 mutation probe,
    # run and restored: disabling the age gate reded exactly the bleak cases -
    # this test's sibling unit test and the corpus established-lookalike fixture.)
    async def fresh(ecosystem, name, client):
        return datetime.now(timezone.utc) - timedelta(days=10)

    diff = _diff("requirements.txt", ["reqests==1.0.0"])
    ctx = _ctx({"requirements.txt": "reqests==1.0.0\n"})
    ctx["created_fn"] = fresh
    findings = await check_typosquat(diff, ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_age_gate_off_without_created_fn():
    # Direct callers (and any surface that never wired the gate) keep today's
    # behaviour: advisory findings, no registry call. The corpus replay proves the
    # wired path; this pins the unwired one.
    diff = _diff("requirements.txt", ["bleak==0.22.0"])
    findings = await check_typosquat(diff, _ctx({"requirements.txt": "bleak==0.22.0\n"}))
    assert len(findings) == 1  # still flagged without age data — advisory, never a block


@pytest.mark.asyncio
async def test_naive_registry_timestamp_does_not_crash_the_gate():
    # PyPI upload_time carries no UTC offset, so fromisoformat yields a NAIVE
    # datetime; subtracting it from an aware now() raises TypeError and would
    # kill the whole analyzer (the corpus fixture passed vacuously through the
    # per-analyzer error catch before this was fixed — probed 2026-11-13).
    # The parser must normalize offset-less timestamps to UTC.
    async def pypi_shape(ecosystem, name, client):
        return datetime(2018, 4, 27, 9, 43, 2)  # naive, exactly as PyPI serves it

    diff = _diff("requirements.txt", ["bleak==0.22.0"])
    ctx = _ctx({"requirements.txt": "bleak==0.22.0\n"})
    ctx["created_fn"] = pypi_shape
    assert await check_typosquat(diff, ctx) == []


@pytest.mark.asyncio
async def test_age_threshold_boundary_729_flags_730_suppresses():
    # Pin the ADR-025 boundary exactly: timedelta.days floors, so now-730d has
    # .days == 730 (suppress) and now-729d has .days == 729 (flag).
    diff = _diff("requirements.txt", ["bleak==0.22.0"])

    async def aged(days):
        async def fn(eco, name, client):
            return datetime.now(timezone.utc) - timedelta(days=days)
        return fn

    ctx_on = _ctx({"requirements.txt": "bleak==0.22.0\n"})
    ctx_on["created_fn"] = await aged(730)
    assert await check_typosquat(diff, ctx_on) == []
    ctx_off = _ctx({"requirements.txt": "bleak==0.22.0\n"})
    ctx_off["created_fn"] = await aged(729)
    assert len(await check_typosquat(diff, ctx_off)) == 1


@pytest.mark.asyncio
async def test_raising_created_fn_keeps_the_finding():
    # A producer that RAISES (a future parser bug, a bad override) must degrade to
    # keep-the-finding for that candidate — never abort the analyzer and silence
    # SQG007 for the whole diff (ADR-025's fail-safe covers raises, not just None).
    async def explodes(ecosystem, name, client):
        raise RuntimeError("producer bug")

    diff = _diff("requirements.txt", ["reqests==1.0.0"])
    ctx = _ctx({"requirements.txt": "reqests==1.0.0\n"})
    ctx["created_fn"] = explodes
    findings = await check_typosquat(diff, ctx)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
