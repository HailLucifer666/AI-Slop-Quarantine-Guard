# DECISIONS — Architecture Decision Record (ADR Log)

Record of **why** each major choice was made. Future reference: "Why did we pick this?"

---

## ADR-001: Python 3.12 + FastAPI for Backend API

**Date:** 2026-06-28  
**Status:** ACCEPTED

**Context:**  
Analyzers (gitleaks, Trivy, Semgrep) are Python-native. Chose between FastAPI, Django, Flask.

**Decision:**  
Use **Python 3.12 + FastAPI** (async, ASGI).

**Rationale:**
- Analyzers are Python libraries; same language = less glue, easier testing.
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
- Still strong: gitleaks + format validation catches 95% of real cases.
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

### Deferred-4: SQG007 (AI Scratchpad) Default Enabled
**Status:** DEFERRED, OFF by default  
**Reason:** Broad regex fires on legit XML/HTML/markdown. Narrow to text files, enable on request only.

---

## Summary

Every major choice is tracked here with context + rationale. Future decisions build on these.

**Guiding principle:** Honesty through verifiable truth. No hype. No over-engineering. Simplicity over flexibility.
