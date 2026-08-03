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
