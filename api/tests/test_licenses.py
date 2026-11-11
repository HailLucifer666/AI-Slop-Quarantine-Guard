"""SQG005 license scanner: advisory on copyleft deps, fail-safe, only PR-introduced deps."""


import pytest

from app.analyzers.base import Confidence
from app.analyzers.licenses import _COPYLEFT, _pypi_license_label, check_licenses


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


def _ctx(files: dict[str, str], licenses: dict[str, str], *, registry_down=False):
    """Build (repo_context, kwargs) with injected fetch + license lookup.

    files: {path: full_content}. licenses: {name: label}. registry_down: lookup → None.
    """
    async def fake_fetch(repo, path, ref, token):
        return files.get(path)

    async def fake_license(ecosystem, name, client):
        if registry_down:
            return None
        return licenses.get(name)  # None if absent → silent

    ctx = {"repo": "o/r", "head_sha": "abc", "token": "t"}
    return ctx, {"fetch_file": fake_fetch, "fetch_license": fake_license}


# --- positive: copyleft deps flagged ---------------------------------------

@pytest.mark.asyncio
async def test_gpl_pypi_dep_flagged():
    diff = _diff("requirements.txt", ["somelib==1.0"])
    ctx, kw = _ctx({"requirements.txt": "somelib==1.0\n"}, {"somelib": "GPL-3.0-or-later"})
    findings = await check_licenses(diff, ctx, **kw)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG005"
    assert f.confidence is Confidence.MEDIUM
    assert f.block_eligible is False
    assert "somelib" in f.message


@pytest.mark.asyncio
async def test_agpl_npm_dep_flagged():
    diff = _diff("package.json", ['    "copyleftpkg": "1.2.3",'])
    content = '{"dependencies": {"copyleftpkg": "1.2.3"}}'
    ctx, kw = _ctx({"package.json": content}, {"copyleftpkg": "AGPL-3.0"})
    findings = await check_licenses(diff, ctx, **kw)
    assert len(findings) == 1


@pytest.mark.asyncio
async def test_pypi_gpl_classifier_flagged():
    diff = _diff("requirements.txt", ["lib==2.0"])
    label = "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"
    ctx, kw = _ctx({"requirements.txt": "lib==2.0\n"}, {"lib": label})
    findings = await check_licenses(diff, ctx, **kw)
    assert len(findings) == 1


# --- negative / fail-safe controls -----------------------------------------

@pytest.mark.asyncio
async def test_permissive_license_silent():
    diff = _diff("requirements.txt", ["requests==2.0"])
    ctx, kw = _ctx({"requirements.txt": "requests==2.0\n"}, {"requests": "Apache-2.0"})
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_no_license_metadata_silent():
    diff = _diff("requirements.txt", ["lib==1.0"])
    ctx, kw = _ctx({"requirements.txt": "lib==1.0\n"}, {})  # lookup returns None
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_registry_unreachable_never_blocks():
    diff = _diff("requirements.txt", ["lib==1.0"])
    ctx, kw = _ctx({"requirements.txt": "lib==1.0\n"}, {"lib": "GPL-3.0"}, registry_down=True)
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []  # outage → silent


@pytest.mark.asyncio
async def test_dep_not_on_added_line_skipped():
    diff = _diff("requirements.txt", ["newlib==1.0"])
    content = "oldgpl==1.0\nnewlib==1.0\n"
    ctx, kw = _ctx({"requirements.txt": content}, {"oldgpl": "GPL-3.0", "newlib": "MIT"})
    findings = await check_licenses(diff, ctx, **kw)
    assert all("oldgpl" not in f.message for f in findings)


@pytest.mark.asyncio
async def test_short_name_inside_unrelated_word_not_flagged():
    # A bare substring test would match npm "ms" inside "milliseconds" and wrongly
    # treat the copyleft "ms" package as touched by this PR when it wasn't.
    diff = _diff("package.json", ["  // cache for milliseconds precision"])
    content = '{"dependencies": {"ms": "2.1.2", "other": "1.0.0"}}'
    ctx, kw = _ctx({"package.json": content}, {"ms": "GPL-3.0", "other": "MIT"})
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_unfetchable_manifest_silent():
    diff = _diff("requirements.txt", ["lib==1.0"])
    ctx, kw = _ctx({}, {"lib": "GPL-3.0"})  # fetch returns None
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []


@pytest.mark.asyncio
async def test_unsupported_ecosystem_silent():
    diff = _diff("Cargo.toml", ['serde = "1.0"'])
    ctx, kw = _ctx({"Cargo.toml": '[dependencies]\nserde = "1.0"\n'}, {"serde": "GPL-3.0"})
    findings = await check_licenses(diff, ctx, **kw)
    assert findings == []  # crates not supported in MVP


# --- PyPI label assembly: structured-only, no full-text false positives ----

def test_pypi_label_ignores_full_license_text_that_mentions_gpl():
    # pandas/scipy/matplotlib paste the whole BSD/PSF license into `license`, and
    # that text mentions "GPL" — but the package is BSD. The label must derive from
    # the trove classifier, not the body, so no copyleft match fires.
    info = {
        "license": "BSD 3-Clause License\n\n... this license is compatible with the GPL ...\n",
        "license_expression": None,
        "classifiers": ["License :: OSI Approved :: BSD License", "Programming Language :: Python"],
    }
    label = _pypi_license_label(info)
    assert "BSD" in label
    assert _COPYLEFT.search(label) is None  # not falsely flagged copyleft


def test_pypi_label_flags_real_gpl_via_classifier():
    info = {
        "license": "Long full GPL license text...\nwith newlines\n",  # ignored (multi-line body)
        "license_expression": None,
        "classifiers": ["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"],
    }
    label = _pypi_license_label(info)
    assert _COPYLEFT.search(label) is not None


def test_pypi_label_keeps_short_spdx_identifier():
    info = {"license": "GPL-3.0-only", "license_expression": None, "classifiers": []}
    assert _COPYLEFT.search(_pypi_license_label(info)) is not None


# --- Packagist: license declared in the lockfile, no registry call -------------

COMPOSER_LOCK_GPL = """{
  "packages": [
    {"name": "monolog/monolog", "version": "1.25.3", "license": ["MIT"]},
    {"name": "copyleft/lib", "version": "2.0.0", "license": ["GPL-3.0-or-later"]},
    {"name": "nolicense/pkg", "version": "1.0.0"}
  ],
  "packages-dev": [
    {"name": "dual/licensed", "version": "1.0.0", "license": ["MIT", "LGPL-2.1"]}
  ]
}
"""


def _lock_diff() -> str:
    lines = COMPOSER_LOCK_GPL.splitlines()
    body = "".join(f"+{line}\n" for line in lines)
    return f"--- a/composer.lock\n+++ b/composer.lock\n@@ -0,0 +1,{len(lines)} @@\n{body}"


@pytest.mark.asyncio
async def test_composer_lock_copyleft_flagged_without_any_registry_call():
    """Composer records the license in the lockfile, so this needs no network.

    The injected fetcher raises if the license path is ever consulted — proof the
    finding came from the repository's own file, which is what `tool` claims.
    """
    async def fetch_file(repo, path, ref, token):
        return COMPOSER_LOCK_GPL if path == "composer.lock" else None

    async def must_not_call(ecosystem, name, client):
        raise AssertionError("composer.lock licenses must not hit a registry")

    findings = await check_licenses(
        _lock_diff(), {"repo": "o/r", "head_sha": "s", "token": "t"},
        fetch_file=fetch_file, fetch_license=must_not_call,
    )
    names = {f.message.split("'")[1] for f in findings}
    assert "copyleft/lib" in names
    assert "dual/licensed" in names       # LGPL half of a dual license still warrants review
    assert "monolog/monolog" not in names  # MIT
    assert "nolicense/pkg" not in names    # no metadata → silent, never inferred
    assert all(f.tool == "lockfile" for f in findings)
    assert all(f.block_eligible is False for f in findings)


@pytest.mark.asyncio
async def test_composer_lock_findings_are_advisory_medium():
    async def fetch_file(repo, path, ref, token):
        return COMPOSER_LOCK_GPL

    findings = await check_licenses(
        _lock_diff(), {"repo": "o/r", "head_sha": "s", "token": "t"}, fetch_file=fetch_file
    )
    assert findings and all(f.confidence is Confidence.MEDIUM for f in findings)


@pytest.mark.asyncio
async def test_malformed_composer_lock_is_silent():
    async def fetch_file(repo, path, ref, token):
        return "{not json"

    assert await check_licenses(
        _lock_diff(), {"repo": "o/r", "head_sha": "s", "token": "t"}, fetch_file=fetch_file
    ) == []
