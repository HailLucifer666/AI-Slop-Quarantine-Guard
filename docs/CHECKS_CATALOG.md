# CHECKS_CATALOG — Every Check, Explained

Each check is normalized into one universal **Finding** record:

```
{
  category: str,           # SQG001, SQG002, etc.
  confidence: str,         # CERTAIN | HIGH | MEDIUM
  block_eligible: bool,    # true iff confidence==CERTAIN
  file_path: str,
  line_start: int,
  line_end: int,
  message: str,
  evidence: {
    snippet: str,
    context_before: [str, ...],
    context_after: [str, ...]
  },
  tool: str,
  fix_suggestion: str (optional),
  analyzer_version: str,
  rule_version: str,
  tool_version: str
}
```

---

## SQG001: Non-existent / Hallucinated Package

| Aspect | Details |
|---|---|
| **Category** | Dependency integrity |
| **Tools** | Custom registry clients (PyPI JSON API, npm, crates.io, Go proxy) |
| **Confidence** | **CERTAIN** (if registry reachable and returns clean 404) |
| **Block-Eligible** | ✓ Yes (CERTAIN) |
| **Message** | `"Package 'quantumllm_helper==1.0.0' does not exist in PyPI (404)"` |

### False-Positive Controls

- **Whitelist workspace packages:** detect `workspace:`, `file:`, `link:` refs and monorepo workspaces (`pnpm-workspace.yaml`, `turbo.json`, Cargo workspaces).
- **Whitelist scoped/private packages:** `@org/*` and private-registry config paths.
- **Grace window:** packages published <72 hours ago → `HIGH` confidence (not `CERTAIN`); indexes lag.
- **Fail-safe for registry unavailable/timeout/429:** retry with exponential backoff; if still failing after N retries, downgrade to `HIGH` + log (never block on registry failure).
- **Path allowlist:** ignore version specifiers in comments (`# old: v1.2.3`), git refs (`git+https://...`).

### Scope

- **Supported manifests:** `requirements.txt`, `pyproject.toml` (pip, poetry, uv), `package.json` (npm, pnpm, yarn, bun), `Cargo.toml` (Rust), `go.mod` (Go), `Gemfile` (Ruby).
- **Parsed via real libraries:** `packaging` (Python), `tomli` (TOML), actual `package.json` parser, `Cargo.toml` TOML parser.

---

## SQG002: Leaked Secrets / API Keys

| Aspect | Details |
|---|---|
| **Category** | Credential exposure |
| **Tools** | **gitleaks** (patterns) + **TruffleHog** (entropy, format validation) |
| **Confidence** | **CERTAIN** (if signature/checksum matches known format AND commit-added diff) · **HIGH** (pattern match only, no format verify) |
| **Block-Eligible** | ✓ Yes (CERTAIN) |
| **Message** | `"Potential AWS secret key (AKIA...) detected at line 42; commit added this line"` |

### False-Positive Controls

- **Commit-diff mapping:** only flag secrets in *newly added* lines (not pre-existing).
- **Format checksum:** AWS keys start with `AKIA`, Stripe keys with `sk_live_` or `sk_test_`, etc. Match exact format before flagging as `CERTAIN`.
- **Path allowlist:** skip `*.example`, `test/fixtures/`, `docs/examples/`, `.github/workflows/` (CI examples).
- **Entropy floor:** gitleaks' built-in entropy filter (skip obvious non-secrets like `aaaaaa`).
- **Live verification (Phase 9+, not MVP):** Optional second check: call AWS/Stripe/GitHub API with the key to see if it's actually valid. MVP ships offline only.

### Scope

- **Patterns:** passwords, API keys, tokens, SSH keys, database URLs, OAuth secrets, webhook secrets.
- **Tools:** `gitleaks` (800+ patterns) scans each commit; `TruffleHog` validates entropy + optional format.

---

## SQG003: Placeholder / Incomplete Code

| Aspect | Details |
|---|---|
| **Category** | Code maturity |
| **Tools** | Regex + **tree-sitter** AST |
| **Confidence** | **MEDIUM** (context-dependent; might be intentional) |
| **Block-Eligible** | ✗ No (advisory only) |
| **Message** | `"TODO comment at line 15: 'TODO: implement password hashing'"` |

### False-Positive Controls

- **Scope to code files only:** skip `*.md`, `*.txt`, comments in generated code.
- **Context window:** look for surrounding implementation; if the function is complete and the TODO is aspirational, downgrade to skip.
- **Allowlist patterns:** intentional placeholders like `# noqa: E501` or `# type: ignore`.
- **Regex only for MVP:** tree-sitter AST parsing (context-aware) deferred to Phase 3+; start with regex patterns.

### Patterns Matched

- `TODO`, `FIXME`, `XXX` comments.
- `NotImplementedError`, `pass  # TODO`, `throw new NotImplementedError()`.
- Empty function bodies.
- Ellipsis (`...`) as body.
- `print("debug")` left behind.

---

## SQG004: Known-Vulnerable Dependencies (CVE)

| Aspect | Details |
|---|---|
| **Category** | Supply-chain security |
| **Tools** | **Trivy** + **OSV-Scanner** |
| **Confidence** | **HIGH** (version match + CVE database hit) · **MEDIUM** (uncertain if function called) |
| **Block-Eligible** | ✗ No (for Phase 9+, after measured FP <1%, can opt-in blocking) |
| **Message** | `"Dependency 'django==3.0.1' has CVE-2020-9402 (SQL injection in ORM)"` |

### Clarification: Why Not CERTAIN?

The **fact** "package X version Y is installed and has CVE-Z" is certain. But "your code is exploitable" is not—the vulnerable code path might never execute. We conservatively rate this `HIGH` (very likely problematic) but reserve `CERTAIN` for unreachable-registry 404s and checksum-valid secrets.

### False-Positive Controls

- **Version matching:** exact version pin only; don't flag ranges.
- **Already patched:** if lockfile shows updated version, don't flag.
- **Severity filtering:** focus on CVSS ≥7.0 (HIGH/CRITICAL); lower severities are noise.
- **Database reconciliation:** Trivy + OSV, cross-check results (one might miss an old CVE).

### Scope

- **Manifest parsing:** extract declared + locked dependencies from `requirements.txt`, `poetry.lock`, `package-lock.json`, `Cargo.lock`, `go.mod`, `Gemfile.lock`.
- **Tools:** Trivy scans installed tree; OSV matches against Google's CVE database.

---

## SQG005: Risky / Incompatible Licenses

| Aspect | Details |
|---|---|
| **Category** | Legal compliance |
| **Tools** | **Trivy** + **Syft** |
| **Confidence** | **HIGH** (GPL in proprietary = risky) · **MEDIUM** (unknown license) |
| **Block-Eligible** | ✗ No (advisory, legal decision required) |
| **Message** | `"Dependency 'libgpl==1.0' is GPL; your project is proprietary. Risk: forced open-source."` |

### False-Positive Controls

- **Allowlist safe licenses:** MIT, Apache 2.0, BSD, ISC all OK for proprietary.
- **Permissive + GPL:** LGPL is safer (linking OK, distribution requires disclosure).
- **Unknown licenses:** flag but lower severity (gather info, make manual decision).
- **Org policy:** dashboard setting to define acceptable licenses per repo.

### Scope

- **Licenses detected:** via SPDX identifiers in manifests + license files in source trees.
- **Tools:** Trivy for high-level scanning; Syft for SBOM + detailed license mapping.

---

## SQG006: Security Vulnerabilities (SAST)

| Aspect | Details |
|---|---|
| **Category** | Code patterns |
| **Tools** | **Semgrep** (P0/P1 rules only) |
| **Confidence** | **HIGH** (proven pattern, potential exploit) |
| **Block-Eligible** | ✗ No (Phase 9+: opt-in, after measured FP <1%) |
| **Message** | `"SQL injection risk: user input concatenated into query at line 42 (CWE-89)"` |

### Why Only P0/P1 Rules?

P0/P1 = proven, exploitable patterns. P2/P3 = style/best-practice (too much noise, kills the signal).

### False-Positive Controls

- **Parameterized queries:** whitelist if detected.
- **ORM usage:** ORM-based queries are safe; flag raw SQL only.
- **Validation context:** if input is validated/sanitized first, downgrade.
- **Language-specific:** rules differ per language; Semgrep handles this.

### Scope

- **Patterns:** SQL injection, XSS, CSRF, hardcoded secrets (secondary check), unsafe deserialization, unsafe file operations.
- **Tool:** Semgrep OSS + community ruleset (not bleeding-edge private rules).

---

## SQG007: AI Reasoning Scratchpads (Experimental, OFF by Default)

| Aspect | Details |
|---|---|
| **Category** | Code cleanliness |
| **Tools** | Regex (file-type gated) |
| **Confidence** | **MEDIUM** (false-positive prone if not scoped) |
| **Block-Eligible** | ✗ No (advisory, off by default) |
| **Message** | `"AI reasoning block found at line 10; remove before shipping"` |

### False-Positive Controls

- **File-type gate:** only flag in `.md`, `.txt`, `.py` files; skip `.xml`, `.html`, `.json` (legit XML/HTML).
- **Narrow pattern:** match only `<thinking>`, `<plan>` on their own lines; skip XML tags in data.
- **Commit allowlist:** `.github/`, `docs/`, tests— exclude from default checks.
- **Opt-in:** this check is **OFF by default**; users enable if they care.

### Scope

- **Detects:** `<thinking>...</thinking>`, `<plan>...</plan>` blocks committed accidentally.
- **Use case:** catching AI tool's scratch work that snuck into code.

---

## Plugin Architecture (Future-Proofing)

Each analyzer is registered as a plugin:

```python
class PluginRegistry:
    analyzers: Dict[str, AnalyzerPlugin] = {
        "SQG001": DependencyAnalyzer(...),
        "SQG002": SecretsAnalyzer(...),
        # ...
    }
```

Properties:
- `id` (SQG###)
- `version` (e.g., "1.2.3")
- `confidence_model` (function that computes CERTAIN/HIGH/MEDIUM)
- `enabled` (kill switch)
- `analyze(diff, context) → [Finding, ...]`

**Benefits:**
- Enable/disable per-repo via env var or dashboard.
- Custom analyzers (organization-specific rules).
- Third-party analyzers (marketplace, future).
- No code changes to disable a misfiring checker.

---

## Confidence Scoring (Three Axes)

1. **`evidence_confidence`:** How strong is the raw signal? (0–100%)
2. **`finding_confidence`:** After context (reachability, format, path), is it a real issue? (CERTAIN/HIGH/MEDIUM)
3. **`block_eligible`:** Can this finding block a merge? (bool, true iff CERTAIN)

The `confidence_resolver` module centralizes this logic (one place to audit, unit-test, and maintain).

---

## Summary Table (Quick Reference)

| Check | Category | Tools | Confidence | Block-Eligible |
|---|---|---|---|---|
| SQG001 | Dependency | Registry APIs | CERTAIN | ✓ |
| SQG002 | Secrets | gitleaks + TruffleHog | CERTAIN/HIGH | ✓ |
| SQG003 | Placeholders | Regex + tree-sitter | MEDIUM | ✗ |
| SQG004 | CVE | Trivy + OSV | HIGH | ✗ |
| SQG005 | License | Trivy + Syft | HIGH/MEDIUM | ✗ |
| SQG006 | SAST | Semgrep (P0/P1) | HIGH | ✗ |
| SQG007 | AI scratchpad | Regex | MEDIUM | ✗ |

---

## Phase-In Schedule

- **Phase 1:** SQG001 (dependencies) + SQG002 (secrets, offline) calibrated.
- **Phase 3:** + SQG004 (CVE) + SQG006 (SAST) + SQG005 (licenses) + SQG003 (placeholders).
- **Phase 9:** SQG002 live verification (opt-in); SQG004/SQG006 blocking (opt-in, if FP <1%).
- **Backlog:** SQG007 (off by default, polish later).

