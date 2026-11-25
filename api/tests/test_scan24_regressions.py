"""Scan #24 (CodebuffAI/freebuff) regression suite + modern lockfile tests.

Pins every single false-positive family from Scan #24 (where 31/36 findings were FPs):
  - SQG002 (4/4 FPs): dunder sentinel, normalized label echo, error-code i18n message,
    reverse-DNS keychain service ID, plus snake_case github_pat_ identifier.
  - SQG006 (6/8 FPs): TypeScript interface eval() signature, async eval() method def,
    eval() inside __tests__/ and test/ compatibility harnesses, plus ESM child_process
    import + CWE-78 keeper.
  - SQG003 (21/21 FPs): kebab-case todo-dock / todo-progress-reminder.ts /
    followup-todo-nudge.ts, JSDoc `* Implement this interface...`, test-runtime
    `throw new Error('... not implemented in test runtime')`, and whole-repo attributed
    `TODO(James):` backlog comments.
  - Lockfiles: pnpm-lock.yaml, bun.lock (JSONC), uv.lock exact-pin parsing.
"""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.placeholders import check_placeholders
from app.analyzers.sast import check_sast
from app.analyzers.secrets import check_secrets
from app.manifests import extract_pinned_lockfile, lockfile_ecosystem
from app.scan import run_scan


def _diff(path: str, lines: list[str]) -> str:
    body = "".join(f"+{ln}\n" for ln in lines)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


# --- SQG002: Scan #24 false positives + keepers -----------------------------------


@pytest.mark.asyncio
async def test_scan24_sqg002_all_four_false_positives_silent():
    cases = [
        ("cli/src/utils/terminal-watchdog.ts", ['const OWNER_START_TOKEN = "__FREEBUFF_OWNER_START__"']),
        ("common/src/ads/sponsored-run-failure.ts", ['  needs_api_key: "An API key is required",']),
        ("common/src/sites/client.ts", ['  secret_not_found: "This secret does not exist.",']),
        ("sdk/src/byok.ts", ['const BYOK_SECRET_SERVICE = "com.codebuff.byok.v1"']),
        # Audit QW4: snake_case identifier starting with github_pat_ is not a real PAT
        ("app/auth.py", ['github_pat_required_prefix_length = 40']),
    ]
    for path, lines in cases:
        findings = await check_secrets(_diff(path, lines), {})
        assert findings == [], f"unexpected SQG002 FP on {path}: {findings}"


@pytest.mark.asyncio
async def test_sqg002_real_secret_near_example_comment_not_suppressed():
    """Audit F7: an unrelated 'example' word in a trailing comment must not suppress a
    real CERTAIN AWS key."""
    tok = "AKIA" + "IOSFODNN7REALKEY"
    findings = await check_secrets(
        _diff("app/cfg.py", [f'AWS_KEY = "{tok}" # example deploy key']),
        {},
    )
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN
    assert findings[0].block_eligible is True


# --- SQG006: Scan #24 false positives + AST & ESM keepers -------------------------


@pytest.mark.asyncio
async def test_scan24_sqg006_redis_eval_interface_and_methods_silent():
    ts_interface = (
        "export interface RedisClient {\n"
        "  eval(\n"
        "    script: string,\n"
        "    numKeys: number,\n"
        "    ...args: string[]\n"
        "  ): Promise<unknown>;\n"
        "}\n"
    )
    ts_mock = (
        "export class MockRedis {\n"
        "  async eval(script: string, numKeys: number, ...args: string[]) {\n"
        "    return [script, numKeys, args];\n"
        "  }\n"
        "}\n"
    )
    py_def = "class Evaluator:\n    def eval(self, x):\n        return x\n"

    for path, src in [
        ("common/src/util/redis-cached-script.ts", ts_interface),
        ("common/src/util/redis-mock.ts", ts_mock),
        ("app/evaluator.py", py_def),
    ]:
        files = {path: src}
        added_by_file = {path: list(enumerate(src.splitlines(), 1))}
        findings = await check_sast("", {"files": files, "added_by_file": added_by_file})
        assert findings == [], f"unexpected SQG006 FP on {path}: {findings}"


@pytest.mark.asyncio
async def test_scan24_sqg006_test_eval_harnesses_silent():
    cases = [
        (
            "agents/__tests__/basher.test.ts",
            "const fn = eval(`(${commander.handleSteps!.toString()})`);\n",
        ),
        (
            "sdk/test/cjs-compatibility/test-imports.js",
            "eval('import { CodebuffClient } from \"@codebuff/sdk\"');\n",
        ),
        (
            "sdk/test/esm-compatibility/test-imports.js",
            "eval('const { CodebuffClient } = require(\"@codebuff/sdk\")');\n",
        ),
    ]
    for path, src in cases:
        files = {path: src}
        added_by_file = {path: list(enumerate(src.splitlines(), 1))}
        findings = await check_sast("", {"files": files, "added_by_file": added_by_file})
        assert findings == [], f"unexpected SQG006 FP on test path {path}: {findings}"


@pytest.mark.asyncio
async def test_scan24_sqg006_esm_and_cjs_exec_sync_flagged_with_cwe78():
    """KEEPER: real execSync() calls via both ESM `node:child_process` and CJS require
    MUST fire with CWE-78 attached."""
    esm_src = (
        "import { execSync } from 'node:child_process';\n"
        "const response = execSync(triggerCmd, { encoding: 'utf8' });\n"
    )
    cjs_src = (
        "const { execSync } = require('child_process');\n"
        "const response = execSync(triggerCmd, { encoding: 'utf8' });\n"
    )
    for path, src in [("cli/scripts/release.ts", esm_src), ("sdk/scripts/release.js", cjs_src)]:
        files = {path: src}
        added_by_file = {path: list(enumerate(src.splitlines(), 1))}
        findings = await check_sast("", {"files": files, "added_by_file": added_by_file})
        assert len(findings) == 1, path
        assert findings[0].confidence is Confidence.HIGH
        assert "CWE-78" in findings[0].cwe


@pytest.mark.asyncio
async def test_sqg006_real_prod_eval_still_flagged_via_ast():
    """KEEPER: real global eval(userInput) in production TS code still fires with CWE-95."""
    src = "export function run(input: string) {\n  return eval(input);\n}\n"
    files = {"src/runner.ts": src}
    added_by_file = {"src/runner.ts": list(enumerate(src.splitlines(), 1))}
    findings = await check_sast("", {"files": files, "added_by_file": added_by_file})
    assert len(findings) == 1
    assert findings[0].line_start == 2
    assert "CWE-95" in findings[0].cwe


# --- SQG003: Scan #24 false positives + keepers -----------------------------------


@pytest.mark.asyncio
async def test_scan24_sqg003_kebab_paths_jsdoc_and_test_stubs_silent():
    cases = [
        ("common/src/ads/__fixtures__/sponsored-proposal-rows.ts", ["// todo-dock vocabulary is exercised in full."]),
        ("common/src/util/axiom-only-log.ts", [" *  tool calls (packages/agent-runtime/src/util/todo-progress-reminder.ts)."]),
        ("packages/agent-runtime/src/run-agent-step.ts", [
            "// Bounded per user prompt; see util/followup-todo-nudge.ts. An explicit",
            "// step; see util/todo-progress-reminder.ts. Once per list, mid-turn only.",
        ]),
        ("cli/src/components/tools/types.ts", [
            "/**",
            " * Implement this interface to create a custom renderer for a specific tool.",
            " */",
        ]),
        ("common/src/testing/fixtures/agent-runtime.ts", [
            "throw new Error('fetch not implemented in test runtime')",
        ]),
        ("packages/code-map/__tests__/test-langs/test.js", [
            "throw new Error('Method not implemented')",
        ]),
    ]
    for path, lines in cases:
        findings = await check_placeholders(_diff(path, lines), {"mode": "repo"})
        assert findings == [], f"unexpected SQG003 FP on {path}: {findings}"


@pytest.mark.asyncio
async def test_scan24_sqg003_attributed_todo_skipped_in_repo_mode_but_flagged_in_pr():
    diff = _diff("cli/src/components/tools/glob.tsx", ["// TODO(James): Reenable when we pass tool results"])
    assert await check_placeholders(diff, {"mode": "repo"}) == []
    pr_findings = await check_placeholders(diff, {"mode": "pr"})
    assert len(pr_findings) == 1


@pytest.mark.asyncio
async def test_end_to_end_scan24_synthetic_repro_zero_false_positives():
    """Full run_scan() over all Scan #24 FP files + the 2 real execSync release scripts:
    must produce 0 FPs and retain both real SQG006 findings with CWE-78."""
    files = {
        "cli/src/utils/terminal-watchdog.ts": 'export const OWNER_START_TOKEN = "__FREEBUFF_OWNER_START__";\n',
        "common/src/ads/sponsored-run-failure.ts": 'export const MSG = { needs_api_key: "An API key is required" };\n',
        "common/src/sites/client.ts": 'export const ERR = { secret_not_found: "This secret does not exist." };\n',
        "sdk/src/byok.ts": 'export const BYOK_SECRET_SERVICE = "com.codebuff.byok.v1";\n',
        "common/src/util/redis-cached-script.ts": "export interface Redis { eval(s: string): Promise<void>; }\n",
        "common/src/util/__tests__/redis-cached-script.test.ts": "class M { async eval(s: string) { return s; } }\n",
        "sdk/test/cjs-compatibility/test-imports.js": "eval('import x from \"y\"');\n",
        "common/src/testing/fixtures/agent-runtime.ts": "throw new Error('fetch not implemented in test runtime');\n",
        "packages/agent-runtime/src/run-agent-step.ts": "// see util/todo-progress-reminder.ts\n",
        "cli/src/components/tools/types.ts": "/**\n * Implement this interface to create a renderer.\n */\nexport interface R {}\n",
        "cli/src/components/tools/glob.tsx": "// TODO(James): Reenable later\nexport const x = 1;\n",
        # The 2 REAL Scan #24 SAST findings:
        "cli/scripts/release.ts": "import { execSync } from 'node:child_process';\nexecSync(triggerCmd);\n",
        "sdk/scripts/release.js": "const { execSync } = require('child_process');\nexecSync(triggerCmd);\n",
    }
    res = await run_scan(files)
    findings = res["findings"]
    assert len(findings) == 2
    assert {f["file_path"] for f in findings} == {"cli/scripts/release.ts", "sdk/scripts/release.js"}
    assert all(
        f["rule_id"] == "SQG006" and "CWE-78" in f["cwe"] and f["tool"] == "ast"
        for f in findings
    )
    assert res["verdict"] == "FLAGGED"
    assert res["analytics"]["verdict"] == "FLAGGED"


# --- Modern lockfile parsers (pnpm-lock.yaml, bun.lock, uv.lock) ------------------


def test_pnpm_lock_yaml_parses_v6_and_v9():
    assert lockfile_ecosystem("pnpm-lock.yaml") == "npm"
    content = (
        "lockfileVersion: '9.0'\n"
        "packages:\n"
        "  lodash@4.17.23:\n"
        "    resolution: {integrity: sha512-abc}\n"
        "  '@babel/core@7.24.0':\n"
        "    resolution: {integrity: sha512-def}\n"
        "  /@scope/pkg@1.2.3(react@18.2.0):\n"
        "    resolution: {integrity: sha512-ghi}\n"
    )
    pins = extract_pinned_lockfile("pnpm-lock.yaml", content)
    assert ("lodash", "4.17.23") in pins
    assert ("@babel/core", "7.24.0") in pins
    assert ("@scope/pkg", "1.2.3") in pins


def test_bun_lock_jsonc_parses_with_trailing_commas():
    assert lockfile_ecosystem("bun.lock") == "npm"
    content = (
        "{\n"
        '  "lockfileVersion": 1,\n'
        '  "packages": {\n'
        '    "lodash": ["lodash@4.17.23", "", {}, "sha512-abc"],\n'
        '    "@babel/core": ["@babel/core@7.24.0", "", {}, "sha512-def"],\n'
        "  },\n"
        "}\n"
    )
    pins = extract_pinned_lockfile("bun.lock", content)
    assert ("lodash", "4.17.23") in pins
    assert ("@babel/core", "7.24.0") in pins


def test_uv_lock_parses_toml_packages():
    assert lockfile_ecosystem("uv.lock") == "pypi"
    content = (
        "version = 1\n\n"
        "[[package]]\n"
        'name = "requests"\n'
        'version = "2.31.0"\n'
    )
    assert extract_pinned_lockfile("uv.lock", content) == [("requests", "2.31.0")]


@pytest.mark.asyncio
async def test_scan28_static_execsync_and_test_execsync_silent_while_dynamic_fires():
    """Scan #28 polish: static-string execSync('git add .', opts) has no injection vector
    (CWE-78 impossible), and test/eval harnesses are skipped; dynamic prod execSync fires."""
    static_src = (
        "import { execSync } from 'node:child_process';\n"
        "execSync('git add .', { cwd: dir, stdio: 'ignore' });\n"
        "execSync(`node test-cjs-dist.cjs`, { stdio: 'pipe' });\n"
    )
    eval_src = (
        "import { execSync } from 'node:child_process';\n"
        "execSync(`git clone ${repoUrl}`);\n"
    )
    dynamic_prod_src = (
        "import { execSync } from 'node:child_process';\n"
        "execSync(`ps -p ${pid}`);\n"
    )
    for path, src in [
        ("sdk/scripts/verify.ts", static_src),
        ("evals/buffbench/runner.ts", eval_src),
        ("cli/src/__tests__/clipboard.test.ts", eval_src),
    ]:
        findings = await check_sast(
            "", {"files": {path: src}, "added_by_file": {path: list(enumerate(src.splitlines(), 1))}}
        )
        assert findings == [], f"unexpected SQG006 FP on {path}: {findings}"

    # KEEPER: dynamic template interpolation in prod code MUST still fire with CWE-78
    prod = await check_sast(
        "",
        {
            "files": {"cli/src/utils/detect-shell.ts": dynamic_prod_src},
            "added_by_file": {"cli/src/utils/detect-shell.ts": list(enumerate(dynamic_prod_src.splitlines(), 1))},
        },
    )
    assert len(prod) == 1
    assert prod[0].tool == "ast"
    assert "CWE-78" in prod[0].cwe


def test_bun_lock_exact_line_anchoring():
    """Scan #28 polish: bun.lock CVEs anchor to `["ajv@8.17.1"`, not an earlier dep line."""
    from app.analyzers.vulns import _find_lock_line

    added = [
        (10, '    "ajv": "^8.17.1",'),
        (221, '    "@eslint/eslintrc": ["@eslint/eslintrc@2.1.4", "", { "dependencies": { "ajv": "^6.12.4" } }],'),
        (350, '    "ajv": ["ajv@8.17.1", "", {}, "sha512-abc"],'),
    ]
    assert _find_lock_line("ajv", "8.17.1", added, "bun.lock") == 350
