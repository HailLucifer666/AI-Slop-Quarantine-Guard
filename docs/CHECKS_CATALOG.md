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
> | SQG004 | Live OSV.dev HTTP API (`analyzers/vulns.py`) over pypi, npm, crates, go, maven, rubygems, packagist, nuget | Trivy, osv-scanner |
> | SQG005 | PyPI / npm registry license metadata + `composer.lock` declared licenses (`analyzers/licenses.py`) | Trivy, Syft |
> | SQG006 | Curated regex, Python + JavaScript only (`analyzers/sast.py`) | Semgrep |
> | SQG007 | Edit distance against a curated popular-package list | — |
> | SQG009 | Python `ast` rewrite detection (`analyzers/simplify.py`) | tree-sitter for JS/TS |
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
| **Tools** | Custom registry clients — PyPI JSON API, npm registry, crates.io (`registries.py`). **No Go proxy client exists**; see Scope below for why the other ecosystems are deliberately not existence-checked |
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

- **Supported manifests (today):** `requirements.txt`, `pyproject.toml` (pip, poetry, uv), `package.json` (npm, pnpm, yarn, bun), `Cargo.toml` (Rust) — the three ecosystems `registries.py` has a client for. `go.mod` and `Gemfile` are **not** existence-checked; the coverage table lists their ecosystems under *not covered* for this rule.
- **Why not the other ecosystems, when SQG004 covers them:** the two rules need different things. SQG004 asks OSV about an (ecosystem, name, version) triple and a wrong answer is an advisory; SQG001 asks a registry whether a name exists at all, and a clean 404 is **CERTAIN and block-eligible**. Go, Maven and NuGet are the ecosystems where private and internal artifacts are most common (a company GitLab module path, an internal Nexus artifact, a private NuGet feed), so a public-registry 404 there is frequently not evidence of a hallucinated package. Shipping it would mean either false blocks or advisory noise on every internal dependency. The controls that make this safe for pypi/npm — `has_pip_extra_index`, `npmrc_private_scopes` — have no equivalent yet for `settings.xml`, `nuget.config` or `GOPRIVATE`. Until they do, the honest report is *not covered*.
- **Parsed via real libraries:** stdlib `tomllib` (TOML), the stdlib `json` parser for `package.json`, and a PEP 508 name tokenizer for requirements.

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

- **Manifest parsing (today):** `requirements.txt`, `pyproject.toml`, `package.json`, `Cargo.toml` for declared deps; `package-lock.json`, `yarn.lock`, `poetry.lock`, `Cargo.lock`, `go.sum`, `Gemfile.lock`, `composer.lock`, `packages.lock.json` for exact pins; `go.mod`, `pom.xml`, `build.gradle(.kts)` and `*.csproj`/`*.fsproj`/`*.vbproj` for the literal versions they declare (`app/pinned.py`). That makes SQG004 cover Go, Maven, RubyGems, Packagist and NuGet, verified against the live OSV API.
- **Deliberately not resolved:** a Gradle version catalog (`libs.okhttp`), a Maven `${property}` defined in a parent POM, a NuGet range (`[13.0.1, )`) or MSBuild variable, a Bundler `GIT`/`PATH` gem, and a Composer `dev-` branch pin. Each names no determinable installed version, so it is **counted** and the file reports as *partial* — never guessed at, because a wrong version returns a confident, wrong "no known vulnerabilities".
- **Still not parsed:** `pnpm-lock.yaml`, `Gemfile`/`composer.json` without their lockfile, `pubspec.yaml`, `mix.exs`, `cabal.project` — a repo using only those is reported as not covered, not as clean.
- **Tools:** today, OSV matched against Google's advisory database over HTTP. Planned: Trivy over the resolved tree, for the ecosystems above.
- **Range specs:** a manifest declaring `^1.2.3` with no lockfile cannot be resolved to an installed version, so SQG004 reports *partial* coverage rather than guessing.

---

## SQG005: Risky / Incompatible Licenses

| Aspect | Details |
|---|---|
| **Category** | Legal compliance |
| **Tools** | **Today:** license metadata from PyPI / npm registry JSON, plus the licenses `composer.lock` declares inline (`analyzers/licenses.py`) — pypi, npm and packagist. **Planned:** Trivy, Syft for SBOM-based detection |
| **Confidence** | **HIGH** (GPL in proprietary = risky) · **MEDIUM** (unknown license) |
| **Block-Eligible** | ✗ No (advisory, legal decision required) |
| **Message** | `"Dependency 'libgpl==1.0' is GPL; your project is proprietary. Risk: forced open-source."` |

### False-Positive Controls

- **Allowlist safe licenses:** MIT, Apache 2.0, BSD, ISC all OK for proprietary.
- **Permissive + GPL:** LGPL is safer (linking OK, distribution requires disclosure).
- **Unknown licenses:** flag but lower severity (gather info, make manual decision).
- **Org policy:** dashboard setting to define acceptable licenses per repo.

### Scope

- **Licenses detected (today):** the registry's own license field, SPDX expression and trove classifiers for PyPI and npm packages; for Packagist, the `license` array Composer writes into `composer.lock` — so that ecosystem needs no network call and the claim's source is the repository's own file (the finding's `tool` says `lockfile`, not `registry`). A package declaring no license is skipped: absent metadata is not evidence of a permissive license.
- **Not covered:** Cargo, Go, Maven, Bundler and NuGet, and reported as such. Their licenses are only obtainable one HTTP request per package, and a `Gemfile.lock` routinely holds 200 gems — doing that serially inside the analyzer's wall-clock budget would time the check out, which is a worse report than an honest *not covered*. Bounded-concurrency registry fetching → backlog.
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

---

## SQG009: Avoidable Complexity (code longer than it needs to be)

| Aspect | Details |
|---|---|
| **Category** | Code maturity — verbosity, the most common form of AI slop |
| **Tools** | **Today:** Python's own `ast`, in-process (`analyzers/simplify.py`). **Planned:** tree-sitter for JavaScript/TypeScript |
| **Confidence** | **MEDIUM** (the rewrite is provable; whether to take it is a judgement) |
| **Block-Eligible** | ✗ No — verbose code is not dangerous code |
| **Message** | `"4 lines can be 1: loop searching for a match, then returning True is any()"` |

### Why this is a Guard rule and not an opinion

"This could be shorter" is a judgement, and the Guard does not ship judgement — that is
the Crew's job (PRD §3). So the rule only fires when the shorter form is **derived from
the syntax tree**, and it reports that form verbatim. Every finding therefore carries a
one-liner a reviewer can read and commit. If the rewrite is not derivable, there is no
finding. That is what keeps a style preference from being reported as a fact.

### Shapes detected (each with its exact rewrite)

| Original | Rewrite |
|---|---|
| `if c: return True` / `else: return False` | `return bool(c)` (or `return c` when `c` is already a comparison) |
| `if c: x = a` / `else: x = b` | `x = a if c else b` |
| `out = []` + a loop that only does `out.append(e)` | `out = [e for t in it]` (with the loop's `if` preserved) |
| `total = 0` + a loop that only does `total += e` | `total = sum(e for t in it)`, or `sum(it)` when `e` is the loop variable |
| a loop returning `True` on a match, then `return False` | `return any(c for t in it)` (and the mirrored form → `all(...)`) |
| `if k in d: v = d[k]` / `else: v = default` | `v = d.get(k, default)` |
| `try: v = d[k]` / `except KeyError: v = default` | `v = d.get(k, default)` |

### False-Positive Controls

- **Python only, structurally.** The rewrite comes from `ast.unparse`, so a language with
  no parser here reports `not_run_unsupported` rather than a regex guess. JS/TS needs
  tree-sitter — the same dependency SQG003 wants.
- **Line count is the test.** Rewrites that do not reduce line count are excluded, even
  correct ones. `len(x) == 0` → `not x` is one line either way, *and* on a NumPy array
  the shorter form raises where the original worked — a rewrite that can change
  behaviour is worse than none, so it is not offered.
- **A comment inside the region withholds the patch.** Collapsing the lines would delete
  a human's note, so the finding becomes guidance and no one-click suggestion is emitted.
- **Width limits.** Past 100 characters the rewrite is reported but not offered as a
  commit (it needs wrapping to fit); past 200 it is not reported at all. Fewer lines of
  unreadable code is not a simplification. Both limits came from running the rule over
  its own source, which proposed a 150-character ternary.
- **Only what the change introduced.** A syntax tree needs the whole file, so the file is
  fetched — but a finding is only reported when its region *starts* on an added line.
- **`# noqa` / `# nosec` / `# keep`** on any line of the region suppress it.

### Scope

- **Covered:** Python. Measured on this repository — 4 findings across 54 Python files,
  one offering a committable patch and three reported as guidance.
- **Not covered:** every other language, reported as `not_run_unsupported`.
- **Not attempted:** anything needing judgement — whether an abstraction earns its place,
  whether a 40-line function is really a `groupby`, whether a wrapper is pointless. Those
  are the Crew's (Phase 7), advisory, and must never be presented as facts.

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
| SQG004 | CVE | OSV.dev HTTP API | pypi, npm, crates, go, maven, rubygems, packagist, nuget | HIGH | ✗ |
| SQG005 | License | Registry license metadata; `composer.lock` declared licenses | pypi, npm, packagist | HIGH/MEDIUM | ✗ |
| SQG006 | SAST | Regex sink detector | Python, JS/TS only | HIGH/MEDIUM | ✗ |
| SQG007 | Typosquat | Edit distance vs curated list | pypi, npm | HIGH | ✗ |
| SQG008 | AI scratchpad | **not implemented** | — | — | — |
| SQG009 | Complexity | Python `ast` | Python only | MEDIUM | ✗ |

---

## Phase-In Schedule

- **Phase 1:** SQG001 (dependencies) + SQG002 (secrets, offline) calibrated.
- **Phase 3:** + SQG004 (CVE) + SQG006 (SAST) + SQG005 (licenses) + SQG003 (placeholders).
- **Phase 9:** SQG002 live verification (opt-in); SQG004/SQG006 blocking (opt-in, if FP <1%).
- **Backlog:** SQG008 (AI scratchpad — never built). SQG007 (typosquat) already ships.

