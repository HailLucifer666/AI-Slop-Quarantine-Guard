# Prompt: Improve detection precision (cut false positives, surface real leaks)

> Copy everything below the line and give it to the reviewing AI. It is self-contained: it states
> the product's hard constraints, the exact problem, the current code that produces the false
> positives, and precisely what to deliver back.

---

## Your role

You are a senior application-security engineer improving the detection logic of **AI Slop
Quarantine Guard** — a pre-release code-quality + security gate. Your job is to make its findings
**precise**: stop flagging non-leaks (especially secrets in local env files), and make sure it
catches the **real** leaks and risks. You will return revised Python and a clear rationale.

## Non-negotiable product constraints (do not break these)

1. **Never lie about a fact.** A finding may be marked `CERTAIN` / `block_eligible=True` **only**
   when it is reproducible/provable. Anything uncertain is `HIGH`/`MEDIUM` **advisory**, never
   block-eligible.
2. **Fail-safe.** If an external check (registry, OSV, etc.) is unreachable, downgrade to advisory —
   never emit a false block.
3. **Audience is non-technical.** Findings must be high-signal. A wall of low-value advisories is a
   product failure, not "thoroughness."
4. **Surgical changes only.** Keep the `Finding` dataclass contract and the analyzer function
   signatures (`async def check_x(diff, repo_context, ...) -> List[Finding]`). Don't rewrite the
   architecture; improve the decision logic.

## The problem (what's wrong right now)

The scanner over-reports. The worst offenders:

- **Secrets in env files are flagged as leaks.** A real `.env` / `.env.local` / `.env.production`
  is **local configuration that is expected to contain secret values and is normally gitignored** —
  finding a key there is **not a leak**, it's the file doing its job. The current allowlist only
  spares `.env.*example` paths, so a genuine `.env.local` gets a `CERTAIN` secret finding. That is a
  false positive and erodes trust.
- **The generic-assignment secret tier** (`name(secret|token|api_key...) = "8+ chars"`) fires on
  config defaults, sample values, enums, and non-secret strings.
- **Placeholder (SQG003) and SAST (SQG006) regexes** fire on substrings in strings/comments
  (`TODO` in a string, `shell=True` as a dict value, `.innerHTML =` on a constant), producing noise.

Meanwhile **real risks slip through** (no entropy detection for prefix-less secrets, no detection of
a secret committed in *tracked source code*, no typosquat detection).

### Important distinction we want you to encode: "leak" vs "local config"

The product question is not "does this string look like a secret?" but **"is this a secret that has
actually leaked / been committed where it shouldn't be?"** Guidance:
- A secret in `.env`, `.env.local`, `.env.*` (non-example) → **expected location, normally
  gitignored → advisory at most, never a `CERTAIN` leak.** (Optionally: only escalate if we have
  evidence the file is tracked/committed.)
- A secret in **application source code** (`.py`, `.ts`, `.js`, `.go`, config checked into the repo,
  CI YAML) → **that is a real leak → `CERTAIN`/block-eligible** when the token shape is provable.
- A secret in `tests/`/`examples/`/`docs/` → advisory (already handled — keep it).

## Current code (the files you will improve)

### `analyzers/base.py` — the contract (DO NOT change shape)
```python
class Confidence(str, Enum):
    CERTAIN = "CERTAIN"   # provable / reproducible -> only tier that may block
    HIGH    = "HIGH"      # strong signal, FP-prone  -> advisory
    MEDIUM  = "MEDIUM"    # worth a look            -> advisory

@dataclass
class Finding:
    category: str          # dependency | secret | placeholder | vulnerability | license | sast
    confidence: Confidence
    block_eligible: bool   # True ONLY on CERTAIN provable findings
    file_path: str
    line_start: int
    line_end: int
    message: str
    evidence: Evidence     # snippet (+ optional context_before/after)
    tool: str
    rule_id: str           # SQG001..SQG006
    fix_suggestion: Optional[str] = None
```

### `analyzers/secrets.py` — SQG002, the main FP source (FULL current file)
```python
"""SQG002 — leaked-secret detector (offline regex, no external tool)."""

import re
from typing import List
from app.diff import parse_diff
from .base import Confidence, Evidence, Finding

RULE_ID = "SQG002"

_ALLOWLIST = (
    "example", "your_", "your-", "yourkey", "placeholder", "changeme",
    "change-me", "redacted", "dummy", "<your", "xxxxxx",
    "os.environ", "os.getenv", "getenv", "process.env", "${", "{{",
)

_CERTAIN_PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
]

_PEM_BODY = re.compile(r"^[A-Za-z0-9+/]{32,}={0,2}$")

# Paths where a distinctive token is treated as test material -> downgraded to advisory.
_TEST_PATH = re.compile(
    r"(?:^|/)(?:tests?|__tests__|testdata|test[-_]data|fixtures?|mocks?|"
    r"examples?|samples?|e2e|specs?|__mocks__)(?:/|$)|\.(?:test|spec)\.",
    re.IGNORECASE,
)

# Illustrative-by-nature files -> distinctive match downgraded to advisory.
_EXAMPLE_PATH = re.compile(
    r"(?:^|/)(?:docs?|examples?|samples?)(?:/|$)"
    r"|\.(?:example|sample|dist|template)(?:$|\.)"
    r"|(?:^|/)\.env\.[^/]*example"     # NOTE: only *.example env files are spared
    r"|(?:^|/)readme",
    re.IGNORECASE,
)

# HIGH tier: a credential-named identifier assigned a quoted literal >= 8 chars.
_ASSIGNMENT = re.compile(
    r"""(?P<name>\b\w*(?:secret|token|passwd|password|pwd|api[_-]?key|access[_-]?key)\w*\b)"""
    r"""\s*[:=]\s*['"](?P<value>[^'"]{8,})['"]""",
    re.IGNORECASE,
)

def _is_allowlisted(line: str) -> bool:
    low = line.lower()
    return any(token in low for token in _ALLOWLIST)

def _redact(secret: str) -> str:
    if len(secret) <= 8:
        return secret[:2] + "..."
    return f"{secret[:4]}...{secret[-2:]}"

# ... _certain / _certain_in_test / _advisory / _high builders return Findings ...

def _looks_placeholder(content: str) -> bool:
    if "..." in content or "…" in content:
        return True
    if "-----END" in content:          # whole PEM on one line == example literal
        return True
    return False

def _has_key_body(added, idx) -> bool:
    for _, line in added[idx + 1 : idx + 41]:
        if _PEM_BODY.match(line.strip()):
            return True
    return False

async def check_secrets(diff: str, repo_context: dict) -> List[Finding]:
    findings: List[Finding] = []
    by_file: dict[str, List[tuple[int, str]]] = {}
    for path, line, content in parse_diff(diff):
        by_file.setdefault(path, []).append((line, content))

    for path, added in by_file.items():
        in_test = bool(_TEST_PATH.search(path))
        in_example = bool(_EXAMPLE_PATH.search(path))    # <-- .env.local NOT matched here
        for idx, (line, content) in enumerate(added):
            if _is_allowlisted(content):
                continue
            matched = False
            for label, pattern in _CERTAIN_PATTERNS:
                m = pattern.search(content)
                if not m:
                    continue
                if label == "private key block" and not _has_key_body(added, idx):
                    finding = _advisory(label, m.group(0), path, line, "header only, no key body")
                elif in_test:
                    finding = _certain_in_test(label, m.group(0), path, line)
                elif in_example:
                    finding = _advisory(label, m.group(0), path, line, "in an example/template file")
                elif _looks_placeholder(content):
                    finding = _advisory(label, m.group(0), path, line, "(placeholder, not a real key)")
                else:
                    finding = _certain(label, m.group(0), path, line)   # <-- .env.local lands here = FALSE POSITIVE
                findings.append(finding); matched = True
                break
            if matched:
                continue
            a = _ASSIGNMENT.search(content)
            if a:
                findings.append(_high(a.group("name"), a.group("value"), path, line))
    return findings
```

### `analyzers/placeholders.py` — SQG003 (noise: substring matches in code lines)
```python
_PATTERNS = [
    ("TODO/FIXME marker", re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")),
    ("not-implemented stub", re.compile(r"NotImplementedError|throw new Error\(\s*['\"]not implemented|\bnot implemented\b", re.I)),
    ("ellipsis-only body", re.compile(r"^\s*\.\.\.\s*$")),
    ("placeholder prose", re.compile(r"\b(your code here|rest of (?:the )?code(?: here)?|implement (?:this|here)|fill in (?:the )?(?:rest|implementation)|add your .+ here)\b", re.I)),
]
# Only doc files are skipped; matches inside string literals / inline comments still fire. All MEDIUM, never block.
```

### `analyzers/sast.py` — SQG006 (noise: regex sinks fire in strings / safe contexts)
```python
_PY_PATTERNS = [
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("use of exec()", Confidence.HIGH, re.compile(r"(?<![.\w])exec\s*\(")),
    ("os.system() call", Confidence.HIGH, re.compile(r"\bos\.system\s*\(")),
    ("subprocess with shell=True", Confidence.HIGH, re.compile(r"shell\s*=\s*True")),
    ("insecure deserialization (pickle)", Confidence.MEDIUM, re.compile(r"\bpickle\.loads?\s*\(")),
    ("unsafe yaml.load()", Confidence.MEDIUM, re.compile(r"\byaml\.load\s*\((?!.*SafeLoader)")),
    ("weak hash (md5/sha1)", Confidence.MEDIUM, re.compile(r"\bhashlib\.(?:md5|sha1)\s*\(")),
]
_JS_PATTERNS = [
    ("use of eval()", Confidence.HIGH, re.compile(r"(?<![.\w])eval\s*\(")),
    ("child_process exec()", Confidence.HIGH, re.compile(r"child_process\.exec(?:Sync)?\s*\(")),
    ("React dangerouslySetInnerHTML", Confidence.MEDIUM, re.compile(r"dangerouslySetInnerHTML")),
    ("innerHTML assignment", Confidence.MEDIUM, re.compile(r"\.innerHTML\s*=(?!=)")),
    ("document.write()", Confidence.MEDIUM, re.compile(r"document\.write\s*\(")),
]
# Doc files skipped, # nosec / # noqa honored, comment-only lines skipped. All advisory.
```

### Context the analyzers receive
- `parse_diff` yields only **added** lines as `(file_path, new_line_number, added_content)`.
- For a **whole-repo scan**, a synthetic diff marks **every line of every file as "added"** — so the
  analyzers run over the full codebase. This means advisory rules report on the *entire* repo at once
  (noise is amplified). Binary/vendored dirs (`node_modules`, `.venv`, `dist`, `.git`, ...) are
  already excluded at ingest; `.env`/`.env.local` files ARE ingested and scanned.

## What to deliver

1. **Revised `secrets.py` logic** that:
   - Treats real env files (`.env`, `.env.local`, `.env.*` except `*.example`/`*.sample`/`*.template`)
     as **expected secret-holding local config → advisory, never `CERTAIN`/block-eligible.** Explain
     your chosen policy (and, if useful, how committing-vs-gitignored could later refine it).
   - **Escalates real leaks:** a distinctive, structurally-valid token in **tracked application
     source code** stays `CERTAIN`/block-eligible.
   - Tightens or removes the generic `_ASSIGNMENT` tier so it stops firing on config defaults / sample
     values (consider: require higher entropy, exclude obvious non-secrets, or gate it to specific
     contexts). Add **entropy-based detection** for prefix-less high-entropy secrets if it raises
     precision without hurting the zero-false-block guarantee.
   - Keeps redaction and the existing test/example/PEM-body downgrades.
2. **Precision fixes for SQG003 and SQG006**: don't fire on matches inside string literals or comments;
   reduce obvious safe-context FPs (e.g. `yaml.load(..., Loader=SafeLoader)`, `shell=True` only when it
   is a real keyword arg). Keep them advisory.
3. **A crisp policy table** — for each rule, "FLAG this" vs "DO NOT flag this", with concrete examples
   (including the `.env.local` case). This is the spec we'll hold the code to.
4. **Test cases** (positive + negative) for each change — especially negative fixtures that must NOT
   produce a finding (`.env.local` with a real-looking key, a `TODO` inside a string, `shell=True` in a
   dict). The project's bar is **zero false positives on the negative fixture set.**
5. **Rationale**: for every escalation to `CERTAIN`/block-eligible, justify why it is provable. For
   every downgrade, justify why the old behavior was a false positive.

Return the revised Python in full (not diffs), the policy table, and the tests. Do not change the
`Finding` contract or the analyzer signatures.
