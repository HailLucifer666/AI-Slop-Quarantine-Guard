"""SQG002 secret scanner: blocks on distinctive tokens, advises on generics, zero-FP gate."""

import pytest

from app.analyzers.base import Confidence
from app.analyzers.secrets import check_secrets


def _diff(path: str, added: list[str]) -> str:
    body = "".join(f"+{line}\n" for line in added)
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{len(added)} @@\n{body}"


# --- generic-tier value guards (real-project FP families) ------------------

@pytest.mark.asyncio
async def test_urn_value_not_flagged():
    # An OAuth grant-type URN is a constant, not a credential.
    diff = _diff("lib.mjs", ['const TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"'])
    assert await check_secrets(diff, {}) == []


@pytest.mark.asyncio
async def test_sequential_placeholder_not_flagged():
    diff = _diff("lib.mjs", ['const apiKey = "1234567890"'])
    assert await check_secrets(diff, {}) == []


@pytest.mark.asyncio
async def test_env_local_secret_not_blocked():
    # A token in a local, gitignored .env.local is not a committed leak.
    diff = _diff("my-agent/.env.local", ['VERCEL_OIDC_TOKEN = "eyJhbGciOiJIUzI1NiscompactJWTvalue"'])
    findings = await check_secrets(diff, {})
    assert all(f.block_eligible is False for f in findings)  # never block-eligible there


@pytest.mark.asyncio
async def test_real_generic_secret_still_flagged():
    # Guard against over-suppression: a high-entropy credential in real source still surfaces.
    diff = _diff("app/config.py", ['API_SECRET = "k7Qz9wp2mX4vB8nL1aF6"'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


# --- CERTAIN tier: distinctive tokens, block-eligible ----------------------

@pytest.mark.asyncio
async def test_aws_key_blocks():
    findings = await check_secrets(_diff("app/cfg.py", ['AWS_KEY = "AKIAIOSFODNN7REALKEY"']), {})
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "SQG002"
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True
    assert "AWS" in f.message


@pytest.mark.asyncio
async def test_real_key_not_suppressed_by_unrelated_allowlist_word_on_same_line():
    # A real, distinctively-shaped key sharing a line with an UNRELATED allowlist
    # token (e.g. a trailing comment mentioning os.environ) must still be caught —
    # the allowlist is scoped to a window around the match, not the whole line.
    diff = _diff("app.py", ['API_KEY = "AKIAABCDEFGHIJKLMNOP"  # fallback if os.environ lookup fails'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN
    assert findings[0].block_eligible is True


@pytest.mark.asyncio
async def test_real_key_not_downgraded_by_unrelated_ellipsis_on_same_line():
    # A distant "..." (e.g. in a trailing comment) must not downgrade a real,
    # complete key elsewhere on the line to a placeholder.
    diff = _diff("app.py", ['API_KEY = "AKIAABCDEFGHIJKLMNOP"  # rotate this later...'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN
    assert findings[0].block_eligible is True


@pytest.mark.asyncio
async def test_github_token_blocks():
    tok = "ghp_" + "a" * 36
    findings = await check_secrets(_diff("x.py", [f'token = "{tok}"']), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN


@pytest.mark.asyncio
async def test_github_fine_grained_pat_blocks():
    tok = "github_pat_11ABCDEF0123456789abcdefghij"
    findings = await check_secrets(_diff("x.py", [f'token = "{tok}"']), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN
    assert findings[0].block_eligible is True


@pytest.mark.asyncio
async def test_unquoted_dotenv_secret_flagged():
    # .env files use bare KEY=value (no quotes) — must not be invisible to the scanner.
    findings = await check_secrets(_diff(".env", ["DATABASE_PASSWORD=SuperSecretPass123"]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert "DATABASE_PASSWORD" in findings[0].message


@pytest.mark.asyncio
async def test_unquoted_assignment_outside_dotenv_not_flagged():
    # The unquoted pattern is scoped to .env* paths — ordinary source code with an
    # unquoted assignment (e.g. a variable reference) must not be flagged.
    findings = await check_secrets(_diff("app/config.py", ["password = get_password()"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_unquoted_dotenv_local_secret_still_silent():
    # .env.local is gitignored/local — the generic tier intentionally stays silent
    # there entirely (pre-existing behavior); the unquoted fix must not change that.
    findings = await check_secrets(_diff(".env.local", ["DATABASE_PASSWORD=SuperSecretPass123"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_unquoted_dotenv_production_variant_flagged():
    # A committed, non-local .env variant (.env.production) is a real leak surface —
    # the unquoted pattern must apply to it too, not just bare ".env".
    findings = await check_secrets(_diff(".env.production", ["DATABASE_PASSWORD=SuperSecretPass123"]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_private_key_block_blocks():
    # A real key — header followed by base64 body — is block-eligible.
    findings = await check_secrets(_diff("key.pem", [
        "-----BEGIN RSA PRIVATE KEY-----",
        "MIIBVgIBADANBgkqhkiGCw0BAQEFAASCAUAwggE8AgEAAkEAq8ZxQ9kFhTQXvEx",
        "-----END RSA PRIVATE KEY-----",
    ]), {})
    assert len(findings) == 1
    assert findings[0].block_eligible is True


@pytest.mark.asyncio
async def test_distinctive_token_in_test_path_is_advisory_not_blocked():
    """A distinctive token WITH key material in a test/fixture path is surfaced but NEVER
    block-eligible (committed test material must not falsely block — honors the 'never
    falsely block' promise). Fixture carries a real base64 body: a header alone is
    structurally not a secret anywhere (see test_bare_pem_headers_with_no_body...)."""
    for path in (
        "tests/fixtures/tls/server.key",
        "src/__tests__/keys.pem",
        "app/api.spec.ts",
        "examples/demo.py",
    ):
        findings = await check_secrets(_diff(path, [
            "-----BEGIN RSA PRIVATE KEY-----",
            "MIIBVgIBADANBgkqhkiGCw0BAQEFAASCAUAwggE8AgEAAkEAq8ZxQ9kFhTQXvEx",
        ]), {})
        assert len(findings) == 1, path
        assert findings[0].confidence is Confidence.HIGH, path
        assert findings[0].block_eligible is False, path
        # still surfaced, just advisory
        assert "private key" in findings[0].message.lower()


@pytest.mark.asyncio
async def test_truncated_or_skeleton_keys_are_not_findings():
    """A PEM header with no real key material anywhere near it — a truncated `...`
    skeleton in an env example, a bare header in docs, a single-line placeholder
    literal — is structurally not a secret and produces NO finding on any path.
    (Previously these surfaced as HIGH advisories: the self-scan's doc/compose false
    alarms. Key material is what we surface, never the public header string.)"""
    cases = [
        (".env.example", r"GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"),
        ("docs/SECURITY.md", r"GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n..."),
        # non-example path, but the whole key is a single-line placeholder literal:
        ("infra/docker-compose.yml", r'KEY: "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3...\n-----END RSA PRIVATE KEY-----"'),
    ]
    for path, content in cases:
        findings = await check_secrets(_diff(path, [content]), {})
        assert findings == [], path


@pytest.mark.asyncio
async def test_bare_pem_headers_with_no_body_are_not_findings():
    """Bare PEM headers with no key body — the detection-pattern examples listed in a
    security playbook (scan #27) or quoted in this repo's own docs and detector
    docstrings (self-scan #15) — are not findings at all. A header alone carries no
    key material, so there is nothing to surface and nothing to block on."""
    findings = await check_secrets(_diff("security/security-senior-secops.md", [
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN PGP PRIVATE KEY-----",
    ]), {})
    assert findings == []
    # normal-path source quoting a bare header (the detector's own docstring case)
    findings = await check_secrets(_diff("app/analyzers/secrets.py", [
        'PEM_TEMPLATE = "-----BEGIN RSA PRIVATE KEY-----"',
    ]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_real_inline_body_pem_still_advisory():
    """KEEPER against recall loss: real-shaped key material crammed onto one line
    (an env-var string literal, as compose files actually embed keys) is still
    surfaced — advisory HIGH, never block-eligible, on every path."""
    for path in ("infra/docker-compose.yml", "app/config.py"):
        findings = await check_secrets(_diff(path, [
            r'KEY: "-----BEGIN RSA PRIVATE KEY-----\nMIIBVgIBADANBgkqhkiGCw0BAQEFAASCAUAwggE8AgEAAkEAq8ZxQ9kFhTQXvEx\n-----END RSA PRIVATE KEY-----"',
        ]), {})
        assert len(findings) == 1, path
        assert findings[0].confidence is Confidence.HIGH, path
        assert findings[0].block_eligible is False, path


@pytest.mark.asyncio
async def test_real_pem_in_normal_path_still_blocks():
    """A genuine key — header + base64 body across multiple lines, no placeholder
    markers — stays block-eligible."""
    findings = await check_secrets(_diff("config/server.key", [
        "-----BEGIN RSA PRIVATE KEY-----",
        "MIIBVgIBADANBgkqhkiGCw0BAQEFAASCAUAwggE8AgEAAkEAq8ZxQ9kFhTQXvEx",
        "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfnoBADCAFEdeadbeefMIIEpAIBAAKCAQEA",
        "-----END RSA PRIVATE KEY-----",
    ]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.CERTAIN
    assert findings[0].block_eligible is True


@pytest.mark.asyncio
async def test_redaction_is_ascii_only():
    """Redacted display must be ASCII (no … ellipsis) to avoid encoding mojibake."""
    findings = await check_secrets(_diff("app/cfg.py", ['AWS_KEY = "AKIAIOSFODNN7REALKEY"']), {})
    assert "…" not in findings[0].message
    assert "…" not in findings[0].evidence.snippet


@pytest.mark.asyncio
async def test_secret_value_redacted():
    findings = await check_secrets(_diff("x.py", ['k = "AKIAIOSFODNN7REALKEY"']), {})
    # full secret never appears verbatim in message or evidence
    assert "AKIAIOSFODNN7REALKEY" not in findings[0].message
    assert "AKIAIOSFODNN7REALKEY" not in findings[0].evidence.snippet


# --- HIGH tier: generic assignments, advisory only -------------------------

@pytest.mark.asyncio
async def test_generic_password_advisory():
    findings = await check_secrets(_diff("app.py", ['password = "hunter2pass"']), {})
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False


# --- prose values: English-phrase values are labels, not credentials --------

@pytest.mark.asyncio
async def test_prose_ui_label_value_not_flagged():
    # A dashboard label whose KEY happens to contain "secret" — the VALUE is an
    # English phrase (spaces, no digits, no symbols), not a credential. This exact
    # line was a self-scan #15 false alarm on web/components/wall/panels/AnimatedScan.tsx.
    findings = await check_secrets(_diff("web/components/wall/panels/AnimatedScan.tsx", [
        '  secrets: "Leaked secrets",',
    ]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_non_echoing_prose_value_still_surfaced():
    """Recall-first (preflight REV finding): a spacey English-phrase value on a
    credential-named key that does NOT echo its own name is ambiguous — a passphrase
    looks exactly like this — so it stays surfaced as HIGH advisory. Only the echo
    (a label naming its own category) is skipped."""
    findings = await check_secrets(_diff("app/config.py", [
        'secret_note = "rotate this credential soon"',
    ]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


@pytest.mark.asyncio
async def test_passphrase_named_keys_still_flagged():
    """KEEPER against recall loss: passphrases are the one credential class whose
    values legitimately contain spaces — a password/passphrase-named key with a
    spacey value must still surface as HIGH advisory."""
    findings = await check_secrets(_diff("app/config.py", [
        'password = "correct horse battery staple"',
    ]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_generic_secret_named_key_with_passphrase_value_still_flagged():
    """KEEPER against recall loss (preflight REV finding): the prose skip must key on
    the value ECHOING its own credential name — a passphrase-shaped value on a
    generically-named key does not echo, so it must still surface."""
    findings = await check_secrets(_diff("app/config.py", [
        'SECRET = "correct horse battery staple"',
    ]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_pem_body_lookahead_stops_at_next_pem_marker():
    """KEEPER against a false-CERTAIN vector (preflight REV finding): a bare private-key
    header followed by a DIFFERENT PEM section's base64 (a certificate example) must
    NOT reach CERTAIN — the key-material lookahead stops at the next BEGIN/END marker."""
    findings = await check_secrets(_diff("SECURITY.md", [
        "Our keys use PEM, e.g.",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN CERTIFICATE-----",
        "MIIBVgIBADANBgkqhkiGCw0BAQEFAASCAUAwggE8AgEAAkEAq8ZxQ9kFhTQXvEx",
        "-----END CERTIFICATE-----",
    ]), {})
    assert all(f.block_eligible is False for f in findings)
    assert all(f.confidence is not Confidence.CERTAIN for f in findings)


@pytest.mark.asyncio
async def test_generic_assignment_on_a_line_with_bare_header_still_flagged():
    """KEEPER against a veto bug (preflight REV finding): a bare PEM header is nothing
    to surface, but it must not silence a real credential-named assignment sharing
    the line — the no-material skip does not set the one-finding-per-line veto."""
    findings = await check_secrets(_diff("scripts/export.sh", [
        'export API_KEY="abcd1234efgh"  # was: -----BEGIN PRIVATE KEY-----',
    ]), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH


# --- zero-FP controls ------------------------------------------------------

@pytest.mark.asyncio
async def test_aws_example_key_silent():
    # AWS's own documented example key — must not flag.
    findings = await check_secrets(_diff("README.md", ['key = "AKIAIOSFODNN7EXAMPLE"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_env_reference_silent():
    findings = await check_secrets(_diff("app.py", ['api_key = os.environ["API_KEY"]']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_placeholder_value_silent():
    findings = await check_secrets(_diff("cfg.py", ['token = "your_token_here"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_clean_code_silent():
    findings = await check_secrets(_diff("math.py", ["def add(a, b):", "    return a + b"]), {})
    assert findings == []


@pytest.mark.asyncio
async def test_short_value_not_flagged():
    # An 8-char minimum keeps trivial assignments quiet.
    findings = await check_secrets(_diff("x.py", ['pwd = "abc"']), {})
    assert findings == []


# --- generic-assignment context noise quieted (the A–F triage) -------------

@pytest.mark.asyncio
async def test_url_value_not_flagged():
    # Cat B: a public OAuth endpoint assigned to a *_URL field is not a secret.
    findings = await check_secrets(_diff("app/cfg.py", ['TOKEN_URL = "https://connect.stripe.com/oauth/token"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_env_reference_value_not_flagged():
    # Cat D: a shell env-var reference, not a hardcoded secret.
    findings = await check_secrets(_diff("app/cfg.py", ['CLOUDFLARE_API_TOKEN = "$CLOUDFLARE_API_KEY"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_masked_value_not_flagged():
    # Cat D: an already-masked/redacted value shown in docs.
    findings = await check_secrets(_diff("app/cfg.py", ['KEEMAKR_API_KEY = "***REDACTED***"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_marker_and_enum_values_not_flagged():
    # Cat A/C/F: SDK markers, config enums, audience claims, dev tokens — lowercase
    # slugs / words / dev- prefixes, never high-entropy secrets.
    for line in (
        'accessToken = "composio"',
        'accessToken = "stub-token"',
        'accessToken = "managed-by-composio"',
        'http_tokens = "required"',
        'MFA_TOKEN_AUDIENCE = "fzst-claw-mfa"',
        'turnstile_token = "dev-1x00000000000000000000AA"',
    ):
        findings = await check_secrets(_diff("app/x.py", [line]), {})
        assert findings == [], line


@pytest.mark.asyncio
async def test_allcaps_placeholder_value_not_flagged():
    # Cat A: an ORIGINAL_VALUE-style placeholder constant.
    findings = await check_secrets(_diff("app/x.py", ['currentAccessToken = "ORIGINAL_VALUE"']), {})
    assert findings == []


@pytest.mark.asyncio
async def test_generic_assignment_in_test_or_compose_path_not_flagged():
    # Cat E: factory-default creds in docker-compose / test fixtures are not leaks.
    for path in ("docker-compose.yml", "tests/brainstorm-server/auth.test.js"):
        findings = await check_secrets(_diff(path, ['IDP_USER1_PASSWORD = "user1pass"']), {})
        assert findings == [], path


@pytest.mark.asyncio
async def test_real_looking_secret_in_app_code_still_advisory():
    # A digit-bearing, mixed-case value in app code still surfaces (HIGH/advisory) —
    # the noise fixes must not blind us to genuine-looking credentials.
    findings = await check_secrets(_diff("app/cfg.py", ['db_password = "Pa55wordHunter9"']), {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


# --- fixture/synthetic downgrades (scan #20: openai/codex-security) ---------

# Probes (2026-11-12, run and restored): ``_token_carries_marker`` → ``return
# False`` reded exactly test_marker_word_inside_token_value_downgraded while the
# surrounding-text steering control stayed green — the check is value-specific.
# Adding "synthetic" to the ±20-char window _ALLOWLIST was deliberately NOT done
# for the same reason; the generic-tier word lives in _NONSESECRET_WORDS, which
# only ever reads the captured value.

_SYNTHETIC_TOKEN = "github_pat_SYNTHETIC_GITHUB_PAT_123"
_REAL_SHAPED_TOKEN = "github_pat_QWERTYUIOPASDFGHJKLZXCVBNM1234"


@pytest.mark.asyncio
async def test_marker_word_inside_token_value_downgraded():
    # The token ITSELF announces it is fake — the value-internal check downgrades it
    # without needing the path (scan #20 finding 2 fired CERTAIN on exactly this).
    diff = _diff("src/lib.ts", [f'const t = "{_SYNTHETIC_TOKEN}";'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "marker" in f.message


@pytest.mark.asyncio
async def test_marker_word_only_in_surrounding_text_stays_certain():
    # Steering guard: a marker word NEXT TO a real-shaped token must not suppress or
    # downgrade it — an attacker can always add a comment. Suppression is
    # value-internal only; the window allowlist gains no new vocabulary.
    diff = _diff("src/lib.ts", [f'sendSynthetic(repo, "{_REAL_SHAPED_TOKEN}");'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.CERTAIN
    assert f.block_eligible is True


@pytest.mark.asyncio
async def test_tests_ts_dash_suffixed_path_downgraded():
    # scan #20 finding 2's path: 'tests-ts' is not a whole segment, the old regex
    # missed it and the fixture token blocked. Real-shaped token isolates the PATH fix.
    diff = _diff("sdk/typescript/tests-ts/cli-fixtures.ts", [f'const t = "{_REAL_SHAPED_TOKEN}";'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False
    assert "test/fixture path" in f.message


@pytest.mark.asyncio
async def test_evals_path_downgraded():
    # 'evals' was absent from the old vocabulary entirely (scan #20 finding 3's path).
    diff = _diff("evals/secret-discovery/test_runtime.mts", [f'const t = "{_REAL_SHAPED_TOKEN}";'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_mid_segment_fixture_filename_downgraded():
    # 'fixtures' buried mid-segment in a filename (cli-fixtures.ts) still counts when
    # delimited — the old segment-exact regex required the token to own the segment.
    diff = _diff("tools/cli-fixtures.ts", [f'const t = "{_REAL_SHAPED_TOKEN}";'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    assert findings[0].confidence is Confidence.HIGH
    assert findings[0].block_eligible is False


@pytest.mark.asyncio
async def test_real_token_in_tests_dir_still_surfaces_high():
    # Pin the pre-existing contract: a real-shaped token in a test path is SURFACED
    # (advisory), never silently dropped — a real leak does land in test folders.
    diff = _diff("tests/auth.test.ts", [f'const t = "{_REAL_SHAPED_TOKEN}";'])
    findings = await check_secrets(diff, {})
    assert len(findings) == 1
    f = findings[0]
    assert f.confidence is Confidence.HIGH
    assert f.block_eligible is False


@pytest.mark.asyncio
async def test_synthetic_generic_value_not_flagged():
    # scan #20 finding 3's family: 'synthetic' in the VALUE of a generic
    # credential-named assignment is not a credential. High-entropy shape on
    # purpose — the low-entropy guard alone already skips meek values, and this
    # test must fail on the word's absence, not coast on an existing guard
    # (probed 2026-11-12: "Synthetic-kX9pQ2vB7nR4mZ8w" surfaces HIGH before the fix).
    diff = _diff("evals/secret-discovery/test_runtime.mts", ['openAiApiKey = "Synthetic-kX9pQ2vB7nR4mZ8w"'])
    assert await check_secrets(diff, {}) == []
