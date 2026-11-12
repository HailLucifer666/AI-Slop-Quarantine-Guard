"""SQG001 analyzer: zero-FP gate. Offline via injected fetch_file + check_exists.

Positive set: hallucinated packages must be flagged CERTAIN at the exact line.
Negative set: real packages, clean diffs, and local/git/url refs must yield NOTHING.
"""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.dependencies import check_dependencies
from app.registries import Existence


def _ctx(files: dict[str, str], existence: dict[str, Existence]):
    """Build a repo_context with injected file fetch + registry lookup."""

    async def fetch_file(path: str):
        return files.get(path)

    async def fake_check_exists(ecosystem: str, name: str, client):
        return existence.get(name, Existence.EXISTS)

    return {"fetch_file": fetch_file, "check_exists": fake_check_exists}


# --- positive set --------------------------------------------------------

FAKE_REQ_DIFF = """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 requests==2.31.0
+quantumllm-helper==9.9.9
"""


@pytest.mark.asyncio
async def test_hallucinated_pypi_flagged():
    files = {"requirements.txt": "requests==2.31.0\nquantumllm-helper==9.9.9\n"}
    ctx = _ctx(files, {"quantumllm-helper": Existence.MISSING})
    findings = await check_dependencies(FAKE_REQ_DIFF, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG001"
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True
    assert f.line_start == 2
    assert "quantumllm-helper" in f.message


FAKE_PKG_JSON_DIFF = """\
--- a/package.json
+++ b/package.json
@@ -2,3 +2,4 @@
   "dependencies": {
     "left-pad": "^1.0.0",
+    "@evil/hallucinated-ui": "^3.0.0",
     "react": "^18.0.0"
   }
"""


@pytest.mark.asyncio
async def test_hallucinated_scoped_npm_flagged():
    files = {
        "package.json": (
            '{"dependencies": {"left-pad": "^1.0.0", '
            '"@evil/hallucinated-ui": "^3.0.0", "react": "^18.0.0"}}'
        )
    }
    ctx = _ctx(files, {"@evil/hallucinated-ui": Existence.MISSING})
    findings = await check_dependencies(FAKE_PKG_JSON_DIFF, ctx)

    assert [f.message for f in findings if "@evil/hallucinated-ui" in f.message]
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN


# --- private-registry false-block guard -----------------------------------

@pytest.mark.asyncio
async def test_pip_extra_index_downgrades_missing_to_advisory():
    # A public-registry 404 is NOT proof of a hallucination when the file itself
    # declares a private index — the name may be a real internal package.
    content = "--extra-index-url https://pypi.mycompany.com/simple\nmycompany-internal-tool==1.0.0\n"
    files = {"requirements.txt": content}
    diff = (
        "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -0,0 +1,2 @@\n"
        "+--extra-index-url https://pypi.mycompany.com/simple\n"
        "+mycompany-internal-tool==1.0.0\n"
    )
    ctx = _ctx(files, {"mycompany-internal-tool": Existence.MISSING})
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False
    assert "private" in findings[0].message.lower()


@pytest.mark.asyncio
async def test_npmrc_scope_downgrades_missing_to_advisory():
    files = {
        "package.json": '{"dependencies": {"@myorg/internal-tool": "^1.0.0"}}',
        ".npmrc": "@myorg:registry=https://npm.mycompany.com/\n",
    }
    diff = (
        "--- a/package.json\n+++ b/package.json\n@@ -0,0 +1,1 @@\n"
        '+  "dependencies": {"@myorg/internal-tool": "^1.0.0"}\n'
    )
    ctx = _ctx(files, {"@myorg/internal-tool": Existence.MISSING})
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_npmrc_scope_does_not_shield_unscoped_hallucination():
    # A private scope for @myorg must not blanket-downgrade an unrelated,
    # unscoped hallucinated package in the same file.
    files = {
        "package.json": (
            '{"dependencies": {"@myorg/internal-tool": "^1.0.0", '
            '"quantumllm-helper": "^1.0.0"}}'
        ),
        ".npmrc": "@myorg:registry=https://npm.mycompany.com/\n",
    }
    diff = (
        "--- a/package.json\n+++ b/package.json\n@@ -0,0 +1,2 @@\n"
        '+  "@myorg/internal-tool": "^1.0.0",\n'
        '+  "quantumllm-helper": "^1.0.0"\n'
    )
    ctx = _ctx(files, {
        "@myorg/internal-tool": Existence.MISSING,
        "quantumllm-helper": Existence.MISSING,
    })
    findings = await check_dependencies(diff, ctx)

    by_name = {f.message: f for f in findings}
    scoped = next(f for msg, f in by_name.items() if "@myorg/internal-tool" in msg)
    unscoped = next(f for msg, f in by_name.items() if "quantumllm-helper" in msg)
    assert scoped.confidence is Confidence.HIGH and scoped.block_eligible is False
    assert unscoped.confidence is Confidence.CERTAIN and unscoped.block_eligible is True


# --- negative set (zero false positives) ---------------------------------

@pytest.mark.asyncio
async def test_real_package_not_flagged():
    files = {"requirements.txt": "requests==2.31.0\n"}
    diff = """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -0,0 +1,1 @@
+requests==2.31.0
"""
    findings = await check_dependencies(diff, _ctx(files, {}))
    assert findings == []


@pytest.mark.asyncio
async def test_clean_diff_no_manifest():
    diff = """\
--- a/app/foo.py
+++ b/app/foo.py
@@ -0,0 +1,1 @@
+import quantumllm_helper
"""
    # Even though it imports a fake-looking module, no manifest changed → silent.
    findings = await check_dependencies(diff, _ctx({}, {}))
    assert findings == []


@pytest.mark.asyncio
async def test_local_and_git_refs_never_queried():
    """A line added with file:/git+ refs is filtered by the parser → no finding,
    even if the registry would 404 it."""
    files = {
        "requirements.txt": (
            "git+https://github.com/x/y.git\n"
            "./local-pkg\n"
        )
    }
    diff = """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -0,0 +1,2 @@
+git+https://github.com/x/y.git
+./local-pkg
"""
    # Map everything to MISSING — if anything were queried it would wrongly flag.
    ctx = _ctx(files, {"y": Existence.MISSING, "local-pkg": Existence.MISSING})
    findings = await check_dependencies(diff, ctx)
    assert findings == []


@pytest.mark.asyncio
async def test_unfetchable_manifest_is_silent():
    diff = FAKE_REQ_DIFF
    findings = await check_dependencies(diff, _ctx({}, {"quantumllm-helper": Existence.MISSING}))
    assert findings == []  # fetch_file returns None → can't parse → no FP


# --- fail-safe: registry outage is advisory, never blocking ---------------

@pytest.mark.asyncio
async def test_registry_unknown_is_high_advisory():
    files = {"requirements.txt": "requests==2.31.0\nmaybe-real==1.0\n"}
    diff = """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,1 +1,2 @@
 requests==2.31.0
+maybe-real==1.0
"""
    ctx = _ctx(files, {"maybe-real": Existence.UNKNOWN})
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


# --- workspace/fixture downgrades (scan #20 finding 1) ----------------------

# Probes (2026-11-12, run and restored): disabling the diff-manifest name union
# in dependencies.py reded exactly
# test_manifest_declared_name_downgraded_from_diff_manifests; removing the
# fixture-path rung reded test_fixture_path_manifest_downgraded; the plain-404
# negative control stayed green throughout — the downgrades never switch
# SQG001's block off.

_PKG_DIFF = """\
--- a/app/package.json
+++ b/app/package.json
@@ -1,1 +1,1 @@
-{}
+{"name": "app", "dependencies": {"helper": "1.0.0"}}
"""


@pytest.mark.asyncio
async def test_workspace_declared_name_downgraded():
    # A public-registry 404 for a name THIS repo declares is a workspace-internal
    # package, not a hallucination (scan-mode set arrives via repo_context,
    # per-ecosystem: an npm declaration answers only npm questions).
    files = {"app/package.json": '{"name": "app", "dependencies": {"helper": "1.0.0"}}'}
    ctx = _ctx(files, {"helper": Existence.MISSING})
    ctx["workspace_names"] = {"npm": {"helper"}}
    findings = await check_dependencies(_PKG_DIFF, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "manifest in this repo declares" in f.message


@pytest.mark.asyncio
async def test_workspace_downgrade_is_ecosystem_scoped():
    # Review finding (2026-11-12): an npm declaration answers npm questions only.
    # A PyPI 404 of the same name is still a hallucinated package and must block.
    files = {"requirements.txt": "helper==1.0.0\n"}
    diff = (
        "--- a/requirements.txt\n+++ b/requirements.txt\n"
        "@@ -1,1 +1,2 @@\n requests==2.31.0\n+helper==1.0.0\n"
    )
    ctx = _ctx(files, {"helper": Existence.MISSING})
    ctx["workspace_names"] = {"npm": {"helper"}}
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True


@pytest.mark.asyncio
async def test_pypi_name_normalization_matches_declared_name():
    # Review finding (2026-11-12): PEP 503 normalization — a pyproject declaring
    # `my_lib` while the dependency spells it `my-lib` is the repo's own package
    # either way; the raw-string membership test used to block on it.
    files = {"requirements.txt": "my-lib==0.1.0\n"}
    diff = (
        "--- a/requirements.txt\n+++ b/requirements.txt\n"
        "@@ -1,1 +1,2 @@\n requests==2.31.0\n+my-lib==0.1.0\n"
    )
    ctx = _ctx(files, {"my-lib": Existence.MISSING})
    ctx["workspace_names"] = {"pypi": {"my_lib"}}
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_manifest_declared_name_downgraded_from_diff_manifests():
    # PR mode has no workspace set — the detector derives it from the manifests the
    # diff itself touches (a new workspace package added in the same PR).
    files = {
        "packages/helper/package.json": '{"name": "helper"}',
        "app/package.json": '{"dependencies": {"helper": "1.0.0"}}',
    }
    diff = (
        _PKG_DIFF
        + "--- a/packages/helper/package.json\n"
        + "+++ b/packages/helper/package.json\n"
        + "@@ -0,0 +1,1 @@\n"
        + '+{"name": "helper"}\n'
    )
    ctx = _ctx(files, {"helper": Existence.MISSING})
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False


@pytest.mark.asyncio
async def test_fixture_path_manifest_downgraded():
    # scan #20 finding 1: a fixture manifest under evals/.../fixtures/ carries a
    # fake package on purpose — surfaced as advisory, never blocked.
    fixture_diff = _PKG_DIFF.replace("app/", "evals/triage-finding/fixtures/repo/")
    files = {"evals/triage-finding/fixtures/repo/package.json": '{"dependencies": {"helper": "1.0.0"}}'}
    ctx = _ctx(files, {"helper": Existence.MISSING})
    findings = await check_dependencies(fixture_diff, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "test/fixture path" in f.message


@pytest.mark.asyncio
async def test_fixture_declared_name_does_not_legitimize_production_404():
    # Review finding (2026-11-12): a fixture manifest's declared name must not feed
    # the workspace rung — a production-path 404 of that name is still a block.
    # The fixture manifest itself is skipped during collection (its own 404, if it
    # had one, is carried by the fixture-path rung alone).
    files = {
        "app/package.json": '{"dependencies": {"helper": "1.0.0"}}',
        "tests/fixtures/demo/package.json": '{"name": "helper"}',
    }
    diff = (
        _PKG_DIFF
        + "--- a/tests/fixtures/demo/package.json\n"
        + "+++ b/tests/fixtures/demo/package.json\n"
        + "@@ -0,0 +1,1 @@\n"
        + '+{"name": "helper"}\n'
    )
    ctx = _ctx(files, {"helper": Existence.MISSING})
    findings = await check_dependencies(diff, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True


@pytest.mark.asyncio
async def test_plain_404_still_blocks_with_no_downgrade_signals():
    # Negative control: without a workspace declaration or fixture path, a clean 404
    # is still CERTAIN and block-eligible — the downgrades must not switch SQG001 off.
    files = {"app/package.json": '{"dependencies": {"helper": "1.0.0"}}'}
    ctx = _ctx(files, {"helper": Existence.MISSING})
    findings = await check_dependencies(_PKG_DIFF, ctx)

    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True
