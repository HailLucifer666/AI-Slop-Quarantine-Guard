"""Gate D guard: every false-positive shape from the 2026-11-27 scans, in ONE repo.

Each shape below produced a wrong or misclassified finding in a real scan — #37
(obra/superpowers) or #38 (firecrawl/firecrawl). They are fed through the analyzers
together so a later change to any single rule cannot quietly reintroduce a
neighbouring shape, and so the corpus is derived from the incident (real paths,
real values, real advisory payloads) rather than from the fix.

The registry and OSV fakes are deliberately hostile: they answer exactly as the real
services did that day. Any finding here is a regression, not a judgment call.
"""

import pytest

from app.analyzers.dependencies import check_dependencies
from app.analyzers.placeholders import check_placeholders
from app.analyzers.sast import check_sast
from app.analyzers.secrets import check_secrets
from app.analyzers.typosquat import check_typosquat
from app.analyzers.vulns import check_vulnerabilities
from app.registries import Existence

# --- the corpus: one file per shape, real paths and values ------------------

FILES = {
    # SQG001/SQG007: npm alias. The label 404s; the target exists.
    "apps/api/package.json": (
        '{"dependencies": {"typescript-7": "npm:typescript@7.0.2", '
        '"left-pad": "^1.0.0"}}'
    ),
    # SQG004: checksum ledger holding versions the build never selects.
    "apps/api/sharedLibs/go-html-to-md/go.sum": (
        "golang.org/x/crypto v0.13.0 h1:abc=\n"
        "golang.org/x/crypto v0.31.0 h1:def=\n"
    ),
    # SQG004: the build list — one module, no advisory.
    "apps/api/sharedLibs/go-html-to-md/go.mod": (
        "module html-to-markdown.go\n\n"
        "go 1.25.0\n\n"
        "require github.com/firecrawl/html-to-markdown v0.0.0-20260312013131-1af9901a5d61\n\n"
        "require golang.org/x/net v0.55.0 // indirect\n"
    ),
    # SQG004: a maintenance notice, not a vulnerability.
    "apps/api/native/Cargo.lock": '[[package]]\nname = "chrono"\nversion = "0.4.45"\n',
    # SQG002: a Redis cache key whose identifier ends in _KEY.
    "apps/api/src/scraper/scrapeURL/engines/wikipedia/index.ts": (
        'const REDIS_TOKEN_KEY = "wikipedia_enterprise:access_token";\n'
    ),
    # SQG006: literal-only markup assigned to innerHTML.
    "skills/brainstorming/scripts/helper.js": (
        "function showTombstone(el) {\n"
        "  el.innerHTML = '<div style=\"max-width:480px\">' +\n"
        "    '<p style=\"margin:0\">Companion paused</p></div>';\n"
        "}\n"
    ),
    # SQG003: a module doc comment whose English contains "rest of the code".
    "apps/api/src/service/service.ts": (
        "/*\n"
        " * The service: what one deployment of the API is made of, built once from a\n"
        " * config and read by the rest of the code.\n"
        " */\n"
        "export const serviceName = 'api';\n"
    ),
    # SQG003: a `...` prose line inside a module docstring.
    "apps/python-sdk/firecrawl/v2/methods/research_docs.py": (
        '"""Canonical docstrings for the research paper index.\n'
        "\n"
        "...\n"
        '"""\n'
        "ARCHIVE: dict = {}\n"
    ),
}

ADDED_BY_FILE = {path: list(enumerate(text.splitlines(), 1)) for path, text in FILES.items()}

REPO_CONTEXT = {
    "files": FILES,
    "added_by_file": ADDED_BY_FILE,
    "mode": "repo",
    "ast_cache": {},
    "repo": "firecrawl/firecrawl",
    "head_sha": "abc",
    "token": "t",
}


async def _fetch(path: str):
    return FILES.get(path)


async def _fetch4(repo: str, path: str, ref: str, token: str):
    return FILES.get(path)


# The exact OSV payload shape that produced the chrono finding on 2026-11-27:
# informational is on the RANGE's database_specific, and there is no fixed event.
INFORMATIONAL = {
    "id": "RUSTSEC-2026-0543",
    "summary": "chrono is unmaintained",
    "affected": [{
        "package": {"name": "chrono", "ecosystem": "crates.io"},
        "ranges": [{
            "type": "SEMVER",
            "events": [{"introduced": "0.0.0-0"}],
            "database_specific": {"informational": "unmaintained"},
        }],
    }],
}


def _deps_ctx() -> dict:
    """Registry answers as npm did: the target exists, the alias label 404s."""
    async def fake_exists(ecosystem: str, name: str, client):
        return {
            "typescript": Existence.EXISTS,
            "left-pad": Existence.EXISTS,
            "typescript-7": Existence.MISSING,
        }.get(name, Existence.EXISTS)

    return {**REPO_CONTEXT, "fetch_file": _fetch, "check_exists": fake_exists}


@pytest.mark.asyncio
async def test_npm_alias_shape_is_silent_everywhere():
    # SQG001 must ask about `typescript`; SQG007 must not typosquat the label.
    assert await check_dependencies("", _deps_ctx()) == []
    assert await check_typosquat("", {**REPO_CONTEXT, "fetch_file": _fetch}) == []


@pytest.mark.asyncio
async def test_dependency_vuln_shapes_are_silent():
    """go.sum is not a build list; an unmaintained advisory is not a vulnerability."""
    async def fake_osv(pins, client):
        # Hostile exactly where the real service was: x/crypto is advisory-bearing
        # (so any go.sum query becomes a finding), chrono is informational (so it
        # must be filtered), and the go.mod build list is clean.
        out = {}
        for ecosystem, name, version in pins:
            if ecosystem == "crates":
                out[(ecosystem, name, version)] = [INFORMATIONAL]
            elif name == "golang.org/x/crypto":
                out[(ecosystem, name, version)] = [{"id": "GO-2026-9999"}]
            else:
                out[(ecosystem, name, version)] = []
        return out

    findings = await check_vulnerabilities(
        "", REPO_CONTEXT, fetch_file=_fetch4, query_batch=fake_osv
    )
    assert findings == []


@pytest.mark.asyncio
async def test_text_rule_shapes_are_silent():
    # SQG002 (cache key), SQG006 (literal innerHTML), SQG003 (prose + docstring).
    assert await check_secrets("", REPO_CONTEXT) == []
    assert await check_sast("", REPO_CONTEXT) == []
    assert await check_placeholders("", REPO_CONTEXT) == []


@pytest.mark.asyncio
async def test_the_corpus_still_produces_the_true_positives():
    """The guard above must not be green because every analyzer saw an empty input.

    One deliberate violation per rule proves each analyzer actually read the corpus:
    a hallucinated dependency, a vulnerable go.mod pin, a real cache-backed secret,
    a dynamic innerHTML, and an actual TODO comment.
    """
    files = dict(FILES)
    files["apps/api/package.json"] = (
        '{"dependencies": {"quantumllm-helper": "^1.0.0"}}'
    )
    files["apps/api/sharedLibs/go-html-to-md/go.mod"] = (
        "module html-to-markdown.go\n\ngo 1.25.0\n\n"
        "require golang.org/x/net v0.17.0\n"
    )
    files["apps/api/src/scraper/scrapeURL/engines/wikipedia/index.ts"] = (
        'const API_SECRET = "k7Qz9wp2mX4vB8nL1aF6";\n'
    )
    files["skills/brainstorming/scripts/helper.js"] = (
        "function render(el, text) {\n  el.innerHTML = text;\n}\n"
    )
    files["apps/api/src/service/service.ts"] = "// TODO: wire the real router\n"

    async def fetch_one(path: str):
        return files.get(path)

    async def fetch_four(repo: str, path: str, ref: str, token: str):
        return files.get(path)

    async def fake_exists(ecosystem: str, name: str, client):
        return Existence.MISSING if name == "quantumllm-helper" else Existence.EXISTS

    async def fake_osv(pins, client):
        # chrono keeps its maintenance notice so only the go.mod pin is a finding.
        return {
            (eco, name, ver): ([INFORMATIONAL] if eco == "crates" else [{"id": "GO-2026-9999"}])
            for eco, name, ver in pins
        }

    ctx = {
        "files": files,
        "added_by_file": {p: list(enumerate(t.splitlines(), 1)) for p, t in files.items()},
        "mode": "repo",
        "ast_cache": {},
        "repo": "firecrawl/firecrawl",
        "head_sha": "abc",
        "token": "t",
        "fetch_file": fetch_one,
        "check_exists": fake_exists,
    }

    assert len(await check_dependencies("", ctx)) == 1
    vulns = await check_vulnerabilities("", ctx, fetch_file=fetch_four, query_batch=fake_osv)
    assert len(vulns) == 1
    assert await check_secrets("", ctx) != []
    assert await check_sast("", ctx) != []
    assert await check_placeholders("", ctx) != []
