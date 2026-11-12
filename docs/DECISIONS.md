# DECISIONS — Architecture Decision Record (ADR Log)

Record of **why** each major choice was made. Future reference: "Why did we pick this?"

---

## ADR-001: Python 3.12 + FastAPI for Backend API

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Chose between FastAPI, Django, Flask.

> **Correction (superseded premise).** This ADR originally read "Analyzers (gitleaks, Trivy,
> Semgrep) are Python-native." That was wrong on both counts: gitleaks, Trivy and Semgrep are
> not Python libraries (the first two are Go binaries), and none of them is invoked by the
> product. The analyzers that shipped are genuinely Python-native — hand-written pattern
> matchers plus HTTP clients — so the conclusion below still holds, but not for the stated
> reason. When those engines are wrapped they will be subprocesses, not imports.

**Decision:**  
Use **Python 3.12 + FastAPI** (async, ASGI).

**Rationale:**
- The shipped analyzers are pure Python (regex + `httpx`); same language = less glue, easier testing.
- FastAPI: async-native, built-in OpenAPI, minimal boilerplate, perfect for webhook-driven model.
- Python 3.12: latest stable, security patches, faster than 3.11.
- Async fits webhook model (accept quickly, process in background).

**Alternatives Considered:**
- Go: Overkill for this scope; slower to iterate.
- Node.js: Analyzers aren't Node-native; would need to shell out.

**Tradeoff:**  
Python slower than Go/Rust at I/O, but irrelevant here (background jobs, not hot-path).

---

## ADR-002: arq (Async Redis Queue) Over Celery

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Need background job queue for PR analysis (can't block on webhook).

**Decision:**  
Use **arq** (async Redis queue), not Celery.

**Rationale:**
- arq: async-native, integrates seamlessly with FastAPI, lightweight.
- Celery: heavier, more features than needed, XML config boilerplate.
- For MVP (single queue, single worker): arq is simpler.
- Easy to migrate to Celery later if multi-worker scaling demands it.

**Tradeoff:**  
arq less mature than Celery, but GitHub/Plaid/others use it successfully at scale.

---

## ADR-003: Two-Layer Model (Guard + Crew) — Never Mixed

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Risk of claiming AI can "prove" safety, which it cannot. Need to separate fact from opinion.

**Decision:**  
**The Guard (deterministic) and The Crew (AI advisor) are separate layers.**
- Guard: proven tools, blocks only on facts.
- Crew: explains findings, never blocks on its own.

**Rationale:**
- Defensible: Guard findings are verifiable (package doesn't exist, secret matches format).
- Trust: non-coders can understand "Guard found a proven fact" vs. "Crew suggests this is risky."
- Moat: separation of concerns is the product differentiation.

**Consequence:**  
Never claim "AI detects vulnerabilities" — only "Guard detects; Crew explains."

---

## ADR-004: Python 3.12 + FastAPI + arq + Redis + Postgres + SQLAlchemy 2.0 Stack

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Full backend stack choice.

**Decision:**  
Python 3.12 + FastAPI + arq + Upstash Redis + Supabase Postgres + SQLAlchemy 2.0 + Alembic.

**Rationale:**
- All async-native.
- SQLAlchemy 2.0: async support, safer ORM.
- Alembic: schema versioning, safe rollback.
- Upstash/Supabase: free tier ample for MVP, managed (zero ops).
- Consistent across dev (SQLite) and prod (Postgres).

---

## ADR-005: Webhook HMAC-SHA256 Verification (Constant-Time)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
GitHub sends signed webhooks; verify they're authentic.

**Decision:**  
**HMAC-SHA256 with constant-time comparison** (`hmac.compare_digest`).

**Rationale:**
- Standard: GitHub's recommended method.
- Constant-time: prevents timing attacks (attacker infers correct signature byte-by-byte).
- Raw body: use the exact bytes GitHub signed, not parsed JSON (parsing can reorder keys).

**Implementation:**
```python
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
hmac.compare_digest(expected, signature)  # Not == (timing-safe)
```

---

## ADR-006: Confidence Scoring: CERTAIN/HIGH/MEDIUM (Not Binary)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Some findings are provable (package doesn't exist); others are likely but not guaranteed (CVE may not be exploitable).

**Decision:**  
Three levels: **CERTAIN** (provable fact) · **HIGH** (very likely) · **MEDIUM** (context-dependent).

**Rationale:**
- Honesty: not all findings are equal. CVE match is HIGH (version is installed, CVE is real), not CERTAIN (code might not call vulnerable function).
- Blocked only CERTAIN: defensive.
- Allows future refinement (reachability analysis → upgrade CVE to CERTAIN).

**Example:**
- SQG001 (fake package): CERTAIN (404 from registry).
- SQG004 (CVE): HIGH (version match + CVE database).
- SQG003 (TODO): MEDIUM (might be intentional placeholder).

---

## ADR-007: Deterministic-First Niche (Not "AI Detection")

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Market noise: dozens of "AI code detection" tools claiming to catch hallucinations. All use ML (imprecise).

**Decision:**  
**Position as "deterministic checks at the scale of the best companies"** (not "AI detection").

**Rationale:**
- Defensible: deterministic tools are provably accurate.
- Moat: competitors are all chasing "AI detection" (hard, fuzzy). We own the deterministic space.
- Honest: "We catch what Google's tools catch" is more credible than "AI hallucination detector."
- Product: Crew explains findings in plain English (the AI is for UX, not detection).

---

## ADR-008: Broad Release Scope (Not Incremental)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Founder wants full product on day one, not incremental releases. Tension with "iterate fast."

**Decision:**  
**No public release until v1 is complete (Guard + Crew + dashboard).** Internal build order is still per-analyzer calibration (avoid FP spirals).

**Rationale:**
- Founder's call: better to ship complete than ship incomplete and iterate.
- Discipline preserved: each analyzer calibrated separately (0% FP), just not released until all done.
- Market: first user sees the complete product (stronger positioning than beta).

**Tradeoff:**  
Longer to first release (~12 weeks) vs. earlier user feedback (would be ~4 weeks for v0.1).

---

## ADR-009: CVE Confidence = HIGH, Not CERTAIN

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
DeepSeek/Kimi critique: "Package X has CVE Y" is certain; "your code is exploitable" is not.

**Decision:**  
CVE confidence = **HIGH**, not CERTAIN.

**Rationale:**
- Precision: reserving CERTAIN for unreachable-registry 404s and checksum-valid secrets.
- Safety: HIGH + block-eligible (Phase 9+) is correct; don't over-claim certainty.
- Future: reachability analysis (Phase 11+) could upgrade to CERTAIN.

**Consequence:**  
Users won't be blocked by CVE findings unless they explicitly enable blocking (Phase 9).

---

## ADR-010: Offline-Only Secrets (No Live Verification in MVP)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
TruffleHog can call AWS/Stripe/GitHub to test if a leaked key is valid. But calling AWS with a *leaked* key is legal/ethical risk.

**Decision:**  
**MVP ships offline secret detection only** (pattern match + format checksum + entropy).

**Rationale:**
- Safe: no API calls with leaked credentials.
- Still strong: format validation on distinctive token shapes catches the common real cases. (The original claim of "gitleaks + format validation catches 95%" cited a tool that was never wired in, and the 95% figure was never measured. Detection is now measured instead — see `api/tests/test_accuracy.py`.)
- Optional later: live verification (Phase 9+) with explicit user consent + audit.

**Tradeoff:**  
Can't distinguish "fake key matching the pattern" from "real leaked key." Acceptable for MVP.

---

## ADR-011: Claude Haiku 4.5 (Cheap, Strong) + Gemini Fallback

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
AI Crew needs to explain findings in plain English. Chose between Claude, Gemini, Llama.

**Decision:**  
**Claude Haiku 4.5 (default) + Gemini 2.5 Flash-Lite (fallback).**

**Rationale:**
- Haiku: cheap (~$0.80/1M tokens), fast, strong at plain-English explanations.
- Gemini: similar cost/speed, good fallback if Anthropic rate-limited.
- Not GPT-4: overkill cost, slower.
- Not Llama: self-hosted, no cost savings (need GPU), explanation quality unproven.

**Cost target:** ~$0.001 per PR (fraction of a cent).

---

## ADR-012: Fly.io + Vercel + Supabase + Upstash (Minimal Ops)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Hosting & infrastructure choice for a solo founder.

**Decision:**  
- API + worker: **Fly.io**
- Dashboard: **Vercel**
- Database: **Supabase** (managed Postgres)
- Queue: **Upstash** (managed Redis)
- Edge: **Cloudflare** (free)

**Rationale:**
- Minimal operational burden (managed services).
- Free tier ample for MVP.
- All integrate well (git push → deploy, env vars, secrets).
- Founder can handle ops solo.

**Tradeoff:**  
Less control than self-hosted Kubernetes, but not needed for MVP scale.

---

## ADR-013: Distroless Non-Root Containers

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Container image security: minimize attack surface.

**Decision:**  
Multi-stage Dockerfile, final stage **distroless** (no shell, no `apt`), **non-root user**.

**Rationale:**
- Distroless: ~200 MB vs. 1 GB standard Python image.
- No shell/apt: attacker can't get a shell even if they break in.
- Non-root: limits damage if container is compromised.

**Consequence:**  
Can't `docker exec bash` into production (by design).

---

## ADR-014: Secrets Never in Code/Image, Only in Platform Vaults

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
GitHub App private key, webhook secret, API keys must be protected.

**Decision:**  
- **Local dev:** `.env.local` (gitignored).
- **Production:** `fly secrets set`, Vercel env vars (encrypted at rest, injected at runtime).
- Never in: source code, Dockerfile, git history, logs.

**Rationale:**
- Industry standard.
- Rotating secrets doesn't require redeploy.
- Audit trail (who set what, when).

---

## ADR-015: Alembic Versioned Migrations (Safe Schema Changes)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Database schema evolves; need safe, reversible changes.

**Decision:**  
**Alembic** (SQLAlchemy migration tool).

**Rationale:**
- Version every change (`001_initial.py`, `002_add_metadata.py`).
- Rollback: `alembic downgrade -1`.
- Expand-contract pattern (Phase 10): zero-downtime schema upgrades.

---

## ADR-016: GitHub App Least-Privilege Permissions

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
GitHub App permissions: request only what's needed.

**Decision:**  
- ✓ Pull Requests (R/W)
- ✓ Checks (R/W)
- ✓ Contents (R)
- ✓ Metadata (R)
- ✗ Admin, Workflows, Issues, etc.

**Events:**
- ✓ `pull_request`, `installation`
- ✗ `push`

**Rationale:**
- Least privilege: if app is compromised, damage is limited.
- Only what we need: PR diff + check output + repo info.

---

## ADR-017: Structured Logging (structlog + JSON)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Logging for debugging & monitoring.

**Decision:**  
**structlog** (JSON structured logs) + **correlation ID** on every request.

**Rationale:**
- Human-readable in dev.
- Machine-parseable in prod (Sentry, dashboards).
- Correlation ID ties webhook → queue → analysis → findings (end-to-end trace).

---

## ADR-018: Plugin Registry for Analyzers (Future-Proofing)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Analyzers (SQG001–SQG007) hardcoded vs. pluggable.

**Decision:**  
**Pluggable registry:** each analyzer is a registered plugin with `id, version, enabled, analyze()`.

**Rationale:**
- Enable/disable per-repo (kill switch).
- Custom analyzers (org-specific rules).
- Third-party analyzers (marketplace, future).
- No code changes to disable a misfiring checker.

**Implementation:**
```python
class PluginRegistry:
    analyzers = {
        "SQG001": DependencyAnalyzer(...),
        "SQG002": SecretsAnalyzer(...),
    }
```

---

## ADR-019: Honest Promise (Never Claim "Hackproof")

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Marketing tension: competitors claim "AI will catch all bugs," "hackproof," etc.

**Decision:**  
**Promise:** "We run every known check the best companies run, and we catch everything those checks can catch. We never lie about a fact."

**Rationale:**
- Credible: nobody can promise "hackproof" or "catch everything."
- Moat: honesty is our competitive advantage.
- Defensible: based on verifiable tools, not hype.

**Consequence:**  
Messaging is humble but stronger (trust > hype).

---

## ADR-020: Benchmark Repository (Operationalize the Moat)

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
How to ensure the Guard works reliably over time?

**Decision:**  
**Curated truth set (positive + negative examples)** tested in CI on every commit.

**Rationale:**
- Operationalizes the promise: 0% FP on negative set.
- Regression detection: break a checker → CI fails.
- Competitive moat: proprietary corpus of real AI coding mistakes competitors can't replicate.

---

## ADR-021: Tooling Boundaries — kee, Cloudflare Audit Skill, codex-security

**Date:** 2026-11-11  
**Status:** ACCEPTED

**Context:**  
Three external security tools were evaluated for adoption. The risk under review: LLM-backed tooling creeping into the deterministic Guard, which would break the two-layer model (ADR-003) and the honest promise (ADR-019).

**Decision:**  
- **kee** (engineering-craft methodology): adopted as the *review gate* — its substance is documented in `CONTRIBUTING.md` and the PR template as process, deliberately not machine-enforced. The tool itself is the maintainer's local harness, not a contributor requirement.
- **cloudflare/security-audit-skill** (agent skill, MIT): adopted as the *dev-side offline auditor* of this repo. Findings are advisory until proven by execution in this repo's own harness; steps needing an OS sandbox (absent on the maintainer's machine) downgrade to `needs_validation` per the skill's own rule.
- **openai/codex-security** (npm CLI): adopted as an *advisory, out-of-band bot only* (`.github/workflows/codex-security.yml`, `workflow_dispatch` only). Never in the fast PR gate, never a required check, never blocking.

**Rationale:**  
- No LLM-backed scanner enters the deterministic Guard path — ADR-003 extended from the product to the toolchain. `.github/workflows/strix.yml` already established the pattern: advisory, firewalled, never blocking.
- The audit skill's confirmed/needs_validation split maps onto this repo's prove-by-execution standard (`docs/AUDIT_2026-08-22.md`).
- kee's rules are portable prose in `CONTRIBUTING.md`; depending on a personal skill for a public gate would be a gate contributors cannot express.

**Tradeoff:**  
Running the codex bot at all sits in tension with this log's guiding principle ("no over-engineering"). Accepted deliberately: dispatch-only, out of the PR path, never required — its cost is one optional manual workflow, and its findings carry no authority until proven, exactly like Strix's.

---

## Deferred Decisions (Right Idea, Wrong Phase)

### Deferred-1: Two-Wave Pipeline (Fast Checks Now, Deep Checks Later)
**Status:** DEFERRED to Phase 11+  
**Reason:** Architecturally correct, over-engineered for MVP. Target <30s; if exceeded, skip + note.

### Deferred-2: TruffleHog Live Verification
**Status:** DEFERRED to Phase 9+ (opt-in)  
**Reason:** Legal/ethical risk in MVP; offline patterns sufficient.

### Deferred-3: Risk Scores (Security/Quality/Supply-Chain)
**Status:** DEFERRED to Phase 11+  
**Reason:** Single "score" can read as a guarantee; dangerous. Advisory-only, post-core.

### Deferred-4: SQG008 (AI Scratchpad) — never built
**Status:** NOT IMPLEMENTED (renumbered from SQG007)  
**Reason:** Broad regex fires on legit XML/HTML/markdown. Narrow to text files, enable on request only.

**Renumbering note:** this check was specified as SQG007, but SQG007 shipped as the
*typosquat* detector, so one supposedly stable id named two different checks. Resolved in
favour of the code: SQG007 stays typosquat (findings under that id already exist in scan
history and in `blocked_rules` settings; renumbering would orphan them), and the unbuilt
scratchpad detector moves to SQG008.

---

## Summary

Every major choice is tracked here with context + rationale. Future decisions build on these.

**Guiding principle:** Honesty through verifiable truth. No hype. No over-engineering. Simplicity over flexibility.

---

## ADR-023: The Scanner Adapts; Scanned Code Never Carries Suppression Annotations

**Date:** 2026-11-12  
**Status:** ACCEPTED (owner decision, Arghya)  
**Context:** self-scan #15 produced 14 false alarms; the first fix proposal used inline `sqg:ignore` markers in the Guard's own source. Rejected by the owner: "this is a scanner — it needs to scan and find. It needs to adapt."

**Decision.** False alarms are detector bugs: they are fixed by tuning the detector, each change red-first tested with a keeper test proving no recall loss, gated on the accuracy corpus (1.0/1.0). The Guard's own repo never carries ignore-markers. The one hit with no sound tuning — bare XXX in the detector's own regex documentation (the comment documenting what the triple-X lookahead excludes in placeholders.py), indistinguishable in shape from a slop XXX — is accepted and PINNED by `test_known_self_reference_advisory_is_pinned` as a documented known self-reference advisory. The scanner flagging its own documentation is the scanner proving it works, not noise to hide.

**Why.** A scanner that requires users to sprinkle ignore-comments offloads the detector's job onto its users. Annotations inside the Guard's own source would also be the harness grading itself leniently.

**Consequence for Phase 4 (suppression feature).** Inline suppression exists as an opt-in ADOPTION feature for users' *accepted* findings only — grammar frozen 2026-11-12 in `docs/PLAN.md` (Phase 4, Step 4.5): `slopguard: ignore SQGnnn -- reason`, rule ids explicit, no wildcard, reasons required, receipts always printed, never able to hide block-eligible findings (those require a base-branch baseline). False alarms never route through it.

---

## ADR-024: Fixture and Workspace-Internal Findings Downgrade, Never Silence

**Date:** 2026-11-12  
**Status:** ACCEPTED

**Context:**  
Scan #20 (openai/codex-security) produced two CERTAIN / block-eligible findings on the repo's own test fixtures: a leaked-token alarm on the literal string `github_pat_SYNTHETIC_GITHUB_PAT_123`, and a hallucinated-package alarm on `evals/triage-finding/fixtures/repo/package.json` — a fixture built to contain a fake package. Blocking on either would have broken the never-false-block promise (ADR-023's principle applied across detectors).

**Decision:**  
Downgrades are detector-side, derived, and layered — most-specific intent signal first, every rung surfaced as advisory, never silently dropped:
1. **Value-internal markers** (SQG002): a distinctive token whose own value carries a fake-marker word (`synthetic`, `not-a-real`, `not_real`) downgrades on every path. The ±20-char window allowlist deliberately gains no vocabulary — a marker word *next to* a real token is attacker-controlled and must not suppress it.
2. **Shared test-path classifier** (`analyzers/paths.py`, one constant for SQG001 + SQG002): segment-delimited test tokens (`tests-ts/`, `cli-fixtures.ts`, `evals/`, `__snapshots__/`, `cypress/` included); boundary rules pin that `contest.py`, `latest.md`, `testutils/`, `prospects/` never match.
3. **Workspace-internal names** (SQG001): a public-registry 404 for a name the repo itself declares (manifest `name` fields, **per ecosystem** — an npm declaration answers npm questions only; **PEP 503-normalized** for PyPI so `my_lib` and `my-lib` match) is a workspace-internal package, advisory only. Whole-tree collection in scan mode, diff-touched manifests in PR mode. `private: true` is deliberately NOT a signal — nearly every application manifest sets it, and their dependencies still come from the registry; the derived signal is "declared by this repo". **Fixture manifests are excluded from collection** — a fixture-declared name must not legitimize a production-path 404 (the fixture rung carries that case alone).

**Accepted tradeoff (steering).** An author chooses file paths, so naming a folder `evals/` or `fixtures/` can steer SQG001's fixture-path downgrade and hide a would-be blocker. Accepted for the dependency case because the alternative is blocking on fixtures, and because the workspace-name and private-index rungs still require repo-declared evidence. For secrets the tradeoff is narrower: test paths only downgrade to advisory (still surfaced), and value-internal markers cannot be added by path naming.

**Known limit (recorded, not fixed):** the detector validates no token checksums (prefix+length regexes only; AWS AKIA is the only pattern with a public checksum algorithm), so a real leak in a test folder surfaces as HIGH advisory rather than CERTAIN. Real leaks do land in test folders — they are surfaced, never silenced.

**Residual classes of the path classifier (probed 2026-11-12, accepted, not fixed):** ordinary production directories whose names contain delimited test tokens are downgraded too — `src/ab-test/`, `src/ab_tests/` (A/B-testing features), `migrations/002_add_tests_table.py`, `api/e2e-monitor/` (production monitoring), `src/patent-samples/`. Same tradeoff as path steering, but these are names nobody chose in order to steer — the cost is advisory-only downgrades, never silencing. Still-unmatched fixture carriers: digit-suffixed segments (`tests2/`) and CamelCase fixture holders (`TestConstants.kt`, `MockResponses.java`) where no delimiter precedes the token — Java/Kotlin repos are the most exposed; widening the vocabulary to those shapes is deferred until a real scan shows the miss.

---

## ADR-025: SQG007 Established-Package Gate (Registry Age)

**Date:** 2026-11-13  
**Status:** ACCEPTED

**Context:**  
Scan #18 (Aether BLE) produced the scan's only false positive: SQG007 flagged `bleak` as a typosquat of `black` — two Levenshtein edits apart. bleak is the standard cross-platform BLE library (hbldh/bleak, MIT, first PyPI release **2018-04-27**, verified live 2026-11-13; 61 releases, still actively maintained). A near-look-alike heuristic with no legitimacy signal cannot tell an established package from a fresh squat. A hand-allowlist of bleak was rejected: it is the Gate-D failure shape — the next legitimate look-alike name needs another hand-edit.

**Decision:**  
A derived legitimacy signal: the package's **first-release date from its own registry**, parsed from the same response bodies the existence check already downloads (PyPI JSON `releases` upload times, npm packument `time.created`, crates `crate.created_at`) — no new endpoint, cached like existence (`cached_registry_created`, None never cached). When the age is known and ≥ **730 days** (ADR'd value: historical typosquat campaigns publish and strike within days-to-weeks; an 8.5-year-old package is categorically not one; anything younger or undated keeps the finding), SQG007 does not flag.

**Fail-safe direction (both ways the gate can fail):** no `created_fn` wired → pre-gate behaviour (finding stays); registry outage, unknown name, or the field missing → None → **finding stays**. Age data going quietly missing must never turn suppression on. PyPI's project-level `releases` key is deprecated by announcement — its disappearance degrades to "age unknown", which is recorded in CHECKS_CATALOG.

**Known limit (recorded):** an attacker can publish a look-alike and wait out the threshold. Acceptable because SQG007 is advisory-only and never blocks; the age signal is a precision tool against the dominant fresh-squat shape, not a security guarantee.

**Wiring:** `scan.py` and `worker.py` inject `created_fn` (cached) into `repo_context`; direct callers without the key keep pre-gate behaviour. The corpus is the loud guard against wiring drift: `established-lookalike` (bleak must stay silent) and `fresh-lookalike` (`reqests` must stay flagged) run through the real `run_scan` with replayed registry facts verified live 2026-11-13 (bleak HTTP 200, reqests HTTP 404).
