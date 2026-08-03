"""SQG004 CVE scanner: advisory HIGH on pinned vulns, fail-safe, only PR-introduced pins."""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.vulns import check_vulnerabilities


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


def _ctx(files: dict[str, str], *, vulns=None, osv_down=False, seen=None):
    """Build (repo_context, kwargs) with injected fetch + batched OSV query.

    files: {path: full_content}. vulns: advisory list the fake batch returns per pin.
    osv_down: batch returns None for every pin (unreachable) to exercise the fail-safe.
    seen: optional list — the fake batch appends the pins it was asked to resolve, so a
          test can assert dedupe/cap behaviour (how many unique pins hit the network).
    """
    async def fake_fetch(repo, path, ref, token):
        return files.get(path)

    async def fake_batch(pins, client):
        if seen is not None:
            seen.extend(pins)
        if osv_down:
            return {p: None for p in pins}
        return {p: (vulns if vulns is not None else []) for p in pins}

    ctx = {"repo": "o/r", "head_sha": "abc", "token": "t"}
    return ctx, {"fetch_file": fake_fetch, "query_batch": fake_batch}


# --- positive: known vuln on an added pin ----------------------------------

@pytest.mark.asyncio
async def test_pip_pinned_vuln_flagged():
    diff = _diff("requirements.txt", ["requests==2.19.0"])
    ctx, kw = _ctx({"requirements.txt": "requests==2.19.0\n"}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG004"
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "GHSA-xxxx" in f.message


@pytest.mark.asyncio
async def test_hash_pinned_vuln_still_flagged():
    # pip's own hash-pinning convention (--hash=...) used to make the fully-anchored
    # regex miss the pin entirely — exactly the security-conscious style that most
    # needs OSV coverage.
    line = "requests==2.19.0 --hash=sha256:abc123def456"
    diff = _diff("requirements.txt", [line])
    ctx, kw = _ctx({"requirements.txt": line + "\n"}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    assert "GHSA-xxxx" in findings[0].message


@pytest.mark.asyncio
async def test_marker_suffixed_vuln_still_flagged():
    line = 'requests==2.19.0; python_version>="3.8"'
    diff = _diff("requirements.txt", [line])
    ctx, kw = _ctx({"requirements.txt": line + "\n"}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_wildcard_version_still_not_treated_as_exact_pin():
    # "1.2.*" is a range, not an exact pin — must not be misread as pinned to "1.2".
    diff = _diff("requirements.txt", ["requests==1.2.*"])
    ctx, kw = _ctx({"requirements.txt": "requests==1.2.*\n"}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_npm_exact_vuln_flagged():
    diff = _diff("package.json", ['    "lodash": "4.17.4",'])
    content = '{"dependencies": {"lodash": "4.17.4"}}'
    ctx, kw = _ctx({"package.json": content}, vulns=[{"id": "CVE-2019-0001"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


# --- negative / fail-safe controls -----------------------------------------

@pytest.mark.asyncio
async def test_no_vulns_silent():
    diff = _diff("requirements.txt", ["requests==2.32.0"])
    ctx, kw = _ctx({"requirements.txt": "requests==2.32.0\n"}, vulns=[])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_osv_unreachable_never_blocks():
    diff = _diff("requirements.txt", ["requests==2.19.0"])
    ctx, kw = _ctx({"requirements.txt": "requests==2.19.0\n"}, osv_down=True)
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []  # outage → silent, never a finding


@pytest.mark.asyncio
async def test_range_spec_not_queried():
    # Caret range can't be exactly pinned → never queried, even if "vulns" exist.
    diff = _diff("package.json", ['    "lodash": "^4.17.4",'])
    content = '{"dependencies": {"lodash": "^4.17.4"}}'
    ctx, kw = _ctx({"package.json": content}, vulns=[{"id": "CVE-2019-0001"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_pin_not_on_added_line_skipped():
    # Manifest touched, but the vulnerable pin is pre-existing (not added).
    diff = _diff("requirements.txt", ["flask==3.0.0"])
    content = "requests==2.19.0\nflask==3.0.0\n"
    ctx, kw = _ctx({"requirements.txt": content}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    # only flask is on an added line; requests is pre-existing and must not appear
    assert all("requests" not in f.message for f in findings)


@pytest.mark.asyncio
async def test_unfetchable_manifest_silent():
    diff = _diff("requirements.txt", ["requests==2.19.0"])
    ctx, kw = _ctx({}, vulns=[{"id": "GHSA-xxxx"}])  # fetch returns None
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_non_manifest_file_silent():
    diff = _diff("app/main.py", ["requests==2.19.0  # not a manifest"])
    ctx, kw = _ctx({"app/main.py": "x"}, vulns=[{"id": "GHSA-xxxx"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []


# --- lockfiles: full resolved tree, exact pins (Sprint B) ------------------

@pytest.mark.asyncio
async def test_poetry_lock_vuln_flagged():
    # name + version on separate lines — the lockfile line finder must still pair them.
    content = '[[package]]\nname = "requests"\nversion = "2.19.0"\n'
    diff = _diff("poetry.lock", ['name = "requests"', 'version = "2.19.0"'])
    ctx, kw = _ctx({"poetry.lock": content}, vulns=[{"id": "GHSA-pppp"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    assert findings[0].rule_id == "SQG004"
    assert findings[0].block_eligible is False  # advisory, always


@pytest.mark.asyncio
async def test_package_lock_transitive_vuln_flagged():
    content = (
        '{"lockfileVersion": 3, "packages": {'
        '"": {"name": "root"}, "node_modules/lodash": {"version": "4.17.4"}}}'
    )
    diff = _diff("package-lock.json", ['"node_modules/lodash": {', '"version": "4.17.4"'])
    ctx, kw = _ctx({"package-lock.json": content}, vulns=[{"id": "CVE-2020-8203"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    assert "lodash" in findings[0].message


@pytest.mark.asyncio
async def test_go_sum_vuln_flagged():
    content = "github.com/foo/bar v1.2.3 h1:abc=\ngithub.com/foo/bar v1.2.3/go.mod h1:def=\n"
    diff = _diff("go.sum", ["github.com/foo/bar v1.2.3 h1:abc="])
    ctx, kw = _ctx({"go.sum": content}, vulns=[{"id": "GO-2023-0001"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert len(findings) == 1
    assert "github.com/foo/bar" in findings[0].message


@pytest.mark.asyncio
async def test_lockfile_osv_unreachable_never_blocks():
    content = '[[package]]\nname = "requests"\nversion = "2.19.0"\n'
    diff = _diff("poetry.lock", ['name = "requests"', 'version = "2.19.0"'])
    ctx, kw = _ctx({"poetry.lock": content}, osv_down=True)
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []  # outage → silent


@pytest.mark.asyncio
async def test_malformed_lockfile_silent():
    diff = _diff("package-lock.json", ["{ not valid json"])
    ctx, kw = _ctx({"package-lock.json": "{ not valid json"}, vulns=[{"id": "X"}])
    findings = await check_vulnerabilities(diff, ctx, **kw)
    assert findings == []  # unparseable → no guess


# --- the hang fix: dedupe + batch + cap (Sprint B regression) ---------------

@pytest.mark.asyncio
async def test_repeated_pins_hit_the_network_once():
    # The same pin on two added lines must be queried ONCE, not twice — this is the
    # dedupe that stops a big lockfile from firing hundreds of duplicate OSV calls.
    seen: list = []
    content = "requests==2.19.0\nrequests==2.19.0\n"
    diff = _diff("requirements.txt", ["requests==2.19.0", "requests==2.19.0"])
    ctx, kw = _ctx({"requirements.txt": content}, vulns=[], seen=seen)
    await check_vulnerabilities(diff, ctx, **kw)
    assert seen == [("pypi", "requests", "2.19.0")]  # one unique pin queried


@pytest.mark.asyncio
async def test_unique_pins_capped(monkeypatch):
    # A pathologically large tree is capped (and the skip is logged) so a scan can
    # never stall on an unbounded number of lookups.
    monkeypatch.setattr("app.analyzers.vulns._MAX_PINS", 2)
    seen: list = []
    pins = [f"pkg{i}==1.0.{i}" for i in range(5)]
    ctx, kw = _ctx({"requirements.txt": "\n".join(pins) + "\n"}, vulns=[], seen=seen)
    await check_vulnerabilities(_diff("requirements.txt", pins), ctx, **kw)
    assert len(seen) == 2  # only the cap's worth of unique pins reached the network


@pytest.mark.asyncio
async def test_one_batched_call_for_many_distinct_pins():
    # Many distinct pins resolve through the single injected batch function — the
    # production path collapses them into one /v1/querybatch request.
    calls: list = []

    async def counting_batch(pins, client):
        calls.append(list(pins))
        return {p: [] for p in pins}

    pins = [f"pkg{i}==1.0.{i}" for i in range(50)]
    ctx = {"repo": "o/r", "head_sha": "abc", "token": "t"}

    async def fake_fetch(repo, path, ref, token):
        return "\n".join(pins) + "\n"

    await check_vulnerabilities(
        _diff("requirements.txt", pins), ctx,
        fetch_file=fake_fetch, query_batch=counting_batch,
    )
    assert len(calls) == 1                # one batch invocation, not 50
    assert len(calls[0]) == 50            # all distinct pins in it
