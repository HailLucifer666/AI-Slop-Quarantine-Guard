"""SQG002 — leaked-secret detector (Phase 3, offline regex, no external tool).

Scans newly added lines for credential material. Two tiers:

* CERTAIN / block-eligible — structurally distinctive tokens whose shape makes a
  false positive near-impossible (AWS AKIA ids, GitHub ghp_ tokens, Stripe
  sk_live_ keys, Slack xox tokens, Google AIza keys, PEM private-key headers).
  These are the only secrets we'd block a PR on.
* HIGH / advisory — generic `secret = "..."` style assignments. Real but
  FP-prone (test fixtures, placeholders), so surfaced, never blocked.
* Downgraded — a distinctive match in a test/example/doc path, or with a
  placeholder body (single-line PEM, truncating ellipsis), is surfaced as
  advisory, never block-eligible. We never block on illustrative material.

An allowlist neutralises the well-known non-secrets (AWS's documented EXAMPLE
key, `your_key_here`, env-var references). Secret values are always redacted in
findings — they must never be echoed into PR comments or logs.

No network, no verification, no entropy guessing — distinctive shapes only,
which is where regex secret-scanning actually earns trust.
"""

import re
from typing import List

from app.diff import parse_diff

from .base import Confidence, Evidence, Finding

RULE_ID = "SQG002"

# Substrings that mark a value as a deliberate non-secret (examples, templates,
# env-var references). Case-insensitive membership test on the whole line.
_ALLOWLIST = (
    "example",
    "your_",
    "your-",
    "yourkey",
    "placeholder",
    "changeme",
    "change-me",
    "redacted",
    "dummy",
    "<your",
    "xxxxxx",
    "os.environ",
    "os.getenv",
    "getenv",
    "process.env",
    "${",
    "{{",
)

# CERTAIN tier: (label, pattern). Distinctive prefixes / structures only.
_CERTAIN_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
]

# A substantial base64 line — the body of a real PEM key. Illustrative/bare headers
# (a detection-pattern example in a doc, a header with no key material) have none.
_PEM_BODY = re.compile(r"^[A-Za-z0-9+/]{32,}={0,2}$")

# Paths where a distinctive token is almost always intentional test/sample material
# (a committed test TLS key, an example token in a spec). We still SURFACE it, but
# downgrade it from CERTAIN/block-eligible to HIGH/advisory — blocking a PR on a known
# test fixture would violate the "never falsely block" promise.
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|testdata|test[-_]data|fixtures?|mocks?|"
    r"examples?|samples?|e2e|specs?|__mocks__)(?:/|$)|\.(?:test|spec)\.",
    re.IGNORECASE,
)

# Files that are illustrative by nature — examples, templates, docs. A "secret" here
# is almost always a placeholder showing the expected shape (e.g. .env.example,
# docker-compose example values, a key snippet in docs), so a distinctive match is
# surfaced as HIGH/advisory rather than block-eligible.
_EXAMPLE_PATH = re.compile(
    r"(?:^|/)(?:docs?|examples?|samples?)(?:/|$)"
    r"|\.(?:example|sample|dist|template)(?:$|\.)"
    r"|(?:^|/)\.env\.[^/]*example"
    r"|(?:^|/)\.env(?:\.[^/]*)?\.local$"  # .env.local / .env.production.local — local, gitignored, not a committed leak
    r"|(?:^|/)docker-compose"  # compose files carry local/dev/test config, not real leaks
    r"|(?:^|/)readme",
    re.IGNORECASE,
)

# HIGH tier: a credential-named identifier assigned a quoted literal >= 8 chars.
_ASSIGNMENT = re.compile(
    r"""(?P<name>\b\w*(?:secret|token|passwd|password|pwd|api[_-]?key|access[_-]?key)\w*\b)"""
    r"""\s*[:=]\s*['"](?P<value>[^'"]{8,})['"]""",
    re.IGNORECASE,
)

# .env files (dotenv format) use bare KEY=value with no quotes — _ASSIGNMENT above
# never matches that shape, so a real hardcoded secret there was invisible. Scoped
# strictly to .env* paths: applying an unquoted match to ordinary source code would
# flag variable-to-variable/function-call assignments (`password = get_password()`)
# as if they were hardcoded literals.
_DOTENV_PATH = re.compile(r"(?:^|/)\.env(?:\.[^/]*)?$", re.IGNORECASE)
_ASSIGNMENT_UNQUOTED = re.compile(
    r"""^\s*(?P<name>\w*(?:secret|token|passwd|password|pwd|api[_-]?key|access[_-]?key)\w*)"""
    r"""\s*=\s*(?P<value>\S{8,})\s*$""",
    re.IGNORECASE,
)


# Value-level tells that a credential-named assignment is NOT a real secret — applied
# only to the generic HIGH tier (never to distinctive CERTAIN tokens). Targets the
# observed false-positive families: SDK marker strings, public OAuth endpoints, config
# enums/audiences, env-var references, masked/doc values, and ALL_CAPS placeholders.
_NONSECRET_WORDS = (
    "stub", "fake", "sample", "example", "dummy", "placeholder", "changeme",
    "redacted", "managed-by", "managed_by", "original_value", "not-a", "not_a",
    "localhost", "your_", "your-", "todo", "dev-",
)
# A value that is a URI/URN/scheme reference is an endpoint, audience, or constant
# (e.g. an OAuth grant-type URN `urn:ietf:params:oauth:grant-type:token-exchange`),
# not a credential.
_URL_VALUE = re.compile(r"^(?:https?://|urn:|mailto:|data:|file://|ftp://|tel:)", re.IGNORECASE)
_ENV_REF_VALUE = re.compile(r"^\$\{?\w+\}?$")


def _is_sequential_placeholder(v: str) -> bool:
    """A keyboard/sequential numeric placeholder like ``1234567890`` or ``0123456789``
    — its digits form one consecutive run, which a real key's never do."""
    if not v.isdigit() or len(v) < 8:
        return False
    u = sorted(set(v))
    return len(u) >= 6 and (ord(u[-1]) - ord(u[0])) == len(u) - 1
# A lowercase slug / dotted identifier (no digits) — a config value, marker, or audience,
# not a high-entropy random secret. Digit-bearing values (e.g. real-looking passwords) are
# deliberately NOT matched here, so genuine credentials in app code still surface.
_SLUG_VALUE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_CONST_VALUE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# A quoted value that reads as an English phrase — letters, spaces, apostrophes,
# hyphens, optional sentence punctuation, never a digit or symbol. Quoted tier only.
_PROSE_VALUE = re.compile(r"^[A-Za-z][A-Za-z' \-]*[.!?]?$")
# The credential-word family _ASSIGNMENT's name group matches. A UI label echoes its
# own category name ("secrets: \"Leaked secrets\""); a real value does not.
_CRED_WORD = re.compile(r"secret|token|pass(?:word|wd|phrase)|pwd|api[_-]?key|access[_-]?key", re.IGNORECASE)


def _looks_nonsecret_value(value: str) -> bool:
    v = value.strip()
    if not v:
        return True
    if _URL_VALUE.match(v) or _ENV_REF_VALUE.match(v):
        return True
    if "***" in v or "..." in v or "…" in v:
        return True
    if _is_sequential_placeholder(v):
        return True
    if len(set(v)) <= 3:  # e.g. "00000000", "abababab" — too low-entropy for a secret
        return True
    low = v.lower()
    if any(w in low for w in _NONSECRET_WORDS):
        return True
    if _SLUG_VALUE.match(v) and not any(ch.isdigit() for ch in v):
        return True
    if _CONST_VALUE.match(v):
        return True
    return False


def _is_label_echo(name: str, value: str) -> bool:
    """True if a quoted value reads as an English phrase AND echoes the credential
    word in its own key's name ("secrets: \\"Leaked secrets\\""). UI labels echo by
    design; real values do not. Spacey values that do NOT echo — a passphrase on a
    generically-named key — still surface: silence there would hide the one
    credential class whose values legitimately contain spaces."""
    m = _CRED_WORD.search(name)
    return (
        " " in value
        and bool(_PROSE_VALUE.match(value))
        and m is not None
        and m.group(0).lower() in value.lower()
    )


def _is_allowlisted(line: str) -> bool:
    low = line.lower()
    return any(token in low for token in _ALLOWLIST)


# How far either side of a match the allowlist/placeholder checks look. Scoped to
# a window around the match — NOT the whole line — so a real secret sharing a line
# with an unrelated mention of `os.environ`/an ellipsis (e.g. in a trailing comment)
# isn't silently dropped or downgraded. A real placeholder/allowlist marker for a
# given credential sits right next to it (the value itself, or an inline comment
# immediately before/after); an unrelated one elsewhere on a long line does not.
_MATCH_WINDOW = 20


def _window(content: str, start: int, end: int) -> str:
    return content[max(0, start - _MATCH_WINDOW):end + _MATCH_WINDOW]


def _redact(secret: str) -> str:
    """Mask a secret for safe display: keep a short head, hide the rest."""
    if len(secret) <= 8:
        return secret[:2] + "..."
    return f"{secret[:4]}...{secret[-2:]}"


def _certain(label: str, match: str, path: str, line: int) -> Finding:
    return Finding(
        category="secret",
        confidence=Confidence.CERTAIN,
        block_eligible=True,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{label} detected at line {line}: '{_redact(match)}'",
        evidence=Evidence(snippet=f"{label}: {_redact(match)}"),
        tool="regex",
        rule_id=RULE_ID,
        fix_suggestion="Remove the secret, rotate it, and load it from an environment variable.",
    )


def _certain_in_test(label: str, match: str, path: str, line: int) -> Finding:
    """Distinctive token in a test/fixture path — surfaced as HIGH advisory, never blocked."""
    return Finding(
        category="secret",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{label} in a test/fixture path at line {line}: '{_redact(match)}' — advisory, not blocked",
        evidence=Evidence(snippet=f"{label} (test fixture): {_redact(match)}"),
        tool="regex",
        rule_id=RULE_ID,
        fix_suggestion="If this is a real credential, remove and rotate it; if it's intentional test material, you can ignore this.",
    )


def _looks_placeholder(content: str) -> bool:
    """A matched key/token that is plainly illustrative, not real material: a
    truncating ellipsis, or a PEM whose BEGIN and END markers sit on a single line
    (an inline string literal with \\n escapes — a real key spans many lines)."""
    if "..." in content or "…" in content:
        return True
    if "-----END" in content:  # whole PEM crammed onto one line == example literal
        return True
    return False


def _has_key_body(added: list[tuple[int, str]], idx: int) -> bool:
    """True if a real PEM key body follows the BEGIN header at ``idx``.

    A genuine private key has substantial base64 body lines after its header; a
    bare or illustrative header (e.g. ``-----BEGIN RSA PRIVATE KEY-----`` listed
    as a detection pattern in a security doc, or three stacked header examples)
    has none. Scanning the following added lines of the same file for base64 body
    is what separates a real, provable key from an illustrative header — so we
    only block on the former. RFC-1421 headers (Proc-Type/DEK-Info) and blank
    lines between header and body are tolerated by scanning a short window.
    """
    for _, line in added[idx + 1 : idx + 41]:
        stripped = line.strip()
        if stripped.startswith("-----BEGIN") or stripped.startswith("-----END"):
            # Another PEM section started before any body line appeared: base64
            # after this point belongs to THAT section (e.g. a certificate example
            # following our bare header), not to the key we are checking.
            return False
        if _PEM_BODY.match(stripped):
            return True
    return False


# A substantial base64 run inside the SAME physical line as the BEGIN header — key
# material crammed into a string literal (how env files and compose embed keys).
_INLINE_BODY = re.compile(r"[A-Za-z0-9+/]{32,}")


def _has_inline_body(after_header: str) -> bool:
    """True if the text after a BEGIN header on the same physical line carries
    real-looking key material — a substantial base64 run with no truncation.

    ``after_header`` is everything following the matched header on the line. A
    truncated skeleton (``-----BEGIN ...\\nMIIEpA...\\n-----END ...``) contains a
    literal ``...``/`…` where body characters would be, and is never real material.
    """
    if "..." in after_header or "…" in after_header:
        return False
    return bool(_INLINE_BODY.search(after_header))


def _advisory(label: str, match: str, path: str, line: int, note: str) -> Finding:
    """A distinctive token downgraded from CERTAIN to HIGH/advisory (example/doc path
    or placeholder body) — surfaced, but never block-eligible."""
    return Finding(
        category="secret",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"{label} {note} at line {line}: '{_redact(match)}' — advisory, not blocked",
        evidence=Evidence(snippet=f"{label}: {_redact(match)}"),
        tool="regex",
        rule_id=RULE_ID,
        fix_suggestion="If this is a real credential, remove and rotate it; if it's an example/placeholder, you can ignore this.",
    )


def _high(name: str, value: str, path: str, line: int) -> Finding:
    return Finding(
        category="secret",
        confidence=Confidence.HIGH,
        block_eligible=False,
        file_path=path,
        line_start=line,
        line_end=line,
        message=f"Possible hardcoded credential '{name}' at line {line}: '{_redact(value)}'",
        evidence=Evidence(snippet=f"{name} = {_redact(value)}"),
        tool="regex",
        rule_id=RULE_ID,
        fix_suggestion="If this is a real credential, move it to an environment variable.",
    )


async def check_secrets(diff: str, repo_context: dict) -> List[Finding]:
    """Detect leaked secrets on added lines. CERTAIN tier blocks; HIGH advises."""
    findings: List[Finding] = []

    # Group added lines per file (parse_diff yields them in order) so a PEM header
    # can look ahead for its key body — a bare header is not a provable secret.
    by_file: dict[str, List[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        by_file.setdefault(path, []).append((line, content))

    for path, added in by_file.items():
        in_test = bool(_TEST_PATH.search(path))
        in_example = bool(_EXAMPLE_PATH.search(path))
        for idx, (line, content) in enumerate(added):
            matched = False
            for label, pattern in _CERTAIN_PATTERNS:
                m = pattern.search(content)
                if not m:
                    continue
                if _is_allowlisted(_window(content, m.start(), m.end())):
                    matched = True  # a real match existed here; don't also fall through to the generic tier
                    break
                # A private-key header with no key material anywhere near it — a bare
                # header quoted in a doc or this detector's own docstring, or a
                # truncated `...` skeleton in an env value — is structurally not a
                # secret: nothing to surface on ANY path, and it must never fall
                # through to _certain below (that would falsely block).
                if label == "private key block":
                    multi_line_body = _has_key_body(added, idx)
                    inline_body = _has_inline_body(content[m.end():])
                    if not multi_line_body and not inline_body:
                        # Nothing to surface — and nothing real matched, so do NOT
                        # set the one-finding-per-line veto: a generic credential
                        # assignment sharing this line must still be examined by
                        # the tier below.
                        continue
                    if inline_body and not multi_line_body:
                        # Real-shaped key material crammed onto one line (an env-var
                        # string literal). Surfaced as advisory on every path — a
                        # one-line literal is never upgraded to CERTAIN, so the
                        # blocking surface is unchanged by this branch.
                        findings.append(_advisory(label, m.group(0), path, line, "inline one-line key literal"))
                        matched = True
                        break
                    # A multi-line key body follows: real key material — existing tiers.
                if in_test:
                    finding = _certain_in_test(label, m.group(0), path, line)
                elif in_example:
                    finding = _advisory(label, m.group(0), path, line, "in an example/template file")
                elif _looks_placeholder(_window(content, m.start(), m.end())):
                    finding = _advisory(label, m.group(0), path, line, "(placeholder, not a real key)")
                else:
                    finding = _certain(label, m.group(0), path, line)
                findings.append(finding)
                matched = True
                break
            if matched:
                continue  # one finding per line; CERTAIN wins over HIGH

            a = _ASSIGNMENT.search(content)
            if a is not None and _is_label_echo(a.group("name"), a.group("value")):
                # Quoted tier only: a phrase value that echoes its own credential
                # name is a UI label, not a credential. Spacey non-echoing values
                # (passphrases on generically-named keys) still surface below.
                # Unquoted .env values with spaces stay advisory — genuinely
                # ambiguous there.
                continue
            if a is None:
                a = _ASSIGNMENT_UNQUOTED.search(content) if _DOTENV_PATH.search(path) else None
            if a:
                # Generic credential-named assignments are FP-prone. Skip them in
                # test/example/doc/compose paths (fixtures, not leaks), values that
                # provably aren't secrets (URLs, env refs, markers, enums, masks), or
                # an allowlist marker near THIS assignment (not just anywhere on the line).
                if in_test or in_example or _looks_nonsecret_value(a.group("value")):
                    continue
                if _is_allowlisted(_window(content, a.start(), a.end())):
                    continue
                findings.append(_high(a.group("name"), a.group("value"), path, line))
    return findings
