"""Scan #30-#33 regression suite (agent-browser & codex-security precision hardening).

Pins every real-world FP family from Scans #30-#33 + keeper tests proving zero recall loss:
  - SQG002: __Host-/__Secure- cookies, $(...) shell substitutions, -- CLI flags,
    Markdown doc files (SKILL.md), Rust inline #[cfg(test)] blocks, minified lines.
  - SQG003: URL hostnames containing `xxx` (`https://xxx.cdp0.browser-use.com`),
    minified bundled JS lines (`installHook.js`).
  - SQG004: fixture-path skip (`tests-ts/fixtures/`), cross-lockfile deduplication
    preserving `(also in N other file(s))` transparency.
"""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.paths import in_test_path
from app.analyzers.placeholders import check_placeholders
from app.analyzers.secrets import check_secrets
from app.analyzers.vulns import check_vulnerabilities


def _diff(path: str, lines: list[str]) -> str:
    body = "".join(f"+{ln}\n" for ln in lines)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


# --- SQG002: Scan #31 false positives + keepers -----------------------------------


@pytest.mark.asyncio
async def test_scan31_sqg002_cookie_shell_flag_markdown_and_rust_test_silent():
    cases = [
        ("packages/dashboard/src/lib/dashboard-routes.ts", ['export const ACCESS_TOKEN_COOKIE = "__Host-agent-browser-token";']),
        ("packages/dashboard/src/lib/auth.ts", ['const SESSION_TOKEN = "__Secure-session-id-v1";']),
        ("scripts/proxy.sh", ['PROXY_TOKEN="$(head -c 24 /dev/urandom | base64)"']),
        ("cli/flags.ts", ['const AUTH_TOKEN_FLAG = "--print-proxy-auth-token";']),
        ("skill-data/vercel/SKILL.md", ['TOKEN="$(vc env pull --token)"']),
        ("cli/src/commands.rs", [
            "pub fn run() {}",
            "#[cfg(test)]",
            "mod tests {",
            '    let name_secret = "LEAK_TEST_9a8b7c6d5e4f3g2h";',
            "}",
        ]),
    ]
    for path, lines in cases:
        findings = await check_secrets(_diff(path, lines), {})
        assert findings == [], f"unexpected SQG002 FP on {path}: {findings}"


@pytest.mark.asyncio
async def test_sqg002_rust_prod_secret_above_cfg_test_still_flagged():
    """KEEPER: a real hardcoded secret ABOVE #[cfg(test)] in a .rs file MUST still fire."""
    lines = [
        'let api_secret = "k7Qz9wp2mX4vB8nL1aF6";',
        "#[cfg(test)]",
        "mod tests {",
        '    let test_secret = "LEAK_TEST_9a8b7c6d5e4f3g2h";',
        "}",
    ]
    findings = await check_secrets(_diff("cli/src/commands.rs", lines), {})
    assert len(findings) == 1
    assert findings[0].line_start == 1
    assert findings[0].confidence is Confidence.HIGH


def test_paths_classifies_harness_as_test_path():
    assert in_test_path("sdk/harness/run_e2e.py") is True
    assert in_test_path("src/integration-tests/auth.ts") is True


# --- SQG003: URL xxx hostname + minified JS bundle --------------------------------


@pytest.mark.asyncio
async def test_scan31_sqg003_url_xxx_and_minified_bundle_silent():
    # URL hostname containing xxx
    findings = await check_placeholders(
        _diff("cli/src/native/browser.rs", ["// WebSocket endpoint (e.g. https://xxx.cdp0.browser-use.com)."]),
        {},
    )
    assert findings == []

    # Minified bundled JS line (>500 chars, <5% whitespace) containing "not implemented"
    minified = "(()=>{var e={" + ",".join(f'k{i}:()=>{{throw new Error("not implemented")}}' for i in range(40)) + "}})();"
    assert len(minified) > 500
    findings = await check_placeholders(_diff("cli/src/native/react/installHook.js", [minified]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_sqg003_bare_xxx_comment_keeper_still_fires():
    """KEEPER: genuine `# XXX: fragile` comment still fires."""
    findings = await check_placeholders(_diff("src/core.py", ["# XXX: fragile parser"]), {})
    assert len(findings) == 1


# --- SQG004: fixture skip + cross-lockfile dedupe ---------------------------------


@pytest.mark.asyncio
async def test_scan30_sqg004_skips_fixture_paths_and_dedupes_across_files():
    async def fake_fetch(_repo, path, _ref, _token):
        if path.endswith("package.json"):
            return '{"dependencies": {"lodash": "4.17.23"}}'
        return None

    async def fake_osv(pins, _client):
        return {p: [{"id": "GHSA-test-1234"}] for p in pins}

    diff = (
        _diff("tests-ts/fixtures/package.json", ['  "lodash": "4.17.23"'])
        + _diff("package.json", ['  "lodash": "4.17.23"'])
        + _diff("common/package.json", ['  "lodash": "4.17.23"'])
    )
    findings = await check_vulnerabilities(
        diff,
        {"repo": "o/r", "head_sha": "abc", "token": "t"},
        fetch_file=fake_fetch,
        query_batch=fake_osv,
    )
    # Fixture skipped; 2 real manifests deduplicated into 1 finding noting the other file!
    assert len(findings) == 1
    assert findings[0].file_path == "package.json"
    assert "also in 1 other file: common/package.json" in findings[0].message
