# CHECKS_CATALOG — Every Check, Explained

> ## Implementation status — read this before the tables below
>
> This document previously described gitleaks, TruffleHog, Trivy, Syft and Semgrep as the
> tools in use. **None of those binaries is invoked by the product today.** SQG002, SQG003
> and SQG006 are hand-written Python pattern matchers; SQG005 reads license metadata from
> registry JSON. `api/pyproject.toml` contains no security-scanning dependency at all.
>
> What is real today:
>
> | Check | What actually runs | Planned engine (not yet wired) |
> |---|---|---|
> | SQG001 | Live PyPI / npm / crates.io registry lookups | — |
> | SQG002 | Curated regex + format validation (`analyzers/secrets.py`) | gitleaks |
> | SQG003 | Regex over added lines (`analyzers/placeholders.py`) | tree-sitter AST |
> | SQG004 | Live OSV.dev HTTP API (`analyzers/vulns.py`) | Trivy, osv-scanner |
> | SQG005 | PyPI / npm registry license metadata (`analyzers/licenses.py`) | Trivy, Syft |
> | SQG006 | Curated regex, Python + JavaScript only (`analyzers/sast.py`) | Semgrep |
> | SQG007 | Edit distance against a curated popular-package list | — |
>
> Each check reports its own coverage at runtime (`api/app/coverage.py`), and a scan states
> which engines are absent and what that costs (`api/app/engines.py`, `GET /api/health`). A
> check that could not run is reported as not run — never as a pass. The "Planned engine"
> column is intent, not current behaviour; treat the per-check **Tools** rows below the same
> way, and trust `coverage` on an actual scan over anything written here.

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
| **Tools** | **Today:** curated regex + format validation, in-process (`analyzers/secrets.py`). **Planned:** gitleaks (patterns), TruffleHog (entropy) |
| **Confidence** | **CERTAIN** (if signature/checksum matches known format AND commit-added diff) · **HIGH** (pattern match only, no format verify) |
| **Block-Eligible** | ✓ Yes (CERTAIN) |
| **Message** | `"Potential AWS secret key (AKIA...) detected at line 42; commit added this line"` |

### False-Positive Controls

- **Commit-diff mapping:** only flag secrets in *newly added* lines (not pre-existing).
- **Format checksum:** AWS keys start with `AKIA`, Stripe keys with `sk_live_` or `sk_test_`, etc. Match exact format before flagging as `CERTAIN`.
- **Path allowlist:** skip `*.example`, `test/fixtures/`, `docs/examples/`, `.github/workflows/` (CI examples).
- **Entropy floor:** planned via gitleaks' built-in entropy filter (skip obvious non-secrets like `aaaaaa`). Today the in-process matcher relies on format validation rather than entropy.
- **Live verification (Phase 9+, not MVP):** Optional second check: call AWS/Stripe/GitHub API with the key to see if it's actually valid. MVP ships offline only.

### Scope

- **Patterns:** passwords, API keys, tokens, SSH keys, database URLs, OAuth secrets, webhook secrets.
- **Tools:** today, a curated in-process pattern set with format validation (AWS, GitHub, Stripe, Slack, Google, PEM). Planned: `gitleaks` (800+ patterns) per commit, `TruffleHog` for entropy. Until then the pattern set is deliberately narrow-but-precise, and the coverage record says gitleaks is not installed.

---

## SQG003: Placeholder / Incomplete Code

| Aspect | Details |
|---|---|
| **Category** | Code maturity |
| **Tools** | **Today:** regex over added lines (`analyzers/placeholders.py`). **Planned:** tree-sitter AST for context |
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
| **Tools** | **Today:** OSV.dev HTTP API, batched (`analyzers/vulns.py`). **Planned:** Trivy and osv-scanner for ecosystems the in-process manifest parsers can't read |
| **Confidence** | **HIGH** (version match + CVE database hit) · **MEDIUM** (uncertain if function called) |
| **Block-Eligible** | ✗ No (for Phase 9+, after measured FP <1%, can opt-in blocking) |
| **Message** | `"Dependency 'django==3.0.1' has CVE-2020-9402 (SQL injection in ORM)"` |

### Clarification: Why Not CERTAIN?

The **fact** "package X version Y is installed and has CVE-Z" is certain. But "your code is exploitable" is not—the vulnerable code path might never execute. We conservatively rate this `HIGH` (very likely problematic) but reserve `CERTAIN` for unreachable-registry 404s and checksum-valid secrets.

### False-Positive Controls

- **Version matching:** exact version pin only; don't flag ranges.
- **Already patched:** if lockfile shows updated version, don't flag.
- **Severity filtering:** focus on CVSS ≥7.0 (HIGH/CRITICAL); lower severities are noise.
- **Database reconciliation:** planned — cross-check Trivy against OSV, since one may miss an old CVE. Today only OSV is queried, so there is no second opinion; the coverage record names the missing engines.

### Scope

- **Manifest parsing (today):** `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml` for declared deps; `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum` for exact pins. **Not parsed yet:** `go.mod`, `pom.xml`, `build.gradle`, `Gemfile.lock`, `composer.lock`, `*.csproj` — a repo using only those is reported as not covered, not as clean.
- **Tools:** today, OSV matched against Google's advisory database over HTTP. Planned: Trivy over the resolved tree, for the ecosystems above.
- **Range specs:** a manifest declaring `^1.2.3` with no lockfile cannot be resolved to an installed version, so SQG004 reports *partial* coverage rather than guessing.

---

## SQG005: Risky / Incompatible Licenses

| Aspect | Details |
|---|---|
| **Category** | Legal compliance |
| **Tools** | **Today:** license metadata from PyPI / npm registry JSON (`analyzers/licenses.py`) — pypi and npm only. **Planned:** Trivy, Syft for SBOM-based detection |
| **Confidence** | **HIGH** (GPL in proprietary = risky) · **MEDIUM** (unknown license) |
| **Block-Eligible** | ✗ No (advisory, legal decision required) |
| **Message** | `"Dependency 'libgpl==1.0' is GPL; your project is proprietary. Risk: forced open-source."` |

### False-Positive Controls

- **Allowlist safe licenses:** MIT, Apache 2.0, BSD, ISC all OK for proprietary.
- **Permissive + GPL:** LGPL is safer (linking OK, distribution requires disclosure).
- **Unknown licenses:** flag but lower severity (gather info, make manual decision).
- **Org policy:** dashboard setting to define acceptable licenses per repo.

### Scope

- **Licenses detected (today):** the registry's own license field, SPDX expression and trove classifiers for PyPI and npm packages. Cargo, Go, Maven, Bundler, Composer and NuGet are **not** covered and are reported as such.
- **Tools:** today, registry JSON already fetched for SQG001. Planned: Trivy for high-level scanning, Syft for SBOM + detailed license mapping.

---

## SQG006: Security Vulnerabilities (SAST)

| Aspect | Details |
|---|---|
| **Category** | Code patterns |
| **Tools** | **Today:** curated regex sink detector, **Python and JavaScript/TypeScript only** (`analyzers/sast.py`). **Planned:** Semgrep (P0/P1 rules) for real multi-language analysis |
| **Confidence** | **HIGH** (proven pattern, potential exploit) |
| **Block-Eligible** | ✗ No (Phase 9+: opt-in, after measured FP <1%) |
| **Message** | `"SQL injection risk: user input concatenated into query at line 42 (CWE-89)"` |

### Why Only P0/P1 Rules?

P0/P1 = proven, exploitable patterns. P2/P3 = style/best-practice (too much noise, kills the signal).

### False-Positive Controls

- **Parameterized queries:** whitelist if detected.
- **ORM usage:** ORM-based queries are safe; flag raw SQL only.
- **Validation context:** if input is validated/sanitized first, downgrade.
- **Language-specific:** rules differ per language; Semgrep would handle this. The current regex set is gated by file extension instead, which is why unsupported languages are reported as not covered.

### Scope

- **Patterns detected today:** code execution (`eval`, `exec`), command injection (`os.system`, `subprocess(shell=True)`, `child_process.exec`), unsafe deserialization (`pickle`, `yaml.load`), weak hashing (md5/sha1), and DOM-XSS sinks (`innerHTML`, `dangerouslySetInnerHTML`, `document.write`). Each carries its CWE id.
- **Not detected today:** SQL injection and CSRF (they need dataflow, not pattern matching), and anything in Go, Java, Ruby, PHP, C#, Rust, C/C++ or SQL — those files are reported as uninspected.
- **Tool:** planned Semgrep OSS + community ruleset. Not installed today.

---

## SQG007: Typosquatted Package Names

> **Rule-ID correction.** This document previously assigned SQG007 to an "AI reasoning
> scratchpad" detector that was never built. The shipped SQG007 is a **typosquat**
> detector (`api/app/analyzers/typosquat.py`), always on. Two different checks were
> sharing one supposedly stable id.
>
> Resolved in favour of the code, not the doc: SQG007 **is** typosquat. Renumbering it
> would orphan SQG007 findings already stored in scan history and silently change the
> meaning of any `blocked_rules` setting that names it. The unbuilt scratchpad detector is
> re-assigned to **SQG008** below, and is not implemented.

| Aspect | Details |
|---|---|
| **Category** | Dependency integrity |
| **Tools** | Levenshtein distance against a curated popular-package list (`analyzers/popular_packages.py`) |
| **Confidence** | **HIGH** — a suspicion, never a proven fact |
| **Block-Eligible** | ✗ No (advisory only, by design) |
| **Message** | `"Dependency 'reqeusts' is a near look-alike of the popular package 'requests' — possible typosquat. Verify it's the package you intended."` |

### Why never CERTAIN

The look-alike usually *does* exist on the registry, so "this is a typosquat" is an
inference about intent, not a reproducible fact. Calling it CERTAIN or blocking on it
would break the product's own honesty rule.

### False-Positive Controls

- **Not itself popular:** a name present in the curated list is the real thing, not a typo of it.
- **Length-scaled distance:** allowed edit distance scales with the target's length, so short names don't collide by coincidence.
- **Minimum length:** names under 3 characters are skipped entirely.
- **Ecosystems:** pypi and npm only; others are reported as not covered.

### Known limitation

The curated list is a hand-maintained snapshot with no refresh mechanism, so a genuinely
popular package that isn't on it can be flagged as a near-miss of one that is (for
example `reqwest` against `request`). Suppressing that class properly needs a registry
cross-check with download statistics. Findings stay advisory, which bounds the damage.

---

## SQG008: AI Reasoning Scratchpads — NOT IMPLEMENTED

Specified, never built. No code, no rule id in use. Documented so the intent isn't lost
and so the number isn't accidentally reused.

- **Would detect:** `<thinking>...</thinking>`, `<plan>...</plan>` blocks committed accidentally.
- **Would be:** MEDIUM, advisory, **off by default**, gated to `.md` / `.txt` / `.py` to
  avoid flagging legitimate XML/HTML.
- **Status:** backlog. A scan today neither runs nor reports this check.

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

"Tools" below is what runs **today**. Planned engines are named per check above.

| Check | Category | Tools (today) | Coverage today | Confidence | Block-Eligible |
|---|---|---|---|---|---|
| SQG001 | Dependency | Registry APIs (PyPI, npm, crates.io) | pypi, npm, crates | CERTAIN | ✓ |
| SQG002 | Secrets | In-process regex + format validation | all text files | CERTAIN/HIGH | ✓ |
| SQG003 | Placeholders | Regex | all text files | MEDIUM | ✗ |
| SQG004 | CVE | OSV.dev HTTP API | pypi, npm, crates, go | HIGH | ✗ |
| SQG005 | License | Registry license metadata | pypi, npm | HIGH/MEDIUM | ✗ |
| SQG006 | SAST | Regex sink detector | Python, JS/TS only | HIGH/MEDIUM | ✗ |
| SQG007 | Typosquat | Edit distance vs curated list | pypi, npm | HIGH | ✗ |
| SQG008 | AI scratchpad | **not implemented** | — | — | — |

---

## Phase-In Schedule

- **Phase 1:** SQG001 (dependencies) + SQG002 (secrets, offline) calibrated.
- **Phase 3:** + SQG004 (CVE) + SQG006 (SAST) + SQG005 (licenses) + SQG003 (placeholders).
- **Phase 9:** SQG002 live verification (opt-in); SQG004/SQG006 blocking (opt-in, if FP <1%).
- **Backlog:** SQG008 (AI scratchpad — never built). SQG007 (typosquat) already ships.

