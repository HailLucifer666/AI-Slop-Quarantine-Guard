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
